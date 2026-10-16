"""Read-only audits and explicit, recoverable collection of expired/junk memory."""
import json
import subprocess
import time
import uuid
from collections import Counter
from datetime import datetime, timezone

from . import memory_policy as policy
from aicore.util.io import atomic_write_json, atomic_write_text
from aicore.util.term import die
from aicore.util.cli import parse_args


def audit(rows, *, now=None, selected_ids=()):
    now = time.time() if now is None else now
    scopes, writers, reasons, kept_scopes = Counter(), Counter(), Counter(), Counter()
    candidates, keep, seen, slots = [], [], set(), set()
    selected_ids = set(selected_ids)
    ordered = sorted(rows, key=lambda r: str(r.get("createdAt") or r.get("timestamp") or ""), reverse=True)
    for row in ordered:
        scope, text, meta = policy.record_parts(row)
        scopes[scope or "unscoped"] += 1
        writers[(meta or {}).get("writer", "unknown")] += 1
        reason = "owner-selected" if row.get("id") in selected_ids else policy.prune_reason(row, now=now)
        if not reason and (scope, text) in seen:
            reason = "duplicate"
        if not reason and text.startswith("[active-handoff]") and scope in slots:
            reason = "old-handoff"
        if not reason and kept_scopes[scope] >= policy.MAX_SCOPE_ITEMS:
            reason = "scope-cap"
        if reason:
            reasons[reason] += 1
            candidates.append({"id": row.get("id"), "scope": scope, "reason": reason})
        else:
            keep.append(row)
            kept_scopes[scope] += 1
            seen.add((scope, text))
            if text.startswith("[active-handoff]"):
                slots.add(scope)
    return {"total": len(rows), "keep": len(keep), "remove": len(candidates),
            "scopes": dict(scopes), "writers": dict(writers), "reasons": dict(reasons),
            "candidates": candidates}


def prune(env, url, headers, rows, *, apply=False, selected_ids=()):
    from .memory import export, forget
    report = audit(rows, selected_ids=selected_ids)
    if not apply:
        return report
    directory = env.state_dir / "memory-backups"
    if directory.exists():
        for path in directory.glob("*.json"):
            if path.is_file() and not path.is_symlink() and path.stat().st_mtime < time.time() - 7 * 86400:
                path.unlink()
    if not report["candidates"]:
        return {**report, "deleted": 0}
    if any(not c["id"] for c in report["candidates"]):
        raise RuntimeError("prune requires an exact id for every candidate")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"{stamp}-{uuid.uuid4().hex[:8]}.json"
    atomic_write_json(path, {"url": url, "audit": report, "memories": rows})
    path.chmod(0o600)
    # Revalidate exact rows after taking the backup; concurrent replacement is never deleted.
    current = {r.get("id"): r for r in export(url, "", headers)}
    original = {r.get("id"): r for r in rows}
    deleted, skipped, errors = [], [], []
    for candidate in report["candidates"]:
        mid = candidate["id"]
        if current.get(mid) != original[mid]:
            skipped.append(mid)
            continue
        try:
            result = forget(url, candidate["scope"], mid, headers=headers)
            if isinstance(result, dict) and result.get("success") is False:
                raise RuntimeError("daemon rejected deletion")
            deleted.append(mid)
        except RuntimeError as e:
            errors.append({"id": mid, "error": str(e)})
    remaining = {r.get("id") for r in export(url, "", headers)}
    failed = [mid for mid in deleted if mid in remaining]
    return {**report, "backup": str(path), "deleted": len(deleted) - len(failed),
            "skipped_changed": skipped, "errors": errors, "still_present": failed}


def install_gc(env):
    """Install hourly collection for this node's configured host; no daemon restart."""
    from .provision.service import _ensure_systemd
    _ensure_systemd()
    directory = env.home / ".config" / "systemd" / "user"
    directory.mkdir(parents=True, exist_ok=True)
    launcher = str(env.root / "bin" / "maind").replace("%", "%%").replace('"', '\\"')
    atomic_write_text(directory / "maind-memory-gc.service", f'''[Unit]
Description=mAInd expired working memory collection
After=network-online.target

[Service]
Type=oneshot
ExecStart="{launcher}" memory prune --all --apply --json
''')
    atomic_write_text(directory / "maind-memory-gc.timer", '''[Unit]
Description=Collect expired mAInd memory hourly

[Timer]
OnCalendar=hourly
Persistent=true
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
''')
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", "maind-memory-gc.timer"], check=True)
    print(f"Hourly memory GC enabled: {directory / 'maind-memory-gc.timer'}")


def cmd_maintenance(env, config, sub, argv):
    from .memory import _memory_target, _require_daemon, export
    opts, _ = parse_args(argv, {"--all": "bool", "--apply": "bool", "--json": "bool",
                               "--project": "str", "--scope": "str", "--ids": "str"}, max_pos=0)
    if opts["help"]:
        print(f"maind memory {sub} [--project ID|--scope S|--all] [--apply] [--ids id1,id2] [--json]")
        return
    if sub == "gc-install":
        install_gc(env)
        return
    if opts["all"] and (opts.get("scope") or opts.get("project")):
        die("--all cannot be combined with --scope or --project")
    url, headers = _require_daemon(env, config)
    rows = export(url, "", headers)
    if not opts["all"]:
        _proj, _write, scopes = _memory_target(env, config, opts)
        rows = [r for r in rows if policy.record_parts(r)[0] in scopes]
    selected_ids = set((opts.get("ids") or "").split(",")) - {""}
    if selected_ids - {r.get("id") for r in rows}:
        die("--ids contains ids outside the selected pool")
    report = prune(env, url, headers, rows, apply=sub == "prune" and opts["apply"], selected_ids=selected_ids)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report.get("errors") or report.get("still_present"):
        die("memory pruning incomplete; consult report and backup")
