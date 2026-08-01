#!/usr/bin/env python3
"""Deterministic AWS architecture diagram renderer for the aws-arch-draw skill.

Takes a small architecture model (JSON) and emits a complete, validated
.drawio file. All layout math, geometry, colors, escaping, and the pre-save
checklist live here so the LLM only needs to supply the model.

Model schema (JSON):
  {
    "title": "My Architecture",
    "nodes":  [{"id": "sqs-order", "name": "order_ingest", "type": "sqs"}, ...],
    "edges":  [{"from": "ext-upstream", "to": "sqs-order"}, ...],
    "externals": [{"id": "ext-upstream", "name": "WMS",
                   "description": "Upstream feeds", "side": "left"}, ...]
  }

Types: sqs, sns, eventbridge, lambda, dynamodb, stepfunctions, apigateway,
s3, kinesis, cloudwatch, ecs, eks, aurora, rds, sagemaker, bedrock, cognito,
cloudfront, route53, vpc, iam, secretsmanager.

Usage:
  python3 render.py model.json --out diagram.drawio --tf deploy/
  python3 render.py model.json --check --tf deploy/       # validate only
  python3 render.py diagram.drawio --check                # validate an existing file
  python3 render.py --discover resources.json             # draft model from graphify
  python3 render.py --discover-tf deploy/                 # draft model from terraform (authoritative)

Ground truth:
  A render is only allowed when the model can be diffed against ground truth:
  graphify-out/resources.json (--graph) OR terraform (--tf <deploy-dir>). When
  neither exists render.py exits with status 3 (UNVERIFIED); the caller should
  ask the user how to proceed instead of saving an unverified diagram.
"""

import json
import os
import sys
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

ICON_SIZE = 80
COL_STEP = 240
ROW_STEP = 160
GRID = 10
WP_MARGIN = 40
WP_FANOUT_STEP = 20

TYPES = {
    "sqs":           {"icon": "mxgraph.aws4.sqs", "color": "#E7157B", "label": "SQS"},
    "sns":           {"icon": "mxgraph.aws4.sns", "color": "#E7157B", "label": "SNS"},
    "eventbridge":   {"icon": "mxgraph.aws4.eventbridge", "color": "#E7157B", "label": "EventBridge"},
    "kinesis":       {"icon": "mxgraph.aws4.kinesis", "color": "#E7157B", "label": "Kinesis"},
    "cloudwatch":    {"icon": "mxgraph.aws4.cloudwatch", "color": "#E7157B", "label": "CloudWatch"},
    "lambda":        {"icon": "mxgraph.aws4.lambda", "color": "#ED7100", "label": "Lambda"},
    "stepfunctions": {"icon": "mxgraph.aws4.step_functions", "color": "#ED7100", "label": "Step Functions"},
    "ecs":           {"icon": "mxgraph.aws4.ecs", "color": "#ED7100", "label": "ECS"},
    "eks":           {"icon": "mxgraph.aws4.eks", "color": "#ED7100", "label": "EKS"},
    "sagemaker":     {"icon": "mxgraph.aws4.sagemaker", "color": "#ED7100", "label": "SageMaker"},
    "bedrock":       {"icon": "mxgraph.aws4.bedrock", "color": "#ED7100", "label": "Bedrock"},
    "dynamodb":      {"icon": "dynamodb_standard_access_table_class", "color": "#C925D1", "label": "DynamoDB"},
    "apigateway":    {"icon": "mxgraph.aws4.api_gateway", "color": "#C925D1", "label": "API Gateway"},
    "aurora":        {"icon": "mxgraph.aws4.aurora", "color": "#C925D1", "label": "Aurora"},
    "rds":           {"icon": "mxgraph.aws4.rds", "color": "#C925D1", "label": "RDS"},
    "cognito":       {"icon": "mxgraph.aws4.cognito", "color": "#C925D1", "label": "Cognito"},
    "cloudfront":    {"icon": "mxgraph.aws4.cloudfront", "color": "#C925D1", "label": "CloudFront"},
    "route53":       {"icon": "mxgraph.aws4.route_53", "color": "#C925D1", "label": "Route 53"},
    "secretsmanager": {"icon": "mxgraph.aws4.secrets_manager", "color": "#C925D1", "label": "Secrets Manager"},
    "s3":            {"icon": "mxgraph.aws4.s3", "color": "#7AA116", "label": "S3"},
    "vpc":           {"icon": "mxgraph.aws4.vpc", "color": "#7AA116", "label": "VPC"},
    "iam":           {"icon": "mxgraph.aws4.iam", "color": "#232F3E", "label": "IAM"},
}

BASE_ICON_STYLE = ("sketch=0;outlineConnect=0;fontColor=#232F3E;strokeColor=#ffffff;dashed=0;"
                   "shadow=1;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;"
                   "fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon={icon};fillColor={color};")
DDB_STYLE = ("sketch=0;outlineConnect=0;fontColor=#232F3E;strokeColor=#ffffff;dashed=0;"
             "shadow=1;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;"
             "aspect=fixed;shape=mxgraph.aws4.dynamodb_standard_access_table_class;fillColor=#C925D1;"
             "gradientColor=none;pointerEvents=1;")
EXTERNAL_STYLE = "rounded=1;whiteSpace=wrap;html=1;fontSize=12;fontColor=#232F3E;shadow=1;"
EDGE_BASE = ("edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;"
             "strokeWidth=2;jumpStyle=arc;endArrow=classic")


class ModelError(Exception):
    pass


def fail(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Model parsing & validation
# ---------------------------------------------------------------------------

def load_model(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        fail(f"cannot read model '{path}': {e}")
    if not isinstance(data, dict):
        fail("model must be a JSON object")
    title = str(data.get("title") or "Architecture")
    nodes, edges, externals = [], [], []

    node_ids = set()
    for n in data.get("nodes", []):
        nid = str(n.get("id", "")).strip()
        if not nid:
            fail("every node needs an 'id'")
        t = str(n.get("type", "")).strip()
        if t not in TYPES:
            fail(f"node '{nid}': unknown type '{t}'. Valid: {', '.join(sorted(TYPES))}")
        if nid in node_ids:
            fail(f"duplicate node id '{nid}'")
        node_ids.add(nid)
        nodes.append({"id": nid, "name": str(n.get("name") or nid), "type": t})

    ext_ids = set()
    for x in data.get("externals", []):
        xid = str(x.get("id", "")).strip()
        if not xid:
            fail("every external needs an 'id'")
        side = str(x.get("side", "left")).strip().lower()
        if side not in ("left", "right"):
            fail(f"external '{xid}': side must be 'left' or 'right'")
        if xid in ext_ids or xid in node_ids:
            fail(f"duplicate external id '{xid}'")
        ext_ids.add(xid)
        externals.append({"id": xid, "name": str(x.get("name") or xid),
                          "description": str(x.get("description") or ""), "side": side})

    known = node_ids | ext_ids
    seen = set()
    for e in data.get("edges", []):
        frm, to = str(e.get("from", "")).strip(), str(e.get("to", "")).strip()
        if frm not in known:
            fail(f"edge '{frm} -> {to}': unknown source id '{frm}'")
        if to not in known:
            fail(f"edge '{frm} -> {to}': unknown target id '{to}'")
        if frm == to:
            fail(f"edge '{frm}' -> itself is not allowed")
        key = (frm, to)
        if key in seen:
            fail(f"duplicate edge '{frm} -> {to}'")
        seen.add(key)
        edges.append({"from": frm, "to": to})

    if not nodes:
        fail("model has no nodes")
    return {"title": title, "nodes": nodes, "edges": edges, "externals": externals}


def load_ignore_set(ignore_path):
    """Read the ignore-resources.txt list into a normalized set."""
    ignored = set()
    if ignore_path:
        try:
            with open(ignore_path) as f:
                for line in f:
                    line = line.strip().lower()
                    if line:
                        ignored.add(line)
        except OSError:
            pass
    return ignored


def prune_non_architectural(model, ignore_path):
    """Remove AWS nodes that are DLQs, failure/redrive queues, test scaffolding,
    or alerting/alarm resources — even if a hand-authored model included them.

    Model node ids use dash form (e.g. `aws-sqs-queue-order-ingest-dlq`); markers
    and ignore entries are underscore form (`_dlq`), so match against a normalized
    underscore rendering of each id. Returns (pruned_model, pruned_ids)."""
    ignored = load_ignore_set(ignore_path)

    def is_plumbing(nid):
        n = nid.lower().replace("-", "_")
        if any(m in n for m in DLQ_MARKERS):
            return True
        n_norm = n.replace(" ", "_")
        return any(ig and (ig in n or ig in n_norm or n_norm.endswith(ig)) for ig in ignored)

    pruned = [n["id"] for n in model["nodes"] if is_plumbing(n["id"])]
    if not pruned:
        return model, []

    keep = {n["id"] for n in model["nodes"]} - set(pruned)
    ext_ids = {x["id"] for x in model.get("externals", [])}
    return {
        "title": model["title"],
        "nodes": [n for n in model["nodes"] if n["id"] in keep],
        "edges": [e for e in model["edges"] if (e["from"] in keep or e["from"] in ext_ids) and (e["to"] in keep or e["to"] in ext_ids)],
        "externals": model["externals"],
    }, pruned


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def bbox_of(x, y):
    return (x, y, x + ICON_SIZE, y + ICON_SIZE)


def segments_cross_bbox(segments, bb):
    x0, y0, x1, y1 = bb
    for (ax, ay, bx, by) in segments:
        if ax == bx:  # vertical
            if x0 < ax < x1:
                if min(ay, by) < y1 and max(ay, by) > y0:
                    return True
        elif ay == by:  # horizontal
            if y0 < ay < y1:
                if min(ax, bx) < x1 and max(ax, bx) > x0:
                    return True
    return False


def edge_segments(src, tgt, wps):
    """Return the orthogonal polyline segments for an edge."""
    sx, sy = src["x"], src["y"]
    tx, ty = tgt["x"], tgt["y"]
    pts = [(sx + ICON_SIZE, sy + src["exitY"] * ICON_SIZE)]
    for (wx, wy) in wps:
        pts.append((wx, wy))
    pts.append((tx, ty + tgt["entryY"] * ICON_SIZE))
    segs = []
    for i in range(len(pts) - 1):
        segs.append((pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]))
    return segs


def layout(model):
    """Compute x/y for every node and external; assign exitY/entryY per edge."""
    nodes = {n["id"]: n for n in model["nodes"]}
    ext = {x["id"]: x for x in model["externals"]}
    aws_ids = set(nodes)
    edges = model["edges"]

    # ---- adjacency over AWS nodes only ----
    incoming = {n: [] for n in aws_ids}
    outgoing = {n: [] for n in aws_ids}
    for e in edges:
        if e["from"] in aws_ids and e["to"] in aws_ids:
            outgoing[e["from"]].append(e["to"])
            incoming[e["to"]].append(e["from"])

    # ---- cycle detection: a cycle would make longest-path depth grow
    # forever; find and report it instead of looping infinitely. ----
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in aws_ids}
    cycle = []

    def visit(n, path):
        color[n] = GRAY
        path.append(n)
        for m in outgoing[n]:
            if color[m] == GRAY:
                start = path.index(m)
                cycle.extend(path[start:] + [m])
                return True
            if color[m] == WHITE and visit(m, path):
                return True
        path.pop()
        color[n] = BLACK
        return False

    for n in aws_ids:
        if color[n] == WHITE and visit(n, []):
            break
    if cycle:
        fail("cycle detected in AWS edges: " + " -> ".join(cycle) +
             "\nA cycle (e.g. a hallucinated DDB stream edge like "
             "'ddb-x -> lambda-y' that should be 'lambda-y -> ddb-x') makes the "
             "layout unsolvable. Fix the model edges before re-rendering.")

    # ---- columns: longest path depth from sources ----
    depth = {n: 1 for n in aws_ids}
    changed = True
    while changed:
        changed = False
        for n in aws_ids:
            for src in incoming[n]:
                if depth[src] + 1 > depth[n]:
                    depth[n] = depth[src] + 1
                    changed = True

    # ---- shared resources: AWS nodes with >= 2 incoming AWS edges ----
    shared = {n for n in aws_ids if len(incoming[n]) >= 2}

    # promote output nodes (no AWS consumers) to the rightmost column,
    # EXCEPT shared resources (multi-writer storage/sinks) which keep their
    # natural rightmost-writer column.
    max_depth = max(depth.values())
    for n in aws_ids:
        if not outgoing[n] and n not in shared:
            depth[n] = max(depth[n], max_depth)

    for n in aws_ids:
        nodes[n]["col"] = depth[n]
        nodes[n]["x"] = depth[n] * COL_STEP

    # ---- chain decomposition ----
    def walk_chain(start):
        chain = [start]
        visited.add(start)
        cur = start
        while True:
            outs = outgoing[cur]
            if len(outs) != 1:
                break
            nxt = outs[0]
            if nxt in shared or nxt in visited:
                break
            chain.append(nxt)
            visited.add(nxt)
            cur = nxt
        return chain

    visited = set()
    chains = []

    def walk_chain(start):
        chain = [start]
        visited.add(start)
        cur = start
        while True:
            outs = outgoing[cur]
            if len(outs) != 1:
                break
            nxt = outs[0]
            if nxt in shared or nxt in visited:
                break
            chain.append(nxt)
            visited.add(nxt)
            cur = nxt
        return chain

    # 1) source chains (no incoming AWS), in input order
    for n in nodes:
        if n not in shared and not incoming[n]:
            chains.append(walk_chain(n))
    # 2) continuation chains from shared resources (stream triggers)
    for s in sorted(shared, key=lambda n: depth[n]):
        for t in outgoing[s]:
            if t not in visited:
                chains.append(walk_chain(t))
    # 3) fan-out targets (nodes fed by a predecessor with >= 2 outgoing)
    for n in nodes:
        if len(outgoing[n]) >= 2:
            for t in outgoing[n]:
                if t not in visited and t not in shared:
                    chains.append(walk_chain(t))
    # 4) leftovers (shouldn't happen)
    for n in nodes:
        if n not in visited and n not in shared:
            chains.append([n])

    # ---- order chains by terminal depth, then input order ----
    def terminal_depth(chain):
        for i in range(len(chain) - 1, -1, -1):
            node = chain[i]
            for t in outgoing[node]:
                if t in shared:
                    return depth[t]
        return 10 ** 9

    idx = {n["id"]: i for i, n in enumerate(model["nodes"])}

    def chain_key(c):
        return (terminal_depth(c), idx.get(c[0], 10 ** 9))

    chains.sort(key=chain_key)

    # ---- assign chain rows ----
    row_index = 1
    for c in chains:
        for n in c:
            nodes[n]["row"] = row_index
            nodes[n]["y"] = row_index * ROW_STEP
        row_index += 1

    # ---- shared resources: row from writers (snap + collision guard) ----
    def row_taken(x, y):
        for n in nodes.values():
            if n.get("x") == x and n.get("y") == y:
                return True
        return False

    for s in sorted(shared, key=lambda n: (depth[n], n)):
        writers = [nodes[w] for w in incoming[s]]
        # Anchor the shared table at the CENTER of its direct users' rows.
        # Only resources that USE the table directly (write/put/read/delete —
        # any incoming edge) should position it. Lambdas that consume the
        # table's DDB stream are outgoing edges (they merely REACT to events
        # the table emits) and must not drag the table away from its writers.
        ws = [w["y"] for w in writers]
        candidate = (min(ws) + max(ws)) / 2
        snapped = int(round(candidate / ROW_STEP)) * ROW_STEP
        while row_taken(nodes[s]["x"], snapped):
            snapped += ROW_STEP
        nodes[s]["row"] = snapped // ROW_STEP
        nodes[s]["y"] = snapped

    # ---- stream-consumer alignment: sit continuation chains that start at a
    # shared resource (e.g. a DDB-stream-triggered lambda) on that resource's
    # row, so a stream consumer sits beside the table that feeds it — the same
    # rule that keeps tables beside their writers. Collision-guarded: if any
    # member of the chain already occupies a cell on that row, leave the chain
    # on its own row.
    chain_by_head = {}
    for c in chains:
        if c:
            chain_by_head.setdefault(c[0], c)
    for s in sorted(shared, key=lambda n: (depth[n], n)):
        sy = nodes[s]["y"]
        for t in outgoing[s]:
            c = chain_by_head.get(t)
            if not c:
                continue
            if any(row_taken(nodes[nid]["x"], sy) for nid in c):
                continue
            for nid in c:
                nodes[nid]["row"] = sy // ROW_STEP
                nodes[nid]["y"] = sy

    # ---- sink alignment: place single-producer sinks beside their producer ----
    # Without this, a sink topic (e.g. an updates topic with no consumers) is
    # chain-sorted to the very bottom of the diagram and connected by a long
    # vertical edge that crosses the whole canvas. Aligning it to its producer's
    # row keeps the edge short and the diagram compact.
    for nid in list(nodes):
        n = nodes[nid]
        if outgoing[nid]:
            continue
        ins = incoming[nid]
        if len(ins) != 1:
            continue
        prod = nodes[ins[0]]
        if prod["x"] >= n["x"]:
            continue
        cand = prod["y"]
        if row_taken(n["x"], cand):
            continue
        n["row"] = cand // ROW_STEP
        n["y"] = cand

    # ---- entry/exit fraction distribution ----
    def fractions(n):
        """n equally spaced, symmetric, non-overlapping fractions in (0,1).
        f_i = (2i+1)/(2n): equal 1/n spacing, pairs sum to 1.0."""
        return [(2 * i + 1) / (2 * n) for i in range(n)]

    def distribute(edges_list, self_y):
        """edges_list: list of (real_edge_index, other_y).
        Returns dict real_edge_index -> fraction. Fractions are equally spaced,
        symmetric about 0.5, and never overlap."""
        result = {}
        count = len(edges_list)
        if count == 0:
            return result
        same = [(i, oy) for (i, oy) in edges_list if oy == self_y]
        cross = [(i, oy) for (i, oy) in edges_list if oy != self_y]
        if same:
            # the same-row edge stays a straight horizontal line at center 0.5;
            # the cross edges are equally spaced symmetric about 0.5, avoiding 0.5.
            result[same[0][0]] = 0.5
            above = sorted([(i, oy) for (i, oy) in cross if oy < self_y],
                           key=lambda t: abs(t[1] - self_y))
            below = sorted([(i, oy) for (i, oy) in cross if oy > self_y],
                           key=lambda t: abs(t[1] - self_y))
            d = 0.5 / (max(len(above), len(below)) + 1)
            for k, (i, _) in enumerate(above):
                result[i] = 0.5 - (k + 1) * d
            for k, (i, _) in enumerate(below):
                result[i] = 0.5 + (k + 1) * d
        else:
            ordered = sorted(edges_list, key=lambda t: t[1])
            for (i, _), f in zip(ordered, fractions(count)):
                result[i] = f
        return result

    # collect per-node edge lists (AWS-to-AWS)
    aws_edge_in = {n: [] for n in aws_ids}
    aws_edge_out = {n: [] for n in aws_ids}
    for i, e in enumerate(edges):
        if e["from"] in aws_ids and e["to"] in aws_ids:
            aws_edge_out[e["from"]].append(i)
            aws_edge_in[e["to"]].append(i)

    edge_fracs = {}
    for n in aws_ids:
        node = nodes[n]
        out_i = aws_edge_out[n]
        if out_i:
            res = distribute([(i, nodes[edges[i]["to"]]["y"]) for i in out_i],
                             node["y"])
            for i, f in res.items():
                edge_fracs.setdefault(i, {})["exitY"] = f
        in_i = aws_edge_in[n]
        if in_i:
            res = distribute([(i, nodes[edges[i]["from"]]["y"]) for i in in_i],
                             node["y"])
            for i, f in res.items():
                edge_fracs.setdefault(i, {})["entryY"] = f

    # ---- external box geometry ----
    for x in ext.values():
        touched = []
        for e in edges:
            if e["from"] == x["id"]:
                touched.append(nodes[e["to"]])
            elif e["to"] == x["id"]:
                touched.append(nodes[e["from"]])
        if not touched:
            fail(f"external '{x['id']}' has no connected edges")
        ys = [t["y"] for t in touched]
        first, last = min(ys), max(ys)
        x["y"] = first - 40
        x["h"] = (last - first) + 160
        x["w"] = 160
        x["x"] = 0 if x["side"] == "left" else max(n["x"] for n in nodes.values()) + 160

    # ---- per-edge exitY/entryY + waypoints ----
    # Compute exitY/entryY fractions first (needed for routing-column overlap).
    edge_exit_pix = {}
    edge_entry_pix = {}
    for i, e in enumerate(edges):
        src_is_aws = e["from"] in aws_ids
        tgt_is_aws = e["to"] in aws_ids
        if not (src_is_aws and tgt_is_aws):
            continue
        src, tgt = nodes[e["from"]], nodes[e["to"]]
        fracs = edge_fracs.get(i, {})
        if src["y"] == tgt["y"]:
            continue
        exit_y = fracs.get("exitY", 0.5)
        entry_y = fracs.get("entryY", 0.5)
        edge_exit_pix[i] = src["y"] + exit_y * ICON_SIZE
        edge_entry_pix[i] = tgt["y"] + entry_y * ICON_SIZE

    # Assign each cross-row edge a routing column. Edges whose vertical
    # segments overlap (same X, overlapping Y range) must get distinct
    # columns; edges whose verticals don't overlap may share a column.
    routing_col = {}
    col_verticals = {}
    for i, e in enumerate(edges):
        if i not in edge_exit_pix:
            continue
        src = nodes[e["from"]]
        base = src["x"] + ICON_SIZE + WP_MARGIN
        y0, y1 = edge_exit_pix[i], edge_entry_pix[i]
        lo, hi = min(y0, y1), max(y0, y1)
        taken = col_verticals.get(src["x"], [])
        rx = base
        while any(lo < hi2 and hi > lo2 for (x, lo2, hi2) in taken if x == rx):
            rx += WP_FANOUT_STEP
        taken.append((rx, lo, hi))
        col_verticals[src["x"]] = taken
        routing_col[i] = rx

    for i, e in enumerate(edges):
        src_is_aws = e["from"] in aws_ids
        tgt_is_aws = e["to"] in aws_ids
        src = nodes[e["from"]] if src_is_aws else ext[e["from"]]
        tgt = nodes[e["to"]] if tgt_is_aws else ext[e["to"]]
        fracs = edge_fracs.get(i, {})

        if src_is_aws and tgt_is_aws:
            if src["y"] == tgt["y"]:
                e["exitY"], e["entryY"] = 0.5, 0.5
                e["waypoints"] = []
            else:
                e["exitY"] = fracs.get("exitY", 0.5)
                e["entryY"] = fracs.get("entryY", 0.5)
                rx = routing_col.get(i, src["x"] + ICON_SIZE + WP_MARGIN)
                # never push the vertical line past the target approach
                rx = min(rx, tgt["x"] - WP_MARGIN - 10)
                e["waypoints"] = [(rx, src["y"] + e["exitY"] * ICON_SIZE),
                                  (tgt["x"] - WP_MARGIN, tgt["y"] + e["entryY"] * ICON_SIZE)]
        elif not src_is_aws and tgt_is_aws:
            # left external -> AWS: horizontal at target center
            e["entryY"] = 0.5
            e["exitY"] = (tgt["y"] + ICON_SIZE / 2 - src["y"]) / src["h"]
            e["waypoints"] = []
        else:
            # AWS -> right external: horizontal at source center
            e["exitY"] = 0.5
            e["entryY"] = (src["y"] + ICON_SIZE / 2 - tgt["y"]) / tgt["h"]
            e["waypoints"] = []
        e["color"] = arrow_color(src, tgt)
        e["src"], e["tgt"] = src, tgt

    return nodes, ext, edges


def arrow_color(src, tgt):
    src_aws = "type" in src
    tgt_aws = "type" in tgt
    if not src_aws or not tgt_aws:
        return None  # external edges: no strokeColor
    if src["type"] == "lambda":
        return TYPES[tgt["type"]]["color"]
    if tgt["type"] == "lambda":
        return TYPES[src["type"]]["color"]
    return TYPES[src["type"]]["color"]


# ---------------------------------------------------------------------------
# XML generation
# ---------------------------------------------------------------------------

def esc_text(s):
    return escape(str(s), {'"': "&quot;"})


def label_html(name, label):
    return f"&lt;b&gt;{esc_text(name)}&lt;/b&gt;&lt;div&gt;{esc_text(label)}&lt;/div&gt;"


def icon_style(n):
    info = TYPES[n["type"]]
    if n["type"] == "dynamodb":
        return DDB_STYLE
    return BASE_ICON_STYLE.format(icon=info["icon"], color=info["color"])


def edge_style(e):
    parts = [EDGE_BASE]
    if e["color"]:
        parts.append(f"strokeColor=light-dark({e['color'].lower()}, #ededed)")
    parts.append(f"exitX=1;exitY={e['exitY']}")
    parts.append(f"entryX=0;entryY={e['entryY']}")
    return ";".join(parts)


def edge_geometry(e):
    if not e["waypoints"]:
        return '<mxGeometry relative="1" as="geometry" />'
    pts = "".join(f'<mxPoint x="{int(wx)}" y="{int(wy)}" />' for wx, wy in e["waypoints"])
    return ('<mxGeometry relative="1" as="geometry">'
            f'<Array as="points">{pts}</Array>'
            "</mxGeometry>")


def generate_xml(model, nodes, ext, edges):
    rightmost = max(n["x"] for n in nodes.values())
    lowest = max(n["y"] for n in nodes.values())
    page_w = rightmost + 320
    page_h = lowest + 320
    title_w = max(page_w, 800)

    cells = []

    def add_cell(cell_xml):
        cells.append(cell_xml)

    # 1. title
    add_cell(
        f'<mxCell id="title" value="&lt;font style=&quot;font-size: 24px;&quot;&gt;'
        f'{esc_text(model["title"])}&lt;/font&gt;" '
        f'style="text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;'
        f'whiteSpace=wrap;rounded=0;fontSize=18;fontStyle=1;fontColor=#232F3E;strokeWidth=1;" '
        f'vertex="1" parent="1"><mxGeometry x="0" y="0" width="{int(title_w)}" height="40" as="geometry" /></mxCell>'
    )

    # 2. DynamoDB nodes
    for n in model["nodes"]:
        if n["type"] == "dynamodb":
            add_cell(node_cell(n))
    # 3. messaging nodes (SQS/SNS/EventBridge)
    for n in model["nodes"]:
        if n["type"] in ("sqs", "sns", "eventbridge"):
            add_cell(node_cell(n))
    # 4. edges
    for e in edges:
        add_cell(
            f'<mxCell id="edge-{esc_text(e["from"])}-{esc_text(e["to"])}" value="" '
            f'style="{edge_style(e)}" edge="1" source="{esc_text(e["from"])}" target="{esc_text(e["to"])}" '
            f'parent="1">{edge_geometry(e)}</mxCell>'
        )
    # 5. external boxes
    for x in ext.values():
        add_cell(
            f'<mxCell id="{esc_text(x["id"])}" value="{label_html(x["name"], x["description"])}" '
            f'style="{EXTERNAL_STYLE}" vertex="1" parent="1">'
            f'<mxGeometry x="{int(x["x"])}" y="{int(x["y"])}" width="{int(x["w"])}" height="{int(x["h"])}" as="geometry" />'
            f"</mxCell>"
        )
    # 6. Lambda nodes (front)
    for n in model["nodes"]:
        if n["type"] == "lambda":
            add_cell(node_cell(n))

    body = "\n        ".join(cells)
    return (
        '<mxfile host="Electron" modified="2026-01-01T00:00:00.000Z" agent="pi" version="24.0.0" type="device">\n'
        f'  <diagram name="Page-1" id="ARCHITECTURE">\n'
        f'    <mxGraphModel dx="0" dy="0" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" '
        f'arrows="1" fold="1" page="1" pageScale="1" pageWidth="{int(page_w)}" pageHeight="{int(page_h)}" '
        f'background="light-dark(#FFFFFF,#FFFFFF)" math="0" shadow="1">\n'
        f"      <root>\n"
        f'        <mxCell id="0" />\n'
        f'        <mxCell id="1" parent="0" />\n'
        f"        {body}\n"
        f"      </root>\n"
        f"    </mxGraphModel>\n"
        f"  </diagram>\n"
        f"</mxfile>\n"
    )


def node_cell(n):
    return (
        f'<mxCell id="{esc_text(n["id"])}" value="{label_html(n["name"], TYPES[n["type"]]["label"])}" '
        f'style="{icon_style(n)}" vertex="1" parent="1">'
        f'<mxGeometry x="{int(n["x"])}" y="{int(n["y"])}" width="80" height="80" as="geometry" />'
        f"</mxCell>"
    )


# ---------------------------------------------------------------------------
# Validation (the pre-save checklist, automated)
# ---------------------------------------------------------------------------

def validate_drawio(xml_text):
    errors = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        return [f"XML not well-formed: {e}"]

    if not xml_text.rstrip().endswith("</mxfile>"):
        errors.append("file must end with </mxfile>")
    for tag in ("</root>", "</mxGraphModel>", "</diagram>"):
        if tag not in xml_text:
            errors.append(f"missing closing tag {tag}")

    # label escaping: no double-escaped entities
    if "&amp;lt;" in xml_text or "&amp;gt;" in xml_text or "&amp;quot;" in xml_text:
        errors.append("double-escaped label entities found (&amp;lt;/&amp;gt;/&amp;quot;)")

    ns = {"mx": "http://www.w3.org/2000/svg"}  # not used; we walk raw elements
    cells = []
    for el in root.iter():
        if el.tag == "mxCell":
            cells.append(el)

    vertices, edges = [], []
    for el in cells:
        if el.get("edge") == "1":
            edges.append(el)
        elif el.get("vertex") == "1":
            vertices.append(el)

    icon_boxes = {}
    for el in vertices:
        nid = el.get("id")
        style = el.get("style", "")
        geom = el.find("mxGeometry")
        if geom is None:
            continue
        x = float(geom.get("x", 0))
        y = float(geom.get("y", 0))
        w = float(geom.get("width", 80))
        h = float(geom.get("height", 80))
        is_external = "rounded=1" in style and "mxgraph" not in style
        if nid == "title":
            continue
        # grid checks for AWS icons
        if not is_external:
            if x % COL_STEP != 0:
                errors.append(f"icon '{nid}' x={x} is not on the 240-column grid")
            if x % GRID != 0 or y % GRID != 0:
                errors.append(f"icon '{nid}' coords ({x},{y}) not multiples of 10")
            if y % ROW_STEP != 0:
                errors.append(f"icon '{nid}' y={y} is not on the 160-row grid")
            if "strokeColor=#ffffff" not in style:
                errors.append(f"icon '{nid}' missing strokeColor=#ffffff")
            if "resourceIcon" not in style and "dynamodb_standard_access_table_class" not in style:
                errors.append(f"icon '{nid}' missing resourceIcon shape")
            icon_boxes[nid] = (x, y, w, h)
        else:
            if x not in (-80,) and x % GRID != 0:
                errors.append(f"external '{nid}' x={x} off-grid")
            icon_boxes[nid] = (x, y, w, h)

    # no two icons share (x, y)
    pos = {}
    for el in vertices:
        nid = el.get("id")
        if nid == "title":
            continue
        geom = el.find("mxGeometry")
        key = (float(geom.get("x")), float(geom.get("y")))
        if key in pos:
            errors.append(f"icons '{pos[key]}' and '{nid}' share position {key}")
        pos[key] = nid

    # edges
    for el in edges:
        eid = el.get("id")
        src, tgt = el.get("source"), el.get("target")
        style = el.get("style", "")
        if src not in icon_boxes or tgt not in icon_boxes:
            errors.append(f"edge '{eid}' references unknown endpoints")
            continue
        sx, sy, sw, sh = icon_boxes[src]
        tx, ty, tw, th = icon_boxes[tgt]
        if sx > tx:
            errors.append(f"edge '{eid}' flows right-to-left ({src} x={sx} > {tgt} x={tx})")
        if "exitX=1" not in style:
            errors.append(f"edge '{eid}' missing exitX=1")
        if "entryX=0" not in style:
            errors.append(f"edge '{eid}' missing entryX=0")
        if "exitY=" not in style or "entryY=" not in style:
            errors.append(f"edge '{eid}' missing exitY/entryY")
        if "endArrow=classic" not in style:
            errors.append(f"edge '{eid}' missing endArrow=classic")
        if "targetPoint" in (el.get("geometry") or "") or "sourcePoint" in (el.get("geometry") or ""):
            errors.append(f"edge '{eid}' must not use targetPoint/sourcePoint")
        geom = el.find("mxGeometry")
        has_points = geom is not None and geom.find("Array") is not None
        exit_y = parse_frac(el, "exitY")
        entry_y = parse_frac(el, "entryY")
        # horizontal edge: exit and entry pixel Y coincide
        horizontal = abs((sy + exit_y * sh) - (ty + entry_y * th)) < 1
        if horizontal and has_points:
            errors.append(f"edge '{eid}' is horizontal but has waypoints")
        if not horizontal and not has_points:
            errors.append(f"edge '{eid}' is cross-row but has no waypoints")
        if has_points:
            pts = [(float(p.get("x")), float(p.get("y"))) for p in geom.find("Array")]
            if len(pts) != 2:
                errors.append(f"edge '{eid}' has {len(pts)} waypoints (expected 2)")
            else:
                # L-shaped cross-row edge: enforce >= WP_MARGIN horizontal runs
                init_run = pts[0][0] - (sx + sw)
                fin_run = tx - pts[1][0]
                if init_run < WP_MARGIN:
                    errors.append(f"edge '{eid}' initial horizontal run is only "
                                  f"{init_run:.0f}px (min {WP_MARGIN}px)")
                if fin_run < WP_MARGIN:
                    errors.append(f"edge '{eid}' final horizontal run is only "
                                  f"{fin_run:.0f}px (min {WP_MARGIN}px)")

    # edge-icon collision check
    for el in edges:
        eid = el.get("id")
        src, tgt = el.get("source"), el.get("target")
        sx, sy, sw, sh = icon_boxes[src]
        tx, ty, tw, th = icon_boxes[tgt]
        exit_y = parse_frac(el, "exitY")
        entry_y = parse_frac(el, "entryY")
        geom = el.find("mxGeometry")
        wps = []
        if geom is not None and geom.find("Array") is not None:
            wps = [(float(p.get("x")), float(p.get("y"))) for p in geom.find("Array")]
        segs = [(sx + sw, sy + exit_y * sh, wps[0][0], wps[0][1])] if wps else []
        for i in range(len(wps) - 1):
            segs.append((wps[i][0], wps[i][1], wps[i + 1][0], wps[i + 1][1]))
        if wps:
            segs.append((wps[-1][0], wps[-1][1], tx, ty + entry_y * th))
        else:
            segs = [(sx + sw, sy + exit_y * sh, tx, ty + entry_y * th)]
        for nid, (bx, by, bw, bh) in icon_boxes.items():
            if nid in (src, tgt):
                continue
            if segments_cross_bbox(segs, (bx, by, bx + bw, by + bh)):
                errors.append(f"edge '{eid}' passes through icon '{nid}'")

    return errors


def parse_frac(el, attr):
    style = el.get("style", "")
    for part in style.split(";"):
        if part.startswith(attr + "="):
            try:
                return float(part.split("=", 1)[1])
            except ValueError:
                return 0.5
    return 0.5


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

# map terraform resource addresses to node types
ADDRESS_TYPE = [
    ("aws_lambda_function", "lambda"),
    ("aws_sqs_queue", "sqs"),
    ("aws_sns_topic", "sns"),
    ("aws_dynamodb_table", "dynamodb"),
    ("aws_cloudwatch_event_rule", "eventbridge"),
    ("aws_sfn_", "stepfunctions"),
    ("aws_apigatewayv2_", "apigateway"),
    ("aws_api_gateway_", "apigateway"),
    ("aws_s3_", "s3"),
    ("aws_kinesis_", "kinesis"),
    ("aws_ecs_", "ecs"),
    ("aws_eks_", "eks"),
    ("aws_aurora_", "aurora"),
    ("aws_rds_", "rds"),
    ("aws_sagemaker_", "sagemaker"),
    ("aws_bedrock_", "bedrock"),
    ("aws_cognito_", "cognito"),
    ("aws_cloudfront_", "cloudfront"),
    ("aws_route53_", "route53"),
    ("aws_ssm_", "secretsmanager"),
    ("aws_secretsmanager_", "secretsmanager"),
]

# terraform addresses whose nodes are never rendered
IGNORED_PREFIX = (
    "aws_iam_", "aws_kms_", "aws_cloudwatch_", "aws_sns_topic_subscription",
    "aws_sqs_queue_policy", "aws_lambda_event_source_mapping", "aws_lambda_permission",
    "aws_ssm_parameter", "module.", "aws_cloudwatch_event_target", "data.",
)
# Substrings that mark a resource as non-architectural plumbing (never rendered):
# DLQs, failure/redrive queues, smoke/fake test scaffolding, and alerting/
# notification topics/alarms. Keep the underscore forms so they match Terraform
# addresses like `aws_sqs_queue.order_ingest_dlq` or `aws_sns_topic.inventory_alerts`.
DLQ_MARKERS = (
    "_dlq", "_failures", "smoke_", "fake_",
    "_alerts", "_alert", "_alarm", "notification",
)


def short_addr(addr):
    """Stable short node id from a terraform resource address."""
    return addr.replace(".", "-").replace("_", "-")


def infer_type(address):
    for prefix, t in ADDRESS_TYPE:
        if address.startswith(prefix):
            return t
    return None


def read_trigger_edges(graph_path):
    """Extract authoritative DDB-stream and SQS trigger edges from
    graphify-out/graph.json.

    Each `aws_lambda_event_source_mapping.<name>` node has `references`
    edges to its source (a DynamoDB table for stream triggers, or an SQS
    queue) and to the Lambda it invokes. This is the authoritative source
    for DDB→Lambda stream edges — resources.json omits it.

    Returns (edges, stream_triggers) where edges is a list of
    (from_addr, to_addr, kind) tuples (kind in {'stream','sqs'}) and
    stream_triggers is a list of "ddb-table -> lambda" strings."""
    edges = []
    stream_triggers = []
    try:
        with open(graph_path) as f:
            g = json.load(f)
    except (OSError, json.JSONDecodeError):
        return edges, stream_triggers

    nodelabel = {n["id"]: n.get("label", n.get("id", "")) for n in g.get("nodes", [])}
    links = g.get("links", [])
    by_source = {}
    for l in links:
        by_source.setdefault(l.get("source"), []).append(l)

    for n in g.get("nodes", []):
        lbl = n.get("label", "")
        if not lbl.startswith("aws_lambda_event_source_mapping."):
            continue
        refs = [nodelabel.get(l.get("target")) for l in by_source.get(n["id"], [])
                if l.get("relation") == "references"]
        refs = [r for r in refs if r]
        table = next((r for r in refs if r.startswith("aws_dynamodb_table.")), None)
        queue = next((r for r in refs if r.startswith("aws_sqs_queue.")), None)
        lamb = next((r for r in refs if r.startswith("aws_lambda_function.")), None)
        if not lamb:
            continue
        if table:
            edges.append((short_addr(table), short_addr(lamb), "stream"))
            stream_triggers.append(f"{table} -> {lamb}")
        elif queue:
            edges.append((short_addr(queue), short_addr(lamb), "sqs"))
    # dedupe
    seen = set()
    dedup = []
    for frm, tgt, kind in edges:
        if (frm, tgt) in seen:
            continue
        seen.add((frm, tgt))
        dedup.append((frm, tgt, kind))
    return dedup, stream_triggers


def read_eventbridge_edges(graph_path):
    """EventBridge schedule rules -> the Lambda functions they trigger.

    Derived from `aws_cloudwatch_event_target.*` nodes, which `references` both
    the `aws_cloudwatch_event_rule` and the target `aws_lambda_function`. This
    is why `stock_sync` must not appear as an orphan: its schedule trigger is
    real data flow and belongs in the model."""
    edges = []
    try:
        with open(graph_path) as f:
            g = json.load(f)
    except (OSError, json.JSONDecodeError):
        return edges
    nodelabel = {n["id"]: n.get("label", n.get("id", "")) for n in g.get("nodes", [])}
    links = g.get("links", [])
    by_source = {}
    for l in links:
        by_source.setdefault(l.get("source"), []).append(l)
    for n in g.get("nodes", []):
        lbl = n.get("label", "")
        if not lbl.startswith("aws_cloudwatch_event_target."):
            continue
        refs = [nodelabel.get(l.get("target")) for l in by_source.get(n["id"], [])
                if l.get("relation") == "references"]
        rule = next((r for r in refs if r.startswith("aws_cloudwatch_event_rule.")), None)
        lamb = next((r for r in refs if r.startswith("aws_lambda_function.")), None)
        if rule and lamb:
            edges.append((short_addr(rule), short_addr(lamb)))
    return list(dict.fromkeys(edges))


def read_sns_subscriptions(graph_path):
    """SNS fan-out edges + externally-fed SQS ingest queues.

    For every `aws_sns_topic_subscription.<name>` node:
      * subscribed to a local `aws_sns_topic.*` -> (sns, sqs) edge
      * subscribed to an external topic (referenced via `var.*`/`data.*`) ->
        the SQS queue is an ingest point fed from outside the account.

    The external topic itself is NOT an AWS node in this project, so it must
    not be rendered as a local `sns` node — it is represented by the upstream
    external box instead."""
    local_edges, ingest_queues = [], []
    try:
        with open(graph_path) as f:
            g = json.load(f)
    except (OSError, json.JSONDecodeError):
        return local_edges, ingest_queues
    nodelabel = {n["id"]: n.get("label", n.get("id", "")) for n in g.get("nodes", [])}
    links = g.get("links", [])
    by_source = {}
    for l in links:
        by_source.setdefault(l.get("source"), []).append(l)
    for n in g.get("nodes", []):
        lbl = n.get("label", "")
        if not lbl.startswith("aws_sns_topic_subscription."):
            continue
        refs = [nodelabel.get(l.get("target")) for l in by_source.get(n["id"], [])
                if l.get("relation") == "references"]
        queue = next((r for r in refs if r.startswith("aws_sqs_queue.")), None)
        if not queue:
            continue
        local_topic = next((r for r in refs if r.startswith("aws_sns_topic.")), None)
        if local_topic:
            local_edges.append((short_addr(local_topic), short_addr(queue)))
        elif any(r.startswith(("var.", "data.")) for r in refs):
            ingest_queues.append(short_addr(queue))
    return list(dict.fromkeys(local_edges)), list(dict.fromkeys(ingest_queues))


def read_iam_write_edges(graph_path):
    """Lambda -> DynamoDB write edges inferred from IAM policy documents.

    `data.aws_iam_policy_document.<lambda-name>` referencing an
    `aws_dynamodb_table.*` => the lambda is granted access to that table
    (a write). The source table of a DDB-stream trigger is EXCLUDED — that
    lambda reads the stream, it does not write the table (adding it would
    create a reversed edge / cycle)."""
    edges = []
    try:
        with open(graph_path) as f:
            g = json.load(f)
    except (OSError, json.JSONDecodeError):
        return edges
    nodelabel = {n["id"]: n.get("label", n.get("id", "")) for n in g.get("nodes", [])}
    links = g.get("links", [])
    by_source = {}
    for l in links:
        by_source.setdefault(l.get("source"), []).append(l)

    # DDB-stream source tables -> the lambda that reads each stream
    stream_sources = set()
    for n in g.get("nodes", []):
        lbl = n.get("label", "")
        if not lbl.startswith("aws_lambda_event_source_mapping."):
            continue
        refs = [nodelabel.get(l.get("target")) for l in by_source.get(n["id"], [])
                if l.get("relation") == "references"]
        table = next((r for r in refs if r.startswith("aws_dynamodb_table.")), None)
        lamb = next((r for r in refs if r.startswith("aws_lambda_function.")), None)
        if table and lamb:
            stream_sources.add((table, lamb))

    for n in g.get("nodes", []):
        lbl = n.get("label", "")
        prefix = "data.aws_iam_policy_document."
        if not lbl.startswith(prefix):
            continue
        name = lbl[len(prefix):]
        lambda_name = name[:-4] if name.endswith("_sqs") else name
        lamb = f"aws_lambda_function.{lambda_name}"
        refs = [nodelabel.get(l.get("target")) for l in by_source.get(n["id"], [])
                if l.get("relation") == "references"]
        for table in (r for r in refs if r.startswith("aws_dynamodb_table.")):
            if (table, lamb) in stream_sources:
                continue
            edges.append((short_addr(lamb), short_addr(table)))
    return list(dict.fromkeys(edges))


def compute_authoritative(resources_path, ignore_path=None):
    """Build the authoritative AWS node + edge inventory from graphify.

    Returns (nodes, aws_edges, ingest_queues, stream_triggers):
      nodes: list of {id, name, type} for every supported, non-ignored resource
      aws_edges: set of (from, to) AWS->AWS data-flow edges (triggers, DDB
                 streams, EventBridge rules, SNS->SQS fan-out, IAM-derived
                 Lambda->DDB writes)
      ingest_queues: ids of SQS queues subscribed to an external SNS topic
      stream_triggers: human-readable "table -> lambda" DDB stream triggers
    """
    with open(resources_path) as f:
        data = json.load(f)

    ignored = set()
    if ignore_path:
        try:
            with open(ignore_path) as f:
                for line in f:
                    line = line.strip().lower()
                    if line:
                        ignored.add(line)
        except OSError:
            pass

    def is_ignored(addr):
        al = addr.lower()
        if al.startswith("aws_cloudwatch_event_rule"):
            return False  # EventBridge schedules render as nodes
        if any(al.startswith(p) for p in IGNORED_PREFIX):
            return True
        if any(m in al for m in DLQ_MARKERS):
            return True
        # ignore-list entries may be written with spaces ("sqs dlq"); normalize to
        # underscores so they match Terraform addresses (aws_sqs_queue.order_ingest_dlq).
        al_norm = al.replace(" ", "_")
        if any(ig and (ig in al or ig in al_norm or al_norm.endswith(ig)) for ig in ignored):
            return True
        return False

    node_type = {}
    node_names = {}
    id2addr = {}
    for n in data.get("nodes", []):
        addr = n.get("address", "")
        nid = n.get("id")
        t = infer_type(addr)
        if t is None or is_ignored(addr):
            continue
        # stable short id from the resource address — the model must keep these
        nid_out = short_addr(addr)
        node_type[nid_out] = t
        node_names[nid_out] = addr.split(".")[-1]
        id2addr[nid] = nid_out

    nodes = [{"id": i, "name": node_names[i], "type": node_type[i]} for i in node_type]

    aws_edges = set()
    for e in data.get("edges", []):
        src = id2addr.get(e.get("source"))
        tgt = id2addr.get(e.get("target"))
        if not src or not tgt or src == tgt:
            continue
        aws_edges.add((src, tgt))

    graph_path = os.path.join(os.path.dirname(os.path.abspath(resources_path)),
                              "graph.json")

    # SQS->Lambda + DDB-stream triggers (event source mappings) — ground truth
    trig_edges, stream_triggers = read_trigger_edges(graph_path)
    for frm, tgt, _kind in trig_edges:
        if frm in node_type and tgt in node_type:
            aws_edges.add((frm, tgt))

    # EventBridge schedule rules -> lambda
    for frm, tgt in read_eventbridge_edges(graph_path):
        if frm in node_type and tgt in node_type:
            aws_edges.add((frm, tgt))

    # SNS -> SQS fan-out for local topics
    local_sns_edges, ingest_queues = read_sns_subscriptions(graph_path)
    for frm, tgt in local_sns_edges:
        if frm in node_type and tgt in node_type:
            aws_edges.add((frm, tgt))
    # only queues that survived filtering (no DLQ/test scaffolding) are ingest
    ingest_queues = [q for q in ingest_queues if q in node_type]

    # Lambda -> DDB writes from IAM policy documents
    for frm, tgt in read_iam_write_edges(graph_path):
        if frm in node_type and tgt in node_type:
            aws_edges.add((frm, tgt))

    return nodes, aws_edges, ingest_queues, stream_triggers


def discover(resources_path, ignore_path=None):
    """Build a draft model from graphify-out/resources.json + graph.json.

    Every node id and every AWS->AWS edge in the draft is authoritative ground
    truth (triggers, DDB streams, EventBridge rules, SNS->SQS fan-out, and
    IAM-derived Lambda->DDB writes). Queues subscribed to an external SNS topic
    get an auto-derived `ext-upstream` external so ingest entry points are never
    left dangling. The model may only rename/describe externals, add downstream
    externals + their boundary edges, and set the title."""
    nodes, aws_edges, ingest_queues, stream_triggers = compute_authoritative(
        resources_path, ignore_path)

    edges = [{"from": f, "to": t} for f, t in sorted(aws_edges)]

    externals = []
    if ingest_queues:
        externals.append({
            "id": "ext-upstream",
            "name": "Upstream SNS publisher",
            "description": "External system publishing to SQS ingest queues "
                           "(auto-derived from SNS subscriptions — rename to the "
                           "real publisher, e.g. adapter)",
            "side": "left",
        })
        for q in sorted(ingest_queues):
            edges.append({"from": "ext-upstream", "to": q})

    with open(resources_path) as f:
        data = json.load(f)

    draft = {
        "title": str(data.get("title") or "Architecture"),
        "nodes": nodes,
        "edges": edges,
        "externals": externals,
        "_draft": True,
        "_note": "Draft from resources.json + graph.json. Node ids are the "
                 "authoritative short ids — KEEP them verbatim. AWS->AWS edges "
                 "(triggers, DDB streams, EventBridge rules, SNS->SQS fan-out, "
                 "IAM-derived Lambda->DDB writes) are ground truth: do NOT remove, "
                 "re-target, or invent any. Only: set the title, rename/describe "
                 "externals, add downstream externals + their boundary edges. Do "
                 "NOT add or replace AWS nodes or AWS->AWS edges. Remove this note.",
        "_stream_triggers": stream_triggers,
    }
    return draft


def model_warnings(model):
    """Heuristic sanity checks on the model that flag likely LLM errors
    (wrong tables, reversed streams, missing edges). Returns a list of
    human-readable warnings; render.py continues regardless."""
    warns = []
    nodes = {n["id"]: n for n in model["nodes"]}
    aws = set(nodes)
    ext = {x["id"] for x in model["externals"]}
    incoming = {n: [] for n in aws}
    outgoing = {n: [] for n in aws}
    for e in model["edges"]:
        if e["from"] in aws and e["to"] in aws:
            outgoing[e["from"]].append(e["to"])
            incoming[e["to"]].append(e["from"])

    for nid, n in nodes.items():
        t = n["type"]
        if t == "dynamodb":
            if not incoming[nid]:
                warns.append(f"DynamoDB '{nid}' has no incoming edges — it should "
                             "be written by at least one Lambda. VERIFY the real "
                             "Lambda→DDB write edges via a graphify query before "
                             "adding them; do not guess.")
            elif not outgoing[nid]:
                # written but nothing reads/streams it — a pure sink is fine,
                # but a missing DDB stream → Lambda edge is the common error
                warns.append(f"DynamoDB '{nid}' is written but has no outgoing "
                             "edges. VERIFY whether it has a DDB stream trigger "
                             "by checking aws_lambda_event_source_mapping in "
                             "graphify BEFORE adding a DDB→Lambda edge — do not "
                             "infer one. If it is a pure sink (no stream), this "
                             "warning can be ignored.")
        elif not incoming[nid] and not outgoing[nid]:
            warns.append(f"node '{nid}' ({t}) has zero edges (orphan)")
    return warns


def validate_model_against_graph(model, resources_path, ignore_path=None):
    """Diff the model's AWS nodes/edges against graphify ground truth.

    Returns (errors, warns). A hard error means: a fabricated AWS node (an id
    that is not a graphify resource), an AWS->AWS edge graphify does not
    support, or a missing authoritative edge between two nodes the model
    already includes. Warnings are review points for external-boundary edges.
    """
    auth_nodes, auth_edges, ingest_queues, _ = compute_authoritative(
        resources_path, ignore_path)
    auth_node_ids = {n["id"] for n in auth_nodes}
    errors, warns = [], []

    model_ids = {n["id"] for n in model["nodes"]}
    ext_ids = {x["id"] for x in model["externals"]}

    for nid in sorted(model_ids - auth_node_ids):
        errors.append(f"node '{nid}' is not a graphify resource (fabricated). "
                      f"Only use ids from the --discover draft.")

    model_aws_edges = set()
    for e in model["edges"]:
        frm, to = e["from"], e["to"]
        if frm in model_ids and to in model_ids:
            model_aws_edges.add((frm, to))

    for frm, to in sorted(model_aws_edges - auth_edges):
        errors.append(f"edge '{frm} -> {to}' has no graphify support. "
                      f"Check the real data flow — the discover draft is ground "
                      f"truth (triggers, EventBridge rules, SNS->SQS fan-out, "
                      f"IAM-derived Lambda->DDB writes).")

    for frm, to in sorted(auth_edges):
        if frm in model_ids and to in model_ids and (frm, to) not in model_aws_edges:
            errors.append(f"missing authoritative edge '{frm} -> {to}' — graphify "
                          f"shows this connection between two nodes you included; "
                          f"add it to the model.")

    for e in model["edges"]:
        frm, to = e["from"], e["to"]
        if frm in ext_ids and to in model_ids and to not in ingest_queues:
            warns.append(f"external '{frm}' -> '{to}': '{to}' is not an "
                         f"externally-fed SQS ingest queue — verify this boundary edge.")
    return errors, warns


def validate_model_against_tf(model, draft):
    """Diff the model against the terraform-derived ground-truth draft.

    Hard errors: a fabricated AWS node, an AWS->AWS edge terraform does not
    support, a missing authoritative edge, a node name/type that does not match
    the terraform-derived name/type, or an external id that is not referenced by
    terraform. Boundary edges (external <-> node) that differ are warnings.
    """
    errors, warns = [], []
    auth_node_ids = {n["id"] for n in draft["nodes"]}
    auth_names = {n["id"]: n["name"] for n in draft["nodes"]}
    auth_types = {n["id"]: n["type"] for n in draft["nodes"]}
    ext_ids = {x["id"] for x in draft["externals"]}
    auth_edges = {(e["from"], e["to"]) for e in draft["edges"]}

    model_ids = {n["id"] for n in model["nodes"]}
    model_ext_ids = {x["id"] for x in model["externals"]}

    for nid in sorted(model_ids - auth_node_ids - ext_ids):
        errors.append(f"node '{nid}' is not a terraform resource (fabricated). "
                      f"Only use ids from `--discover-tf`.")
    for n in model["nodes"]:
        if n["id"] in auth_names:
            if n["name"] != auth_names[n["id"]]:
                errors.append(f"node '{n['id']}': name '{n['name']}' does not match "
                              f"the terraform-derived name '{auth_names[n['id']]}'.")
            if n["type"] != auth_types[n["id"]]:
                errors.append(f"node '{n['id']}': type '{n['type']}' should be "
                              f"'{auth_types[n['id']]}'.")
    for x in model["externals"]:
        if x["id"] not in ext_ids:
            errors.append(f"external '{x['id']}' is not referenced by terraform "
                          f"(`--discover-tf` ground truth).")
    for eid in sorted(ext_ids - model_ext_ids):
        warns.append(f"external '{eid}' exists in terraform ground truth but is "
                     f"not in the model — add it, or merge it into a box only if "
                     f"it represents the same external system.")

    model_aws = {(e["from"], e["to"]) for e in model["edges"]
                 if e["from"] in model_ids and e["to"] in model_ids}
    model_ext_edges = {(e["from"], e["to"]) for e in model["edges"]
                       if e["from"] in ext_ids or e["to"] in ext_ids}

    for frm, to in sorted(model_aws - auth_edges):
        errors.append(f"edge '{frm} -> {to}' has no terraform support. "
                      f"Check the real data flow — `--discover-tf` is ground truth.")
    for frm, to in sorted(auth_edges):
        if frm in model_ids and to in model_ids and (frm, to) not in model_aws:
            errors.append(f"missing authoritative edge '{frm} -> {to}' — terraform "
                          f"shows this connection between two nodes you included.")
    for frm, to in sorted(model_ext_edges - auth_edges):
        warns.append(f"external boundary edge '{frm} -> {to}' is not in terraform "
                     f"ground truth — verify it.")
    for frm, to in sorted(auth_edges):
        if frm in ext_ids and (frm, to) not in model_ext_edges:
            warns.append(f"missing boundary edge '{frm} -> {to}' — terraform feeds "
                         f"'{to}' from external '{frm}'.")
    return errors, warns


def find_resources(near=None):
    """Locate graphify-out/resources.json for ground-truth validation.

    Tries the obvious spots first, then a shallow recursive scan so a graphify
    run rooted in a subfolder (e.g. `deploy/graphify-out/resources.json`) is
    still found instead of silently skipping validation."""
    base = os.path.dirname(os.path.abspath(near)) if near else os.getcwd()
    cands = [
        os.path.join(base, "graphify-out", "resources.json"),
        os.path.join(base, "resources.json"),
        os.path.join(os.getcwd(), "graphify-out", "resources.json"),
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    root = os.getcwd()
    for dirpath, dirnames, filenames in os.walk(root):
        # prune heavy/irrelevant trees
        dirnames[:] = [d for d in dirnames
                       if d not in ("node_modules", ".git", "bin", "obj",
                                    "cache", "__pycache__", ".serverless")]
        if os.path.basename(dirpath) == "graphify-out" and "resources.json" in filenames:
            return os.path.join(dirpath, "resources.json")
    return None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    base = os.path.dirname(os.path.abspath(__file__))
    ignore_path = os.path.join(base, "..", "references", "ignore-resources.txt")

    if sys.argv[1] == "--discover":
        resources_path = sys.argv[2] if len(sys.argv) > 2 else "graphify-out/resources.json"
        draft = discover(resources_path, ignore_path)
        stream_triggers = draft.pop("_stream_triggers", [])
        draft.pop("_draft", None)
        print(json.dumps(draft, indent=2))
        if stream_triggers:
            print("\n# Confirmed DDB stream triggers (from graph.json):")
            for s in stream_triggers:
                print(f"#   {s}")
        return

    if sys.argv[1] == "--discover-tf":
        from tf_parser import discover as tf_discover
        deploy_dir = sys.argv[2] if len(sys.argv) > 2 else "deploy"
        draft, notes = tf_discover(deploy_dir)
        draft["title"] = "Architecture"
        print(json.dumps(draft, indent=2))
        if notes["evidence"]:
            print("\n# TF ground-truth evidence (kind @ file:line):")
            for k, v in notes["evidence"].items():
                print(f"#   {k}  [{v}]")
        if notes["pruned"]:
            print("\n# Pruned (DLQ/test/alert/IAM plumbing):")
            for p in notes["pruned"]:
                print(f"#   {p}")
        return

    path = sys.argv[1]
    flags = sys.argv[2:]
    check_only = "--check" in flags
    out = None
    if "--out" in flags:
        out = flags[flags.index("--out") + 1]

    if path.endswith(".drawio") and check_only:
        with open(path) as f:
            xml_text = f.read()
        errors = validate_drawio(xml_text)
        if errors:
            for e in errors:
                print(f"  [FAIL] {e}")
            sys.exit(1)
        print(f"OK: {path} passes all checks")
        return

    model = load_model(path)

    model, pruned = prune_non_architectural(model, ignore_path)
    if pruned:
        print("Pruned non-architectural nodes (DLQ/alert/test scaffolding):")
        for pid in pruned:
            print(f"  [PRUNED] {pid}")

    resources_path = None
    if "--graph" in flags:
        resources_path = flags[flags.index("--graph") + 1]
    else:
        resources_path = find_resources(path)
    tf_path = None
    if "--tf" in flags:
        tf_path = flags[flags.index("--tf") + 1]
    gv_errors, gv_warns = [], []
    if resources_path:
        gv_errors, gv_warns = validate_model_against_graph(
            model, resources_path, ignore_path)
        if gv_errors:
            print("Model does not match graphify ground truth:")
            for e in gv_errors:
                print(f"  [FAIL] {e}")
            sys.exit(1)
    elif tf_path:
        from tf_parser import discover as tf_discover
        tf_draft, _notes = tf_discover(tf_path)
        gv_errors, gv_warns = validate_model_against_tf(model, tf_draft)
        if gv_errors:
            print("Model does not match terraform ground truth:")
            for e in gv_errors:
                print(f"  [FAIL] {e}")
            sys.exit(1)
    else:
        print("UNVERIFIED: no ground truth available (no graphify-out/resources.json "
              "and no --tf <deploy-dir>). Refusing to render an unverified diagram.", file=sys.stderr)
        sys.exit(3)

    warns = model_warnings(model)
    nodes, ext, edges = layout(model)
    xml_text = generate_xml(model, nodes, ext, edges)

    errors = validate_drawio(xml_text)
    if errors:
        for e in errors:
            print(f"  [FAIL] {e}")
        sys.exit(1)

    if warns or gv_warns:
        print("Warnings (review these — may indicate a model error):")
        for w in warns:
            print(f"  [WARN] {w}")
        for w in gv_warns:
            print(f"  [WARN] {w}")

    if check_only:
        print("OK: model renders cleanly (no errors)")
        return

    if not out:
        fail("use --out <file.drawio>")
    with open(out, "w") as f:
        f.write(xml_text)
    print(f"Diagram saved: {out}")
    print(f"  {len(model['nodes'])} AWS nodes, {len(model['externals'])} externals, {len(model['edges'])} edges")
    print("  All layout + validation checks passed.")


if __name__ == "__main__":
    main()
