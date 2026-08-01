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

Generate an AWS architecture diagram from the project's deployment code and
graphify knowledge graph — left-to-right flow, 80×80 AWS icons, color-coded
edges, distributed entry points, external system boxes.

Accuracy is a hard gate: the diagram is only rendered when the model can be
diffed against ground truth — the project's terraform (`--discover-tf
deploy/`, authoritative) or graphify's `resources.json` (`--discover`).

**All layout math, geometry, colors, XML escaping, discovery, and validation
live in `scripts/render.py` + `scripts/tf_parser.py`. The model does NOT compute
coordinates, waypoints, or colors. It only annotates the discovered draft and
writes the model JSON.**

Evidence layers, most to least trusted:
1. **Terraform (IaC)** — `render.py --discover-tf <deploy-dir>` parses resources,
   triggers, subscriptions, writes, and external ARNs deterministically.
2. **graphify EXTRACTED** — code-level intent (which lambdas exist, payloads).
3. **graphify INFERRED** — low confidence; never used as the sole source for a
   node or edge. INFERRED `references` edges are ambiguous about direction and
   ownership (a lambda can reference a topic it *subscribes to*, one it
   *publishes to*, or a queue feeding it). Always resolve them against
   `--discover-tf` output or the code before keeping them.

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
- **No ground truth is available** (no terraform dir and no `resources.json`) —
  stop and ask the user how to proceed (see Step 4)

**Do NOT:**
- Ask "what would you like me to do?" at the start — start the workflow
- Ask for confirmation before starting
- Compute any layout numbers yourself — that is render.py's job
- Call `drawio_search_shapes` — icon styles are embedded in render.py
- Invent or rename AWS nodes or re-target edges — every id/edge must come from
  the `--discover-tf` draft (or `--discover`) and survive ground-truth
  validation. Renaming a node or dropping an edge will FAIL the render.
- Treat an INFERRED graphify edge as directional data flow on its own — resolve
  it against terraform/code first.

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

**Primary (authoritative): terraform.** If the project has a terraform
deployment directory (e.g. `deploy/`), generate the draft directly:

```bash
python3 <SKILL_DIR>/scripts/render.py --discover-tf deploy/
```

`--discover-tf` deterministically parses HCL (no `terraform` CLI needed) and
emits the full draft: resources (SNS/SQS/Lambda/DynamoDB), authoritative edges
(event source mappings, SNS→SQS subscriptions, Lambda→DDB writes, env-var
publish targets), and externals (any ARN referenced via `var.*`/`local.*`
config, e.g. consignment queues/topics owned by another platform). Every node
id and edge is ground truth — do not rename or re-target any of them.

**Fallback: graphify.** If there is no terraform, prefer
`graphify-out/resources.json` via `--discover` (see the batched queries below
when it is missing). Remember: graphify `references` edges are often
**INFERRED** and direction-ambiguous. An SQS-triggered lambda
(`Handler(SQSEvent)`) consumes from a queue; a topic in a lambda's env var is a
publish target; a topic with an SNS→SQS subscription in the same account is a
local node, not an external. Resolve each ambiguous edge against the code or
terraform before keeping it.

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

The draft is now the **complete authoritative skeleton**. Beyond the SQS→Lambda
triggers and DDB streams, render.py derives and includes:

- **EventBridge schedule rules → Lambda** (from `aws_cloudwatch_event_target.*`),
  so a scheduled lambda like `stock_sync` can never appear as an orphan.
- **SNS → SQS fan-out** (from `aws_sns_topic_subscription.*`) for subscriptions
  to a local topic.
- **Lambda → DynamoDB writes** (from `data.aws_iam_policy_document.<lambda>`
  referencing `aws_dynamodb_table.*`, minus the stream-source tables that the
  triggered lambda only reads). You never guess a write target.
- An **auto-derived upstream external** (`ext-upstream`) wired to every SQS
  queue that subscribes to an *external* SNS topic (referenced via `var.*`/
  `data.*`), so ingest queues are never left with a missing inbound edge.

**Every node id and every AWS→AWS edge in the draft is ground truth. Do not
invent, remove, or re-target any of them.**

### Step 3 — Refine into a model JSON

Take the **draft** from `--discover-tf` (or `--discover`) and produce the model
JSON by editing it **in place**: set the title, rename/describe the externals,
add downstream externals + their boundary edges, and **nothing else**. The node
ids in the draft are the authoritative ids — **keep them verbatim**, and keep
each node's `name` as discovered (render.py fails the render if a name or type
drifts from ground truth).

```json
{
  "title": "Rainingdreams — Inventory Management",
  "nodes": [
    {"id": "aws-sqs-queue-order-ingest", "name": "order_ingest", "type": "sqs"},
    {"id": "aws-lambda-function-order-ingest", "name": "order_ingest", "type": "lambda"},
    {"id": "aws-dynamodb-table-mutation", "name": "mutation", "type": "dynamodb"}
  ],
  "edges": [
    {"from": "ext-upstream", "to": "aws-sqs-queue-order-ingest"},
    {"from": "aws-sqs-queue-order-ingest", "to": "aws-lambda-function-order-ingest"},
    {"from": "aws-lambda-function-order-ingest", "to": "aws-dynamodb-table-mutation"}
  ],
  "externals": [
    {"id": "ext-upstream", "name": "WMS", "description": "Upstream SNS event feeds", "side": "left"}
  ]
}
```

Rules (the ONLY judgment the model does):

1. **Keep every node id AND name from the draft.** Never add an AWS node — if you
   think a resource is missing, re-run `--discover-tf`/`--discover`; do not invent
   it. An SNS topic that fans out to SQS queues is an AWS node (from the draft) if
   it is a local `aws_sns_topic`; an *external* SNS topic (referenced via
   `var.*`/`local.*`/config ARN) is represented by an external box, never as a
   local `sns` node.
2. **Keep every AWS→AWS edge from the draft** exactly as-is (triggers, DDB
   streams, EventBridge rules, SNS→SQS fan-out, Lambda→DDB writes). Do not
   re-target or drop any, and never add an AWS→AWS edge that is not in the draft.
3. **Externals** = systems/queues/topics outside this component's ownership:
   upstream publishers and inbound queues/topics on the left, downstream
   consumers and publish targets on the right. The draft already contains every
   ARN referenced via config; you may rename/describe each box and merge boxes
   that represent the same external system. **Check for downstream externals the
   draft cannot infer** — e.g. on-prem TCP endpoints the lambdas dial out to, or
   topics published from the code — and add them as right-side boxes with their
   boundary edges.
4. **DDB stream edge rule (CRITICAL):** a DDB→Lambda edge exists ONLY where an
   `aws_lambda_event_source_mapping` references that DDB table as its source.
   The draft already includes every confirmed one — never guess or invent a
   DDB→Lambda edge, and never reverse one to silence a render.py warning.
   The triggered Lambda reads the stream; it does NOT write that table.
5. **Never carry nodes/edges forward from an old `architecture-model.json` or
   backup without re-validating each one against ground truth.** Start from the
   fresh `--discover-tf`/`--discover` draft each time.
6. Save the model to `graphify-out/architecture-model.json`.

Do NOT worry about: columns, rows, x/y, waypoints, entry/exit fractions, colors,
fan-out promotion, external box heights, z-order, or XML escaping. render.py
handles all of it. Keep node ids short and stable (the draft already does).

### Step 4 — Render

```bash
python3 <SKILL_DIR>/scripts/render.py graphify-out/architecture-model.json \
  --tf deploy/ --out docs/<dirname>-architecture.drawio
```

Pass `--tf <deploy-dir>` to validate the model against the terraform-derived
ground truth (the same source used for discovery). If the project has no
terraform, omit it and render.py will look for `graphify-out/resources.json`
(override with `--graph <path>`).

render.py computes the layout, emits the XML, and runs the entire pre-save
checklist (grid alignment, left-to-right flow, anchors, waypoint math, external
box geometry, edge-icon collisions, XML well-formedness). It exits non-zero with
a list of failures if anything is wrong — fix the MODEL, not the XML, and re-run.

**render.py also validates the model against ground truth** (`--tf` or
`--graph`). It exits non-zero when the model:
- contains an AWS node that is not a ground-truth resource (**fabricated**
  node, e.g. an invented SNS topic),
- contains an AWS→AWS edge that ground truth does not support (e.g. a
  Lambda→DDB write to the wrong table),
- omits an authoritative edge between two nodes it already includes (e.g. a
  missing SNS→SQS→Lambda trigger chain or a missing DDB write), or
- names a node differently from ground truth (e.g. a table called
  `address_records` when terraform calls it `deliveries`, or a renamed topic).

Each failure is printed with the offending id/edge — fix the MODEL, never the
XML, and re-run.

**No ground truth available → STOP and ask the user.** If render.py exits with
status 3 (`UNVERIFIED: no ground truth available`), no `resources.json` and no
`--tf` input exists. Do not save an unverified diagram. Ask the user how to
proceed, offering: (a) point the skill at the terraform dir
(`--discover-tf deploy/`), (b) provide a `resources.json`, (c) proceed with a
clearly watermarked draft via `--allow-unverified`, or (d) abort.

render.py detects **cycles** in the AWS edges and fails with the cycle listed
instead of looping forever. A cycle almost always means a hallucinated/reversed
DDB stream edge (e.g. `ddb-x -> lambda-y` that should be `lambda-y -> ddb-x`) —
correct the model edges and re-run.

render.py also prints **model warnings** (e.g. a DynamoDB table with no writers,
an orphan node, an external feeding a non-ingest node). Treat these as review
points, NOT as instructions: verify a suspected missing edge against ground
truth before adding it. Never add an edge to silence a warning. Ignore a warning
only if the resource is genuinely a sink with no stream consumer.

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
