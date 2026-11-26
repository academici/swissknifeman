"""maind fleet — cross-project layer for the optimizer agent.

Cross-project optimization ~N similar projects (common core packages):
- manifest  — single JSON: projects (paths/namespaces/scopes) + groups by COMMON packages
              (who demands what) → agent entry point, «where to look».
- duplicates — cross-project search for code duplicates (wrapper over jscpd) by grouped
              paths → «what exactly is repeated» (cross-project clones first).
- similar    — SEMANTIC similarity of code (function embeddings/classes) over literals
              takes jscpd: «similar in meaning, not verbatim». Backend of embeddings - external
              (config code_graph.embed), orchestrated; without it - intelligible die.

«Leaked» there is no code graph and no need: signal = topology (groups) + duplicates + memory; point
gives the edit Serena in the desired project. stdlib-only; jscpd/embedder - external, orchestrated."""
import json
import math
import os
import re
import shutil
import tempfile
from pathlib import Path

from aicore.util.term import die, warn
from aicore.util.cli import parse_args
from ..config import load_config
from ..federation import federated_graph, graph_disabled
from ..namespaces import group_scopes, namespaces_of, private_scope
from ..projects import listing
from aicore.util.proc import run as run_with_timeout


# ── manifest ─────────────────────────────────────────────────────────────────
def _proj_entry(project):
    local = project.get("local_path")
    return {
        "id": project["id"], "name": project.get("name", project["id"]),
        "type": project.get("type", "unknown"),
        "path": str(Path(os.path.expanduser(local))) if local else None,
        "namespaces": sorted(namespaces_of(project)),
        "code": bool(project.get("code", project.get("graphify", False))),
        "scopes": {"private": private_scope(project), "group": group_scopes(project)},
    }


def shared_packages(env, config):
    """[{package, name, provider, consumers[], consumer_count}] — first-party packages,
    which require ≥2 project. These are cross-project optimization groups."""
    if graph_disabled(config):
        return []
    g = federated_graph(env, config)
    consumers, providers, names = {}, {}, {}
    for src_id, dsts in g.adj.items():
        for dst_id, e in dsts.items():
            if (e["type"] == "requires" and src_id.startswith("project:")
                    and dst_id.startswith("package:")):
                consumers.setdefault(dst_id, set()).add(src_id.split(":", 1)[1])
            elif (e["type"] == "provided_by" and src_id.startswith("package:")
                  and dst_id.startswith("project:")):
                providers[src_id] = dst_id.split(":", 1)[1]
    for nid, n in g.nodes.items():
        if nid.startswith("package:"):
            names[nid] = n["attrs"].get("name") or nid.split("/")[-1]
    out = [{"package": pkg, "name": names.get(pkg, pkg.split("/")[-1]),
            "provider": providers.get(pkg), "consumers": sorted(cons),
            "consumer_count": len(cons)}
           for pkg, cons in consumers.items() if len(cons) >= 2]
    out.sort(key=lambda x: (-x["consumer_count"], x["package"]))
    return out


def manifest(env, config):
    projects = [p for p in listing(env, config) if p.get("enabled", True)]
    return {"node": config.get("node", {}),
            "projects": [_proj_entry(p) for p in projects],
            "shared_packages": shared_packages(env, config)}


# ── cross-project duplicates (jscpd) ────────────────────────────────────────────
def _resolve_targets(env, config, opts):
    """(pmap: path→pid, [paths]) by --projects / --group / all enabled with path."""
    projects = [p for p in listing(env, config)
                if p.get("enabled", True) and p.get("local_path")]
    if opts.get("projects"):
        want = {x.strip() for x in opts["projects"].split(",") if x.strip()}
        projects = [p for p in projects if p["id"] in want]
    elif opts.get("group"):
        grp = next((s for s in shared_packages(env, config)
                    if opts["group"] in (s["package"], s["name"])), None)
        if grp is None:
            die(f"group (general package) not found: {opts['group']}")
        ids = set(grp["consumers"]) | ({grp["provider"]} if grp["provider"] else set())
        projects = [p for p in projects if p["id"] in ids]
    pmap, paths = {}, []
    for p in projects:
        path = str(Path(os.path.expanduser(p["local_path"])))
        pmap[path] = p["id"]
        paths.append(path)
    return pmap, paths


def _jscpd_cmd(paths, outdir, *, min_tokens, pattern, ignore):
    return ["npx", "--yes", "jscpd", "--silent", "--reporters", "json",
            "--output", outdir, "--min-tokens", str(min_tokens),
            "--pattern", pattern, "--ignore", ignore, *paths]


def _which_project(file_path, pmap):
    for base, pid in pmap.items():
        if file_path == base or (file_path or "").startswith(base + os.sep):
            return pid
    return None


def _parse_report(report, pmap):
    """jscpd-report.json → clones; cross-project (between different projects) first."""
    out = []
    for d in (report.get("duplicates", []) if isinstance(report, dict) else []):
        f1, f2 = d.get("firstFile", {}), d.get("secondFile", {})
        p1, p2 = _which_project(f1.get("name"), pmap), _which_project(f2.get("name"), pmap)
        out.append({
            "lines": d.get("lines"), "tokens": d.get("tokens"),
            "format": d.get("format"),
            "projects": sorted({x for x in (p1, p2) if x}),
            "cross_project": bool(p1 and p2 and p1 != p2),
            "files": [{"project": p1, "name": f1.get("name"),
                       "start": f1.get("start"), "end": f1.get("end")},
                      {"project": p2, "name": f2.get("name"),
                       "start": f2.get("start"), "end": f2.get("end")}],
        })
    out.sort(key=lambda c: (not c["cross_project"], -(c["lines"] or 0)))
    return out


def find_duplicates(env, config, opts):
    if shutil.which("npx") is None:
        die("npx not found - needed Node.js for jscpd (cross-project duplicate detector)")
    pmap, paths = _resolve_targets(env, config, opts)
    if not paths:
        die("no projects with local_path for analysis (specify --projects or --group)")
    min_tokens = int(opts.get("min_tokens") or 50)
    pattern = opts.get("pattern") or "**/*.php"
    ignore = opts.get("ignore") or "**/vendor/**,**/node_modules/**,**/packages/**"
    with tempfile.TemporaryDirectory() as out:
        proc = run_with_timeout(_jscpd_cmd(paths, out, min_tokens=min_tokens, pattern=pattern,
                                         ignore=ignore), capture_output=True, text=True, timeout=900)
        if proc.returncode != 0:
            die(f"jscpd failed with code {proc.returncode} — check npx/network "
                f"(first run installs the package):\n{(proc.stderr or '').strip()[:500]}")
        rp = Path(out) / "jscpd-report.json"
        if not rp.is_file():
            die("jscpd did not create a report - check npx/network (first run installs the package)")
        report = json.loads(rp.read_text(encoding="utf-8"))
    clones = _parse_report(report, pmap)
    return {"projects": sorted(set(pmap.values())), "min_tokens": min_tokens,
            "total": len(clones),
            "cross_project": sum(1 for c in clones if c["cross_project"]),
            "clones": clones}


# ── semantic similarity (embeddings) ─────────────────────────────────────
# Code chunk = function declaration/class/method + following lines (context). Simple
# language-agnostic-ish capture by keywords: function (PHP/JS/TS), class/interface/trait
# (PHP/TS), def (Python) — exactly the default extension languages (.php/.py/.ts/.js, see
# extract_chunks(exts=...)). Deep parsing is not needed - the text of the fragment is important for embedding,
# not accurate AST; interlingual false pairs are cut off by a cosine threshold of cross_project_pairs.
_DECL_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|static|final|abstract|async)\s+)*"
    r"(?:function|class|interface|trait|def)\s+(\w+)", re.MULTILINE)
_IGNORE_DIRS = {"vendor", "node_modules", ".git", "storage", "dist", "build"}


def _iter_code_files(base, exts):
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
        for f in files:
            if os.path.splitext(f)[1] in exts:
                yield os.path.join(root, f)


def extract_chunks(pmap, exts=(".php", ".py", ".ts", ".js"), context=24, min_chars=80):
    """[{project, file, name, text}] — function declarations/classes + context from paths pmap."""
    out = []
    for base, pid in pmap.items():
        for fp in _iter_code_files(base, set(exts)):
            try:
                lines = Path(fp).read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            text = "\n".join(lines)  # once per file (and not per match)
            for m in _DECL_RE.finditer(text):
                start = text.count("\n", 0, m.start())
                chunk = "\n".join(lines[start:start + context]).strip()
                if len(chunk) >= min_chars:
                    out.append({"project": pid, "file": fp, "name": m.group(1), "text": chunk})
    return out


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def cross_project_pairs(chunks, vectors, threshold):
    """Pairs of chunks from DIFFERENT projects with cosine ≥ threshold (descending)."""
    n = len(chunks)
    if n > 2000:  # clean python O(N²): warn before freezing (numpy/faiss — out stdlib-only)
        warn(f"fleet similar: {n} chunks → ~{n * n // 2:,} comparisons in pure python; "
             "narrow down the set via --projects/--group")
    pairs = []
    for i in range(len(chunks)):
        for j in range(i + 1, len(chunks)):
            if chunks[i]["project"] == chunks[j]["project"]:
                continue
            sim = _cosine(vectors[i], vectors[j])
            if sim >= threshold:
                pairs.append({"similarity": round(sim, 4),
                              "a": {k: chunks[i][k] for k in ("project", "name", "file")},
                              "b": {k: chunks[j][k] for k in ("project", "name", "file")}})
    pairs.sort(key=lambda p: -p["similarity"])
    return pairs


def _embed(texts, embed_cfg):
    """Embeddings via EXTERNAL backend from config.code_graph.embed:
    {command:[...], input_env|input_arg, output} — write JSONL texts to a temporary file,
    run the command, read JSON-array of vectors. Without config - die."""
    if not embed_cfg or not embed_cfg.get("command"):
        die("embedder is not configured - specify code_graph.embed.command in config.json "
            "(external tool: text→vector). Without it, only available `fleet duplicates`.")
    with tempfile.TemporaryDirectory() as tmp:
        inp, outp = Path(tmp) / "in.jsonl", Path(tmp) / "out.json"
        inp.write_text("\n".join(json.dumps(t, ensure_ascii=False) for t in texts),
                       encoding="utf-8")
        argv = [a.replace("{input}", str(inp)).replace("{output}", str(outp))
                for a in embed_cfg["command"]]
        proc = run_with_timeout(argv, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            die(f"embedder exited with code {proc.returncode} "
                f"(code_graph.embed.command):\n{(proc.stderr or '').strip()[:500]}")
        if not outp.is_file():
            die("embedder not created {output} — check code_graph.embed.command")
        vecs = json.loads(outp.read_text(encoding="utf-8"))
    if len(vecs) != len(texts):
        die(f"embedder returned {len(vecs)} vectors on {len(texts)} texts")
    return vecs


def find_similar(env, config, opts):
    pmap, _paths = _resolve_targets(env, config, opts)
    if not pmap:
        die("no projects to analyze (specify --projects or --group)")
    chunks = extract_chunks(pmap)
    if not chunks:
        return {"projects": sorted(set(pmap.values())), "chunks": 0, "pairs": []}
    embed_cfg = (config.get("code_graph") or {}).get("embed")
    vectors = _embed([c["text"] for c in chunks], embed_cfg)
    threshold = float(opts.get("threshold") or 0.85)
    pairs = cross_project_pairs(chunks, vectors, threshold)
    return {"projects": sorted(set(pmap.values())), "chunks": len(chunks),
            "threshold": threshold, "pairs": pairs}


# ── CLI ──────────────────────────────────────────────────────────────────────
def cmd_fleet(env, argv):
    sub = argv[0] if argv and not argv[0].startswith("-") else "manifest"
    rest = argv[1:] if argv and not argv[0].startswith("-") else argv
    if sub in ("-h", "--help", "help"):
        print("maind fleet [manifest] | duplicates [--group PKG|--projects a,b|--min-tokens N] "
              "| similar [--group|--projects|--threshold T]   [--json]")
        return
    config, _ = load_config(env)

    if sub == "manifest":
        print(json.dumps(manifest(env, config), ensure_ascii=False, indent=2))
        return

    if sub == "duplicates":
        opts, _pos = parse_args(rest, {"--group": "str", "--projects": "str",
                                       "--min-tokens": "str", "--pattern": "str",
                                       "--ignore": "str", "--json": "bool"})
        res = find_duplicates(env, config, {
            "group": opts["group"], "projects": opts["projects"],
            "min_tokens": opts["min_tokens"], "pattern": opts["pattern"],
            "ignore": opts["ignore"]})
        if opts["json"]:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(f"duplicates: {res['total']} (cross-project {res['cross_project']}) "
                  f"in {', '.join(res['projects'])}, min-tokens={res['min_tokens']}")
            for c in res["clones"][:30]:
                tag = "⇄" if c["cross_project"] else " "
                a, b = c["files"]
                print(f"  {tag} {c['lines']}page  {a['project']}:{a['name']} ↔ "
                      f"{b['project']}:{b['name']}")
        return

    if sub == "similar":
        opts, _pos = parse_args(rest, {"--group": "str", "--projects": "str",
                                       "--threshold": "str", "--json": "bool"})
        res = find_similar(env, config, {"group": opts["group"],
                                         "projects": opts["projects"],
                                         "threshold": opts["threshold"]})
        if opts["json"]:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(f"semantically similar pairs: {len(res['pairs'])} "
                  f"(chunks {res['chunks']}, threshold {res.get('threshold')})")
            for p in res["pairs"][:30]:
                print(f"  {p['similarity']}  {p['a']['project']}:{p['a']['name']} ~ "
                      f"{p['b']['project']}:{p['b']['name']}")
        return

    die(f"unknown subcommand fleet: {sub} "
        "(manifest|duplicates|similar)")
