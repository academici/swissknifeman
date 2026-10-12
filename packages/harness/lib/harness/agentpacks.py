"""Internal documentation."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

from aicore.artifacts.artifact import (
    ArtifactAdapterIdentity,
    ArtifactRenderRequest,
    ArtifactSource,
    ArtifactTarget,
    plan_artifact_render,
    sha256_digest,
)
from aicore.provider.values import ProviderId

from aicore.util.cli import parse_flags
from aicore.util.io import safe_load_json
from aicore.util.term import die, warn
from aicore.util.text import sanitize
from .settings import add_hook, load_settings, write_json, write_text

LOCK_REL = ".claude/agent-pack.lock.json"
PROBE_TIMEOUT = 5



_SAFE_PROBE_PREFIXES = (
    "pwd", "command -v", "git symbolic-ref", "git rev-parse", "git config --get",
    "test ", "cat ", "ls ", "grep ", "echo ", "php ", "composer ",
    "dart ", "flutter ", "node ", "npm ", "npx ", "pnpm ", "yarn ",
    "python ", "python3 ", "uv ", "poetry ",
)
_FILE_HINT_RE = re.compile(r"^[\w./-]+\.(json|ya?ml|toml):")
_SINGLE_RE = re.compile(r"\{([A-Z_][A-Z0-9_]*)\}")
_DOUBLE_RE = re.compile(r"\{\{([A-Z_][A-Z0-9_]*)\}\}")
_IF_RE = re.compile(r"<!--\s*pack:if\s+(\w+)\s*-->(.*?)<!--\s*pack:endif\s*-->",
                    re.DOTALL)
_IFNOT_RE = re.compile(r"<!--\s*pack:ifnot\s+(\w+)\s*-->(.*?)<!--\s*pack:endif\s*-->",
                       re.DOTALL)


# ── discovery ────────────────────────────────────────────────────────────────
def pack_dir(env, pack):
    return env.agent_packs_dir / pack


def src_file(env, pack, f):
    """Internal documentation."""
    return pack_dir(env, f.get("src_pack") or pack) / f["src"]


def list_packs(env):
    d = env.agent_packs_dir
    return sorted(p.parent.name for p in d.glob("*/pack.json")) if d.is_dir() else []


def load_manifest(env, pack):
    f = pack_dir(env, pack) / "pack.json"
    if not f.exists():
        die(f"agent-pack not found: {pack} (no {f})")
    data = safe_load_json(f, default=None)
    if not isinstance(data, dict):
        die(f"{f}: invalid JSON")
    if data.get("schema") != 1:
        die(f"{f}: schema should be 1")
    return data



class _Defaulting(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def _interp(text, answers, target):
    """Internal documentation."""
    if not isinstance(text, str):
        return text
    m = _Defaulting({k: str(v) for k, v in answers.items()})
    m["project_dirname"] = target.name
    m["pwd"] = str(target)
    return text.format_map(m)


def _read_json(path):
    return safe_load_json(path, default=None)


def _file_hint(probe, target):
    """Internal documentation."""
    rel, _, dotted = probe.partition(":")
    if not rel.endswith(".json"):
        return ""
    data = _read_json(target / rel)
    if not isinstance(data, dict):
        return ""
    cur = data
    for seg in dotted.split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return ""
    return "true"


def _probe_allowed(probe):
    for seg in re.split(r"\|\||&&|;|\|", probe):
        seg = seg.strip()
        if not seg:
            continue
        if not any(seg.startswith(p) for p in _SAFE_PROBE_PREFIXES):
            return False
    return True


def _run_detect(probe, target, shell_policy, report):
    """Internal documentation."""
    probe = probe.strip()
    if not probe:
        return ""
    if probe == "pwd":
        return str(target)
    if _FILE_HINT_RE.match(probe):
        return _file_hint(probe, target)
    if shell_policy == "off":
        return ""
    if shell_policy == "safe" and not _probe_allowed(probe):
        report["skipped_probes"].append(probe)
        return ""
    try:
        r = subprocess.run(["bash", "-lc", probe], cwd=str(target),
                           capture_output=True, text=True, timeout=PROBE_TIMEOUT)
        return (r.stdout or "").strip() if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _coerce(value, kind):
    if kind == "slug":
        return sanitize(value) if value else value
    if kind == "bool":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() not in ("", "0", "false", "no")
    return value


def resolve_interview(manifest, target, overrides, shell_policy="safe"):
    """Internal documentation."""
    answers, report = {}, {"assumed": [], "unresolved": [], "skipped_probes": []}
    for e in manifest.get("interview", []):
        key, kind = e["id"], e.get("kind", "str")
        enum = e.get("enum")
        if key in overrides:
            answers[key] = _coerce(overrides[key], kind)
            continue
        raw = ""
        if e.get("detect"):
            raw = _run_detect(e["detect"], target, shell_policy, report)
        if raw == "" and "default" in e:
            raw = e["default"]
        if isinstance(raw, str):
            raw = _interp(raw, answers, target)
        val = _coerce(raw, kind)
        if enum and val not in enum:
            dflt = e.get("default")
            val = dflt if dflt in enum else (enum[0] if enum else val)
            report["assumed"].append(f"{key}={val}")
        if val == "" and not enum and "default" not in e:
            report["unresolved"].append(key)
        answers[key] = val
    return answers, report


# ── provenance header ────────────────────────────────────────────────────────




_COMMENT_STYLES = {".md": "html", ".js": "line//", ".mjs": "line//",
                   ".sh": "line#", ".ini": "line#"}


def provenance_header(pack, version, src_rel, target_rel, edit_policy,
                      extension_points):
    """Internal documentation."""
    style = _COMMENT_STYLES.get(os.path.splitext(target_rel)[1])
    if not style:
        return ""
    pts = ", ".join(extension_points) if extension_points else "—"
    lines = [
        "swissknifeman:generated",
        "Generated-by: harness agent-packs",
        f"Pack: {pack}@{version}",
        f"Template: {src_rel}",
        f"Edit-policy: {edit_policy}",
        f"Extension-points: {pts}",
        f"Upgrade: harness agent-packs upgrade --pack {pack} --target .",
    ]
    if style == "html":
        return "<!-- " + lines[0] + "\n" + "\n".join(lines[1:]) + "\n-->\n"
    prefix = "//" if style == "line//" else "#"
    return "\n".join(f"{prefix} {ln}" for ln in lines) + "\n"


def inject_header(rendered, header, target_rel):
    """Internal documentation."""
    if not header:
        return rendered
    ext = os.path.splitext(target_rel)[1]
    if ext == ".md" and rendered.startswith("---"):
        lines = rendered.splitlines(keepends=True)
        if lines[0].rstrip("\n") == "---":
            for i, ln in enumerate(lines[1:], start=1):
                if ln.rstrip("\n") == "---":
                    return "".join(lines[:i + 1]) + header + "".join(lines[i + 1:])
        return header + rendered
    if rendered.startswith("#!"):
        nl = rendered.find("\n")
        if nl != -1:
            return rendered[:nl + 1] + header + rendered[nl + 1:]
        return rendered + "\n" + header
    return header + rendered


def _edit_policy(f):
    """Internal documentation."""
    return ("user-owned — file is yours, the pack will not overwrite it" if f.get("user_owned")
            else "generated-core — DO NOT edit; expand through extension-point")


def _extension_points(manifest, answers):
    """Internal documentation."""
    return [_subst_single(x["target"], answers)
            for x in manifest.get("files", []) if x.get("role") == "override"]


# ── render engine ────────────────────────────────────────────────────────────
def sha256_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _subst_single(text, answers):
    return _SINGLE_RE.sub(lambda m: str(answers.get(m.group(1), m.group(0))), text)


def _subst_double(text, answers):
    return _DOUBLE_RE.sub(lambda m: str(answers.get(m.group(1), m.group(0))), text)


def _apply_conditionals(text, answers):
    """Internal documentation."""
    for _ in range(10):
        new = _IF_RE.sub(lambda m: m.group(2) if answers.get(m.group(1)) else "", text)
        new = _IFNOT_RE.sub(
            lambda m: m.group(2) if not answers.get(m.group(1)) else "", new)
        if new == text:
            return new
        text = new
    return text


def _render_template_text(src_text, answers):
    return _subst_double(_apply_conditionals(src_text, answers), answers)


def validate_expect_globs(manifest, target, answers):
    """Internal documentation."""
    misses = []
    for pattern in manifest.get("expect_globs", []):
        pat = _subst_single(pattern, answers).strip()
        if not pat:
            continue
        try:
            hit = any(True for _ in target.glob(pat))
        except (ValueError, OSError):
            hit = False
        if not hit:
            misses.append(pat)
    return misses


def _chmod_x(path):
    cur = os.stat(path).st_mode
    os.chmod(path, cur | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _decide(target_path, new_sha, owned, base_sha):
    """Internal documentation."""
    if not target_path.exists():
        return "write"
    disk_sha = sha256_text(target_path.read_text(encoding="utf-8"))
    if not owned:
        return "skip-identical" if disk_sha == new_sha else "skip-foreign"
    if disk_sha != base_sha:
        return "skip-local-modified"
    return "skip-nochange" if disk_sha == new_sha else "write"


def render_pack(env, pack, target, answers, *, dry=False, prior=None):
    """Internal documentation."""
    manifest = load_manifest(env, pack)
    prior_files = {f["src"]: f for f in (prior or {}).get("files", [])}
    ext_points = _extension_points(manifest, answers)
    out_files, changed, notes = [], False, []
    for f in manifest.get("files", []):
        src, kind = f["src"], f.get("kind", "template")
        sfile = src_file(env, pack, f)
        if not sfile.exists():
            if f.get("optional"):
                continue
            die(f"{f.get('src_pack') or pack}: no pack file {src}")
        tgt_rel = _subst_single(f["target"], answers)
        tgt = target / tgt_rel
        prior_f = prior_files.get(src)
        base_sha = (prior_f or {}).get("base_sha256", "")
        owned = prior_f is not None

        if kind == "merge":
            ch = _merge_fragment(target, sfile, f.get("merge", ""), answers, dry)
            changed = changed or ch
            out_files.append({"src": src, "target": tgt_rel, "kind": kind,
                              "base_sha256": sha256_text(sfile.read_text(encoding="utf-8")),
                              "local_modified": False,
                              "user_owned": bool(f.get("user_owned", False))})
            continue

        rendered = (_render_template_text(sfile.read_text(encoding="utf-8"), answers)
                    if kind == "template" else sfile.read_text(encoding="utf-8"))
        rendered = inject_header(
            rendered,
            provenance_header(pack, manifest["version"], src, tgt_rel,
                              _edit_policy(f), ext_points),
            tgt_rel)
        new_sha = sha256_text(rendered)
        decision = _decide(tgt, new_sha, owned, base_sha)
        local_mod = decision == "skip-local-modified"
        if decision == "write":
            tgt.parent.mkdir(parents=True, exist_ok=True)
            write_text(tgt, rendered, dry)
            if not dry and f.get("chmod") == "+x":
                _chmod_x(tgt)
            changed = True
        elif decision == "skip-foreign":
            warn(f"  collision: {tgt_rel} already exists and does not belong to the pack - skip")
            notes.append(f"collision:{tgt_rel}")
        elif decision == "skip-local-modified":
            warn(f"  {tgt_rel} edited locally - I don’t overwrite it (see upgrade)")
        out_files.append({"src": src, "target": tgt_rel, "kind": kind,
                          "base_sha256": new_sha, "local_modified": local_mod,
                          "user_owned": bool(f.get("user_owned", False))})
    report = {"files": out_files, "changed": changed, "notes": notes}
    return report


def _merge_fragment(target, sfile, directive, answers, dry):
    """Internal documentation."""
    raw = _subst_double(sfile.read_text(encoding="utf-8"), answers)
    frag = json.loads(raw)
    settings, f = load_settings(target, "settings.json")
    added = False
    events = [seg.split("[")[0].split(".")[-1]
              for seg in directive.replace("append-if-absent", "").split("+")
              if seg.strip()]
    for event in events or list(frag.get("hooks", {})):
        for entry in frag.get("hooks", {}).get(event, []):
            matcher = entry.get("matcher")
            for h in entry.get("hooks", []):
                if add_hook(settings, event, matcher, h.get("command")):
                    added = True
    if added:
        write_json(f, settings, dry)
    else:
        print("  settings.json: fragment hooks are already in place - skipping")
    return added


# ── lock ─────────────────────────────────────────────────────────────────────
def lock_path(target):
    return target / LOCK_REL


def load_lock(target):
    return safe_load_json(lock_path(target), default={"schema": 1, "packs": {}})


def write_lock(target, lock, dry):
    lp = lock_path(target)
    if dry:
        print(f"  [dry-run] would update {lp}")
        return
    lp.parent.mkdir(parents=True, exist_ok=True)
    from aicore.util.io import atomic_write_json
    atomic_write_json(lp, lock)
    print(f"  lock: {lp}")


def _pack_lock_entry(env, pack, answers, report):
    return {
        "version": load_manifest(env, pack)["version"],
        "source": f"harness:configs/claude-code/agent-packs/{pack}",
        "answers": answers,
        "files": report["files"],
        "removed_optional": [],
    }


# ── operations ───────────────────────────────────────────────────────────────
def do_render(env, pack, target, *, auto, overrides, dry, install_only, shell_policy):
    manifest = load_manifest(env, pack)
    lock = load_lock(target)
    prior = lock.get("packs", {}).get(pack)
    if install_only and prior is not None:
        print(f"agent-pack '{pack}' is already installed (v{prior.get('version')}) — pass")
        return 0

    base_overrides = dict((prior or {}).get("answers", {}))
    base_overrides.update(overrides)
    answers, rep = resolve_interview(manifest, target, base_overrides, shell_policy)
    print(f"=== agent-pack render: {pack} v{manifest['version']} → {target} ===")
    if rep["assumed"]:
        warn(f"  assumptions (check): {', '.join(rep['assumed'])}")
    if rep["skipped_probes"]:
        warn(f"  unsafe samples skipped: {len(rep['skipped_probes'])}")
    report = render_pack(env, pack, target, answers, dry=dry, prior=prior)
    new_entry = _pack_lock_entry(env, pack, answers, report)
    lock.setdefault("packs", {})[pack] = new_entry








    if report["changed"] or prior is None or new_entry != prior:
        write_lock(target, lock, dry)
    for pat in validate_expect_globs(manifest, target, answers):
        warn(f"  expected path '{pat}' match 0 files - check layout/answers "
             f"(risk of false green access-layer)")
    status = "needs-agent" if rep["unresolved"] else "ok"
    print(f"=== {status} (changed={report['changed']}) ===")
    return 0 if status == "ok" else 0


def categorize_file_change(f, pf, new_sha, tgt):
    """Internal documentation."""
    if pf is None:
        return "new-optional" if f.get("optional") else "new"
    if f.get("user_owned"):
        return "user-owned"
    if not tgt.exists():






        return "new-optional" if f.get("optional") else "new"
    disk_sha = sha256_text(tgt.read_text(encoding="utf-8"))
    local_mod = disk_sha != pf.get("base_sha256")
    base_changed = new_sha != pf.get("base_sha256")
    if base_changed and local_mod:
        return "conflict"
    if base_changed:
        return "safe-apply"
    return "nochange"


def do_upgrade(env, pack, target, *, overrides, dry, shell_policy):
    """Internal documentation."""
    manifest = load_manifest(env, pack)
    lock = load_lock(target)
    prior = lock.get("packs", {}).get(pack)
    if prior is None:
        die(f"agent-pack '{pack}' not installed - first render")
    v_old, v_new = prior.get("version"), manifest["version"]
    same_version = v_old == v_new
    base_overrides = dict(prior.get("answers", {}))
    base_overrides.update(overrides)
    answers, _ = resolve_interview(manifest, target, base_overrides, shell_policy)
    prior_files = {f["src"]: f for f in prior.get("files", [])}
    ext_points = _extension_points(manifest, answers)
    plan, out_files = [], []
    for f in manifest.get("files", []):
        src, kind = f["src"], f.get("kind", "template")
        sfile = src_file(env, pack, f)
        if not sfile.exists():
            continue
        tgt_rel = _subst_single(f["target"], answers)
        tgt = target / tgt_rel
        if kind == "merge":
            _merge_fragment(target, sfile, f.get("merge", ""), answers, dry)
            out_files.append({"src": src, "target": tgt_rel, "kind": kind,
                              "base_sha256": sha256_text(sfile.read_text(encoding="utf-8")),
                              "local_modified": False,
                              "user_owned": bool(f.get("user_owned", False))})
            continue
        rendered = (_render_template_text(sfile.read_text(encoding="utf-8"), answers)
                    if kind == "template" else sfile.read_text(encoding="utf-8"))


        rendered = inject_header(
            rendered,
            provenance_header(pack, manifest["version"], src, tgt_rel,
                              _edit_policy(f), ext_points),
            tgt_rel)
        new_sha = sha256_text(rendered)
        cat = categorize_file_change(f, prior_files.get(src), new_sha, tgt)



        install_new = cat == "new" or (
            cat == "new-optional" and src not in prior.get("removed_optional", []))
        plan.append((cat, src, tgt_rel,
                     bool(install_new or cat in ("safe-apply", "conflict"))))
        if (cat == "safe-apply" or install_new) and not dry:
            tgt.parent.mkdir(parents=True, exist_ok=True)
            write_text(tgt, rendered, dry)
            if f.get("chmod") == "+x":
                _chmod_x(tgt)
        elif cat == "conflict" and not dry:
            write_text(target / (tgt_rel + ".pack-new"), rendered, dry)
            warn(f"  conflict: {tgt_rel} — new option in {tgt_rel}.pack-new (merge manually)")
        out_files.append({"src": src, "target": tgt_rel, "kind": kind,
                          "base_sha256": new_sha,
                          "local_modified": cat == "conflict",
                          "user_owned": bool(f.get("user_owned", False))})
    acted = [(c, t) for c, _s, t, a in plan if a]
    if same_version:
        print(f"=== upgrade {pack}: v{v_new} (version is the same - verification of actual files) ===")
    else:
        print(f"=== upgrade {pack}: {v_old} → {v_new} ===")
    for cat, _src, tgt_rel, a in plan:
        if a or cat != "nochange":
            print(f"  [{cat}] {tgt_rel}")
    if not acted:
        print("  nothing to do: files match lock'ohm")
    elif same_version:


        warn(f"  ⚠ pack '{pack}' did not change the version (v{v_new}), but {len(acted)} file(ov) "
             f"separated from lock'ohm - applied after the fact; to the authors of the pack: bump it "
             f"pack.json:version, otherwise the upgrade relies only on hashes")
    conflicts = [t for c, _s, t, _a in plan if c == "conflict"]
    if conflicts:
        warn(f"  ⚠ {len(conflicts)} conflict → manual merge from .pack-new: "
             + ", ".join(t + ".pack-new" for t in conflicts))
    for pat in validate_expect_globs(manifest, target, answers):
        warn(f"  expected path '{pat}' match 0 files - check layout/answers "
             f"(risk of false green access-layer)")
    removed = sorted(set(prior_files) - {f["src"] for f in manifest.get("files", [])})
    for src in removed:
        warn(f"  removed in {v_new}: {src} — I don't delete the car (deleted manually if desired)")
    entry = _pack_lock_entry(env, pack, answers, {"files": out_files})
    entry["removed_optional"] = prior.get("removed_optional", [])
    lock.setdefault("packs", {})[pack] = entry
    write_lock(target, lock, dry)
    return 0


def do_remove(env, pack, target, *, dry):
    """Internal documentation."""
    lock = load_lock(target)
    entry = lock.get("packs", {}).get(pack)
    if entry is None:
        print(f"agent-pack '{pack}' is not set to {target} — nothing to delete")
        return 0
    tag = " [dry-run]" if dry else ""
    print(f"=== agent-pack remove: {pack} v{entry.get('version')} ← {target} ==={tag}")
    merge_kept = []
    for f in entry.get("files", []):
        tgt_rel = f.get("target", "")
        tgt = target / tgt_rel
        if f.get("kind", "template") == "merge":
            merge_kept.append(tgt_rel)
            continue
        if f.get("user_owned"):
            warn(f"  {tgt_rel}: user-owned — left, delete manually if desired")
            continue
        if not tgt.exists():
            continue
        try:
            disk_sha = sha256_text(tgt.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            warn(f"  {tgt_rel}: is not readable - left just in case")
            continue
        if disk_sha != f.get("base_sha256"):
            warn(f"  {tgt_rel}: locally edited - left")
            continue
        print(f"  [{'dry-run' if dry else 'remove'}] {tgt_rel}")
        if not dry:
            tgt.unlink()
    if merge_kept:
        warn("  hooks in settings.json remain - delete manually if necessary: "
             + ", ".join(merge_kept))
    if dry:
        print(f"  [dry-run] lock: entry '{pack}' would have been removed")
        return 0
    lock.get("packs", {}).pop(pack, None)
    if lock.get("packs"):
        write_lock(target, lock, dry=False)
    else:
        lp = lock_path(target)
        if lp.exists():
            lp.unlink()
        print(f"  lock: {lp} deleted (empty)")
    return 0


def lock_drift(target):
    """Internal documentation."""
    lock = load_lock(target)
    drift = []
    for pack, entry in (lock.get("packs") or {}).items():
        for f in entry.get("files") or []:
            if f.get("kind") == "merge" or f.get("user_owned"):
                continue
            tgt_rel = f.get("target", "")
            tgt = target / tgt_rel
            if not tgt.exists():
                drift.append({"pack": pack, "target": tgt_rel, "status": "missing"})
                continue
            try:
                disk_sha = sha256_text(tgt.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                drift.append({"pack": pack, "target": tgt_rel, "status": "missing"})
                continue
            if disk_sha != f.get("base_sha256"):
                drift.append({"pack": pack, "target": tgt_rel, "status": "modified"})
    return drift


def do_doctor_drift(target, *, strict=False):
    """Internal documentation."""
    drift = lock_drift(target)
    if not drift:
        print("[OK] drift generated-files not found")
        return 0
    for d in drift:
        if d["status"] == "modified":
            warn(f"[{d['pack']}] generated-file edited locally: {d['target']} — "
                 f"move the edit to override and restore render")
        else:
            warn(f"[{d['pack']}] generated-file missing: {d['target']} — "
                 f"restore render (harness agent-packs render --pack {d['pack']} "
                 f"--target .)")
    return 1 if strict else 0


def do_doctor(env, pack=None, target=None, json_out=False):
    packs = [pack] if pack else list_packs(env)
    rc = 0
    catalog = []
    for pk in packs:
        manifest = load_manifest(env, pk)
        problems = []
        ids = {e["id"] for e in manifest.get("interview", [])}
        for f in manifest.get("files", []):
            if not src_file(env, pk, f).exists() and not f.get("optional"):
                problems.append(f"no {f['src']}")

        for f in manifest.get("files", []):
            if f.get("kind", "template") != "template":
                continue
            sfile = src_file(env, pk, f)
            if not sfile.exists():
                continue
            for tok in set(_DOUBLE_RE.findall(sfile.read_text(encoding="utf-8"))):
                if tok not in ids:
                    problems.append(f"{f['src']}: {{{{{tok}}}}} not in interview")

        defaults = {e["id"]: e.get("default", "") for e in manifest.get("interview", [])}
        for f in manifest.get("files", []):
            if f.get("kind", "template") != "template":
                continue
            sfile = src_file(env, pk, f)
            if not sfile.exists():
                continue
            left = _DOUBLE_RE.findall(_render_template_text(
                sfile.read_text(encoding="utf-8"), defaults))
            if left:
                problems.append(f"{f['src']}: residual {{{{{','.join(sorted(set(left)))}}}}}")
        if problems:
            rc = 1
        catalog.append({"pack": pk, "version": manifest["version"],
                        "ok": not problems, "problems": problems})
        if not json_out:
            print(f"[{'OK ' if not problems else 'BAD'}] {pk} v{manifest['version']}")
            for p in problems:
                print(f"      - {p}")
    installed, shared = None, {}
    if target:
        lock = load_lock(target)
        lock_ok = lock.get("schema") == 1
        installed = {name: {"version": pk.get("version"),
                            "files": len(pk.get("files") or []),
                            "modified": any(f.get("local_modified")
                                            for f in (pk.get("files") or []))}
                     for name, pk in (lock.get("packs") or {}).items()}
        if not lock_ok:
            rc = 1
            if not json_out:
                print("[BAD] lock: schema != 1")
        elif installed and not json_out:
            print(f"Installed in {target.name}: {', '.join(sorted(installed))}")


        owners = {}
        for name, pk in (lock.get("packs") or {}).items():
            for f in pk.get("files") or []:
                owners.setdefault(f.get("target", ""), set()).add(name)
        shared = {tt: sorted(pp) for tt, pp in owners.items() if len(pp) > 1}
        if shared and not json_out:
            warn(f"intersection targets: {len(shared)} file(ov) belong to 2+ packam - "
                 f"remove of one will take away the files of another (recovery: "
                 f"harness agent-packs upgrade --pack <second> --target .)")
            for t in sorted(shared):
                warn(f"  {t} ← {', '.join(shared[t])}")


        bak_files = sorted(f.name for f in (target / ".claude" / "agents").glob("*.bak"))
        if bak_files and not json_out:
            warn(f".claude/agents: {len(bak_files)} .bak-file(ov) — "
                 f"check and remove unnecessary ({', '.join(bak_files)})")
    if json_out:
        print(json.dumps({"catalog": catalog, "installed": installed,
                          "shared_targets": shared, "rc": rc},
                         ensure_ascii=False, indent=2))
    return rc


# ── CLI ──────────────────────────────────────────────────────────────────────
def _pop_answers(argv):
    """Internal documentation."""
    rest, answers = [], {}
    it = iter(argv)
    for a in it:
        if a == "--answer":
            kv = next(it, "")
            k, _, v = kv.partition("=")
            if k:
                answers[k] = v
        else:
            rest.append(a)
    return rest, answers


def cmd_agent_packs(env, argv):
    if not argv:
        die("usage: harness agent-packs <list|render|upgrade|remove|doctor> [...]")
    sub, rest = argv[0], argv[1:]
    rest, answers = _pop_answers(rest)
    opts = parse_flags(rest, {
        "--pack": "str", "--target": "str", "--auto": "bool", "--dry-run": "bool",
        "--install-only": "bool", "--allow-shell": "str", "--list": "bool", "--json": "bool",
        "--drift": "bool", "--strict": "bool", "--provider": "str",
    })
    if opts.get("help"):
        print("harness agent-packs <list|render|upgrade|remove|doctor> "
              "[--pack P] [--target DIR] [--auto] [--answer K=V] "
              "[--install-only] [--allow-shell off|safe|full] [--dry-run] [--json] "
              "[--drift [--strict]] [--provider claude-code|codex|cursor|grok]")
        return
    shell_policy = opts.get("allow_shell") or "safe"
    provider = opts.get("provider") or "claude-code"
    if provider not in ("claude-code", "codex", "cursor", "grok"):
        die(f"--provider unknown: {provider} (claude-code|codex|cursor|grok)")

    if provider == "codex":
        if sub not in ("render", "remove", "doctor"):
            die(f"--provider codex does not support the subcommand '{sub}' "
                f"(render combines install/upgrade — declarative reassembly, D89)")
        if not opts.get("target"):
            die(f"needed --target DIR for {sub} --provider codex")
        target = Path(os.path.expanduser(opts["target"])).resolve()
        if not target.is_dir():
            die(f"target not a directory: {target}")
        dry = bool(opts.get("dry_run"))
        if sub == "render":
            raise SystemExit(do_codex_role_render(env, target, pack=opts.get("pack"), dry=dry))
        if sub == "remove":
            if not opts.get("pack"):
                die("needed --pack P for remove --provider codex")
            raise SystemExit(do_codex_role_remove(env, target, opts["pack"], dry=dry))
        raise SystemExit(do_codex_role_doctor(env, target, json_out=bool(opts.get("json")),
                                              strict=bool(opts.get("strict"))))

    if provider in ("cursor", "grok"):
        if sub not in ("render", "remove", "doctor"):
            die(f"--provider {provider} does not support the subcommand "
                f"'{sub}' (consumer mapping only: render/remove/doctor)")
        if not opts.get("target"):
            die(f"needed --target DIR for {sub} --provider {provider}")
        target = Path(os.path.expanduser(opts["target"])).resolve()
        if not target.is_dir():
            die(f"target not a directory: {target}")
        dry = bool(opts.get("dry_run"))
        if sub == "render":
            raise SystemExit(do_cursor_role_render(env, target, pack=opts.get("pack"), dry=dry,
                                                   provider=provider))
        if sub == "remove":
            if not opts.get("pack"):
                die(f"needed --pack P for remove --provider {provider}")
            raise SystemExit(do_cursor_role_remove(env, target, opts["pack"], dry=dry,
                                                   provider=provider))
        raise SystemExit(do_cursor_role_doctor(
            env, target, json_out=bool(opts.get("json")), strict=bool(opts.get("strict")),
            pack=opts.get("pack"), provider=provider))

    if sub == "list":
        for pk in list_packs(env):
            m = load_manifest(env, pk)
            print(f"{pk}\tv{m['version']}\t{m.get('stack', {}).get('shape', '-')}\t"
                  f"{m.get('description', '')[:70]}")
        return

    if sub == "doctor":
        target = Path(opts["target"]).resolve() if opts.get("target") else None
        if opts.get("drift"):
            if target is None:
                die("--drift requires --target DIR")
            raise SystemExit(do_doctor_drift(target, strict=bool(opts.get("strict"))))
        raise SystemExit(do_doctor(env, opts.get("pack"), target, json_out=opts.get("json")))

    if sub in ("render", "install", "upgrade", "remove"):
        if not opts.get("pack") or not opts.get("target"):
            die(f"needed --pack P and --target DIR for {sub}")
        target = Path(os.path.expanduser(opts["target"])).resolve()
        if not target.is_dir():
            die(f"target not a directory: {target}")
        pack = opts["pack"]
        dry = bool(opts.get("dry_run"))
        if sub == "upgrade":
            raise SystemExit(do_upgrade(env, pack, target, overrides=answers,
                                        dry=dry, shell_policy=shell_policy))
        if sub == "remove":
            raise SystemExit(do_remove(env, pack, target, dry=dry))
        raise SystemExit(do_render(env, pack, target, auto=bool(opts.get("auto")),
                                   overrides=answers, dry=dry,
                                   install_only=bool(opts.get("install_only")),
                                   shell_policy=shell_policy))

    die(f"unknown subcommand agent-packs: {sub}")


# provider projection seam. The role catalog is the semantic source; the
# established Claude lifecycle and templates above are compatibility consumers.
@dataclass(frozen=True)
class AgentRole:
    pack_id: str
    role_id: str
    description_lines: tuple[str, ...]
    content: str
    skills: tuple[str, ...]
    tool_requirements: tuple[str, ...]
    command_ids: tuple[str, ...]
    model_class: str
    activation_requirements: tuple[str, ...]


@dataclass(frozen=True)
class AgentProjection:
    provider_id: str
    target_path: str
    rendered: bytes
    diagnostic: str | None = None


@dataclass(frozen=True)
class CursorAgentConsumerMapping:
    provider_id: str
    mapping_version: str
    projection_owner: str
    projection_consumers: tuple[str, ...]
    projection_root: str
    projection_glob: str
    target_template: str
    create_cursor_agents: bool
    disconnect_policy: str


_ROLE_FIELDS = {"pack_id", "role_id", "description_lines", "content", "skills",
                "tool_requirements", "command_ids", "model_class", "activation_requirements"}
_CURSOR_CONSUMER_FIELDS = {
    "provider_id", "mapping_version", "projection_owner", "projection_consumers",
    "projection_root", "projection_glob", "target_template", "create_cursor_agents",
    "disconnect_policy",
}
_COMMON_FORBIDDEN = re.compile(
    r"\.claude(?:/|\b)|(?<![\w-])/(?:planner|task):[a-z-]+|(?<![\w-])/(?:effort|clear)\b|"
    r"\bWorkflow\b|\bSubagentStop\b|(?<![\w-])(?:Read|Grep|Glob|Bash|Edit|Write|"
    r"Haiku|Sonnet|Opus)(?![\w-])")
_TOKEN = re.compile(r"\{\{token:([a-z-]+)\}\}")
_MODEL_SELECTORS = {"economy": "gpt-5.6-luna", "implementation": "gpt-5.6-terra",
                    "frontier": "gpt-5.6-sol"}
_CLAUDE_TOKENS = {
    "agent-roster": "`.claude/agents/{{PACK_PREFIX}}-*.md` (Glob/Read)",
    "managed-role-override-pattern": "`.claude/rules/*-overrides.md`",
    "managed-role-override": "`.claude/rules/{{PACK_PREFIX}}-reviewer-overrides.md`",
    "background-orchestration": "**background** Workflow `{{PACK_PREFIX}}-dev-loop` (not step by step\nin the main context)",
    "tool-read": "Read", "tool-grep": "Grep", "tool-glob": "Glob",
    "tool-shell": "Bash", "tool-edit": "Edit", "tool-write": "Write",
    "model-economy": "Haiku", "model-implementation": "Sonnet", "model-frontier": "Opus",
}
_CODEX_TOKENS = {
    "agent-roster": "`.codex/agents/{{PACK_PREFIX}}-*.toml`",
    "managed-role-override-pattern": "`.codex/agents/*-overrides.toml`",
    "managed-role-override": "`.codex/agents/{{PACK_PREFIX}}-reviewer-overrides.toml`",
    "tool-read": "filesystem-read capability", "tool-grep": "filesystem-search capability",
    "tool-glob": "filesystem-search capability", "tool-shell": "shell-execute capability",
    "tool-edit": "file-edit capability", "tool-write": "filesystem-write capability",
    "model-economy": "economy model class", "model-implementation": "implementation model class",
    "model-frontier": "frontier model class",
}
_CLAUDE_TOOLS = {
    "command.filesystem-read": "Read", "agent.tool.search": "Grep, Glob",
    "agent.tool.edit": "Edit", "command.filesystem-write": "Write",
    "agent.tool.shell-execute": "Bash",
}


def load_agentpack_catalog(path):
    """Load the common role source without reading any provider consumer."""
    value = safe_load_json(Path(path), default=None)
    if not isinstance(value, dict) or set(value) != {"catalog_version", "roles"}:
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    rows = value["roles"]
    if value["catalog_version"] != "1.0.0" or not isinstance(rows, list):
        raise ValueError("HARNESS_VERSION_UNSUPPORTED")
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != _ROLE_FIELDS:
            raise ValueError("HARNESS_CATALOG_MISMATCH")
        key = (row["pack_id"], row["role_id"])
        list_fields = ("skills", "tool_requirements", "command_ids", "activation_requirements")
        if (key in seen or row["model_class"] not in _MODEL_SELECTORS
                or not all(isinstance(row.get(field), str) and row[field] for field in
                           ("pack_id", "role_id", "content"))
                or not isinstance(row["description_lines"], list)
                or not row["description_lines"]
                or not all(isinstance(item, str) for item in row["description_lines"])
                or not all(isinstance(row[field], list)
                           and all(isinstance(item, str) and item for item in row[field])
                           for field in list_fields)
                or _COMMON_FORBIDDEN.search(row["content"])):
            raise ValueError("HARNESS_CATALOG_MISMATCH")
        if set(_TOKEN.findall(row["content"])) - set(_CLAUDE_TOKENS):
            raise ValueError("HARNESS_MAPPING_MISSING")
        seen.add(key)
        result.append(AgentRole(row["pack_id"], row["role_id"], tuple(row["description_lines"]),
                                row["content"], tuple(row["skills"]),
                                tuple(row["tool_requirements"]), tuple(row["command_ids"]),
                                row["model_class"], tuple(row["activation_requirements"])))
    if not result:
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    return tuple(result)


def semantic_agent_roles(catalog_path):
    return load_agentpack_catalog(catalog_path)


def expected_agent_inventory(env):
    """Manifest-derived independent expected set; renderer output cannot define it."""
    result = []
    for pack in list_packs(env):
        for entry in load_manifest(env, pack).get("files", []):
            if entry.get("role") == "agent":
                result.append((pack, Path(entry["src"]).stem))
    if len(result) != len(set(result)):
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    return tuple(sorted(result))


def compare_agent_inventory(roles, expected):
    observed = [(role.pack_id, role.role_id) for role in roles]
    return {"missing": tuple(sorted(set(expected) - set(observed))),
            "extra": tuple(sorted(set(observed) - set(expected))),
            "duplicates": tuple(sorted({item for item in observed if observed.count(item) > 1}))}


def _resolve_tokens(role, provider_id):
    mapping = _CLAUDE_TOKENS if provider_id == "claude-code" else _CODEX_TOKENS
    def replace(match):
        try:
            return mapping[match.group(1)]
        except KeyError as error:
            raise ValueError("HARNESS_ACTIVATION_UNSUPPORTED") from error
    return _TOKEN.sub(replace, role.content)


def load_claude_role_bindings(path, roles):
    value = safe_load_json(Path(path), default=None)
    if not isinstance(value, dict) or set(value) != {"binding_version", "roles"}:
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    if value["binding_version"] != "1.0.0" or not isinstance(value["roles"], list):
        raise ValueError("HARNESS_VERSION_UNSUPPORTED")
    result = {}
    for row in value["roles"]:
        if not isinstance(row, dict) or set(row) != {"pack_id", "role_id", "model_selector", "color"}:
            raise ValueError("HARNESS_CATALOG_MISMATCH")
        key = (row["pack_id"], row["role_id"])
        if (key in result or not all(isinstance(row[field], str) and row[field]
                                     for field in row)):
            raise ValueError("HARNESS_CATALOG_MISMATCH")
        result[key] = (row["model_selector"], row["color"])
    expected = {(role.pack_id, role.role_id) for role in roles}
    if set(result) != expected:
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    return result


def agent_model_trace(roles, bindings_path, env):
    """Independently trace common classes to Claude selectors and pack defaults."""
    value = safe_load_json(Path(bindings_path), default=None)
    if not isinstance(value, dict) or value.get("binding_version") != "1.0.0":
        raise ValueError("HARNESS_VERSION_UNSUPPORTED")
    rows = value.get("roles")
    if not isinstance(rows, list):
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    bound, duplicates = {}, set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"pack_id", "role_id", "model_selector", "color"}:
            raise ValueError("HARNESS_CATALOG_MISMATCH")
        key = (row["pack_id"], row["role_id"])
        if key in bound:
            duplicates.add(key)
        bound[key] = row["model_selector"]
    expected = {(role.pack_id, role.role_id): role for role in roles}
    report = {"missing": tuple(sorted(set(expected) - set(bound))),
              "extra": tuple(sorted(set(bound) - set(expected))),
              "duplicates": tuple(sorted(duplicates)), "unknown_selector": (),
              "model_class_mismatch": ()}
    unknown, mismatch = [], []
    classes = {"haiku": "economy", "sonnet": "implementation", "inherit": "implementation",
               "opus": "frontier"}
    for key in sorted(set(expected) & set(bound)):
        selector = bound[key]
        match = re.fullmatch(r"\{\{([A-Z0-9_]+)\}\}", selector)
        if match:
            defaults = {row["id"]: row.get("default")
                        for row in load_manifest(env, key[0]).get("interview", [])}
            selector = defaults.get(match.group(1))
        if selector not in classes:
            unknown.append((key[0], key[1], selector))
            continue
        if expected[key].model_class != classes[selector]:
            mismatch.append((key[0], key[1], expected[key].model_class, classes[selector]))
    return {**report, "unknown_selector": tuple(unknown),
            "model_class_mismatch": tuple(mismatch)}


def _claude_frontmatter(role, binding):
    """Map semantic requirements to Claude syntax; no legacy template is consulted."""
    try:
        tools = ", ".join(_CLAUDE_TOOLS[item] for item in role.tool_requirements)
    except KeyError as error:
        raise ValueError("HARNESS_MAPPING_MISSING") from error
    model_selector, color = binding[(role.pack_id, role.role_id)]
    lines = ["---", f"name: {{{{PACK_PREFIX}}}}-{role.role_id}", "description: >-"]
    lines.extend("  " + line if line else "" for line in role.description_lines)
    lines.append(f"tools: {tools}")
    if role.skills:
        lines.append("skills:")
        lines.extend(f"  - {skill}" for skill in role.skills)
    lines.extend((f"model: {model_selector}", f"color: {color}", "---", ""))
    return "\n".join(lines)


def project_agent_role(role, provider_id, *, claude_bindings=None, pack_prefix=None,
                       answers=None):
    """Render named consumers from the semantic record, never from a provider output."""
    if provider_id == "codex" and "command.workflow-carrier" in role.activation_requirements:
        raise ValueError("HARNESS_ACTIVATION_UNSUPPORTED:codex:command.workflow-carrier:P4")
    resolved_answers = dict(answers or {})
    if pack_prefix is not None:
        resolved_answers["PACK_PREFIX"] = pack_prefix
    content = _resolve_tokens(role, provider_id)
    if resolved_answers:
        content = _render_template_text(content, resolved_answers)
    if provider_id == "claude-code":
        if claude_bindings is None:
            raise ValueError("HARNESS_MAPPING_MISSING")
        target = f".claude/agents/{{{{PACK_PREFIX}}}}-{role.role_id}.md"
        rendered_text = _claude_frontmatter(role, claude_bindings) + content
        if resolved_answers:
            rendered_text = _render_template_text(rendered_text, resolved_answers)
        rendered = rendered_text.encode("utf-8")
    elif provider_id == "codex":
        target = f".codex/agents/{{{{PACK_PREFIX}}}}-{role.role_id}.toml"
        model = _MODEL_SELECTORS[role.model_class]
        skills = ", ".join(json.dumps(item, ensure_ascii=False) for item in role.skills)
        commands = ", ".join(json.dumps(item, ensure_ascii=False) for item in role.command_ids)
        rendered = (f'name = {json.dumps(role.pack_id + "-" + role.role_id)}\n'
                    f'model = {json.dumps(model)}\n'
                    f'skills = [{skills}]\n'
                    f'command_requirements = [{commands}]\n'
                    f'developer_instructions = {json.dumps(content, ensure_ascii=False)}\n').encode("utf-8")
    else:
        raise ValueError("HARNESS_MAPPING_MISSING")
    if pack_prefix is not None:
        target = target.replace("{{PACK_PREFIX}}", pack_prefix)
        rendered = rendered.replace(b"{{PACK_PREFIX}}", pack_prefix.encode("utf-8"))
    return AgentProjection(provider_id, target, rendered)


def load_cursor_agent_consumer_mapping(path):
    """Load and validate Cursor consumer-only mapping for shared Claude projections."""
    value = safe_load_json(Path(path), default=None)
    if not isinstance(value, dict) or set(value) != _CURSOR_CONSUMER_FIELDS:
        raise ValueError("HARNESS_MAPPING_MISSING")
    consumers = value.get("projection_consumers")
    if not isinstance(consumers, list) or not consumers:
        raise ValueError("HARNESS_MAPPING_MISSING")
    mapping = CursorAgentConsumerMapping(
        provider_id=value["provider_id"],
        mapping_version=value["mapping_version"],
        projection_owner=value["projection_owner"],
        projection_consumers=tuple(consumers),
        projection_root=value["projection_root"],
        projection_glob=value["projection_glob"],
        target_template=value["target_template"],
        create_cursor_agents=value["create_cursor_agents"],
        disconnect_policy=value["disconnect_policy"],
    )
    if (mapping.provider_id not in {"cursor", "grok"}
            or mapping.mapping_version != "1.0.0"
            or mapping.projection_owner != "claude-code"
            or mapping.provider_id not in mapping.projection_consumers
            or mapping.projection_root != ".claude/agents"
            or mapping.projection_glob != "*.md"
            or not isinstance(mapping.target_template, str)
            or "{pack_prefix}" not in mapping.target_template
            or "{role_id}" not in mapping.target_template
            or mapping.create_cursor_agents
            or mapping.disconnect_policy != "preserve-shared-projection"):
        raise ValueError("HARNESS_MAPPING_MISSING")
    return mapping


def cursor_consumer_target(role: AgentRole, mapping: CursorAgentConsumerMapping, *,
                           pack_prefix: str) -> str:
    name = mapping.target_template.format(pack_prefix=pack_prefix, role_id=role.role_id)
    target = f"{mapping.projection_root}/{name}"
    if (not target.startswith(".claude/agents/")
            or ".cursor/agents" in target
            or ".grok/agents" in target
            or ".." in Path(target).parts):
        raise ValueError("HARNESS_MAPPING_MISSING")
    return target


def cursor_consumer_targets(roles, mapping: CursorAgentConsumerMapping, *,
                            pack_prefix: str = "{{PACK_PREFIX}}"):
    seen, result = set(), []
    for role in roles:
        target = cursor_consumer_target(role, mapping, pack_prefix=pack_prefix)
        key = (role.pack_id, role.role_id)
        if key in seen:
            raise ValueError("HARNESS_CATALOG_MISMATCH")
        seen.add(key)
        result.append((role.pack_id, role.role_id, target))
    return tuple(result)


_ARTIFACT_ID_SEGMENT = re.compile(r"^[a-z][a-z0-9-]*$")


def _artifact_identity_component(value):
    """Preserve valid segments; encode only semantic values P2 cannot represent."""
    if _ARTIFACT_ID_SEGMENT.fullmatch(value):
        return value
    return "encoded-" + value.encode("utf-8").hex()


def _agent_artifact_id(role, provider_id):
    return (f"harness.{provider_id}.agent.{_artifact_identity_component(role.pack_id)}."
            f"{_artifact_identity_component(role.role_id)}")


def _validate_agent_artifact_ids(roles, provider_id):
    artifact_ids = tuple(_agent_artifact_id(role, provider_id) for role in roles)
    if len(artifact_ids) != len(set(artifact_ids)):
        raise ValueError("HARNESS_CATALOG_MISMATCH:agent-artifact-id-collision")


def plan_agent_artifact(role, *, provider_id, catalog_path, claude_bindings_path=None,
                        claude_bindings=None, pack_prefix=None, answers=None):
    catalog_roles = semantic_agent_roles(catalog_path)
    catalog_role = next((candidate for candidate in catalog_roles
                         if (candidate.pack_id, candidate.role_id)
                         == (role.pack_id, role.role_id)), None)
    if catalog_role != role:
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    _validate_agent_artifact_ids(catalog_roles, provider_id)
    if provider_id == "claude-code" and claude_bindings is None:
        claude_bindings = load_claude_role_bindings(claude_bindings_path, catalog_roles)
    projection = project_agent_role(role, provider_id, claude_bindings=claude_bindings,
                                    pack_prefix=pack_prefix, answers=answers)
    source = ArtifactSource("harness.agent-role.catalog",
                            "packages/harness/configs/common/agent-packs/roles.json",
                            sha256_digest(Path(catalog_path).read_bytes()))
    sources = (source,)
    if provider_id == "claude-code":
        sources += (ArtifactSource("harness.claude.agent-bindings",
                                   "packages/harness/configs/claude-code/agent-packs/role-bindings.json",
                                   sha256_digest(Path(claude_bindings_path).read_bytes())),)
    identity = ArtifactAdapterIdentity(f"harness.{provider_id}.agent", "1.0.1",
                                       ProviderId(provider_id), "1.0.0", ())
    return plan_artifact_render(ArtifactRenderRequest(
        _agent_artifact_id(role, provider_id), sources,
        ArtifactTarget(projection.target_path, ("whole-file", ())), identity, (),
        {"pack_id": role.pack_id, "role_id": role.role_id, "model_class": role.model_class,
         "command_ids": list(role.command_ids), "pack_prefix": pack_prefix or "template",
         "answers": dict(sorted((answers or {}).items()))},
        lambda _request: projection.rendered, contract_version="1.1.0"))


def classify_agent_projection(*, managed: bool, observed: bytes | None, expected: bytes,
                              user_owned: bool = False):
    """Keep P2-style no-adoption and managed-drift states visible for both targets."""
    if user_owned:
        return "ownership-conflict"
    if observed is None:
        return "missing"
    if not managed:
        return "ownership-conflict"
    return "clean" if observed == expected else "managed-drift"


# ── Codex role-projection lifecycle (P2.4, codex-parity-verdicts-v1.md §3.12, bounded
#    closure, D89 §6) ──────────────────────────────────────────────────────────
# Render/check/remove/diagnose `.codex/agents/*.toml` role projections through the
# SAME semantic role catalog and the SAME `project_agent_role`/`plan_agent_artifact`/
# `classify_agent_projection` machinery already proven by the `agents.catalog`
# create/noop self-test (`provider_audit.py`). Scoped to packs already installed
# under Claude (`.claude/agent-pack.lock.json` is the single source of the resolved
# `PACK_PREFIX` — no second interview pass). Excludes role members that are
# Claude-runtime pack artifacts (`.claude/workflows/*.js`, rules, the review-gate
# shell hook) — `project_agent_role` already refuses `command.workflow-carrier`
# roles for Codex, and this closure names the exclusion instead of hiding it. This
# is NOT the interview-driven pack engine above: Codex carries no `pack.json`
# manifest of its own, only the provider-neutral role catalog.
CODEX_ROLES_LOCK_REL = ".codex/agent-roles.lock.json"


def codex_roles_lock_path(target):
    return Path(target) / CODEX_ROLES_LOCK_REL


def load_codex_roles_lock(target):
    return safe_load_json(codex_roles_lock_path(target), default={"schema": 1, "roles": {}})


def write_codex_roles_lock(target, lock, dry):
    lp = codex_roles_lock_path(target)
    if dry:
        print(f"  [dry-run] would update {lp}")
        return
    lp.parent.mkdir(parents=True, exist_ok=True)
    from aicore.util.io import atomic_write_json
    atomic_write_json(lp, lock)
    print(f"  lock: {lp}")


def _codex_installed_pack_prefix(target, pack):
    """Internal documentation."""
    entry = (load_lock(target).get("packs") or {}).get(pack)
    return None if entry is None else entry.get("answers", {}).get("PACK_PREFIX")


def expected_codex_role_projections(env, target, catalog_path=None, *, pack=None):
    """Internal documentation."""
    catalog_path = catalog_path or (Path(env.root) / "configs" / "common" /
                                    "agent-packs" / "roles.json")
    roles = semantic_agent_roles(catalog_path)
    installed_packs = load_lock(target).get("packs") or {}
    pairs, excluded = [], []
    for role in roles:
        if role.pack_id not in installed_packs:
            continue
        if pack is not None and role.pack_id != pack:
            continue
        prefix = _codex_installed_pack_prefix(target, role.pack_id)
        if not prefix:
            continue
        try:
            pairs.append((role, project_agent_role(role, "codex", pack_prefix=prefix)))
        except ValueError as error:
            excluded.append((role.pack_id, role.role_id, str(error)))
    return tuple(pairs), tuple(excluded)


def codex_role_state(target, projection):
    """Internal documentation."""
    path = Path(target) / projection.target_path
    observed = path.read_bytes() if path.exists() else None
    managed = projection.target_path in (load_codex_roles_lock(target).get("roles") or {})
    return classify_agent_projection(managed=managed, observed=observed, expected=projection.rendered)


def do_codex_role_render(env, target, *, pack=None, dry=False):
    """Internal documentation."""
    pairs, excluded = expected_codex_role_projections(env, target, pack=pack)
    lock = load_codex_roles_lock(target)
    roles_lock = lock.setdefault("roles", {})
    changed = False
    print(f"=== agent-packs render --provider codex → {target} ===" + (" [dry-run]" if dry else ""))
    for role, projection in pairs:
        state = codex_role_state(target, projection)
        path = Path(target) / projection.target_path
        if state == "ownership-conflict":
            warn(f"  {projection.target_path}: file exists and is not tracked by this lock'ohm - skip")
            continue
        if state == "clean":
            continue
        if dry:
            print(f"  [dry-run] {'created' if state == 'missing' else 'updated'} would "
                 f"{projection.target_path}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(projection.rendered)
        roles_lock[projection.target_path] = {
            "pack_id": role.pack_id, "role_id": role.role_id,
            "base_sha256": hashlib.sha256(projection.rendered).hexdigest(),
        }
        changed = True
        print(f"  {'create' if state == 'missing' else 'repair'}: {projection.target_path}")
    for pack_id, role_id, reason in excluded:
        print(f"  · {pack_id}.{role_id}: does not map to Codex — {reason}")
    if changed:
        write_codex_roles_lock(target, lock, dry)
    return 0


def do_codex_role_remove(env, target, pack, *, dry=False):
    """Internal documentation."""
    pairs, _excluded = expected_codex_role_projections(env, target, pack=pack)
    if not pairs:
        print(f"agent-pack '{pack}' is not mapped to Codex in {target} — nothing to delete")
        return 0
    lock = load_codex_roles_lock(target)
    roles_lock = lock.setdefault("roles", {})
    print(f"=== agent-packs remove --provider codex: {pack} ← {target} ===" + (" [dry-run]" if dry else ""))
    for _role, projection in pairs:
        state = codex_role_state(target, projection)
        path = Path(target) / projection.target_path
        if state not in ("clean", "missing"):
            warn(f"  {projection.target_path}: {state} — left, remove demolishes only "
                 f"incorrect files")
            continue
        if state == "clean":
            print(f"  [{'dry-run' if dry else 'remove'}] {projection.target_path}")
            if not dry:
                path.unlink()
        if not dry:
            roles_lock.pop(projection.target_path, None)
    if dry:
        return 0
    if roles_lock:
        write_codex_roles_lock(target, lock, dry=False)
    else:
        lp = codex_roles_lock_path(target)
        if lp.exists():
            lp.unlink()
        print(f"  lock: {lp} deleted (empty)")
    return 0


def do_codex_role_doctor(env, target, *, json_out=False, strict=False):
    """Internal documentation."""
    pairs, excluded = expected_codex_role_projections(env, target)
    rows = [{"pack_id": role.pack_id, "role_id": role.role_id,
             "target": projection.target_path, "state": codex_role_state(target, projection)}
            for role, projection in pairs]
    drift = [row for row in rows if row["state"] in ("managed-drift", "ownership-conflict")]
    if json_out:
        print(json.dumps({
            "rows": rows,
            "excluded": [{"pack_id": p, "role_id": r, "reason": reason}
                        for p, r, reason in excluded],
            "drift": len(drift),
        }, ensure_ascii=False, indent=2))
        return 1 if drift and strict else 0
    for row in rows:
        print(f"[{row['state']}] {row['pack_id']}.{row['role_id']} → {row['target']}")
    for pack_id, role_id, reason in excluded:
        print(f"  · {pack_id}.{role_id}: excluded — {reason}")
    print("[OK] drift not found" if not drift else f"[WARN] drift: {len(drift)} entry(to her)")
    return 1 if drift and strict else 0


def expected_cursor_role_consumers(env, target, mapping_path=None, catalog_path=None, *,
                                   pack=None, provider="cursor"):
    """Resolve consumer targets over shared Claude role projections."""
    if provider not in {"cursor", "grok"}:
        raise ValueError("HARNESS_MAPPING_MISSING")
    mapping_path = mapping_path or (Path(env.root) / "configs" / provider /
                                    "agent-packs" / "consumer-mapping.json")
    catalog_path = catalog_path or (Path(env.root) / "configs" / "common" /
                                    "agent-packs" / "roles.json")
    mapping = load_cursor_agent_consumer_mapping(mapping_path)
    roles = semantic_agent_roles(catalog_path)
    installed_packs = load_lock(target).get("packs") or {}
    rows = []
    for role in roles:
        if role.pack_id not in installed_packs:
            continue
        if pack is not None and role.pack_id != pack:
            continue
        prefix = installed_packs[role.pack_id].get("answers", {}).get("PACK_PREFIX")
        if not prefix:
            continue
        rows.append((role, cursor_consumer_target(role, mapping, pack_prefix=prefix)))
    targets = [target_path for _role, target_path in rows]
    if len(targets) != len(set(targets)):
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    return mapping, tuple(rows)


def do_cursor_role_render(env, target, *, pack=None, dry=False, provider="cursor"):
    """Consumer mapping is visibility-only and never writes role files."""
    mapping, rows = expected_cursor_role_consumers(env, target, pack=pack, provider=provider)
    tag = " [dry-run]" if dry else ""
    print(f"=== agent-packs render --provider {provider} → {target} ==={tag}")
    print(f"  consumer-only: no .{provider}/agents writer; shared .claude/agents projection is preserved")
    missing = 0
    for role, target_path in rows:
        state = "visible" if (Path(target) / target_path).is_file() else "missing"
        if state == "missing":
            missing += 1
        print(f"  [{state}] {role.pack_id}.{role.role_id} → {target_path}")
    if not rows:
        print(f"  there are no installed packages with role-projection for {provider}")
    print(f"  projection owner: {mapping.projection_owner}; disconnect policy: {mapping.disconnect_policy}")
    return 0 if missing == 0 else 1


def do_cursor_role_remove(env, target, pack, *, dry=False, provider="cursor"):
    """Removing a consumer mapping never deletes shared Claude projections."""
    _mapping, rows = expected_cursor_role_consumers(env, target, pack=pack, provider=provider)
    tag = " [dry-run]" if dry else ""
    print(f"=== agent-packs remove --provider {provider}: {pack} ← {target} ==={tag}")
    if not rows:
        print("  nothing to delete: consumer mapping does not own role-files")
        return 0
    print("  shared .claude/agents projection remains unchanged (projection_owner=claude-code)")
    for role, target_path in rows:
        print(f"  [preserve] {role.pack_id}.{role.role_id} → {target_path}")
    return 0


def do_cursor_role_doctor(env, target, *, json_out=False, strict=False, pack=None, provider="cursor"):
    mapping, rows = expected_cursor_role_consumers(env, target, pack=pack, provider=provider)
    report = []
    for role, target_path in rows:
        state = "visible" if (Path(target) / target_path).is_file() else "missing"
        report.append({"pack_id": role.pack_id, "role_id": role.role_id,
                       "target": target_path, "state": state})
    missing = [row for row in report if row["state"] == "missing"]
    if json_out:
        print(json.dumps({
            "projection_owner": mapping.projection_owner,
            "projection_consumers": list(mapping.projection_consumers),
            "projection_root": mapping.projection_root,
            "disconnect_policy": mapping.disconnect_policy,
            "rows": report,
            "missing": len(missing),
        }, ensure_ascii=False, indent=2))
        return 1 if missing and strict else 0
    print(f"=== agent-packs doctor --provider {provider} → {target} ===")
    for row in report:
        print(f"[{row['state']}] {row['pack_id']}.{row['role_id']} → {row['target']}")
    if not report:
        print(f"not installed role-projections for {provider} consumer mapping")
    print(f"[OK] projection owner: {mapping.projection_owner}; disconnect: {mapping.disconnect_policy}")
    return 1 if missing and strict else 0
