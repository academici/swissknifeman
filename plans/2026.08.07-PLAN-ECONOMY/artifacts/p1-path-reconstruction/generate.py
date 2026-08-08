#!/usr/bin/env python3
"""Rebuild the P1.5 v2 read-path reconstruction and feasibility artifact.

The script reads real layout-v1 plans, extracts only selectors explicitly present in each
item's Required Reads, materializes the five v2 slots, and measures every resulting file with
the frozen token-estimate calibration. It is intentionally scoped to the six P1.5 samples.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "packages/task/lib"))

from task import plan_lint, plan_weight, token_estimate  # noqa: E402


PLAN_ROOT = REPO / "plans/2026.08.07-PLAN-ECONOMY"
OUT = Path(__file__).resolve().parent
SOURCE_TREE = "b82aa8ee"
SAMPLES = (
    {
        "class": "large",
        "plan_dir": REPO / "plans/2026.08.07-PLAN-ECONOMY",
        "items": ("P2.1", "P0.4", "P0.5"),
    },
    {
        "class": "healthy",
        "plan_dir": REPO / "plans/archive/2026.07.15-TOKEN-ECON-P6",
        "items": ("P6.1", "P7.1", "P7.2"),
    },
)
EXTRA_INPUTS = {
    ("2026.07.15-TOKEN-ECON-P6", "P6.1"): (
        ("budget.py:337-354", "packages/skiller/lib/skiller/budget.py", "lines:337-354"),
        ("скилл `skill-authoring`", "packages/skiller/skills/repository-bootstrap/skill-authoring/SKILL.md", "whole-file"),
    ),
}
FIELD_RE = re.compile(r"^\*\*([^*]+):\*\*\s*(.*)$")
ITEM_RE = re.compile(r"^### (P\d+\.\d+) — ")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
LINE_RANGE_RE = re.compile(r"(?:строк(?:и|а)?|lines?)\s+(\d+)\s*[–-]\s*(\d+)", re.I)
SECTION_RANGE_RE = re.compile(r"§\s*(\d+(?:\.\d+)?)\s*[–-]\s*§?\s*(\d+(?:\.\d+)?)")
SECTION_RE = re.compile(r"§\s*(\d+(?:\.\d+)?)")
DECISION_RE = re.compile(r"\bD\d+\b")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_bytes(path: Path) -> bytes:
    relpath = path.resolve().relative_to(REPO).as_posix()
    completed = subprocess.run(
        ["git", "show", f"{SOURCE_TREE}:{relpath}"],
        cwd=REPO,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise ValueError(
            f"source path is absent from pinned tree {SOURCE_TREE}: {relpath}: "
            f"{completed.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return completed.stdout


def read(path: Path) -> str:
    return source_bytes(path).decode("utf-8", errors="replace")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def section(lines: list[str], title_prefix: str) -> str:
    start = next(i for i, line in enumerate(lines) if line.startswith(title_prefix))
    level = len(lines[start]) - len(lines[start].lstrip("#"))
    end = len(lines)
    for i in range(start + 1, len(lines)):
        match = HEADING_RE.match(lines[i])
        if match and len(match.group(1)) <= level:
            end = i
            break
    return "\n".join(lines[start:end]).rstrip() + "\n"


def plan_core(plan_dir: Path) -> str:
    lines = read(plan_dir / "plan.md").splitlines()
    identity = [lines[0], "", "## Identity"]
    wanted = {"Plan ID", "Title", "Repository", "Document Type", "Home"}
    for line in lines:
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) >= 2 and cells[0] in wanted:
                identity.append(f"- {cells[0]}: {cells[1]}")
    parts = ["\n".join(identity).rstrip() + "\n"]
    for prefix in ("## 1. Context", "## 2. Execution Rules", "## 3. Routing"):
        parts.append(section(lines, prefix))
    return "\n".join(parts)


def phase_context(phase_path: Path) -> str:
    lines = read(phase_path).splitlines()
    return lines[0] + "\n\n" + section(lines, "## Phase Context")


def item_spec(phase_path: Path, item_id: str) -> tuple[str, str, str]:
    lines = read(phase_path).splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"### {item_id} — "))
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if ITEM_RE.match(lines[i]) or lines[i].startswith("## Phase Handoff"):
            end = i
            break
    block = lines[start:end]
    fields: dict[str, list[str]] = {}
    current = None
    for line in block[1:]:
        match = FIELD_RE.match(line)
        if match:
            current = match.group(1)
            fields[current] = [match.group(2)]
        elif current is not None:
            fields[current].append(line)
    stable_order = (
        "Intent", "Why", "Scope Included", "Scope Excluded", "Inputs", "Files",
        "Required Reads", "Implementation Rules", "Code Guidance", "Validation", "Deliverables",
    )
    out = [block[0], ""]
    for name in stable_order:
        value = "\n".join(fields.get(name, ["—"])).rstrip()
        separator = "" if value.startswith("\n") else " "
        out.append(f"**{name}:**{separator}{value}")
    status = "\n".join(fields.get("Status", ["⬜ Not started"])).strip()
    required = "\n".join(fields.get("Required Reads", ["—"])).strip()
    return "\n".join(out).rstrip() + "\n", required, status


def heading_numbers(entry: str) -> list[str]:
    result: list[str] = []
    for left, right in SECTION_RANGE_RE.findall(entry):
        if "." not in left and "." not in right:
            result.extend(str(value) for value in range(int(left), int(right) + 1))
        else:
            result.extend((left, right))
    for value in SECTION_RE.findall(entry):
        if value not in result:
            result.append(value)
    return result


def markdown_sections(text: str, numbers: list[str], names: list[str] | None = None) -> str:
    lines = text.splitlines()
    selected: list[str] = []
    names = names or []
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if not match:
            continue
        title = match.group(2).strip()
        number_hit = any(re.match(rf"^§?\s*{re.escape(number)}(?:\D|$)", title) for number in numbers)
        name_hit = any(name.casefold() in title.casefold() for name in names)
        if not (number_hit or name_hit):
            continue
        level = len(match.group(1))
        end = len(lines)
        for cursor in range(index + 1, len(lines)):
            following = HEADING_RE.match(lines[cursor])
            if following and len(following.group(1)) <= level:
                end = cursor
                break
        selected.extend(lines[index:end])
        selected.append("")
    if not selected:
        raise ValueError(f"declared markdown selector did not resolve: sections={numbers}, names={names}")
    return "\n".join(selected).rstrip() + "\n"


def plan_decision_slice(text: str, entry: str) -> str:
    lines = text.splitlines()
    parts = [section(lines, "## 2. Execution Rules")]
    wanted = set(DECISION_RE.findall(entry))
    decision_rows = [line for line in lines if line.startswith("| D") and line.split("|")[1].strip() in wanted]
    parts.append("## 5. Decision Log — selected rows\n\n| D# | Дата | Решение | Почему |\n|:--|:--|:--|:--|\n" + "\n".join(decision_rows) + "\n")
    parts.append(section(lines, "## 7. Contracts"))
    return "\n".join(parts)


def python_symbols(text: str, symbols: list[str]) -> str:
    tree = ast.parse(text)
    lines = text.splitlines()
    blocks: list[str] = []
    for node in tree.body:
        names: list[str] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [target.id for target in targets if isinstance(target, ast.Name)]
        if any(name in symbols for name in names):
            blocks.extend(lines[node.lineno - 1 : node.end_lineno])
            blocks.append("")
    return "\n".join(blocks).rstrip() + ("\n" if blocks else "")


def select_text(path: Path, entry: str, explicit: str | None = None) -> tuple[str, str]:
    text = read(path)
    if explicit and explicit.startswith("lines:"):
        start, end = map(int, explicit.split(":", 1)[1].split("-", 1))
        return "\n".join(text.splitlines()[start - 1 : end]).rstrip() + "\n", explicit
    if explicit == "whole-file" or "целиком" in entry:
        return text, "whole-file"
    ranges = [(int(a), int(b)) for a, b in LINE_RANGE_RE.findall(entry)]
    if ranges:
        lines = text.splitlines()
        chunks = ["\n".join(lines[start - 1 : end]) for start, end in ranges]
        if "докстр" in entry and path.suffix == ".py":
            module = ast.parse(text)
            doc = ast.get_docstring(module, clean=False)
            if doc:
                chunks.insert(0, '"""' + doc + '"""')
        return "\n\n".join(chunks).rstrip() + "\n", ",".join(f"lines:{a}-{b}" for a, b in ranges)
    if path.name == "plan.md" and "Decision Log" in entry:
        return plan_decision_slice(text, entry), "sections:2,5:selected-decisions,7"
    numbers = heading_numbers(entry)
    quoted = re.findall(r"«([^»]+)»", entry)
    if path.suffix == ".md" and (numbers or (quoted and "раздел" in entry)):
        return markdown_sections(text, numbers, quoted), "sections:" + ",".join(numbers + quoted)
    if path.suffix == ".py":
        symbols = [token for token in re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", entry)]
        if "докстр" in entry:
            module = ast.parse(text)
            doc = ast.get_docstring(module, clean=False) or ""
        else:
            doc = ""
        body = python_symbols(text, symbols)
        if doc or body:
            chunks = [('"""' + doc + '"""') if doc else "", body]
            return "\n\n".join(chunk for chunk in chunks if chunk).rstrip() + "\n", "symbols:" + ",".join(symbols)
    return text, "whole-file"


def required_inputs(plan_dir: Path, plan_id: str, item_id: str, required: str) -> list[dict]:
    repo_root = plan_weight.repo_root_for(plan_dir)
    roots = [plan_dir, repo_root]
    inputs: list[dict] = []
    seen: set[Path] = set()
    for entry in plan_weight.split_entries(required):
        hits = 0
        for token, _declared in plan_weight.path_candidates(entry):
            path = plan_weight.resolve_candidate(token, roots)
            if path is None or path in seen:
                continue
            seen.add(path)
            try:
                selected, selector = select_text(path, entry)
            except ValueError as exc:
                raise ValueError(f"{plan_id} {item_id}: {path}: {entry}: {exc}") from exc
            inputs.append({"path": path, "entry": entry, "selector": selector, "text": selected})
            hits += 1
        for marker, relpath, selector in EXTRA_INPUTS.get((plan_id, item_id), ()):
            if marker not in entry:
                continue
            path = REPO / relpath
            if path not in seen:
                seen.add(path)
                selected, normalized = select_text(path, entry, selector)
                inputs.append({"path": path, "entry": entry, "selector": normalized, "text": selected})
            hits += 1
        if hits == 0:
            raise ValueError(f"{plan_id} {item_id}: Required Reads entry did not resolve: {entry}")
    if required != "—" and not inputs:
        raise ValueError(f"{plan_id} {item_id}: Required Reads resolved to zero inputs")
    return inputs


def legacy_floor_bytes(plan_record: dict) -> int:
    return max(
        (
            sum(file["bytes"] for file in item["files"] if file["role"] != "required_read")
            for item in plan_record["items"]
        ),
        default=0,
    )


def measured_file(path: Path, slot: str, artifact: dict, limits: dict) -> dict:
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    estimate = token_estimate.estimate_text(text, artifact=artifact)
    return {
        "path": str(path.relative_to(PLAN_ROOT)),
        "slot": slot,
        "bytes": len(raw),
        "tokens": estimate,
        "passes_single_read": len(raw) <= limits["size_bytes"] and estimate <= limits["tokens"],
    }


def main() -> None:
    artifact = token_estimate.load_artifact()
    limits = plan_weight.load_read_limit()
    fleet_path = PLAN_ROOT / "artifacts/fleet-weight.json"
    fleet = json.loads(fleet_path.read_text(encoding="utf-8"))
    legacy_plans = {plan["plan_id"]: plan for plan in fleet["plans"]}
    generator_hash = sha256(Path(__file__).read_bytes())
    threshold = 100000
    result = {
        "schema": "p1-feasibility-v1",
        "generated_by": "artifacts/p1-path-reconstruction/generate.py",
        "generator_sha256": generator_hash,
        "source_tree": SOURCE_TREE,
        "unit": {
            "calibration_id": f"token-estimate-calibration@{artifact['version']}",
            "provider": artifact["calibration_target"]["provider"],
            "model_id": artifact["calibration_target"]["requested_model_id"],
            "adapter": artifact["calibration_target"]["adapter"],
            "probe_protocol": artifact["calibration_target"]["probe_protocol_version"],
            "per_file_overhead_tokens": artifact["per_file_overhead_tokens"],
        },
        "threshold": threshold,
        "single_read_limits": {
            "size_bytes": limits["size_bytes"],
            "tokens": limits["tokens"],
        },
        "measurement_kind": "reconstruction estimate, not implemented-layout proof",
        "plans": [],
    }
    for sample in SAMPLES:
        plan_dir: Path = sample["plan_dir"]
        diag = plan_lint.Diagnostics()
        meta, _ = plan_lint.parse_plan_md(plan_dir / "plan.md", diag)
        plan_id = meta["Plan ID"][0]
        legacy_plan = legacy_plans[plan_id]
        legacy = {item["item_id"]: item for item in legacy_plan["items"]}
        core = plan_core(plan_dir)
        plan_out = {
            "plan_id": plan_id,
            "source": str(plan_dir.relative_to(REPO)),
            "weight_class": sample["class"],
            "legacy_floor_bytes": legacy_floor_bytes(legacy_plan),
            "legacy_baseline": {
                "source": str(fleet_path.relative_to(REPO)),
                "source_sha256": sha256(fleet_path.read_bytes()),
            },
            "items": [],
        }
        for item_id in sample["items"]:
            phase_id = item_id.split(".")[0]
            phase_path = plan_dir / "phases" / f"{phase_id}.md"
            phase = phase_context(phase_path)
            spec, required, status = item_spec(phase_path, item_id)
            inputs = required_inputs(plan_dir, plan_id, item_id, required)
            item_out = OUT / "samples" / plan_id / item_id
            core_path = item_out / "01-plan-core.md"
            phase_out = item_out / "02-phase-context.md"
            spec_path = item_out / "03-item-spec.md"
            write(core_path, core)
            write(phase_out, phase)
            write(spec_path, spec)
            bundle_inputs = []
            for order, input_ in enumerate(inputs, 1):
                suffix = input_["path"].suffix or ".txt"
                fragment = item_out / f"04-input-{order:02d}{suffix}"
                write(fragment, input_["text"])
                source_raw = source_bytes(input_["path"])
                selected_raw = fragment.read_bytes()
                bundle_inputs.append({
                    "order": order,
                    "source": str(input_["path"].relative_to(REPO)),
                    "selector": input_["selector"],
                    "source_sha256": sha256(source_raw),
                    "selected_sha256": sha256(selected_raw),
                    "fragment": str(fragment.relative_to(PLAN_ROOT)),
                })
            bundle = {
                "schema": "p1-reconstruction-bundle-v1",
                "plan_id": plan_id,
                "item_id": item_id,
                "inputs": bundle_inputs,
            }
            bundle_path = item_out / "04-bundle.json"
            write(bundle_path, json.dumps(bundle, ensure_ascii=False, indent=2) + "\n")
            input_digest = sha256(
                b"".join(path.read_bytes() for path in (core_path, phase_out, spec_path, bundle_path))
            )
            state = {
                "projection_meta": {
                    "projection": "item-state",
                    "projection_version": "1.0.0",
                    "source_scope": {
                        "item": item_id,
                        "event_types": ["attempt"],
                        "subjects": [item_id],
                        "ordering": "journal line ascending",
                    },
                    "through": {"journal_line": 0, "ts": "2026-08-08T00:00:00Z"},
                    "inputs_sha256": input_digest,
                    "generated_by": {"name": "p1-path-reconstruction", "version": "1.0.0"},
                },
                "state": {
                    "world": {"paths": [], "commits": []},
                    "position": {"status": status, "attempt": 0, "last_result": None},
                    "next_step": f"Execute {item_id} according to its stable specification.",
                    "active_context": {"risks": [], "workarounds": [], "decisions": []},
                    "history_pointer": {
                        "view": f".plan-cache/history/{item_id}.md",
                        "command": f"task plan-view history {item_id}",
                    },
                },
            }
            state_path = item_out / "05-item-state.json"
            write(state_path, json.dumps(state, ensure_ascii=False, indent=2) + "\n")
            files = [
                measured_file(core_path, "plan-core", artifact, limits),
                measured_file(phase_out, "phase-context", artifact, limits),
                measured_file(spec_path, "item-spec", artifact, limits),
                measured_file(bundle_path, "item-inputs-manifest", artifact, limits),
                *(measured_file(item_out / Path(row["fragment"]).name, "item-input", artifact, limits)
                  for row in bundle_inputs),
                measured_file(state_path, "item-state", artifact, limits),
            ]
            total = sum(file["tokens"] for file in files)
            item_record = {
                "item": item_id,
                "selected_as": "heaviest Required Reads" if item_id in {"P2.1", "P6.1"} else "representative",
                "legacy_v1_tokens_lower_bound": legacy[item_id]["weight_tokens"],
                "files": files,
                "slots": {
                    slot: sum(file["tokens"] for file in files if file["slot"] == slot)
                    for slot in sorted({file["slot"] for file in files})
                },
                "total": total,
                "threshold": threshold,
                "passes": total <= threshold and all(file["passes_single_read"] for file in files),
                "unresolved_inputs": [],
            }
            plan_out["items"].append(item_record)
        result["plans"].append(plan_out)
    result["sample_aggregate"] = {
        "legacy_v1_tokens_lower_bound": sum(
            item["legacy_v1_tokens_lower_bound"] for plan in result["plans"] for item in plan["items"]
        ),
        "reconstructed_v2_tokens": sum(
            item["total"] for plan in result["plans"] for item in plan["items"]
        ),
        "scope_escape_answer": "No mandatory declared input was excluded; explicit slices remain in the measured bundle. This sample does not prove the whole-plan closed-graph aggregate.",
    }
    write(PLAN_ROOT / "artifacts/p1-feasibility.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        plan["plan_id"]: {item["item"]: item["total"] for item in plan["items"]}
        for plan in result["plans"]
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
