#!/usr/bin/env python3
"""Extract every FastAPI REST endpoint + builtin tool from Letta v0.16.8 server source (AST-based).
Writes inventory/raw/endpoints_ast.json and inventory/raw/builtin_tools.json.
Ground truth: letta-0.16.8 sdist (PyPI), same tree as letta-ai/letta@v0.16.8.
"""
import ast, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent   # ./lettaui
SRC = ROOT / "letta-0.16.8" / "letta"
OUT = ROOT / "inventory" / "raw"
OUT.mkdir(parents=True, exist_ok=True)

DECOR_KINDS = {"get", "post", "put", "patch", "delete", "api_route"}

def deco_name(d):
    t = d.func
    if isinstance(t, ast.Attribute):
        return t.attr
    if isinstance(t, ast.Name):
        return t.id
    return None

def deco_path(d):
    if d.args and isinstance(d.args[0], ast.Constant) and isinstance(d.args[0].value, str):
        return d.args[0].value
    for kw in d.keywords:
        if kw.arg == "path" and isinstance(kw.value, ast.Constant):
            return kw.value.value
    return None

def deco_meta(d):
    meta = {}
    for kw in d.keywords:
        if kw.arg in ("tags", "summary", "operation_id"):
            v = kw.value
            if isinstance(v, ast.Constant):
                meta[kw.arg] = v.value
            elif isinstance(v, ast.List) and v.elts and isinstance(v.elts[0], ast.Constant):
                meta[kw.arg] = [e.value for e in v.elts if isinstance(e, ast.Constant)]
    return meta

endpoints = []
seen = set()

for py in sorted(SRC.rglob("*.py")):
    rel = str(py.relative_to(ROOT / "letta-0.16.8"))
    if not (("server" in rel or rel.endswith("main.py") or "routers" in rel)):
        continue
    try:
        tree = ast.parse(py.read_text(encoding="utf-8"))
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in node.decorator_list:
                if not isinstance(d, ast.Call):
                    continue
                m = deco_name(d)
                if m not in DECOR_KINDS:
                    continue
                p = deco_path(d)
                if p is None:
                    continue
                if m == "api_route":
                    methods = sorted({str(x.value).upper() for x in d.args[1:]
                                      if isinstance(x, ast.Constant)})
                    method = ",".join(methods) if methods else "ANY"
                else:
                    method = m.upper()
                meta = deco_meta(d)
                key = (method, p, node.name)
                if key in seen:
                    continue
                seen.add(key)
                endpoints.append({
                    "method": method,
                    "path": p,
                    "handler": node.name,
                    "line": node.lineno,
                    "file": rel,
                    "tags": meta.get("tags", []),
                    "summary": meta.get("summary", ""),
                    "op_id": meta.get("operation_id", node.name),
                })

json.dump(endpoints, open(OUT / "endpoints_ast.json", "w"), indent=1)
print(f"endpoints extracted: {len(endpoints)}")

# ---- builtin tools (all 5 core tool modules from letta/constants.py) ---
BUILTIN_FILES = [
    "letta/functions/function_sets/base.py",
    "letta/functions/function_sets/multi_agent.py",
    "letta/functions/function_sets/builtin.py",
    "letta/functions/function_sets/files.py",
    "letta/functions/function_sets/voice.py",
]
tools = []
for bf in BUILTIN_FILES:
    fp = ROOT / "letta-0.16.8" / bf
    if not fp.exists():
        print("MISSING", bf)
        continue
    tree = ast.parse(fp.read_text())
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = []
            for a in node.args.args:
                ann = ast.unparse(a.annotation) if a.annotation else ""
                args.append({"name": a.arg, "type": ann})
            doc = ast.get_docstring(node) or ""
            tools.append({
                "name": node.name,
                "file": bf,
                "line": node.lineno,
                "args": args,
                "returns": ast.unparse(node.returns) if node.returns else "",
                "doc": doc,
            })
json.dump(tools, open(OUT / "builtin_tools.json", "w"), indent=1)
print(f"builtin tools extracted: {len(tools)}")

fs_dir = SRC / "functions" / "function_sets"
print("function_sets:", [p.name for p in fs_dir.glob("*.py")])
