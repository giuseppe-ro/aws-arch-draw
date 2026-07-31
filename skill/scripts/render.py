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
  python3 render.py model.json --out diagram.drawio
  python3 render.py model.json --check          # validate only
  python3 render.py diagram.drawio --check      # validate an existing file
  python3 render.py --discover resources.json   # draft model from graphify
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
                   "verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;"
                   "fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon={icon};fillColor={color};")
DDB_STYLE = ("sketch=0;outlineConnect=0;fontColor=#232F3E;strokeColor=#ffffff;dashed=0;"
             "verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;"
             "aspect=fixed;shape=mxgraph.aws4.dynamodb_standard_access_table_class;fillColor=#C925D1;"
             "gradientColor=none;pointerEvents=1;")
EXTERNAL_STYLE = "rounded=1;whiteSpace=wrap;html=1;fontSize=12;fontColor=#232F3E;"
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

    for s in sorted(shared, key=lambda n: depth[n]):
        writers = [nodes[w] for w in incoming[s]]
        lowest = min(w["y"] for w in writers)
        candidate = lowest + ROW_STEP
        snapped = round(candidate / ROW_STEP) * ROW_STEP
        if snapped < candidate:
            snapped += ROW_STEP
        while row_taken(nodes[s]["x"], snapped):
            snapped += ROW_STEP
        nodes[s]["row"] = snapped // ROW_STEP
        nodes[s]["y"] = snapped

    # ---- entry/exit fraction distribution ----
    frac_table = {1: [0.5], 2: [0.25, 0.75], 3: [0.25, 0.5, 0.75]}

    def distribute(edges_list, self_y):
        """edges_list: list of (real_edge_index, other_y).
        Returns dict real_edge_index -> fraction."""
        result = {}
        count = len(edges_list)
        if count == 0:
            return result
        if count > 3:
            fail("max 3 arrows per icon edge — split the fan-out")
        same = [(i, oy) for (i, oy) in edges_list if oy == self_y]
        cross = [(i, oy) for (i, oy) in edges_list if oy != self_y]
        if same:
            result[same[0][0]] = 0.5
            pool = [f for f in frac_table[count] if f != 0.5]
            below = sorted([(i, oy) for (i, oy) in cross if oy > self_y], key=lambda t: t[1])
            above = sorted([(i, oy) for (i, oy) in cross if oy < self_y], key=lambda t: -t[1])
            # above edges take low fractions, below edges take high fractions
            for (i, _) in above:
                result[i] = pool.pop(0)
            for (i, _) in below:
                result[i] = pool.pop(-1)
        else:
            ordered = sorted(edges_list, key=lambda t: t[1])
            for (i, _), f in zip(ordered, frac_table[count]):
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
        x["x"] = -80 if x["side"] == "left" else max(n["x"] for n in nodes.values()) + 160

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
    title_w = max(page_w, 2100)

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
        f'background="light-dark(#FFFFFF,#FFFFFF)" math="0" shadow="0">\n'
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
DLQ_MARKERS = ("_dlq", "_failures", "smoke_", "fake_", "_dlq")


def infer_type(address):
    for prefix, t in ADDRESS_TYPE:
        if address.startswith(prefix):
            return t
    return None


def discover(resources_path, ignore_path=None):
    """Build a draft model from graphify-out/resources.json + ignore list."""
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
        if any(al.startswith(p) for p in IGNORED_PREFIX):
            return True
        if any(m in al for m in DLQ_MARKERS):
            return True
        if any(ig and (ig in al or al.endswith(ig)) for ig in ignored):
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
        # stable short id from the resource address
        short = addr.replace(".", "-").replace("_", "-")
        nid_out = short
        node_type[nid_out] = t
        node_names[nid_out] = addr.split(".")[-1]
        id2addr[nid] = nid_out

    nodes = [{"id": i, "name": node_names[i], "type": node_type[i]} for i in node_type]
    edges = []
    seen = set()
    for e in data.get("edges", []):
        src = id2addr.get(e.get("source"))
        tgt = id2addr.get(e.get("target"))
        if not src or not tgt or src == tgt:
            continue
        if (src, tgt) in seen:
            continue
        seen.add((src, tgt))
        edges.append({"from": src, "to": tgt})

    draft = {
        "title": str(data.get("title") or "Architecture"),
        "nodes": nodes,
        "edges": edges,
        "externals": [],
        "_draft": True,
        "_note": "Draft from resources.json. Add externals + missing edges "
                 "(DDB stream triggers, Lambda->DDB writes, external boundaries) "
                 "from graphify queries, then remove this note.",
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
                warns.append(f"DynamoDB '{nid}' has no incoming edges — "
                             "it should be written by at least one Lambda (check "
                             "Lambda→DDB edges are present)")
            elif not outgoing[nid]:
                # written but nothing reads/streams it — a pure sink is fine,
                # but a missing DDB stream → Lambda edge is the common error
                warns.append(f"DynamoDB '{nid}' is written but has no outgoing "
                             "edges — OK if a pure sink; otherwise add the DDB "
                             "stream → Lambda edge")
        elif not incoming[nid] and not outgoing[nid]:
            warns.append(f"node '{nid}' ({t}) has zero edges (orphan)")
    return warns


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "--discover":
        resources_path = sys.argv[2] if len(sys.argv) > 2 else "graphify-out/resources.json"
        base = os.path.dirname(os.path.abspath(__file__))
        ignore_path = os.path.join(base, "..", "references", "ignore-resources.txt")
        draft = discover(resources_path, ignore_path)
        print(json.dumps(draft, indent=2))
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
    warns = model_warnings(model)
    nodes, ext, edges = layout(model)
    xml_text = generate_xml(model, nodes, ext, edges)

    errors = validate_drawio(xml_text)
    if errors:
        for e in errors:
            print(f"  [FAIL] {e}")
        sys.exit(1)

    if warns:
        print("Warnings (review these — may indicate a model error):")
        for w in warns:
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
