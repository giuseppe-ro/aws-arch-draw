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

### Rule 3b: One routing column per edge — no collinear segments

**No two edges may share the same routing column X.** When two lines occupy the same X position, they become collinear (running on top of each other) instead of crossing with a visible arc jump.

**Fan-out from one source to N targets:** each edge gets its own routing column X.
```
base_x = source.x + source.width + 40   # first routing column (40px right of source)
# Each edge i (0, 1, 2, ...) routes through:
routing_x = base_x + (i * 20)           # 20px separation between columns
```

Example — SNS at x=160 w=80 fanning to 4 SQS queues:
```
Edge 0: waypoint x=280  (160+80+40)
Edge 1: waypoint x=300
Edge 2: waypoint x=320
Edge 3: waypoint x=340
```

**Fan-in from multiple sources to one target:** each edge gets its own waypoint_y (Rule 3a). The routing column X can be shared ONLY if each edge uses a different waypoint_y — they cross at different Y positions so they don't overlap.

**Minimum separation:** 20px between any two parallel vertical routing segments.

**If edges must cross (different X, different Y):** `jumpStyle=arc` will draw a visible arc jump. This is acceptable and expected. Collinear overlap is NEVER acceptable.

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

External boxes distribute exit points so each edge's `exitY` aligns with the
**center Y** of its target icon:

```
exitY = (target.midY - ext.y) / ext.h
```

Where `target.midY = target.y + target.height/2`.

Example — 3-row external at y=80, h=800 with targets at rows y=160, y=400, y=640:
```
Row 1 target midY=200:  exitY = (200-80)/800 = 0.15
Row 2 target midY=440:  exitY = (440-80)/800 = 0.45
Row 3 target midY=680:  exitY = (680-80)/800 = 0.75
```

`exitX` is always `1.0` (right edge of external box).

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

## Rule 8: Overlap Forbidden — Intersect Only (MANDATORY)

### 8a: Definitions
- **Overlap**: Two edges share one or more consecutive coordinate points along
  their paths (any parallel segment of any length at the same X or Y).
  This is **FORBIDDEN** — the edges become invisible on top of each other.
- **Intersect (cross)**: Two edges pass through the same (x,y) point at
  different angles. This is **ACCEPTABLE** — draw.io's `jumpStyle=arc` will
  visually arc one edge over the other.

### 8b: Parallel Paths Rule
When multiple edges travel in the same direction between the same columns,
they MUST run **parallel** — all horizontal segments at distinct Y positions
or all vertical segments at distinct X positions. Edges on the same general
route must never converge to share the same line.

**Same-route edges must be offset by ≥20px** in the perpendicular axis:
- Horizontal edges going left→right: different Y positions, ≥20px apart
- Vertical edges going top→bottom: different X positions, ≥20px apart

### 8c: Collision Check Algorithm
Before finalizing the diagram, run this check for EVERY pair of edges:

1. **Decompose** each edge into its line segments (straight horizontal or
   vertical between waypoints + source exit + target entry)
2. **For each pair of segments** from different edges, check:
   - **Vertical-vertical (parallel)**: Same X AND overlapping Y ranges →
     OVERLAP → offset one routing column by +20px until clear
   - **Horizontal-horizontal (parallel)**: Same Y AND overlapping X ranges →
     OVERLAP → adjust one edge's routing Y by +20px until clear
   - **Vertical-horizontal (perpendicular)**: The vertical's X is within the
     horizontal's X range AND horizontal's Y is within vertical's Y range →
     **INTERSECT** → acceptable (jumpStyle=arc handles it)

### 8d: Same-Row Edge Constraint
Two same-row edges would have `entryY=0.5, exitY=0.5` at the same Y →
parallel overlap. **Only ONE straight same-row edge is permitted per Y level.**
If multiple flows share the same row, use the Branch Exception (Rule 2)
or route extra edges as cross-row edges through distinct routing columns.

### 8e: Routing Column Uniqueness
**No two edges may share the same routing column X.** When two lines occupy
the same X position, they become collinear instead of crossing.

**Fan-out from one source to N targets:** each edge gets its own routing column.
```
base_x = source.x + source.width + 40   # first routing column (40px right of source)
# Each edge i (0, 1, 2, ...) routes through:
routing_x = base_x + (i * 20)           # 20px separation between columns
```

Example — SNS at x=160 w=80 fanning to 4 SQS queues:
```
Edge 0: waypoint x=280  (160+80+40)
Edge 1: waypoint x=300
Edge 2: waypoint x=320
Edge 3: waypoint x=340
```

**Fan-in from multiple sources to one target:** each edge enters at a
distinct entryY. The routing column X can be shared ONLY if each edge
uses a different waypoint_y — they cross at different Y positions so
they can't overlap. Horizontal approach segments must be at different Y
levels, ≥20px apart.

**If edges must cross (different X, different Y):** `jumpStyle=arc` will
draw a visible arc jump. Parallel overlap is NEVER acceptable.

## Rule 9: Symmetric Distribution (MANDATORY)

Entry and exit points must be symmetric around the vertical midpoint (0.5)
of the icon edge. This applies to BOTH source exit points and target entry
points.

### 9a: Symmetry Definition
For N exit/entry points at positions p₁, p₂, ..., pₙ (sorted ascending):
`p₁ + pₙ = 1.0`, `p₂ + pₙ₋₁ = 1.0`, etc. The evenly-spaced distribution
table already satisfies this for N≤4.

| N | Positions | Pairs sum to 1.0? |
|---|-----------|-------------------|
| 1 | 0.5 | N/A (trivially symmetric) |
| 2 | 0.25, 0.75 | ✓ (0.25+0.75=1.0) |
| 3 | 0.25, 0.5, 0.75 | ✓ (0.25+0.75=1.0, 0.5 self-pair) |
| 4 | 0.167, 0.389, 0.611, 0.833 | ✓ (0.167+0.833=1.0, 0.389+0.611=1.0) |

### 9b: Symmetric Assignment
When assigning positions to sources/targets, preserve symmetry:
- Sources above and below the target must be assigned in mirror pairs:
  the furthest-above source gets the lowest entry, the furthest-below
  source gets the highest entry, and so on
- For odd N: the source/target directly on the same row gets the center
  point (0.5)
- For even N: no source/target gets 0.5 — all points come in mirror pairs

Example — 4 arrows to DynamoDB at y=320, h=80:
```
Lambda at y=80  (upper, 240px above):  entryY=0.167  → entry at y=333.4
Lambda at y=200 (upper, 120px above):  entryY=0.389  → entry at y=351.1
Lambda at y=440 (lower, 120px below):  entryY=0.611  → entry at y=368.9
Lambda at y=560 (lower, 240px below):  entryY=0.833  → entry at y=386.6
```
(0.167+0.833=1.0 ✓, 0.389+0.611=1.0 ✓)

## Rule 10: No Edge-Icon Overlap (MANDATORY)

No edge path may pass through any icon's bounding box. An edge traced
through an icon looks like it connects to that icon, which is visually
misleading.

### 10a: Icon Bounding Box
Each icon occupies: `[icon.x, icon.y, icon.x+80, icon.y+80]`.

### 10b: Collision Check
For every edge segment, check against every icon bounding box:
- **Horizontal segment at Y**: if Y is within `[icon.y, icon.y+80]` AND
  the segment's X range overlaps `[icon.x, icon.x+80]` → COLLISION
- **Vertical segment at X**: if X is within `[icon.x, icon.x+80]` AND
  the segment's Y range overlaps `[icon.y, icon.y+80]` → COLLISION

**Exclude the edge's own source and target icons from the check.**

### 10c: Resolution
If a collision is found:
1. **Adjust routing column X** to move the vertical segment into the
   160px gap between icon columns
2. **Adjust waypoint Y** to move a horizontal segment into the 160px
   gap between icon rows
3. **Add intermediate waypoints** to route AROUND the obstructing icon
   (extra L-shape detour)
4. As a last resort, reposition the obstructing icon to create clearance

**Route edges through inter-column gaps, not through icon columns.**
The 160px gap between columns (240px center-to-center minus 80px icon)
is your routing corridor.

## Rule 11: Minimum Separation Distance (MANDATORY)

### 11a: Universal Minimum
All parallel edge segments must be separated by at least **20px**:
- **Vertical segments**: routing column X values must differ by ≥20px
- **Horizontal segments**: routing Y values must differ by ≥20px

### 11b: Entry/Exit Point Spacing
For an 80px icon, the pixel spacing between adjacent entry/exit points:

| N arrows | Spacing | ≥20px? |
|----------|---------|--------|
| 2 | 40px | ✓ |
| 3 | 20px | ✓ |
| 4 | ~18px | ✗ — VIOLATION |

**Maximum 3 arrows per icon edge.** If a source/target needs 4+ connections:
- Split flows across separate instances of the resource
- Introduce intermediate routing nodes (SNS topics, SQS queues)
- Adjust layout to reduce fan-in/fan-out at a single icon
