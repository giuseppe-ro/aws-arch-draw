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

The draft contains typed nodes + AWS-to-AWS edges, with KMS/IAM/DLQ/test
scaffolding already filtered. You still need to add (via judgment or a few
queries):

- **DDB stream triggers** (DynamoDB → Lambda) — often absent from resources.json
- **Lambda → DynamoDB writes**
- **Externals** (upstream / downstream systems) and their edges

## Fallback — batched graphify queries

If `resources.json` is missing or stale, use 3 batched queries (not per-resource):

```
graphify query "list all AWS resources in this project and their types (lambda, sqs, sns, dynamodb, eventbridge, etc)." --budget 8000
graphify query "trace the data flow: which SQS queues feed which lambdas, which lambdas write which DynamoDB tables, which DDB streams trigger which lambdas, which lambdas publish to which SNS topics." --budget 8000
graphify query "what external systems (WMS, upstream publishers, downstream consumers) does this project interact with?" --budget 4000
```

If a query truncates, raise `--budget` or split it — never ask the user to
re-run graphify.

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
