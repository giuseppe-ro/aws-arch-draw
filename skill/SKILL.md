---
name: aws-arch-draw
description: >-
  Generate AWS architecture diagrams from a project's graphify knowledge graph.
  Produces a .drawio file with AWS icons, left-to-right flow, color-coded edges,
  external system boxes, and strict layout rules. Requires graphify + draw.io MCP.
---

# aws-arch-draw

Generate an AWS architecture diagram from graphify queries — left-to-right flow,
80×80 AWS icons, color-coded edges, distributed entry points, external system boxes.

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

Execute the full Workflow below. Only stop to tell the user when:
- `graphify` is not installed
- `graphify-out/graph.json` does not exist
- After discovery, no supported AWS resources remain

**Do NOT:**
- Ask "what would you like me to do?"
- Ask for confirmation before starting
- Read project source files (.tf, .cs, .yml, .md) — graphify is the ONLY source
- Use the visual rules from any other skill — use ONLY the references/ files in this skill
- Add arrowheads to edges

## Prerequisites

**graphify is the ONLY source of architectural information. No fallback.**

```bash
graphify --version 2>&1 || { echo "STOP: graphify is not installed."; exit 1; }
test -f graphify-out/graph.json || { echo "STOP: graphify-out/graph.json not found."; exit 1; }
```

If `graphify --version` fails → tell user: `pip install graphifyy`, then stop.

If `graphify-out/graph.json` missing → tell user: `Run /graphify . first, then re-run /aws-arch-draw.`, then stop.

Do NOT run `/graphify` yourself. Do NOT read project source files.

## Subcommands

### `/aws-arch-draw ignore-resource <name>`

Append `<name>` to `references/ignore-resources.txt`. The resource type will be
filtered out of all future diagram generations.

### `/aws-arch-draw enable-resource <name>`

Remove `<name>` from `references/ignore-resources.txt` if present.
The resource type will appear in future diagrams.

## Tools (draw.io MCP)

Invoke via the `drawio` MCP server:

| Tool | Purpose |
|------|---------|
| `drawio_search_shapes` | Look up AWS4 icon style strings |
| `drawio_get_page` | Read the reference template |
| `drawio_set_page` | Save the generated diagram |

## Workflow

### Step 1 — Verify prerequisites

```bash
graphify --version 2>&1
test -f graphify-out/graph.json
```

Stop with instructions if either fails.

### Step 2 — Discover architecture via graphify

Follow **[references/graphify-discovery.md](references/graphify-discovery.md)**.

1. **Phase A** — Resource inventory (`--budget 8000`)
2. **Phase B** — Per-resource connection traces (`--dfs --budget 4000`)
3. **Phase C** — External system detection (`--budget 4000`)

Filter all results against `references/ignore-resources.txt` (case-insensitive match
against resource type). Remove any resource whose type appears in the ignore list.

Merge all query results. If truncated, raise `--budget` or split queries — never ask
the user to re-run graphify.

### Step 3 — Read the visual rules

Read these files to understand the required visual contract:

- `references/layout-rules.md` — canvas, grid, spacing, title bar
- `references/color-rules.md` — service colors, arrow color logic
- `references/arrow-rules.md` — edge styles, entry distribution, routing
- `references/component-specs.md` — icon specs, external boxes, full service mapping

### Step 4 — Look up AWS icon styles

For each service type present, call `drawio_search_shapes`:

```
drawio_search_shapes query: "aws4 lambda" limit: 3
drawio_search_shapes query: "aws4 sqs" limit: 3
drawio_search_shapes query: "aws4 sns" limit: 3
drawio_search_shapes query: "aws4 dynamodb standard access table class" limit: 3
drawio_search_shapes query: "aws4 eventbridge" limit: 3
```

Also search for any additional types present (apigateway, s3, kinesis, stepfunctions, ecs, aurora, etc.).

Always use the `resourceIcon` variant: `shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.<service>`.
Exception: DynamoDB uses `shape=mxgraph.aws4.dynamodb_standard_access_table_class`.

### Step 5 — Plan layout

From the merged graphify results, determine:

1. **Rows** — each independent flow chain gets its own horizontal row
2. **Columns** — left→right: external source → messaging → compute → database → messaging → external sink
3. **Shared resources** — DynamoDB tables or SQS queues used by multiple flows appear ONCE,
   positioned between the rows that use them
4. **External boxes** — upstream systems on the left (`x=-80`), downstream on the right (`x=1920`)

Layout grid (from `references/layout-rules.md`):
- Row Y: 160, 480, 800, 1120, ... (step 320)
- Column X: 240, 480, 720, 960, 1200, 1440, 1680, ... (step 240)
- Icons: 80×80
- External box width: 160

### Step 6 — Generate and save .drawio XML

Build the complete `<mxfile>` XML following every rule in the reference files.

**Critical rules (see reference files for full detail):**

| Rule | Source |
|------|--------|
| No arrowheads on ANY edge | `arrow-rules.md` |
| Arrow color = non-Lambda service in the connection | `color-rules.md` |
| Same-row edges = perfectly straight horizontal | `arrow-rules.md` |
| Multi-arrow targets: distribute entryY (0.25, 0.5, 0.75) | `arrow-rules.md` |
| External boxes: `rounded=1;whiteSpace=wrap;html=1;` | `component-specs.md` |
| Icons: 80×80, aspect=fixed, label below | `component-specs.md` |
| Grid: 10px, snap all coordinates | `layout-rules.md` |
| Title at top: `<font style="font-size: 24px;">&lt;TITLE&gt;</font>` | `layout-rules.md` |

**Generate order (back to front):**
1. Section separators / dashed edges
2. Title
3. DynamoDB nodes
4. SQS / SNS / EventBridge nodes
5. Main-flow edges
6. External boxes
7. Lambda nodes (front)

**Save the file:**

1. Create `docs/` folder if it doesn't exist:
```bash
mkdir -p docs
```

2. Write the XML to `docs/<dirname>-architecture.drawio` via bash.

3. Then save via MCP:
```
drawio_set_page path: "docs/<dirname>-architecture.drawio" page: 0 content: "<mxGraphModel XML>"
```

### Step 7 — Report

Tell the user:
```
Diagram saved: docs/<dirname>-architecture.drawio
```

Then list any AWS resources that were found in graphify but filtered out by the ignore list.

Stop. Do NOT open the diagram in the editor unless the user explicitly asks.
