#!/usr/bin/env python3
"""Internal documentation."""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import parse_events  # noqa: E402

_DEFAULT_KEEP = 30


def _report_root(cwd):
    """Internal documentation."""
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        root = result.stdout.strip()
        if result.returncode == 0 and root:
            return root
    except (OSError, subprocess.SubprocessError):
        pass
    return cwd


def _carrier(cwd, key):
    """Value of `key` in the committed carrier .swissknifeman/hooks.env (provider key first)."""
    try:
        text = (Path(cwd) / ".swissknifeman" / "hooks.env").read_text(encoding="utf-8")
    except Exception:
        return None
    found = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            found[k.strip()] = v.strip()
    return found.get(key + "__CLAUDE_CODE", found.get(key))


def _read_enabled(cwd):
    """Internal documentation."""
    enabled, keep, digest = True, _DEFAULT_KEEP, True
    if not cwd:
        return enabled, keep, digest
    carried = _carrier(cwd, "RUN_REPORT_ENABLED")
    if carried is not None:
        enabled = carried.lower() not in ("off", "0", "false", "no")
    carried_keep = _carrier(cwd, "RUN_REPORT_RUNS_KEEP")
    if carried_keep is not None:
        try:
            keep = max(1, int(carried_keep))
        except ValueError:
            carried_keep = None
    f = Path(cwd) / ".claude" / "run-report.env.ini"
    try:
        text = f.read_text(encoding="utf-8")
    except Exception:
        return enabled, keep, digest
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = (x.strip() for x in line.split("=", 1))
        if k == "ENABLED" and carried is None:
            enabled = v.lower() not in ("off", "0", "false", "no")
        elif k == "RUNS_KEEP" and carried_keep is None:
            try:
                keep = max(1, int(v))
            except ValueError:
                pass
        elif k == "DIGEST":
            digest = v.lower() not in ("off", "0", "false", "no")
    return enabled, keep, digest


def _ensure_gitignore(runs_dir):
    """Internal documentation."""
    gi = runs_dir / ".gitignore"
    try:
        if not gi.exists():
            gi.write_text("*\n", encoding="utf-8")
    except OSError:
        pass


def _atomic_write_json(path, data):
    """Internal documentation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_gitignore(path.parent)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _prune(runs_dir, keep):
    """Internal documentation."""
    try:
        files = sorted(runs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files[keep:]:
            p.unlink(missing_ok=True)
    except Exception:
        pass


_TREND_LIMIT = 4000
_TREND_KEEP = 2000


def _prune_trend(f):
    """Internal documentation."""
    try:
        lines = f.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lines) <= _TREND_LIMIT:
        return
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text("\n".join(lines[-_TREND_KEEP:]) + "\n", encoding="utf-8")
    os.replace(tmp, f)


def _append_trend(cwd, sid, report):
    """Internal documentation."""
    try:
        usage = report.get("usage") or {}
        totals = usage.get("totals") or {}
        by_model = usage.get("by_model") or {}
        agents = usage.get("agents") or []
        main_agent = agents[0] if agents else {}
        analyze_dir = Path(cwd) / ".claude" / "analyze"
        analyze_dir.mkdir(parents=True, exist_ok=True)
        gi = analyze_dir / ".gitignore"
        if not gi.exists():
            gi.write_text("*\n", encoding="utf-8")
        entry = {
            "ts": report.get("generated_at"),
            "session": sid,
            "in": totals.get("in", 0),
            "out": totals.get("out", 0),
            "cache_read": totals.get("cache_read", 0),
            "cache_creation": totals.get("cache_creation", 0),
            "by_model": {m: {"in": v.get("in", 0), "out": v.get("out", 0)}
                        for m, v in by_model.items() if isinstance(v, dict)},
            "tools_total": (report.get("tools") or {}).get("total", 0),
            "files_changed": len(report.get("files_changed") or []),
            "agents": len(agents),
            "wall_s": main_agent.get("wall_seconds"),
            "retr_chars": (report.get("retrieval") or {}).get("result_chars", 0),
        }
        f = analyze_dir / "usage-trend.ndjson"
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _prune_trend(f)
    except Exception:
        pass


def _analyst_bin():
    """Partner lookup (hook-side copy of aicore.util.partners): ANALYST_BIN (deprecated) -> SKM_ANALYST_BIN
    -> SKM_ANALYST_ROOT/bin/analyst -> PATH; None when not found."""
    import shutil
    candidates = [os.environ.get("ANALYST_BIN"), os.environ.get("SKM_ANALYST_BIN")]
    root = os.environ.get("SKM_ANALYST_ROOT")
    if root:
        candidates.append(os.path.join(os.path.expanduser(root), "bin", "analyst"))
    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return shutil.which("analyst")


def _run_digest(cwd, sid):
    """Internal documentation."""
    try:
        import subprocess
        bin_ = _analyst_bin()
        if not bin_:
            return
        subprocess.run([bin_, "digest", "--session", sid],
                       cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=30, check=False)
    except Exception:
        pass


def main():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)
    if not isinstance(payload, dict):
        sys.exit(0)

    cwd = payload.get("cwd") or os.getcwd()
    enabled, keep, digest = _read_enabled(cwd)
    if not enabled:
        sys.exit(0)

    tpath = payload.get("transcript_path")
    if not tpath or not isinstance(tpath, str):
        sys.exit(0)
    tpath = os.path.expanduser(tpath)
    if not os.path.isfile(tpath):
        sys.exit(0)

    sid = payload.get("session_id") or "session"
    sid = "".join(c for c in str(sid) if c.isalnum() or c in "-_") or "session"

    try:
        with open(tpath, encoding="utf-8", errors="replace") as fh:


            report = parse_events(fh, transcript_path=tpath, cwd=cwd)
    except Exception:
        sys.exit(0)

    report["session_id"] = sid
    report["cwd"] = cwd
    report["reason"] = payload.get("reason") or ""
    try:
        from datetime import datetime, timezone
        report["generated_at"] = datetime.now(timezone.utc).isoformat()
    except Exception:
        report["generated_at"] = None

    runs_dir = Path(_report_root(cwd)) / ".claude" / "runs"
    try:
        _atomic_write_json(runs_dir / f"{sid}.json", report)
        _prune(runs_dir, keep)
    except Exception:
        sys.exit(0)
    _append_trend(cwd, sid, report)
    if digest:
        _run_digest(cwd, sid)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
