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

1. **Rows** — each independent flow chain gets its own horizontal row. Row Y: 160, 400, 640, 880, 1120, 1360, 1600, 1840, 2080, 2320, 2560, ... (step **240** = 80px icon + 160px gap = 2× icon height). **Every distinct flow gets a full 240px row — never cram multiple flows at sub-spacing.** If 5 flows share one external source, they occupy 5 full rows, and the external box height expands to span them all.
2. **Columns** — left→right. Column X: 240, 480, 720, 960, 1200, 1440, 1680, 1920, 2160, 2400, 2640, ... (step 240). Add more columns to the right as needed.
3. **Shared resources** — DynamoDB tables used by multiple flows appear ONCE, positioned at a column to the right of the flows that write to them, at a Y between the rows that use them
4. **External boxes** — ONLY at the left edge (`x=-80`) or right edge (past the rightmost icon + 80px). NEVER place an external box mid-diagram at a column X used by AWS icons.

**CRITICAL: Every flow chain must continue RIGHTWARD.** When a resource feeds into another, it must be at a larger X column — never reset to x=240 mid-pipeline.

**CRITICAL: One flow = one full row.** Even when multiple flows share the same source (e.g. one external box feeds 5 SQS queues), each flow gets its own 320px row. The external box height grows to match.

Example — WRONG:
```
# 3 flows crammed into 160px (80px sub-spacing):
Row y=480: SQS_order → Lambda_order
Row y=560: SQS_receipt → Lambda_receipt    ← touching! labels collide!
Row y=640: SQS_adjust → Lambda_adjust     ← touching!
External box h=560 covers y=160..720
```

Example — CORRECT:
```
# 3 flows, each gets 240px row:
Row y=400:  SQS_order → Lambda_order → DDB
Row y=640:  SQS_receipt → Lambda_receipt → DDB
Row y=880: SQS_adjust → Lambda_adjust → DDB
External box h=960 covers y=160..1120
```

Column assignment per resource type (add columns to the right as the chain grows):
| Role | Column X |
|------|----------|
| External (in) | -80 |
| EventBridge / SNS (entry) | 240 |
| SQS | 480 |
| Lambda (ingest) | 720 |
| DynamoDB (shared) | 960 |
| Lambda (stream) | 1200 |
| SQS/SNS (downstream) | 1440 |
| Lambda (output) | 1680 |
| DynamoDB (output) | 1920 |
| Lambda (next stage) | 2160 |
| SQS/SNS (next stage) | 2400 |
| Lambda (final) | 2640 |
| External (out) | rightmost_icon_x + 160 |

Add more columns (step 240) as the chain grows. Never put an external box at an AWS icon column.

Icons: 80×80. External box width: 160. All coordinates multiples of 10.

### Step 6 — Generate and save .drawio XML

**ALL rules below are mandatory. Apply them while generating. Do not rely on reference files — these rules ARE the reference.**

#### 6.1 File Skeleton

```xml
<mxfile host="Electron" modified="2025-01-01T00:00:00.000Z" agent="pi" version="24.0.0" type="device">
  <diagram name="Page-1" id="ARCHITECTURE">
    <mxGraphModel dx="0" dy="0" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="2100" pageHeight="2400" background="light-dark(#FFFFFF,#FFFFFF)" math="0" shadow="0">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <!-- ALL cells here -->
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

Grow `pageWidth`/`pageHeight` if the diagram needs more room.

#### 6.2 Label Encoding (READ CAREFULLY — most common bug)

The `value` attribute contains HTML, XML-escaped ONCE:

```
Desired:  <b>order_ingest</b><div>SQS</div>
WRONG:    &amp;lt;b&amp;gt;order_ingest&amp;lt;/b&amp;gt;&amp;lt;div&amp;gt;SQS&amp;lt;/div&amp;gt;   ← double-escaped, renders as literal text!
CORRECT:  &lt;b&gt;order_ingest&lt;/b&gt;&lt;div&gt;SQS&lt;/div&gt;
```

**After generating every mxCell, immediately check its `value=` attribute:** if you see `&amp;lt;` or `&amp;gt;` or `&amp;quot;` anywhere, STOP and fix it. Those should be `&lt;`, `&gt;`, `&quot;`.

#### 6.3 Title Bar

```xml
<mxCell id="title" value="&lt;font style=&quot;font-size: 24px;&quot;&gt;PROJECT TITLE&lt;/font&gt;" style="text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;fontSize=18;fontStyle=1;fontColor=#232F3E;strokeWidth=1;" vertex="1" parent="1">
  <mxGeometry x="0" y="0" width="2100" height="40" as="geometry" />
</mxCell>
```

Note: `&quot;` not `&amp;quot;`.

#### 6.4 Layout Grid

| | Value |
|---|-------|
| Icon size (all AWS) | 80×80 |
| Column X grid | 240, 480, 720, 960, 1200, 1440, 1680 (step 240) |
| Row Y grid | 160, 480, 800, 1120, 1440, 1760, 2080 (step 320) |
| Left external box | x=-80, w=160 |
| Right external box | x=1920, w=160 |

**All x/y coordinates must be multiples of 10.**

**Flow direction is ALWAYS left→right.** Source icon must have a smaller X than target icon.

#### 6.5 AWS Icon Template

```xml
<mxCell id="UNIQUE_ID" value="&lt;b&gt;Name&lt;/b&gt;&lt;div&gt;TYPE&lt;/div&gt;" style="sketch=0;outlineConnect=0;fontColor=#232F3E;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.SERVICE;fillColor=FILL_COLOR;" vertex="1" parent="1">
  <mxGeometry x="X" y="Y" width="80" height="80" as="geometry" />
</mxCell>
```

DynamoDB exception: use `shape=mxgraph.aws4.dynamodb_standard_access_table_class` (no `resourceIcon`, no `resIcon`). Add `gradientColor=none;pointerEvents=1;`. Size 80×80.

#### 6.6 Service Colors

| Service | fillColor |
|---------|-----------|
| SQS, SNS, EventBridge | `#E7157B` |
| Lambda | `#ED7100` |
| DynamoDB | `#C925D1` |

#### 6.7 External Box Template

```xml
<mxCell id="ext-NAME" value="&lt;b&gt;Name&lt;/b&gt;&lt;div&gt;Description&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;fontSize=12;fontColor=#232F3E;" vertex="1" parent="1">
  <mxGeometry x="-80" y="Y" width="160" height="H" as="geometry" />
</mxCell>
```

Height must span the rows it connects to.

#### 6.8 Edge Style

Every edge uses this base style (NO arrowheads — no `endArrow`):

```
edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=2;jumpStyle=arc
```

Plus color: add `strokeColor=light-dark(#HEX, #ededed)` where HEX is the non-Lambda service color (see 6.9).
Dashed edges (scheduled/cron triggers ONLY): also add `dashed=1;dashPattern=8 8;opacity=50`. Only EventBridge/cron-triggered flows use dashed — mark the entire scheduled chain (EventBridge → Lambda → DDB). Everything else is solid: SQS polling, Lambda invocations, DDB Streams, direct writes, SNS publishes are always-on.

#### 6.9 Arrow Color Rule

Arrow color = fillColor of the non-Lambda service in the connection. Lambda's orange is NEVER used as arrow color. External→AWS edges have no strokeColor (default black).

| Edge | strokeColor |
|------|-------------|
| SQS → Lambda | `light-dark(#E7157B, #ededed)` |
| Lambda → DynamoDB | `light-dark(#C925D1, #ededed)` |
| Lambda → SNS | `light-dark(#E7157B, #ededed)` |
| DynamoDB → Lambda | `light-dark(#C925D1, #ededed)` |
| External → SQS | _(no strokeColor)_ |

#### 6.10 Entry/Exit Distribution

**All arrows exit RIGHT edge of source** (`exitX=1`), **enter LEFT edge of target** (`entryX=0`).

For an 80px icon, distribute entry/exit points equally:

| Arrow count | entryY / exitY | Pixels from top |
|-------------|----------------|-----------------|
| 1 | 0.5 | 40px |
| 2 | 0.25, 0.75 | 20px, 60px |
| 3 | 0.25, 0.5, 0.75 | 20px, 40px, 60px |

**Assignment by position:**
- Same-row source → center (0.5) if odd count
- Upper-left source → upper entries first
- Lower-left source → lower entries first

#### 6.11 Edge Routing

**Same-row edges:** no waypoints needed. `exitX=1;exitY=0.5;entryX=0;entryY=0.5` produces a straight horizontal line.

**Cross-row edges:** use waypoints. The final waypoint Y MUST equal the target entry pixel Y:
```
waypoint_y = target.y + (entryY * target.height)
```

**No collinear segments:** no two edges may share the same (waypoint_x, waypoint_y). Offset by 20px if there's a collision.

**External box fan-out:** each edge from an external box to a different target needs its own `exitY` matching the target's center Y.

#### 6.12 Z-Order (generate in this order, back to front)

1. Dashed/stream edges
2. Title
3. DynamoDB nodes
4. SQS / SNS / EventBridge nodes
5. Main-flow edges
6. External boxes
7. Lambda nodes (front)

#### 6.13 MANDATORY PRE-SAVE CHECKLIST

**Before writing the file, read back every mxCell and verify ALL of these:**

- [ ] **NO `&amp;lt;` or `&amp;gt;` or `&amp;quot;` in ANY `value="..."` attribute.** Must be `&lt;`, `&gt;`, `&quot;`.
- [ ] **Every edge: `source.x < target.x`.** Flow goes left→right. If any source is to the right of its target, the layout is wrong — move the target to a larger X column.
- [ ] **Every edge: `entryX=0`** (enters LEFT side of target). Never `entryX=1`. If you see `entryX=1`, it means the layout has a right→left flow — fix the layout, not the entry side.
- [ ] **Every edge: `exitX=1`** (exits RIGHT side of source).
- [ ] **Every edge from an External box: has `exitY=<value>` in the style** matching the target icon's center Y. No bare `mxPoint` for external edges.
- [ ] **Multi-arrow targets: entryY values are ALL DISTINCT and correctly distributed.** For N arrows, use N equally-spaced values. Check: 2 arrows → 0.25, 0.75 (not both 0.5). 3 arrows → 0.25, 0.5, 0.75. 4 arrows → 0.167, 0.389, 0.611, 0.833. Count them — if two share the same value, fix it.
- [ ] **Cross-row edges: the final waypoint Y = `target.y + entryY * target.height`.** Compute this for every cross-row edge. If any waypoint Y doesn't match, fix it.
- [ ] **No two edges share the same (waypoint_x, waypoint_y).** Check every pair of waypoints. Even if X differs by 20 but Y is the same, ensure the vertical segments don't overlap.
- [ ] **Row spacing: icons in different rows are at Y values that differ by 240px (step = 80 icon + 160 gap = 2× icon height).** If two icons share the same X column but are only 80px apart, they're crammed — spread them to proper rows.
- [ ] **No external boxes mid-diagram.** External boxes only at x=-80 or at x = (rightmost_icon_x + 160).
- [ ] **All coordinates are multiples of 10.**
- [ ] **No `endArrow` or `startArrow` on any edge.**

**If ANY checkbox fails, fix the XML before saving. Do not skip.**

#### 6.14 Save

```bash
mkdir -p docs
```

Write the XML to `docs/<dirname>-architecture.drawio` via bash. Then:

```
drawio_set_page path: "docs/<dirname>-architecture.drawio" page: 0 content: "<mxGraphModel XML>"
```

### Step 7 — Report

Tell the user:
```
Diagram saved: docs/<dirname>-architecture.drawio
```

List any AWS resources found in graphify but filtered by the ignore list.

Stop. Do NOT open the diagram in the editor unless the user explicitly asks.
