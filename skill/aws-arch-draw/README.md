# aws-arch-draw skill

Generate an AWS architecture diagram (`.drawio`) from a project's deployment
code and graphify knowledge graph — left-to-right flow, 80×80 AWS icons,
color-coded edges, distributed entry points, and external system boxes.

Accuracy is a hard gate: the diagram is only rendered when the model can be
diffed against ground truth — the project's terraform (`--discover-tf deploy/`)
or graphify's `resources.json` (`--discover`). At render time `resources.json`
takes precedence: when one is found (auto-detected or via `--graph`), `--tf` is
ignored.

The core contract: **all layout math, geometry, colors, XML escaping,
discovery, and validation live in the scripts. The model (LLM) only annotates
the discovered draft and writes the model JSON.** The model never computes
coordinates, waypoints, or colors.

## Skill layout

| Path | Role |
|------|------|
| `SKILL.md` | The active skill definition loaded by opencode; the full generation workflow lives here. |
| `references/ignore-resources.txt` | Plain-text ignore list appended to by the `ignore-resource` subcommand. |
| `references/ignore-resources.md` | Human-readable rationale for every ignored resource category. |
| `references/component-specs.md` | Service → icon/color mapping and external-box conventions (documentation only; render.py is canonical). |
| `references/graphify-discovery.md` | Graphify discovery strategy: `resources.json` fast path, batched-query fallback, validation contract. |
| `scripts/render.py` | Deterministic renderer: model parsing, layout, XML generation, discovery (`--discover`, `--discover-tf`), pre-save validation. |
| `scripts/tf_parser.py` | HCL-lite parser for terraform discovery; emits the authoritative draft (`--discover-tf`). |
| `scripts/test_tf_parser.py` | Self-test guarding tf_parser behaviors (module expansion, externals, trigger chains, writes, publish targets, names). |

## Prerequisites

The skill runs `graphify --version` to verify graphify is installed; if it
fails, the skill stops and points the user to
https://github.com/Graphify-Labs/graphify. View the generated `.drawio` output
with draw.io (the draw.io MCP:
https://github.com/jgraph/drawio-mcp/blob/main/mcp-tool-server/README.md).

## Invocation

### Full workflow (bare `/aws-arch-draw`)

1. **Verify prerequisites** — `graphify --version`.
2. **Fast discovery** — generate the authoritative draft:
   - Primary: `python3 <SKILL_DIR>/scripts/render.py --discover-tf deploy/`
     (deterministic HCL parse, no `terraform` CLI needed).
   - Fallback: `python3 <SKILL_DIR>/scripts/render.py --discover graphify-out/resources.json`
     (reads `graph.json` too for stream triggers).
3. **Refine into a model JSON** — edit the draft in place, save to
   `graphify-out/architecture-model.json`. Only: set the title, rename/describe
   externals, add downstream externals + their boundary edges. Everything else
   stays verbatim.
4. **Render** — `python3 <SKILL_DIR>/scripts/render.py graphify-out/architecture-model.json --tf deploy/ --out docs/<dirname>-architecture.drawio`.
5. **Report** — ignored resources, orphans, backward-flow resolutions.

### Subcommands (route away from the full workflow)

| Subcommand | Behavior |
|-----------|----------|
| `/aws-arch-draw ignore-resource <name>` | Append `<name>` to `references/ignore-resources.txt`. |
| `/aws-arch-draw enable-resource <name>` | Remove `<name>` from `references/ignore-resources.txt`. |
| `/aws-arch-draw re-render` | Re-render the `.drawio` from the existing model — no discovery, no model edits. |
| `/aws-arch-draw regenerate` | Re-run discovery, diff the fresh draft vs the model (report drift), then re-render. The model is never auto-edited. |
| `/aws-arch-draw help` | Show usage. |

## Discovery (ground truth)

The draft produced by discovery is the **complete authoritative skeleton**. The
model keeps every node id and every AWS→AWS edge verbatim — renaming a node or
dropping an edge fails the render.

### Terraform (`--discover-tf`, authoritative)

`tf_parser.py` brace-balances HCL and derives:

- **Nodes** from supported resource types (`ADDRESS_TYPE` in render.py), with
  module-instance expansion (`factory_name` argument prefixes the node id;
  single-instance modules are unprefixed).
- **Externals** from `*_arn` config paths resolved through `var.*` / `local.*` / `module.*`
  (e.g. `local.config.tamworth_consignment_sent_queue_arn`).
- **Edges**, each with `kind @ file:line` evidence:
  - `aws_lambda_event_source_mapping` → SQS/DDB → Lambda trigger edges,
  - `aws_sns_topic_subscription` → SNS → SQS fan-out,
  - `aws_cloudwatch_event_target` → EventBridge schedule → Lambda,
  - `data.aws_iam_policy_document.<lambda>` → Lambda → DynamoDB write edges
    (stream-source tables excluded — the triggered lambda reads the stream),
  - `aws_lambda_function` env vars (`*_TOPIC`, `*_ARN`, `*_SQS_URL`,
    `*_QUEUE_URL`) → publish targets.

### Graphify (`--discover`)

`--discover` reads `resources.json` and additionally derives from `graph.json`:
DDB-stream + SQS→Lambda triggers (`read_trigger_edges`), EventBridge rules
(`read_eventbridge_edges`), SNS→SQS fan-out (`read_sns_subscriptions`),
Lambda→DDB writes (`read_iam_write_edges`), and an auto-derived `ext-upstream`
external wired to every ingest queue subscribed to an external topic.

If `resources.json` is missing, use the batched graphify queries in
`references/graphify-discovery.md` — never read project source files.

## Model JSON schema

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
    {"id": "ext-upstream", "name": "ext-upstream", "description": "", "side": "left"}
  ]
}
```

Model rules (the only judgment the LLM does):

1. Keep every node id **and name** from the draft. Never add an AWS node.
   Local SNS topics fanning out to SQS are AWS nodes; external topics (via
   `var.*`/config ARN) are external boxes.
2. Keep every AWS→AWS edge from the draft exactly as-is; never add one that is
   not in the draft.
3. **Externals** = systems outside the component's ownership. Upstream on the
   left, downstream consumers/publish targets on the right. `name` is the
   snake_case resource id (e.g. `tamworth_consignment_sent_queue`), never
   prose. Leave `description` empty (render.py shows the inferred `SQS`/`SNS`
   type from the `_queue`/`_topic` suffix); set it only for non-queue/topic
   externals (e.g. an on-prem TCP endpoint).
4. **DDB stream edge rule (critical):** a DDB→Lambda edge exists ONLY where an
   `aws_lambda_event_source_mapping` references that table. The triggered
   lambda reads the stream; it does NOT write that table. Never guess a
   DDB→Lambda edge, and never reverse one to silence a warning.
5. Never carry nodes/edges forward from an old model without re-validating
   against ground truth — start from the fresh draft each time.

## Rendering

```bash
python3 <SKILL_DIR>/scripts/render.py graphify-out/architecture-model.json \
  --tf deploy/ --out docs/<dirname>-architecture.drawio
```

- **Ground-truth validation** — render.py re-derives the authoritative
  inventory and hard-fails when the model contains a fabricated node, an
  unsupported AWS→AWS edge, a missing authoritative edge, or a node whose
  name/type drifts from ground truth. Fix the **model**, never the XML.
  A `resources.json` found near the model (or passed with `--graph`) is used
  before `--tf`.
- **No ground truth → exit 3** (`UNVERIFIED`). render.py refuses to save an
  unverified diagram; the caller asks the user how to proceed (point at the
  terraform dir, provide `resources.json`, or abort).
- **Cycles** — detected and reported instead of looping. A cycle almost always
  means a hallucinated/reversed DDB stream edge.
- **Warnings** — orphan nodes, tables with no writers, prose external names,
  over-long descriptions, unverified boundary edges. Review points, NOT
  instructions: verify a suspected edge against ground truth before adding it;
  never add an edge just to silence a warning.
- `--check` validates without writing a file; also validates an existing
  `.drawio` (e.g. `render.py diagram.drawio --check`).

## Script architecture

### render.py

- `load_model` parses/validates the model schema; `prune_non_architectural`
  strips DLQ/test/alert/IAM nodes at render time even if hand-authored into the
  model.
- `layout` is the deterministic pipeline: cycle detection → column assignment
  (longest-path depth) → chain decomposition → shared-resource row anchoring →
  DDB-stream chain alignment → sink alignment → entry/exit fraction
  distribution → uniform external geometry → per-edge L/Z waypoint routing with
  drop-column allocation and collision avoidance (`segments_cross_bbox`).
- `generate_xml` emits the `.drawio` (title, DDB/messaging nodes, edges,
  externals, lambda nodes on top), with `light-dark()` stroke colors.
- `validate_drawio` is the pre-save checklist: XML well-formedness, 240px
  column grid + 160px row grid + 10px multiples, left-to-right flow
  (`exitX=1`/`entryX=0`), waypoint counts (2 or 4), L/Z axis-adjacency,
  `>= WP_MARGIN` runs, and edge-icon collision checks.
- Discovery entry points: `--discover` (graphify) and `--discover-tf`
  (delegates to tf_parser), plus the `compute_authoritative` / graph.json
  readers and `validate_model_against_graph` / `validate_model_against_tf`.

### tf_parser.py

- Brace-balanced HCL-lite scanner (`scan_blocks`) — no terraform CLI.
- Module instances expanded per `factory_name` argument (`instance_prefix`);
  plumbing module dirs (`cross-region-relay`, `factory-testing`, `testing`)
  resolve references but never emit nodes.
- `_resolve` maps expressions → `node` / `external` / `unknown`, chasing
  `var.*`, `local.*`, and `module.*` output references; `_register_external`
  dedupes external boxes.
- `_derive_block_edges` dispatches by resource type (event source mapping, SNS
  subscription, EventBridge target, IAM policy doc, lambda env vars) — the
  authoritative edge source.

## Ignore rules

Non-architectural plumbing is never rendered — applied at discovery AND as a
render-time prune so a hand-authored model cannot reintroduce it:

- `references/ignore-resources.txt` (e.g. `kms`, `sqs dlq`, `iam role`,
  `alerts`, `alarm`, `notification`).
- `DLQ_MARKERS` in render.py: `_dlq`, `_failures`, `smoke_`, `_alerts`,
  `_alert`, `_alarm`, `notification`.
- `IGNORED_PREFIX`: `aws_iam_`, `aws_kms_`, `aws_cloudwatch_`, subscriptions,
  queue policies, event source mappings, lambda permissions, SSM params,
  `module.`, event targets, `data.` (EventBridge `aws_cloudwatch_event_rule`
  schedules are kept — they render as nodes).

If a resource exists solely for security, encryption, error-handling, or
observability, it is omitted; only resources in the business data flow render.

## Conventions

- **Icons/colors** (`TYPES` in render.py): SQS/SNS/EventBridge/Kinesis/CloudWatch
  `#E7157B`; Lambda/Step Functions/ECS/EKS/SageMaker/Bedrock `#ED7100`;
  DynamoDB/API Gateway/Aurora/RDS/Cognito/CloudFront/Route 53/Secrets Manager
  `#C925D1`; S3/VPC `#7AA116`; IAM `#232F3E`.
- **External box labels:** bold snake_case `name` + type line (SQS/SNS derived
  from the id suffix). `name` must not be prose; `description` ≤ 24 chars.
- **External box geometry:** uniform width (longest label, min 160px) and
  uniform height (largest node-span requirement); minimum 80px clearance
  (`EXT_GAP`) from icons, pushing the AWS grid right uniformly when needed.

## Testing

```bash
python3 scripts/test_tf_parser.py
```

Guards: module-instance expansion, external vs local resources, SNS→SQS→Lambda
trigger chains, IAM-derived writes, env-var publish targets, BOM-prefixed files,
DDB stream triggers (and that the stream-source table is not a write target),
and unprefixed single-instance modules.
