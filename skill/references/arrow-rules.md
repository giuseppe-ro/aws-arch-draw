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

## Rule 4: Target Entry Points (Left Edge)

**All arrows enter the LEFT edge of the target icon** (`entryX=0`).

### 4a: Equal distribution

Entry points are equally distributed along the left edge. For an 80px icon:

| Incoming arrows | entryY values | Pixel positions (from top) |
|-----------------|---------------|----------------------------|
| 1 | `0.5` | 40px (center) |
| 2 | `0.25`, `0.75` | 20px, 60px |
| 3 | `0.25`, `0.5`, `0.75` | 20px, 40px, 60px |
| 4 | `0.167`, `0.389`, `0.611`, `0.833` | ~13px, 31px, 49px, 67px |

Never stack two arrows on the same entry point.

### 4b: Assignment by source position

The entryY assigned to each source depends on where the source is relative to the target:

| Source position | Gets entryY |
|-----------------|-------------|
| **Directly left** (same row Y) | `0.5` (center) — when total arrow count is odd (1,3,5...) |
| **Upper-left** (source Y < target Y) | Upper entry points first (0.25, 0.167, etc.) |
| **Lower-left** (source Y > target Y) | Lower entry points first (0.75, 0.833, etc.) |

Example — 3 arrows to DynamoDB at y=320, h=78:
```
Lambda at y=160 (upper-left):   entryY=0.25  → entry at y=339.5
Lambda at y=320 (same row):     entryY=0.50  → entry at y=359.0  ← directly left, odd count → center
Lambda at y=800 (lower-left):   entryY=0.75  → entry at y=378.5
```

### 4c: Formula

```
entry_pixel_y = target.y + (entryY * target.height)
waypoint_y must equal entry_pixel_y (see Rule 3a)
```

## Rule 5: Source Exit Points (Right Edge)

**All arrows exit from the RIGHT edge of the source icon** (`exitX=1`).

Same distribution principles as Rule 4, applied to the right edge:

| Outgoing arrows | exitY values |
|-----------------|-------------|
| 1 | `0.5` |
| 2 | `0.25`, `0.75` |
| 3 | `0.25`, `0.5`, `0.75` |

Assignment by target position:

| Target position | Gets exitY |
|-----------------|-----------|
| **Directly right** (same row Y) | `0.5` (center) — when total arrow count is odd |
| **Upper-right** (target Y < source Y) | Upper exit points first |
| **Lower-right** (target Y > source Y) | Lower exit points first |

## Rule 6: Exit Points from External Boxes

External boxes spanning multiple rows distribute exit points proportionally:

- 3-row external (h=480): exits at `exitY=0.164` and `exitY=0.832` (~1/6 and 5/6)
- exitY aligns with the **center Y** of the target icon in each respective row
- `exitX ≈ 1.0` (right edge)

## Rule 7: Dashed Edges (Async / Event-Driven)

```
dashed=1;dashPattern=8 8;opacity=50
```

Used for:
- **EventBridge → Lambda** (event-driven trigger)
- **Lambda → DynamoDB** cross-row (async eventual consistency)

Semantics: represents asynchronous, event-driven, or non-blocking flows.

## Arrow Source/Target Anchoring Summary

| Direction | Anchor | Distribution |
|-----------|--------|-------------|
| Source exit | Right edge (`exitX=1`) | Evenly distributed (`exitY` varies — see Rule 5) |
| Target entry | Left edge (`entryX=0`) | Evenly distributed (`entryY` varies — see Rule 4) |

**Source always → RIGHT. Target always ← LEFT.**

## Quick Reference: Entry/Exit Distribution

For an 80px icon, the pixel positions from top:

| Count | entryY/exitY | Pixels from top |
|-------|-------------|-----------------|
| 1 | 0.5 | 40px |
| 2 | 0.25, 0.75 | 20px, 60px |
| 3 | 0.25, 0.5, 0.75 | 20px, 40px, 60px |
| 4 | 0.167, 0.389, 0.611, 0.833 | 13px, 31px, 49px, 67px |

**Assignment:** Same-row source/target gets center (if odd count). Upper gets upper. Lower gets lower.
