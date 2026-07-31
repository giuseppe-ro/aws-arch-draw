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

The draft contains typed nodes + AWS-to-AWS edges, with KMS/IAM/DLQ/test
scaffolding already filtered. You still need to add (via judgment or a few
queries):

- **Lambda → DynamoDB writes** (safe to infer from IAM policy documents)
- **Externals** (upstream / downstream systems) and their edges

You do NOT need to guess DDB stream triggers — they are already in the draft.

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

From merged results, build the model JSON (see SKILL.md Step 3):

1. **Nodes:** each supported AWS resource `{id, name, type}`
2. **Edges:** each data-flow connection `{from, to}` (SQS→Lambda, Lambda→DDB,
   DDB stream→Lambda, Lambda→SNS, EventBridge→Lambda, External↔AWS)
3. **Externals:** systems outside the AWS account; upstream on the left,
   downstream on the right
4. Filter against `references/ignore-resources.txt`

Layout (columns, rows, waypoints, colors, external-box geometry) is computed by
`scripts/render.py`. Do not attempt to lay out the diagram yourself.
