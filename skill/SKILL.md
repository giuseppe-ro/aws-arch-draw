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
- After discovery, no supported AWS resources remain

**Do NOT:**
- Ask "what would you like me to do?"
- Ask for confirmation before starting
- Read project source files (.tf, .cs, .yml, .md) — graphify is the ONLY source
- Use the visual rules from any other skill — the skill body (§6) is the CANONICAL reference. Reference files in references/ are provided for context only; if they conflict with the skill body, the skill body always wins.

## Prerequisites

**graphify is the ONLY source of architectural information. No fallback.**

```bash
graphify --version 2>&1 || { echo "STOP: graphify is not installed."; exit 1; }
```

If `graphify --version` fails → tell user: `pip install graphifyy`, then stop.

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

Read these files for **context only**. The skill body (§6) is the CANONICAL reference — if any reference file conflicts with the skill body, the skill body always wins.

- `references/layout-rules.md` — canvas, grid, spacing, title bar (context)
- `references/color-rules.md` — service colors, arrow color logic (context)
- `references/arrow-rules.md` — edge styles, entry distribution, routing (context)
- `references/component-specs.md` — icon specs, external boxes, full service mapping (context)

> **External box Y/H formula conflict resolved:** The skill body §6.7 is authoritative: `y = icon_y - 40`, `height = (last_row - first_row) + 160`. The reference file component-specs.md states `y = icon_y - 80`, `height = (last-first) + 240` — **this is wrong, do not use it.**

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

**DISCARD all attributes from search results EXCEPT the `resIcon` suffix.** The search may return `points=...`, `whiteSpace=...`, `spacing=...`, `gradientColor=...`, `pointerEvents=...` — NONE of these go into the icon style. Always build the icon style from the template in §6.5, substituting only:
- `SERVICE` → the `resIcon` suffix (e.g. `sqs`, `lambda`, `sns`, `s3`, `dynamodb`)
- `FILL_COLOR` → the fillColor for the service

The search results are ONLY to verify the `resIcon` suffix exists. Never copy style attributes from search results.

### Step 5 — Plan layout

From the merged graphify results, determine layout using the deterministic formulas below.

#### 5.1 — Deterministic Column Assignment (CANONICAL FORMULA)

Columns are assigned based on pipeline depth with a single authoritative formula. **No hardcoding per resource type.**

```
Column index (starting at 1):
  1. Walk each flow chain from source to sink
  2. Assign column index 1 to the first AWS processing stage
  3. Each downstream stage increments column index by 1
  4. Column index N → absolute X = 240 × N

Resulting grid: col 1=240, col 2=480, col 3=720, col 4=960, col 5=1200, col 6=1440, col 7=1680, ...

External box at x=-80 is NOT a column — it does not consume a column index.
```

**Same-stage parallel resources** (e.g. 5 SQS queues all fed by one SNS topic) share the same column X.

**CRITICAL:** Every adjacent stage on a flow chain must have exactly **240px center-to-center** (160px edge-to-edge). If any gap ≠ 240px, the column assignment is wrong.

#### 5.2 — Deterministic Row Assignment

```
Row grid: 160, 320, 480, 640, 800, 960, 1120, 1280, 1440, 1600, ... (step 160 = 80px icon + 80px gap)
Row formula: y_n = 160 × n  (n = 1, 2, 3, ...)
```

Each independent flow chain gets its own horizontal row. Every distinct flow gets a full 160px row — never cram multiple flows at sub-spacing.

#### 5.3 — Shared Resource Placement (DynamoDB)

DynamoDB tables used by multiple flows appear **ONCE**.

**Column X (rightmost-writer rule):**
```
ddb_col_index = max(all writer Lambda column indices) + 1
ddb_x = 240 × ddb_col_index
```

Example: writers at col 2 and col 3 → ddb_col = 4 → ddb_x = 960.

**Row Y (snapped-to-grid, never "between"):**
```
1. Find the lowest row Y among all writer Lambdas
2. candidate = lowest_writer_y + 160
3. Snap to nearest valid row grid: snapped = round(candidate / 160) × 160
4. If snapped < candidate, use snapped + 160
5. Apply collision guard (advance by +160 if occupied)
```

This guarantees DDB always lands on a valid row (160, 320, 480, 640...), never at off-grid values like 560.

#### 5.4 — Backward-Flow Resolution

Some architectures have natural backward edges (e.g. DynamoDB triggers → consumer Lambdas that then feed SNS). This contradicts the "every flow goes rightward" rule.

**Resolution:**
```
When a shared resource (DynamoDB) has edges TO downstream consumers:
1. Determine if the consumer has ONLY this one incoming edge (trigger-driven)
2. If YES: place the consumer at the NEXT column right of the shared resource
   (advance its pipeline stage — e.g. DDB at col 4, consumer at col 5)
3. If NO (consumer has other incoming edges too): place it at the column matching its natural stage
4. Re-route all downstream edges from the consumer starting from its new column
```

This preserves the left→right flow rule while handling the trigger pattern correctly.

#### 5.5 — Fan-In Handling

When a single target receives edges from multiple sources at different columns, each incoming edge gets a distinct entryY (distributed per §6.10). The target must be placed at a column strictly greater than the rightmost source. If this causes a collision, promote the target to a new row.

#### 5.6 — Icon Collision Guard (MANDATORY before placing each icon)

Check if any other icon already occupies the candidate (col_x, row_y). If occupied, advance the candidate row by +160 and recheck. Never place two icons at the same (x, y).

#### 5.7 — External Boxes

ONLY at the left edge (`x=-80`) or right edge (past the rightmost icon + 160px). NEVER place an external box mid-diagram at a column X used by AWS icons.

**IMPORTANT:** An SNS topic that fans out to SQS queues via subscriptions is an AWS resource, NOT an external box. Only systems outside the AWS account boundary (e.g. an upstream WMS, downstream consumers) go in external boxes. If graphify discovers `aws_sns_topic_subscription` resources connecting an SNS topic to SQS queues, render that SNS topic as a standard AWS icon node at its assigned column — do NOT collapse it into the external box.

**Left external box:** x=-80, w=160
**Right external box:** x = rightmost_icon_x + 160, w=160

**Y positioning:** `y = icon_y - 40` so the box extends 40px above and 40px below the icon.
**Multi-row formula:** `y = first_row_icon_y - 40`, `height = (last_row_icon_y - first_row_icon_y) + 160`.

#### 5.8 — Fan-Out Row Promotion

When any node sends edges to 2+ downstream nodes in the same column, only the FIRST target stays on the current row with a straight horizontal edge (exitY=0.5). ALL additional targets MUST move to new rows below: `y = current_row_y + n × 160` where n=1,2,3… This guarantees every edge is either a straight horizontal or a clean L-shape — no edge will pass through another icon.

Example — Lambda at y=320 with two SNS targets at column 1200:
```
sns-updates at y=320 (same row, exitY=0.5 → straight horizontal)
sns-cancel-req at y=480 (next row, exitY=0.75 → clean L-shape)
```

#### 5.9 — External Box Height Synthesis

An external box's height must span ALL rows of icons it connects to (incoming OR outgoing). Scan every edge touching the external box, find the first (lowest Y) and last (highest Y) connected icon rows, and compute: `ext.y = first_row_icon_y - 40`, `ext.h = (last_row_icon_y - first_row_icon_y) + 160`. Never use a fixed height — compute it from the actual row span.

**Canonical formula (same as §6.7):** This is the authoritative formula. Do not use alternative formulas from context files.

#### 5.10 — Orphan Resource Handling

If graphify discovers a supported AWS resource with **zero edges** (no incoming or outgoing connections):
- Place it in the rightmost column on a new row below all active flows at `y = lowest_active_row + 320`
- Render it normally but **do not create any edges for it**
- List it in the Step 7 report as "discovered but no connections found"

#### 5.11 — Column Assignment Pre-Flight Check (MANDATORY before generating XML)

Before generating any XML, print and verify this table:

```
Column Assignment Table:
  col 1 (x=240):  <list resources>
  col 2 (x=480):  <list resources>
  col 3 (x=720):  <list resources>
  ...

Verification:
  [ ] Every adjacent stage on the same flow chain has exactly 240px X spacing
  [ ] No column index is skipped between connected stages on any chain
  [ ] External boxes are NOT assigned a column index
```

If the verification fails, **rebuild the column assignment** before proceeding. Do not generate XML with broken column spacing.

**CRITICAL: One flow = one full row.** Even when multiple flows share the same source (e.g. one external box feeds 5 SQS queues), each flow gets its own 160px row. The external box height grows to match.

Example — CORRECT with 3 flows (step 160):
```
Row y=160:  SQS_order → Lambda_order → DDB
Row y=320:  SQS_receipt → Lambda_receipt → DDB
Row y=480: SQS_adjust → Lambda_adjust → DDB
External box h=640 covers y=120..600
```

**SNS→SQS fan-out is a first-class pattern.** When graphify discovers `aws_sns_topic_subscription` resources connecting an SNS topic to multiple SQS queues, render the SNS topic as a standard AWS icon node at its assigned column. Do NOT collapse it into an external box.

Icons: 80×80. Inter-icon x gap: 160px edge-to-edge (240px center-to-center). External box width: 160. All coordinates multiples of 10.

### Step 6 — Generate and save .drawio XML

**ALL rules below are mandatory. Apply them while generating. Do not rely on reference files — these rules ARE the reference.**

#### 6.1 File Skeleton

**The closing tags are MANDATORY and must appear in this exact order.** Never use `...` or skip any closing tag.

```xml
<mxfile host="Electron" modified="2025-01-01T00:00:00.000Z" agent="pi" version="24.0.0" type="device">
  <diagram name="Page-1" id="ARCHITECTURE">
    <mxGraphModel dx="0" dy="0" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="[CALCULATED]" pageHeight="[CALCULATED]" background="light-dark(#FFFFFF,#FFFFFF)" math="0" shadow="0">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <!-- ALL cells here -->
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

**MUST close in reverse open order: `</root>` → `</mxGraphModel>` → `</diagram>` → `</mxfile>`.**

**Page dimensions:** `pageWidth = rightmost_icon_x + 320`, `pageHeight = lowest_icon_y + 320`. These are computed AFTER layout is complete — use the actual final values, not placeholders.

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
| Column X grid | 240, 480, 720, 960, 1200, ... (step 240, grows rightwards as pipeline deepens; no fixed limit) |
| Row Y grid | 160, 320, 480, 640, 800, 960, 1120, ... (step 160) |
| Left external box | x=-80, w=160 |
| Right external box | `x = rightmost_icon_x + 160`, w=160 (dynamic, not hardcoded) |
| External box Y (40px padding above & below icons) | `y = icon_y - 40` (for 160px tall single-row box) |

**All x/y coordinates must be multiples of 10.**

**Flow direction is ALWAYS left→right.** Source icon must have a smaller X than target icon.

#### 6.5 AWS Icon Template

**Every AWS icon MUST use this exact style structure.** Substitute `SERVICE` and `FILL_COLOR` only:

```xml
<mxCell id="UNIQUE_ID" value="&lt;b&gt;Name&lt;/b&gt;&lt;div&gt;TYPE&lt;/div&gt;" style="sketch=0;outlineConnect=0;fontColor=#232F3E;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.SERVICE;fillColor=FILL_COLOR;" vertex="1" parent="1">
  <mxGeometry x="X" y="Y" width="80" height="80" as="geometry" />
</mxCell>
```

**CRITICAL — `strokeColor=#ffffff` is MANDATORY for ALL icons.** Never use `strokeColor=none`. The white border is required for icon visibility.

**DynamoDB exception:** Use `shape=mxgraph.aws4.dynamodb_standard_access_table_class` (no `resourceIcon`, no `resIcon`). Add `gradientColor=none;pointerEvents=1;` AFTER the shape. Full style:
```
sketch=0;outlineConnect=0;fontColor=#232F3E;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.dynamodb_standard_access_table_class;fillColor=#C925D1;gradientColor=none;pointerEvents=1;
```

**S3 uses `resourceIcon` template with `resIcon=mxgraph.aws4.s3`.** Do NOT use `shape=mxgraph.aws4.bucket` — that is not the standard icon format.

**After generating every icon, verify its style contains `strokeColor=#ffffff`.** If any icon has `strokeColor=none`, `strokeColor=white`, or no strokeColor at all, fix it.

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

**Y positioning:** Set `y = icon_y - 40` so the external box extends 40px above and 40px below the icon. For a single-row external alongside an icon at y=160: `y=120`, `h=160`. Height must span the rows it connects to.

**Multi-row external box formula:** `y = first_row_icon_y - 40`, `height = (last_row_icon_y - first_row_icon_y) + 160`.

**CRITICAL — Height synthesis:** compute height from ALL edges touching the external box, not just the obvious ones. Scan every edge where source or target is an external box. Find the highest and lowest icon midY among connected icons. Height must span from the lowest icon top (minus 80) to the highest icon bottom (plus 80). Recompute after any row promotion.

#### 6.8 Edge Style

Every edge uses this base style with arrowheads:

```
edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=2;jumpStyle=arc;endArrow=classic
```

Plus color: add `strokeColor=light-dark(#HEX, #ededed)` where HEX is the non-Lambda service color (see 6.9).

Plus entry/exit anchors: add `exitX=1;exitY=<value>;entryX=0;entryY=<value>` to every edge. **Every edge MUST have both `exitX=1` AND `entryX=0`.** Never omit them.

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

**Maximum 3 arrows per icon edge.** For 4+ arrows, spacing drops below 20px — split flows or add intermediate nodes.

**Assignment by position:**
- Same-row source → center (0.5) if odd count
- Upper-left source → upper entries first
- Lower-left source → lower entries first

**Same-row edges MUST use exitY=0.5 and entryY=0.5** (straight horizontal line). Only offset exitY/entryY when:
- The source has multiple outgoing edges (fan-out) — each additional edge gets a different exitY
- The target has multiple incoming edges (fan-in) — each edge gets a different entryY
- The edge crosses rows (non-zero vertical deviation needed)

#### 6.11 Edge Routing

**Same-row edges (source.y == target.y):** No waypoints, no `targetPoint`, no `sourcePoint`. The geometry is EXACTLY:

```xml
<mxGeometry relative="1" as="geometry" />
```

Nothing between the tags. No children. No attributes other than `relative="1"` and `as="geometry"`.

**Cross-row edges (source.y ≠ target.y):** Use exactly two waypoints forming an L-shaped path:

```xml
<mxGeometry relative="1" as="geometry">
  <Array as="points">
    <mxPoint x="wp1_x" y="wp1_y" />
    <mxPoint x="wp2_x" y="wp2_y" />
  </Array>
</mxGeometry>
```

**NO `targetPoint`, NO `sourcePoint` on cross-row edges.**

Compute waypoints as follows:

```
# Waypoint 1 — the turn AFTER exiting source (must be ≥10px right of source edge):
wp1_x = source.x + 80 + 10     # = source.x + 90  (NEVER source.x + 80)
wp1_y = source.y + (exitY * 80) # exit pixel Y on source right edge

# Waypoint 2 — the turn BEFORE entering target (must be ≥10px left of target edge):
wp2_x = target.x - 10           # (NEVER target.x, NEVER target.x + 80)
wp2_y = target.y + (entryY * 80) # entry pixel Y on target left edge (MUST match exactly)
```

**The horizontal segment after source exit MUST be ≥10px long** — wp1_x must never equal source.x + 80 (the icon's right edge). **The horizontal segment before target entry MUST be ≥10px long** — wp2_x must never equal target.x (the icon's left edge). Both waypoints must be placed with visible horizontal offset from the icon edges.

**Icon collision pre-check (MANDATORY before every edge):**

Before finalizing any edge path, verify it avoids ALL icon bounding boxes:
- For each **horizontal segment at Y**: no icon has [icon.y, icon.y+80] that includes Y AND [icon.x, icon.x+80] that overlaps the segment's X range
- For each **vertical segment at X**: no icon has [icon.x, icon.x+80] that includes X AND [icon.y, icon.y+80] that overlaps the segment's Y range
- Exclude the edge's own source and target icons from the check

**If collision found**: promote the downstream target to a new row (fan-out row promotion, Step 5 rule 8). Never route an edge THROUGH an icon — it looks like a connection.

**No collinear segments:** no two edges may share the same (waypoint_x, waypoint_y). Offset by 10px if there's a collision. **Parallel same-route edges must be ≥10px apart** in the perpendicular axis (see arrow-rules.md Rules 8, 11).

**No edge-icon overlap:** every edge segment must avoid all icon bounding boxes. Route edges through the 160px inter-column/row gaps, never through icon columns. If a segment would pass through an icon, adjust routing column X or waypoint Y (see arrow-rules.md Rule 10).

**External box fan-out:** each edge from an external box to a different target needs its own `exitY` matching the target's center Y.

#### 6.12 Z-Order (generate in this order, back to front)

1. Title
2. DynamoDB nodes
3. SQS / SNS / EventBridge nodes
4. Main-flow edges
5. External boxes
6. Lambda nodes (front)

#### 6.13 MANDATORY PRE-SAVE CHECKLIST

**Before writing the file, read back every mxCell and verify ALL of these:**

- [ ] **NO `&amp;lt;` or `&amp;gt;` or `&amp;quot;` in ANY `value="..."` attribute.** Must be `&lt;`, `&gt;`, `&quot;`.
- [ ] **Every edge: `source.x < target.x`.** Flow goes left→right. If any source is to the right of its target, the layout is wrong — move the target to a larger X column.
- [ ] **Column spacing verified:** Every adjacent pipeline stage on the same flow chain has exactly 240px center-to-center spacing (160px edge-to-edge). No skipped columns between connected stages. Check: `target.x - source.x` should be 240, 480, 720, etc. (multiples of 240) for connected stages. If any gap ≠ multiple of 240, the column assignment is wrong.
- [ ] **No off-grid X values:** Every icon x must be in {240, 480, 720, 960, 1200, 1440, 1680, 1920, 2160, 2400, ...} (formula: 240 × N, N≥1). External box x=-80 and right external at x=rightmost+160 are the only exceptions. If any icon has x=160, x=400, x=880, x=1120, x=1600 — REBUILD the column assignment.
- [ ] **Icon style validation:** Every icon style must contain `strokeColor=#ffffff`. No icon may have `strokeColor=none`. Every icon style must use `shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.<service>` (or DynamoDB exception). No icon style may contain `points=` array from search results.
- [ ] **Edge geometry validation:** Same-row edges must have empty `<mxGeometry relative="1" as="geometry" />` (no children). Cross-row edges must have `<Array as="points">` with exactly 2 `<mxPoint>` elements. NO edge may have `targetPoint` or `sourcePoint` in its geometry.
- [ ] **Edge entry/exit anchors:** Every edge must have `exitX=1;exitY=<value>` AND `entryX=0;entryY=<value>` in its style. No edge may omit these anchors.
- [ ] **Every edge: `entryX=0`** (enters LEFT side of target). Never `entryX=1`. If you see `entryX=1`, it means the layout has a right→left flow — fix the layout, not the entry side.
- [ ] **Every edge: `exitX=1`** (exits RIGHT side of source).
- [ ] **Every edge from an External box: has `exitY=<value>` in the style** matching the target icon's center Y. No bare `mxPoint` for external edges.
- [ ] **Multi-arrow targets: entryY values are ALL DISTINCT and correctly distributed.** For N arrows (max 3 per edge), use N equally-spaced symmetric values. 2 arrows → 0.25, 0.75. 3 arrows → 0.25, 0.5, 0.75. Max 3 arrows per icon edge — if a resource needs 4+ connections, split flows. Pairs sum to 1.0 (symmetry).
- [ ] **Cross-row edges: the final waypoint Y = `target.y + entryY * target.height`.** Compute this for every cross-row edge. If any waypoint Y doesn't match, fix it.
- [ ] **No edge overlap (Rule 8):** For every pair of edges, decompose into segments. No two parallel segments share same X with overlapping Y range, or same Y with overlapping X range. Same-route edges must be parallel and ≥10px apart on both X and Y axes. Intersections (perpendicular crossing at a point) are OK.
- [ ] **Symmetric distribution (Rule 9):** For every icon with N>1 incoming/outgoing arrows, entryY/exitY values form mirror pairs (upper ↔ lower). Pairs sum to 1.0. Same-row source/target gets center (0.5) when N is odd.
- [ ] **No edge passes through any icon (Rule 10):** For every edge segment, verify it avoids all icon bounding boxes (icon.x..icon.x+80, icon.y..icon.y+80). Exclude the edge's own source/target icons. Route through 160px inter-column gaps.
- [ ] **Minimum 10px separation (Rule 11):** Vertical routing columns differ by ≥10px. Horizontal routing Y values differ by ≥10px. Entry/exit points have ≥10px pixel spacing (max 3 arrows per icon edge).
- [ ] **Minimum 10px horizontal run at every edge start and end:** For every cross-row edge, wp1_x ≥ source.x + 90 (never source.x + 80). wp2_x ≤ target.x - 10 (never target.x). No vertical turn directly at an icon edge — both waypoints must be visibly offset from the source and target boundaries.
- [ ] **No two edges share the same (waypoint_x, waypoint_y).** Check every pair of waypoints. Even if X differs by 20 but Y is the same, ensure the vertical segments don't overlap.
- [ ] **Row spacing: icons in different rows are at Y values that differ by 160px (step = 80 icon + 80 gap).** If two icons share the same X column but are only 80px apart, they're crammed — spread them to proper rows.
- [ ] **No external boxes mid-diagram.** External boxes only at x=-80 or at x = (rightmost_icon_x + 160).
- [ ] **Fan-out row promotion:** For every node with 2+ outgoing edges to same-column targets, only the FIRST target shares the source row (straight horizontal exitY=0.5). ALL additional targets must be on new rows at y = current_row_y + n×160. Rebuild the edge routing after promoting.
- [ ] **External box height synthesis:** For each external box, scan ALL edges touching it. Find first and last connected icon rows. Height = (last_row_y - first_row_y) + 160, Y = first_row_y - 40. If promoting a target to a new row increased the span, grow the external box height accordingly. Recompute AFTER row promotion.
- [ ] **All coordinates are multiples of 10.**
- [ ] **Every edge has `endArrow=classic`.** No edge should be missing its arrowhead.
- [ ] **No two icons share the same (x, y) position.** Scan all icon `<mxGeometry>` elements. If any two icons have the same x AND same y, the layout has a collision — advance the later one to a new row at y+160.
- [ ] **No edge flows right→left.** After any icon repositioning, re-verify all edges: `source.x < target.x`. Recheck this after every layout adjustment.
- [ ] **DynamoDB row is on-grid.** Verify `ddb_y % 160 == 0`. If not, the row placement snapped incorrectly — recalculate using: `candidate = lowest_writer_y + 160`, `snapped = round(candidate / 160) × 160`, `if snapped < candidate: snapped += 160`.
- [ ] **All closing tags present:** File must end with `</root>\n</mxGraphModel>\n</diagram>\n</mxfile>` in that exact order. Missing any closing tag will make the file unopenable in draw.io.
- [ ] **Page dimensions calculated:** `pageWidth = rightmost_icon_x + 320`, `pageHeight = lowest_icon_y + 320`. Not placeholders — actual computed numbers.

**If ANY checkbox fails, fix the XML before saving. Do not skip.**

#### 6.14 Save

Write the XML to `docs/<dirname>-architecture.drawio` via bash. Then:

```
drawio_set_page path: "docs/<dirname>-architecture.drawio" page: 0 content: "<mxGraphModel XML>"
```

**Before saving, validate the XML is well-formed.** If the file cannot be parsed by an XML parser, it will fail to open in draw.io. The most common cause is a missing closing tag (especially `</mxGraphModel>`). Verify the file has all closing tags in reverse order: `</root>`, `</mxGraphModel>`, `</diagram>`, `</mxfile>`.

### Step 7 — Report

Tell the user:
```
Diagram saved: docs/<dirname>-architecture.drawio
```

List:
1. Any AWS resources filtered by the ignore list
2. Any orphan resources (discovered with zero edges) — placed on a separate row
3. Any backward-flow resolutions applied (e.g. DDB-triggered Lambdas placed right of DDB)

Stop. Do NOT open the diagram in the editor unless the user explicitly asks.
