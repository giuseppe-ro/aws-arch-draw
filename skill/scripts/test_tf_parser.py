#!/usr/bin/env python3
"""Self-test for the terraform discovery parser (tf_parser.py).

Guards the behaviors that previously produced inaccurate diagrams:
module-instance expansion, external vs local resources, SNS->SQS->Lambda
trigger chains, IAM-derived writes, env-var publish targets, and names.
Run: python3 test_tf_parser.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tf_parser import discover

FIXTURE = {
    "factory.tf": '''
module "factory_tam" {
  source = "./factory"
  factory_name = "tam"
  consignment_sent_queue_arn = local.config.tamworth_consignment_sent_queue_arn
  consignment_updates_topic_arn = local.config.tamworth_consignment_updates_topic_arn
  consignment_cancel_queue_arn = local.config.tamworth_consignment_cancel_queue_arn
}
module "factory_gsy" {
  source = "./factory"
  factory_name = "gsy"
  consignment_sent_queue_arn = local.config.guernsey_consignment_sent_queue_arn
  consignment_updates_topic_arn = local.config.guernsey_consignment_updates_topic_arn
  consignment_cancel_queue_arn = local.config.guernsey_consignment_cancel_queue_arn
}
''',
    "factory/lambdas.tf": '''
resource "aws_lambda_function" "ingest" {
  function_name = "${var.component_name}-${var.factory_name}-ingest"
  environment { variables = { COMPONENT_NAME = var.component_name } }
}
resource "aws_lambda_function" "updates" {
  function_name = "${var.component_name}-${var.factory_name}-updates"
  environment { variables = { DISTRIBUTION_CONSIGNMENT_UPDATES_TOPIC_ARN = var.consignment_updates_topic_arn } }
}
resource "aws_sns_topic" "updates" { name = "${var.component_name}-${var.factory_name}-updates" }
resource "aws_sqs_queue" "updates" { name = "${var.component_name}-${var.factory_name}-updates" }
resource "aws_dynamodb_table" "deliveries" { name = "${var.component_name}-${var.factory_name}-deliveries" }
resource "aws_lambda_event_source_mapping" "ingest" {
  event_source_arn = var.consignment_sent_queue_arn
  function_name    = aws_lambda_function.ingest.arn
}
resource "aws_lambda_event_source_mapping" "updates" {
  event_source_arn = aws_sqs_queue.updates.arn
  function_name    = aws_lambda_function.updates.arn
}
resource "aws_sns_topic_subscription" "updates" {
  topic_arn = aws_sns_topic.updates.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.updates.arn
}
data "aws_iam_policy_document" "updates_lambda" {
  statement { actions = ["dynamodb:PutItem"] resources = [aws_dynamodb_table.deliveries.arn] }
}
''',
    "factory/variables.tf": '''
variable "component_name" { type = string }
variable "factory_name" { type = string }
variable "consignment_sent_queue_arn" { type = string }
variable "consignment_updates_topic_arn" { type = string }
variable "consignment_cancel_queue_arn" { type = string }
''',
}


def _write_fixture():
    tmp = tempfile.mkdtemp(prefix="aws-arch-draw-test-")
    for rel, text in FIXTURE.items():
        p = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(text)
    return tmp


def main():
    draft, _notes = discover(_write_fixture())
    node_ids = {n["id"] for n in draft["nodes"]}
    edges = {(e["from"], e["to"]) for e in draft["edges"]}
    externals = {x["id"] for x in draft["externals"]}

    checks = []
    def ok(cond, msg):
        checks.append((cond, msg))

    # module instances expand per factory
    ok("tam_ingest" in node_ids, "node tam_ingest from module instance")
    ok("gsy_ingest" in node_ids, "node gsy_ingest from second module instance")
    # local resources get role-based ids
    ok("tam_updates_topic" in node_ids, "local SNS topic node tam_updates_topic")
    ok("tam_updates_queue" in node_ids, "local SQS queue node tam_updates_queue")
    ok("tam_deliveries" in node_ids, "DynamoDB table node tam_deliveries")
    # trigger / fan-out / write / publish edges
    ok(("tamworth_consignment_sent_queue", "tam_ingest") in edges,
       "external sent queue -> ingest lambda (event source mapping)")
    ok(("tam_updates_topic", "tam_updates_queue") in edges,
       "local topic -> queue (SNS subscription)")
    ok(("tam_updates_queue", "tam_updates") in edges,
       "queue -> lambda (event source mapping)")
    ok(("tam_updates", "tam_deliveries") in edges,
       "updates lambda -> deliveries (IAM write)")
    ok(("tam_updates", "tamworth_consignment_updates_topic") in edges,
       "updates lambda -> external distribution topic (env publish)")
    # externals resolved from config ARNs, sides correct
    ok("tamworth_consignment_sent_queue" in externals, "external sent queue registered")
    ok("tamworth_consignment_updates_topic" in externals, "external updates topic registered")
    sides = {x["id"]: x["side"] for x in draft["externals"]}
    ok(sides.get("tamworth_consignment_sent_queue") == "left",
       "upstream queue on left")
    ok(sides.get("tamworth_consignment_updates_topic") == "right",
       "publish target on right")
    # nothing fabricated / misnamed
    ok("almelo" not in " ".join(node_ids), "no invented 'almelo' resources")
    ok("tam_cancel" not in node_ids, "no unprovisioned role invented")

    failed = [c for c in checks if not c[0]]
    for ok_cond, msg in checks:
        print(f"{'PASS' if ok_cond else 'FAIL'}  {msg}")
    if failed:
        print(f"\n{len(failed)} check(s) failed")
        sys.exit(1)
    print(f"\nAll {len(checks)} checks passed.")


if __name__ == "__main__":
    main()
