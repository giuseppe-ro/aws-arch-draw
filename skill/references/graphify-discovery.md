# Graphify Discovery Strategy

The skill discovers architecture via graphify. Never read project source files.
Never hardcode service names.

## Fast path — `graphify-out/resources.json`

Graphify already emits a structured, machine-readable inventory at
`graphify-out/resources.json`:

```json
{
  "title": "<project>",
  "nodes": [{"id": "...", "address": "aws_lambda_function.order_ingest",
             "source_file": "deploy/regional/order-ingest-lambda.tf"}, ...],
  "edges": [{"source": "<id>", "target": "<id>", "relation": "wiring"}, ...]
}
```

Generate a draft model directly (no LLM queries needed for the inventory):

```bash
python3 <SKILL_DIR>/scripts/render.py --discover graphify-out/resources.json
```

`--discover` also reads `graphify-out/graph.json` and derives the
**authoritative DDB stream trigger edges** (and SQS→Lambda trigger edges) from
`aws_lambda_event_source_mapping.*` nodes, printing them as
`# Confirmed DDB stream triggers`. These are ground truth — use them as-is.
`resources.json` alone omits stream triggers, which is why graph.json is read.

Beyond triggers, `--discover` derives from `graph.json`:

- **EventBridge schedule rules → Lambda** from `aws_cloudwatch_event_target.*`
  (so scheduled lambdas are never orphans),
- **SNS → SQS fan-out** from `aws_sns_topic_subscription.*` for local topics,
- **Lambda → DynamoDB writes** from `data.aws_iam_policy_document.<lambda>`
  referencing `aws_dynamodb_table.*` (minus stream-source tables the triggered
  lambda only reads),
- an **auto-derived upstream external** (`ext-upstream`) wired to every SQS
  queue subscribed to an *external* SNS topic (topic referenced via `var.*` /
  `data.*`, i.e. no local `aws_sns_topic`).

The draft's node ids and AWS→AWS edges are **complete and authoritative**. The
model's only remaining work is: set the title, rename/describe externals, add
downstream externals + their boundary edges. Do NOT add or replace AWS nodes or
AWS→AWS edges.

The draft contains typed nodes + AWS-to-AWS edges, with KMS/IAM/DLQ/test
scaffolding already filtered. It already includes all triggers (SQS→Lambda,
DDB stream→Lambda), EventBridge schedule rules, SNS→SQS fan-out, IAM-derived
Lambda→DDB writes, and the auto-derived upstream external. You still need to add:

- **Downstream externals** (systems that consume this service's output) and
  their boundary edges — these are judgment calls from the README/project docs
- **Rename/describe** the auto-derived upstream external
- **Title**

You do NOT need to guess DDB stream triggers, EventBridge triggers, SNS→SQS
fan-out, or Lambda→DDB write targets — they are already in the draft.

## Fallback — batched graphify queries

If `resources.json` is missing or stale, use 4 batched queries (not per-resource):

```
graphify query "list all AWS resources in this project and their types (lambda, sqs, sns, dynamodb, eventbridge, etc)." --budget 8000
graphify query "trace the data flow: which SQS queues feed which lambdas, which lambdas write which DynamoDB tables, which DDB streams trigger which lambdas, which lambdas publish to which SNS topics." --budget 8000
graphify query "list all DynamoDB stream triggers and their Lambda targets (aws_lambda_event_source_mapping referencing aws_dynamodb_table and aws_lambda_function)." --budget 4000
graphify query "what external systems (WMS, upstream publishers, downstream consumers) does this project interact with?" --budget 4000
```

If a query truncates, raise `--budget` or split it — never ask the user to
re-run graphify.

## DDB stream edge rule (CRITICAL)

- A **DDB → Lambda** edge exists ONLY where an `aws_lambda_event_source_mapping`
  references that DynamoDB table as its source (stream trigger). The triggered
  Lambda reads the stream; it does NOT write that table.
- A **Lambda → DDB write** edge exists where the Lambda's IAM policy grants
  write on the table.
- Confirming a stream trigger: `graphify explain "aws_lambda_event_source_mapping.<name>"`
- NEVER infer or invent a DDB→Lambda edge to silence a render.py warning, and
  never carry edges from an old/backup model without re-validating each one.

## Building the Architecture Model

Take the `--discover` draft and edit it in place (see SKILL.md Step 3):

1. **Nodes:** keep every draft node id verbatim — never add or remove an AWS node
2. **Edges:** keep every AWS→AWS draft edge (SQS→Lambda, Lambda→DDB, DDB
   stream→Lambda, Lambda→SNS, EventBridge→Lambda, SNS→SQS); only add
   external-boundary edges
3. **Externals:** upstream on the left (rename/describe the auto-derived
   `ext-upstream`), downstream consumers on the right
4. Filtering against `references/ignore-resources.txt` already happened in
   `--discover`

Layout (columns, rows, waypoints, colors, external-box geometry) is computed by
`scripts/render.py`. Do not attempt to lay out the diagram yourself.

## Validation contract (render.py, on the normal render path)

render.py re-derives the authoritative node/edge inventory from the same
`resources.json` + `graph.json` and **hard-fails** the model unless:

- every model AWS node id is a graphify resource (no fabricated nodes),
- every model AWS→AWS edge is supported by graphify (no fabricated edges), and
- every authoritative edge between two nodes the model already includes is
  present (no missing edges).

This is what prevents the common failure modes: invented SNS topics, ingest
queues with no inbound edge, Lambda→DDB writes to the wrong table, and orphaned
scheduled lambdas. Fix the MODEL, never the XML.
