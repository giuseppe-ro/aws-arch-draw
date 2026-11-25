#!/usr/bin/env python3
"""Deterministic terraform discovery for the aws-arch-draw skill.

Parses a deploy/ directory of HCL and emits an authoritative architecture
draft: AWS nodes (id/name/type), AWS->AWS edges (with evidence), and externals
(resources referenced via `*_arn` config paths through var./local./module.).

Design notes
------------
* No `terraform` CLI required: this is a lightweight, brace-balanced HCL-lite
  parser tuned for the resource patterns that define architecture (SNS topics,
  SQS queues, Lambda functions, DynamoDB tables, event source mappings, SNS
  subscriptions, IAM policy documents, lambda env vars).
* Module instances: a module dir instantiated several times (e.g. factory_tam /
  factory_gsy / factory_alm) is expanded per instance, with node ids prefixed by
  the instance's `factory_name` argument (falls back to the instance name).
  Non-architectural module dirs (relays, test scaffolding) are used for
  reference resolution but never emit nodes.
* Externals: any ARN resolved through `var.*`/`local.*` (typically the
  per-environment config, e.g. `local.config.tamworth_consignment_sent_queue_arn`)
  becomes an external resource; upstream publishers default to the left side and
  publish targets to the right.
"""

import json
import os
import re

from render import infer_type, IGNORED_PREFIX, DLQ_MARKERS

# Module dirs whose resources are plumbing (never rendered as nodes), but which
# may still be referenced for output/ARN resolution (e.g. cross-region relays,
# smoke/fake test scaffolding).
PLUMBING_MODULE_DIRS = ("cross-region-relay", "factory-testing", "testing")

BLOCK_RE = re.compile(r"(?m)^\s*(resource|data|module|variable|output|locals)\b([^\n{]*)\{")

TOP_ATTR_RE = re.compile(r"(?m)^\s*([a-zA-Z0-9_-]+)\s*=\s*([^{}][^\n]*)$")
REF_RES_RE = re.compile(r"\b(aws_[a-z0-9_]+)\.([a-zA-Z0-9_-]+)")
REF_VAR_RE = re.compile(r"\bvar\.([a-zA-Z0-9_.\[\]-]+)")
REF_LOCAL_RE = re.compile(r"\blocal\.([a-zA-Z0-9_.\[\]-]+)")
REF_MODULE_RE = re.compile(r"\bmodule\.([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)")


# ---------------------------------------------------------------------------
# HCL-lite parsing helpers
# ---------------------------------------------------------------------------

def scan_blocks(text, path):
    """Return top-level {resource,data,module,variable,output,locals} blocks."""
    blocks = []
    n = len(text)
    for m in BLOCK_RE.finditer(text):
        kind = m.group(1)
        quoted = re.findall(r'"([^"]+)"', m.group(2))
        if kind in ("resource", "data"):
            rtype, name = quoted[0], quoted[1] if len(quoted) > 1 else None
        else:
            rtype, name = None, quoted[0] if quoted else None
        start = m.end() - 1  # position of '{'
        depth = 1
        j = start + 1
        while j < n and depth:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            j += 1
        blocks.append({
            "kind": kind,
            "rtype": rtype,
            "name": name,
            "body": text[start + 1: j - 1],
            "file": path,
            "line": text.count("\n", 0, m.start()) + 1,
        })
    return blocks


def top_attrs(body):
    """Single-line top-level `key = value` pairs (nested brace blocks excluded)."""
    attrs = {}
    for m in TOP_ATTR_RE.finditer(body):
        v = m.group(2).strip()
        if len(v) >= 2 and v.startswith('"') and v.endswith('"'):
            v = v[1:-1]
        attrs[m.group(1)] = v
    return attrs


def refs(text):
    """Collect aws_* resource refs, var/local paths and module refs in text."""
    res = {}
    for m in REF_RES_RE.finditer(text):
        res.setdefault(m.group(1), set()).add(m.group(2))
    var_paths = set(REF_VAR_RE.findall(text))
    local_paths = set(REF_LOCAL_RE.findall(text))
    module_refs = set(REF_MODULE_RE.findall(text))
    return res, var_paths, local_paths, module_refs


def env_vars(body):
    """Extract KEY = value pairs from a lambda `variables = { ... }` block."""
    out = {}
    m = re.search(r"\bvariables\s*=\s*(?:merge\s*\()?\s*\{", body)
    if not m:
        return out
    start = m.end() - 1
    depth = 1
    j = start + 1
    n = len(body)
    while j < n and depth:
        if body[j] == "{":
            depth += 1
        elif body[j] == "}":
            depth -= 1
        j += 1
    inner = body[start + 1: j - 1]
    for k, v in re.findall(r"([A-Za-z0-9_]+)\s*=\s*([^,\n]+)", inner):
        out[k.strip()] = v.strip().strip('"')
    return out


def is_plumbing(tf_type, res_name):
    addr = f"{tf_type}.{res_name}".lower()
    if addr.startswith("aws_cloudwatch_event_rule"):
        return False  # EventBridge schedules render as nodes
    if any(addr.startswith(p) for p in IGNORED_PREFIX):
        return True
    if any(m in addr for m in DLQ_MARKERS):
        return True
    return False


def external_id_for_path(path):
    """Map a config/var path to an external resource id, or None if not ARN-like."""
    k = path.split(".")[-1]
    if not k.endswith("_arn"):
        return None
    return k[:-4]


def node_id(prefix, tf_type, res_name, t):
    """Deterministic node id from module prefix + resource identity."""
    p = f"{prefix}_" if prefix else ""
    base = res_name
    if t == "sqs":
        base = res_name[:-6] if res_name.endswith("_queue") else res_name
        return f"{p}{base}_queue"
    if t == "sns":
        base = res_name[:-6] if res_name.endswith("_topic") else res_name
        return f"{p}{base}_topic"
    if t == "eventbridge":
        base = res_name[:-8] if res_name.endswith("_schedule") else res_name
        return f"{p}{base}_schedule"
    return f"{p}{res_name}"


def instance_prefix(inst, multi=False):
    fn = inst["args"].get("factory_name", "")
    if fn and not any(c in fn for c in "{}[$\".]"):
        return fn
    if multi:
        return inst["name"]
    return ""


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

class Discovery:
    def __init__(self, deploy_dir):
        self.deploy_dir = os.path.abspath(deploy_dir)
        self.nodes = {}            # id -> {id, name, type}
        self.edges = []            # {"from", "to"}
        self.edge_evidence = {}    # (from, to) -> str
        self.externals = {}        # id -> {id, name, description, side}
        self.pruned = []
        self.notes = []
        self.node_by_resource = {}  # (inst_name, rtype, rname) -> nid
        self.instances = []         # module instances
        self.inst_by_name = {}
        self.blocks_by_dir = {}

    def run(self):
        self._load()
        self._emit_nodes()
        self._derive_edges()
        self._assign_sides()
        return self._draft()

    def _load(self):
        files = []
        for root, dirs, fnames in os.walk(self.deploy_dir):
            dirs[:] = [d for d in dirs if d not in (".git", ".terraform", "node_modules")]
            for fn in sorted(fnames):
                if fn.endswith(".tf"):
                    files.append(os.path.join(root, fn))
        if not files:
            raise SystemExit(
                f"ERROR: no .tf files found under '{self.deploy_dir}'. "
                "Point --discover-tf at the directory containing the terraform root."
            )
        for fp in files:
            with open(fp, encoding="utf-8-sig", errors="replace") as f:
                text = f.read()
            blocks = scan_blocks(text, fp)
            self.blocks_by_dir.setdefault(os.path.dirname(fp), []).extend(blocks)
            for b in blocks:
                if b["kind"] != "module":
                    continue
                args = top_attrs(b["body"])
                src = args.get("source", "")
                if not (src.startswith("./") or src.startswith("../")):
                    continue
                source_dir = os.path.normpath(os.path.join(os.path.dirname(fp), src))
                inst = {"name": b["name"], "source_dir": source_dir,
                        "args": args, "file": fp,
                        "parent_dir": os.path.dirname(fp)}
                self.instances.append(inst)
                self.inst_by_name[inst["name"]] = inst

    def _emit_nodes(self):
        by_src = {}
        for inst in self.instances:
            by_src.setdefault(inst["source_dir"], []).append(inst)

        for mdir, blocks in self.blocks_by_dir.items():
            base = os.path.basename(mdir)
            root_dir = mdir == self.deploy_dir
            if root_dir:
                insts = [None]  # root resources have no prefix
            else:
                insts = by_src.get(mdir, [])
                if not insts:
                    continue
                if base in PLUMBING_MODULE_DIRS:
                    continue
            for b in blocks:
                if b["kind"] != "resource":
                    continue
                t = infer_type(b["rtype"])
                if t is None or is_plumbing(b["rtype"], b["name"]):
                    self.pruned.append(f"{b['rtype']}.{b['name']} ({b['file']}:{b['line']})")
                    continue
                for inst in insts:
                    prefix = instance_prefix(inst, len(insts) > 1) if inst else ""
                    nid = node_id(prefix, b["rtype"], b["name"], t)
                    key = (inst["name"], b["rtype"], b["name"]) if inst else (None, b["rtype"], b["name"])
                    self.node_by_resource[key] = nid
                    if nid in self.nodes:
                        continue
                    self.nodes[nid] = {"id": nid, "name": nid, "type": t}

    # ---- reference resolution ----

    def _nested_deployed(self, inst, parent):
        """True if the nested module `inst` is actually deployed under `parent`.

        Mirrors `count = var.<flag> ? 1 : 0` in the nested module block: when
        `count` is gated on a parent-module flag, a `false`/`0` value for that
        flag means the child module has zero instances under this parent, so its
        resources must not be resolved in the parent's scope."""
        count = (inst.get("args", {}).get("count") or "").strip()
        m = re.fullmatch(r"var\.([a-zA-Z0-9_]+)\s*\?\s*1\s*:\s*0", count)
        if not m:
            return True
        flag = m.group(1)
        val = (parent.get("args", {}).get(flag) or "").strip().strip('"').lower()
        return val not in ("false", "0", "", "null")

    def _parent_instances(self, inst):
        """Instances that instantiate the directory `inst`'s module block lives
        in, restricted to parents under which `inst` is deployed."""
        if not inst:
            return []
        parents = []
        for p in self.instances:
            if p is inst:
                continue
            if p["source_dir"] == inst.get("parent_dir") and self._nested_deployed(inst, p):
                parents.append(p)
        return parents

    def _resolve(self, expr, mdir, inst):
        e = expr.strip().strip('"')
        if not e:
            return ("unknown", None)
        e = re.sub(r"\[[a-z0-9._]+\]", "", e)
        m = re.fullmatch(r"(aws_[a-z0-9_]+)\.([a-zA-Z0-9_-]+)\.(?:arn|id|name|.*)", e)
        if m:
            rtype, rname = m.group(1), m.group(2)
            key = (inst["name"] if inst else None, rtype, rname)
            nid = self.node_by_resource.get(key)
            if not nid and inst:
                for p in self._parent_instances(inst):
                    nid = self.node_by_resource.get((p["name"], rtype, rname))
                    if nid:
                        break
            return ("node", nid) if nid else ("unknown", None)
        if e.startswith("var.config."):
            eid = external_id_for_path(e[len("var.config."):])
            return ("external", eid) if eid else ("unknown", None)
        if e.startswith("var."):
            path = e[len("var."):]
            arg = (inst or {}).get("args", {}).get(path, "") if inst else ""
            if arg:
                return self._resolve(arg, mdir, inst)
            return ("unknown", None)
        if e.startswith("local.config."):
            eid = external_id_for_path(e[len("local.config."):])
            return ("external", eid) if eid else ("unknown", None)
        if e.startswith("local."):
            eid = external_id_for_path(e[len("local."):])
            return ("external", eid) if eid else ("unknown", None)
        m = re.fullmatch(r"module\.([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)", e)
        if m:
            mname, out = m.groups()
            tgt = self.inst_by_name.get(mname)
            if tgt:
                r = self._resolve_output(tgt, out)
                if r[0] != "unknown":
                    return r
                sq = tgt["args"].get("source_queue_arn", "")
                if sq.startswith("local.config."):
                    eid = external_id_for_path(sq[len("local.config."):])
                    if eid:
                        return ("external", eid)
            return ("unknown", None)
        return ("unknown", None)

    def _resolve_output(self, inst, out_name):
        blocks = self.blocks_by_dir.get(inst["source_dir"], [])
        for b in blocks:
            if b["kind"] == "output" and b["name"] == out_name:
                attrs = top_attrs(b["body"])
                return self._resolve(attrs.get("value", ""), inst["source_dir"], inst)
        return ("unknown", None)

    def _register_external(self, eid, path, context):
        if eid and eid not in self.externals:
            self.externals[eid] = {
                "id": eid,
                "name": eid,
                "description": f"External resource referenced via '{path}' in {context}",
                "side": "left",
            }
        return eid

    def _add_edge(self, src, tgt, kind, evidence):
        if src[0] == "unknown" or tgt[0] == "unknown":
            return
        f, t = src[1], tgt[1]
        if f == t:
            return
        if src[0] == "external":
            self._register_external(f, f, "config")
        if tgt[0] == "external":
            self._register_external(t, t, "config")
        key = (f, t)
        if key not in self.edge_evidence:
            self.edges.append({"from": f, "to": t})
        self.edge_evidence[key] = f"{kind} @ {evidence}"

    def _lambda_for_policydoc(self, doc_name, inst):
        cands = [doc_name]
        if doc_name.endswith("_lambda"):
            cands.append(doc_name[:-len("_lambda")])
        if doc_name.endswith("_sqs"):
            cands.append(doc_name[:-len("_sqs")])
        for c in cands:
            key = (inst["name"], "aws_lambda_function", c) if inst else (None, "aws_lambda_function", c)
            nid = self.node_by_resource.get(key)
            if nid:
                return nid
        return None

    def _ddb_refs(self, body, inst):
        res, var_paths, _l, _m = refs(body)
        tables = set()
        for t in res.get("aws_dynamodb_table", ()):
            key = (inst["name"], "aws_dynamodb_table", t) if inst else (None, "aws_dynamodb_table", t)
            nid = self.node_by_resource.get(key)
            if nid:
                tables.add(nid)
        for vp in var_paths:
            if "_table_arn" in vp:
                r = self._resolve("var." + vp, None, inst)
                if r[0] == "node":
                    tables.add(r[1])
        return tables

    def _derive_edges(self):
        by_src = {}
        for inst in self.instances:
            by_src.setdefault(inst["source_dir"], []).append(inst)

        self._stream_consumers = self._build_stream_consumers(by_src)

        for mdir, blocks in self.blocks_by_dir.items():
            base = os.path.basename(mdir)
            root_dir = mdir == self.deploy_dir
            if root_dir:
                insts = [None]
            else:
                insts = by_src.get(mdir, [])
                if not insts:
                    continue
                if base in PLUMBING_MODULE_DIRS:
                    continue
            for b in blocks:
                if b["kind"] not in ("resource", "data"):
                    continue
                rtype, rname = b["rtype"], b["name"]
                for inst in insts:
                    self._derive_block_edges(b, mdir, inst)

    def _build_stream_consumers(self, by_src):
        """Map lambda node id -> set of DDB table node ids it consumes via a
        DDB-stream event source mapping. A stream-triggered lambda READS its
        source table's stream; an IAM policy doc reference to that table is
        stream-read permission, not a write target."""
        consumers = {}
        for mdir, blocks in self.blocks_by_dir.items():
            if os.path.basename(mdir) in PLUMBING_MODULE_DIRS:
                continue
            if mdir == self.deploy_dir:
                insts = [None]
            else:
                insts = by_src.get(mdir, [])
            for inst in insts:
                for b in blocks:
                    if b["kind"] != "resource" or b["rtype"] != "aws_lambda_event_source_mapping":
                        continue
                    attrs = top_attrs(b["body"])
                    src = self._resolve(attrs.get("event_source_arn", ""), mdir, inst)
                    tgt = self._resolve(attrs.get("function_name", ""), mdir, inst)
                    if src[0] == "node" and tgt[0] == "node":
                        consumers.setdefault(tgt[1], set()).add(src[1])
        return consumers

    def _derive_block_edges(self, b, mdir, inst):
        rtype, rname = b["rtype"], b["name"]
        if rtype == "aws_lambda_event_source_mapping":
            attrs = top_attrs(b["body"])
            src = self._resolve(attrs.get("event_source_arn", ""), mdir, inst)
            tgt = self._resolve(attrs.get("function_name", ""), mdir, inst)
            self._add_edge(src, tgt, "trigger", f"{b['file']}:{b['line']}")
        elif rtype == "aws_sns_topic_subscription":
            attrs = top_attrs(b["body"])
            topic = self._resolve(attrs.get("topic_arn", ""), mdir, inst)
            endp = self._resolve(attrs.get("endpoint", ""), mdir, inst)
            self._add_edge(topic, endp, "sns-sub", f"{b['file']}:{b['line']}")
        elif rtype == "aws_cloudwatch_event_target":
            attrs = top_attrs(b["body"])
            rule = self._resolve(attrs.get("rule", ""), mdir, inst)
            tgt = self._resolve(attrs.get("arn", ""), mdir, inst)
            self._add_edge(rule, tgt, "eventbridge-schedule", f"{b['file']}:{b['line']}")
        elif rtype == "aws_iam_policy_document":
            lambda_nid = self._lambda_for_policydoc(rname, inst)
            if not lambda_nid:
                return
            skip = self._stream_consumers.get(lambda_nid, set())
            for table in self._ddb_refs(b["body"], inst):
                if table in skip:
                    continue
                self._add_edge(("node", lambda_nid), ("node", table), "write",
                               f"{b['file']}:{b['line']} iam policy doc {rname}")
        elif rtype == "aws_lambda_function":
            lambda_nid = None
            key = (inst["name"], "aws_lambda_function", rname) if inst else (None, "aws_lambda_function", rname)
            lambda_nid = self.node_by_resource.get(key)
            if not lambda_nid:
                return
            consume = self._stream_consumers.get(lambda_nid, set())
            for vname, val in env_vars(b["body"]).items():
                if not any(k in vname for k in ("TOPIC", "_ARN", "_SQS_URL", "_QUEUE_URL")):
                    continue
                r = self._resolve(val, mdir, inst)
                if r[0] == "node" and r[1] in consume:
                    # the queue this lambda consumes via its event source
                    # mapping — an env-var reference to it is a read target,
                    # not a publish target. Skip the reverse edge.
                    continue
                if r[0] in ("node", "external"):
                    self._add_edge(("node", lambda_nid), r, "publish",
                                   f"{b['file']}:{b['line']} env {vname}")

    def _assign_sides(self):
        out = {e["from"] for e in self.edges}
        into = {e["to"] for e in self.edges}
        for eid, x in self.externals.items():
            if eid in into and eid not in out:
                x["side"] = "right"

    def _draft(self):
        draft = {
            "title": None,
            "nodes": [self.nodes[i] for i in sorted(self.nodes)],
            "edges": self.edges,
            "externals": [self.externals[e] for e in sorted(self.externals)],
        }
        notes = {
            "evidence": {f"{f} -> {t}": ev for (f, t), ev in self.edge_evidence.items()},
            "pruned": sorted(set(self.pruned)),
            "notes": list(self.notes),
        }
        return draft, notes


def discover(deploy_dir):
    return Discovery(deploy_dir).run()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python3 tf_parser.py <deploy-dir>")
        sys.exit(1)
    d, notes = discover(sys.argv[1])
    print(json.dumps(d, indent=2))
    print("\n# TF ground-truth evidence:")
    for k, v in notes["evidence"].items():
        print(f"#   {k}  [{v}]")
    if notes["pruned"]:
        print("\n# Pruned (DLQ/test/alert/IAM plumbing):")
        for p in notes["pruned"]:
            print(f"#   {p}")
