---
name: aws-arch-draw
description: >-
  Generate AWS architecture diagrams from a project's graphify knowledge graph.
  Produces a .drawio file with AWS icons, left-to-right flow, color-coded edges,
  and external system boxes. All layout is computed deterministically by
  scripts/render.py — the model only supplies the architecture model JSON.
  Requires graphify + the draw.io MCP.
---

# aws-arch-draw

Generate an AWS architecture diagram from graphify — left-to-right flow, 80×80
AWS icons, color-coded edges, distributed entry points, external system boxes.

**All layout math, geometry, colors, XML escaping, and validation live in
`scripts/render.py`. The model does NOT compute coordinates, waypoints, or
colors. It only discovers the architecture and writes the model JSON.**

## Usage

```
/aws-arch-draw                        # generate diagram for current project
/aws-arch-draw -h | help | --help     # show this usage
/aws-arch-draw ignore-resource <name>  # add a resource type to the ignore list
/aws-arch-draw enable-resource <name>  # remove a resource type from the ignore list
```

## What You Must Do

**Skill invocation = generate an AWS architecture diagram. Start immediately.
Do not ask what the user wants. Do not ask for confirmation.**

Only stop to tell the user when:
- `graphify` is not installed
- After discovery, no supported AWS resources remain
- `render.py` fails validation (report its exact output)

**Do NOT:**
- Ask "what would you like me to do?"
- Ask for confirmation before starting
- Read project source files (.tf, .cs, .yml, .md) — graphify is the ONLY source
- Compute any layout numbers yourself — that is render.py's job
- Call `drawio_search_shapes` — icon styles are embedded in render.py

## Prerequisites

```bash
graphify --version 2>&1 || { echo "STOP: graphify is not installed."; exit 1; }
```

If `graphify --version` fails → tell user: `pip install graphifyy`, then stop.

## Subcommands

### `/aws-arch-draw ignore-resource <name>`

Append `<name>` to `references/ignore-resources.txt`. The resource type will be
filtered out of all future diagram generations.

### `/aws-arch-draw enable-resource <name>`

Remove `<name>` from `references/ignore-resources.txt` if present.

---

## Workflow

### Step 1 — Verify prerequisites

```bash
graphify --version 2>&1
```

### Step 2 — Fast discovery

Prefer `graphify-out/resources.json` (a structured, machine-readable node/edge
inventory that graphify already emits). Generate a **draft model** directly:

```bash
python3 <SKILL_DIR>/scripts/render.py --discover graphify-out/resources.json
```

If `resources.json` is missing or stale, fall back to **batched** graphify
queries instead of per-resource queries:

```
graphify query "list all AWS resources in this project and their types (lambda, sqs, sns, dynamodb, eventbridge, etc)." --budget 8000
graphify query "trace the data flow: which SQS queues feed which lambdas, which lambdas write which DynamoDB tables, which DDB streams trigger which lambdas, which lambdas publish to which SNS topics." --budget 8000
graphify query "list all DynamoDB stream triggers and their Lambda targets (aws_lambda_event_source_mapping referencing aws_dynamodb_table and aws_lambda_function)." --budget 4000
graphify query "what external systems (WMS, upstream publishers, downstream consumers) does this project interact with?" --budget 4000
```

`--discover` already reads `graphify-out/graph.json` and includes the
authoritative **DDB stream trigger edges** (and SQS→Lambda trigger edges) in
the draft — it prints them as `# Confirmed DDB stream triggers`. Treat those
as ground truth.

### Step 3 — Refine into a model JSON

Take the draft (or the query results) and produce a model JSON in this exact
shape:

```json
{
  "title": "Rainingdreams — Inventory Management",
  "nodes": [
    {"id": "sqs-order", "name": "order_ingest", "type": "sqs"},
    {"id": "lambda-order", "name": "order_ingest", "type": "lambda"},
    {"id": "ddb-mutation", "name": "mutation", "type": "dynamodb"}
  ],
  "edges": [
    {"from": "ext-upstream", "to": "sqs-order"},
    {"from": "sqs-order", "to": "lambda-order"},
    {"from": "lambda-order", "to": "ddb-mutation"}
  ],
  "externals": [
    {"id": "ext-upstream", "name": "WMS", "description": "Upstream SNS event feeds", "side": "left"}
  ]
}
```

Rules for building the model (this is the ONLY judgment the model does):

1. **Types** (address → type): `aws_sqs_queue.*`→`sqs`, `aws_sns_topic.*`→`sns`,
   `aws_lambda_function.*`→`lambda`, `aws_dynamodb_table.*`→`dynamodb`,
   `aws_cloudwatch_event_rule.*`→`eventbridge`, `aws_s3_bucket.*`→`s3`,
   `aws_kinesis_*`→`kinesis`, `aws_sfn_*`→`stepfunctions`, `aws_ecs_*`→`ecs`,
   `aws_apigateway*`→`apigateway`, `aws_aurora_*`→`aurora`, etc.
2. **Filter** against `references/ignore-resources.txt` (case-insensitive match on
   resource type) and drop non-architectural resources (DLQs, KMS, IAM roles,
   CloudWatch alarms, SSM params, test scaffolding).
3. **Edges** = data-flow connections only: SQS→Lambda, Lambda→DDB, DDB stream→
   Lambda, Lambda→SNS, EventBridge→Lambda, External→SQS, SNS→External. Include
   Lambda→DDB writes even if `resources.json` omits them. DDB stream→Lambda
   edges MUST come from the confirmed triggers in the `--discover` output (or
   from the stream-trigger query) — never guess or invent a DDB→Lambda edge.
4. **DDB stream edge rule (CRITICAL):**
   - A DDB→Lambda edge exists ONLY where an `aws_lambda_event_source_mapping`
     references that DDB table as its source. Use the confirmed triggers.
   - The triggered Lambda reads the stream; it does NOT write that table.
   - Lambda→DDB **write** edges are the ones where the Lambda's IAM policy
     grants write on the table — these are safe to include.
   - If you are unsure whether an edge exists, run a targeted graphify query
     (`graphify explain "aws_lambda_event_source_mapping.<name>"`) BEFORE
     adding it. Never add an edge to silence a render.py warning.
5. **Externals** = systems outside the AWS account (upstream WMS / publishers on
   the left, downstream consumers on the right). An SNS topic that fans out to
   SQS queues is an AWS node, NOT an external.
6. **Never carry edges forward from an old `architecture-model.json` or backup
   without re-validating each one against graphify.** Start from the fresh
   `--discover` draft each time.
7. Save the model to `graphify-out/architecture-model.json`.

Do NOT worry about: columns, rows, x/y, waypoints, entry/exit fractions, colors,
fan-out promotion, external box heights, z-order, or XML escaping. render.py
handles all of it. Keep node ids short and stable.

### Step 4 — Render

```bash
python3 <SKILL_DIR>/scripts/render.py graphify-out/architecture-model.json \
  --out docs/<dirname>-architecture.drawio
```

render.py computes the layout, emits the XML, and runs the entire pre-save
checklist (grid alignment, left-to-right flow, anchors, waypoint math, external
box geometry, edge-icon collisions, XML well-formedness). It exits non-zero with
a list of failures if anything is wrong — fix the MODEL, not the XML, and re-run.

render.py detects **cycles** in the AWS edges and fails with the cycle listed
instead of looping forever. A cycle almost always means a hallucinated/reversed
DDB stream edge (e.g. `ddb-x -> lambda-y` that should be `lambda-y -> ddb-x`) —
correct the model edges and re-run.

render.py also prints **model warnings** (e.g. a DynamoDB table with no writers,
an orphan node). Treat these as review points, NOT as instructions: verify a
suspected missing edge against graphify before adding it. Never add an edge to
silence a warning. Ignore a warning only if the resource is genuinely a sink
with no stream consumer.

If you need to debug a layout without writing a file: append `--check`.

### Step 5 — Report

```
Diagram saved: docs/<dirname>-architecture.drawio
```

List:
1. Any AWS resources filtered by the ignore list
2. Any orphan resources (zero edges) placed on a separate row
3. Any backward-flow resolutions applied (DDB-triggered Lambdas placed right of DDB)

Stop. Do NOT open the diagram in the editor unless the user explicitly asks.
