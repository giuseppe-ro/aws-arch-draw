# Arrow / Edge Rules

Extracted from `aws_arch_template.drawio`.

## Edge Style Constants

Every edge uses this base style:

```
edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=2;jumpStyle=arc
```

- `orthogonalEdgeStyle` — always orthogonal (never curved/direct)
- `rounded=0` — sharp 90° corners, never rounded
- `strokeWidth=2` — consistent bold weight
- `jumpStyle=arc` — crossing lines arc over each other
- **No arrowheads** — no `endArrow` or `startArrow` on any edge

## Rule 1: Same-Row Arrows = STRAIGHT HORIZONTAL

When source and target share the same Y row, the arrow is a **single straight horizontal line** with zero vertical deviation.

```
exitX=1  exitY=0.5  (right edge, vertical center)
entryX=0  entryY=0.5 (left edge, vertical center)
```

Both exit and entry must be at Y=0.5 (midpoint). This guarantees the path is perfectly horizontal.

**10 of 11 same-row edges have 0px deviation.**

## Rule 2: The "Branch" Exception

A single edge (Lambda → SNS in top row) uses `entryY=0.25` — a **20px upward offset**.

This happens when a single source fans out to two targets: one same-row (SNS) and one cross-row (DynamoDB below). The offset visually distinguishes the branch from the main downstream path. Use sparingly.

## Rule 3: Cross-Row Arrows = L-shaped via Routing Column

When source and target are in different rows:

```
source_right_edge → horizontal → routing_column → vertical → target_entry_Y → horizontal → target_left_edge
```

- A routing column is placed **between** the source's right edge and target's left edge
- Default routing column `x=620` (between source right=560 and target left=720)

### Rule 3a: Waypoint Y MUST equal entryY pixel position (CRITICAL)

The final horizontal segment into the target must be at the EXACT Y of the entry point.
Compute the waypoint Y from the entryY fraction:

```
waypoint_y = target.y + (entryY * target.height)
```

**Wrong** (all edges route to center, then correct at the last moment):
```
# Two edges to same DynamoDB at (880, 320), h=78:
# Edge A: entryY=0.25 → actual entry at y=339.5
# Edge B: entryY=0.75 → actual entry at y=378.5

# WRONG: both waypoint at y=359 (center)
Edge A: → (800,520) → (800,359) → (880,339.5)   ← last segment slopes!
Edge B: → (800,840) → (800,359) → (880,378.5)   ← last segment slopes!
```

**Correct** (each edge routes to its own entry Y):
```
# CORRECT: waypoint Y matches entry Y exactly
Edge A: → (800,520) → (800,339.5) → (880,339.5)  ← final segment is horizontal
Edge B: → (800,840) → (800,378.5) → (880,378.5)  ← final segment is horizontal
```

The horizontal approach to the target must be at the entry Y — never slope into the icon.

### Rule 3b: One routing lane per edge

When multiple edges target the same icon, each edge gets its own lane:
- Different `entryY` → different `waypoint_y` → distinct horizontal approach
- No two edges share the same routing column X when fanning out from one source
- Each edge's `<Array as="points">` must have unique waypoint coordinates

## Rule 4: Entry Point Distribution (Multi-Arrow Targets)

When multiple arrows hit the **same target icon**, entry points are distributed equally along the left edge:

| Incoming arrows | entryY values |
|-----------------|---------------|
| 1 | `0.5` |
| 2 | `0.25`, `0.75` |
| 3 | `0.25`, `0.5`, `0.75` |
| 4 (extrapolated) | `0.167`, `0.389`, `0.611`, `0.833` |

- **All entryX = 0** (left edge of target)
- Never stack two arrows on the same entry point
- Arrows always enter the **left edge**, exit the **right edge**

## Rule 5: Exit Points from External Boxes

External boxes spanning multiple rows distribute exit points proportionally:

- 3-row external (h=480): exits at `exitY=0.164` and `exitY=0.832` (~1/6 and 5/6)
- exitY aligns with the **center Y** of the target icon in each respective row
- `exitX ≈ 1.0` (right edge)

## Rule 6: Dashed Edges (Async / Event-Driven)

```
dashed=1;dashPattern=8 8;opacity=50
```

Used for:
- **EventBridge → Lambda** (event-driven trigger)
- **Lambda → DynamoDB** cross-row (async eventual consistency)

Semantics: represents asynchronous, event-driven, or non-blocking flows.

## Arrow Source/Target Anchoring Summary

| Direction | Anchor |
|-----------|--------|
| Source exit | Right edge (`exitX=1`), centered (`exitY=0.5`) |
| Target entry | Left edge (`entryX=0`), distributed (`entryY` varies) |
