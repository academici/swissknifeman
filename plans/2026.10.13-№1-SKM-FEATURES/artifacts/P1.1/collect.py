#!/usr/bin/env python3
"""One-off baseline collector for PLAN4 P1.1 (not a product file). A rerun overwrites baseline.json.

Usage: collect.py [--log FILE] [--reuse-log]   (run from the hub root; --reuse-log parses an earlier ci-matrix log)
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HUB = Path(__file__).resolve().parents[4]
OUT = Path(__file__).with_name("baseline.json")
PLAN3 = HUB / "plans" / "2026.10.07-№1-SKM-ECOSYSTEM"
STATUS = re.compile(r"^(ok|fail|skip) (\S+) (\S+) ([0-9.]+)$")
RAN = re.compile(r"^(?:tests: (?:OK|FAILED) \()?Ran (\d+) tests?")
SUMMARY = re.compile(r"(FAILED|OK)(?: \((.*)\))?")


def tmp_env(extra=None):
    home = tempfile.mkdtemp(prefix="skm-baseline-")
    env = dict(os.environ, HOME=home, SKM_HOME=home)
    env.update(extra or {})
    return env


def sh(argv, **kw):
    return subprocess.run(argv, cwd=str(HUB), capture_output=True, text=True, **kw)


def version(cmd):
    try:
        out = sh([cmd, "--version"]).stdout.strip().splitlines()
    except OSError:
        return None
    m = re.search(r"\d+\.\d+\.\d+", out[0]) if out else None
    return m.group(0) if m else None


def run_matrix(log):
    with open(log, "w", encoding="utf-8") as fh:
        subprocess.run([sys.executable, "scripts/ci-matrix.py", "run", "--all"], cwd=str(HUB), stdout=fh,
                       stderr=subprocess.STDOUT)


def parse_matrix(log):
    units, tests, pending = {}, {}, {"ran": 0, "failures": 0, "errors": 0, "skipped": 0}
    for line in Path(log).read_text(encoding="utf-8", errors="replace").splitlines():
        m = RAN.match(line)
        if m:
            pending["ran"] += int(m.group(1))
            continue
        m = SUMMARY.match(line)
        if m and m.group(2):
            for key, val in re.findall(r"(failures|errors|skipped)=(\d+)", m.group(2)):
                pending[key] += int(val)
            continue
        m = STATUS.match(line)
        if m:
            state, unit, step, sec = m.groups()
            units.setdefault(unit, {})[step] = {"status": state, "seconds": float(sec)}
            if step == "test":
                tests[unit] = pending
                pending = {"ran": 0, "failures": 0, "errors": 0, "skipped": 0}
    return units, tests


def skills():
    sys.path.insert(0, str(HUB / "packages" / "aicore" / "lib"))
    from aicore.content.budget import estimate_tokens, skill_budget
    rows, total_bytes = [], 0
    for md in sorted((HUB / "packages" / "skiller" / "skills").glob("*/*/SKILL.md")):
        bud = skill_budget(md.parent)
        text = md.read_text(encoding="utf-8-sig")
        rows.append({"key": f"{md.parent.parent.name}/{md.parent.name}", "bytes": len(text.encode("utf-8")),
                     "tokens": estimate_tokens(text), "tier": bud})
        total_bytes += rows[-1]["bytes"]
    rows.sort(key=lambda r: -r["tokens"])
    top = [{k: r[k] for k in ("key", "bytes", "tokens")} for r in rows[:20]]
    return {"count": len(rows), "bytes": total_bytes, "tokens": sum(r["tokens"] for r in rows), "top": top}


def first_turn():
    proc = sh(["bash", "packages/skiller/bin/skiller", "budget", "--first-turn", "--json"],
              env=tmp_env({"SKM_DEV_ALLOW_LIVE": "1"}))
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return {"tokens": None, "verdict": None, "error": (proc.stderr or proc.stdout).strip()[:300]}
    tokens = data.get("tokens", data.get("total", data.get("first_turn_tokens")))
    return {"tokens": tokens, "verdict": data.get("verdict"), "raw_keys": sorted(data)}


def plan3():
    events = [json.loads(l) for l in (PLAN3 / "log.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    finishes = [e for e in events if e["type"] == "finish"]
    deviations = [e for e in events if e["type"] == "deviation"]
    without = [e for e in deviations if not ((e.get("data") or {}).get("impact") and (e.get("data") or {}).get("next"))]
    items = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((PLAN3 / "phases").glob("*/P*.*.json"))]
    return {"finish_events": len(finishes), "deviation_events": len(deviations),
            "deviations_without_impact_or_next": len(without),
            "items_done_with_deviations": sum(1 for i in items if i.get("status") == "done_with_deviations"),
            "items_total": len(items)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=str(Path(tempfile.gettempdir()) / "p1.1-ci-matrix.log"))
    ap.add_argument("--reuse-log", action="store_true")
    args = ap.parse_args()
    if not args.reuse_log:
        run_matrix(args.log)
    units, tests = parse_matrix(args.log)
    check = sh([sys.executable, "scripts/ecosystem-units.py", "check"], env=tmp_env())
    data = {
        "commit": sh(["git", "rev-parse", "HEAD"]).stdout.strip(),
        "date": datetime.date.today().isoformat(),
        "python": ".".join(map(str, sys.version_info[:3])),
        "units": units,
        "tests": tests,
        "ecosystem_units_check": "ok" if check.returncode == 0 else "fail",
        "skills": skills(),
        "first_turn": first_turn(),
        "providers": {name: version(name) for name in ("claude", "codex", "grok")},
        "plan3_deviations": plan3(),
    }
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
