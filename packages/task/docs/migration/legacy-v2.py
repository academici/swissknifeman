#!/usr/bin/env python3
"""Temporary explicit mapper for the common Layout-v2 Markdown carriers.

The script reads source Markdown as migration input and emits only a current Task snapshot plus a
source map. It is deliberately outside runtime and does not execute commands found in a plan.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

TASK = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK / "lib"))
from task.plan import schema, snapshot, store
from task.plan.model import id_sort_key, phase_status

URN = "urn:swissknifeman:task:plan:"
EMPTY = {"", "—", "-", "no", "none", "null"}
EFFORTS = ("low", "medium", "high", "xhigh", "max", "ultra")
STATUS = {
    "Not started": "todo", "In progress": "in_progress", "Done with deviations": "done_with_deviations",
    "Done": "done", "Blocked": "blocked", "Skipped by decision": "skipped",
}
ROOT_CARRIERS = {
    "index.md", "plan.md", "roadmap.md", "status.md", "handoff.md", "open-questions.md",
    "session-routing.md", "execution-batches.md", "execution-commands.md", "execution-phase-audits.md",
    "execution-prompts.md", "DRIVER.md",
}
COMMAND_START = re.compile(
    r"^(?:python\d*|php|composer|npm|pnpm|yarn|bun|make|git|docker|pytest|uv|bash|sh|test|jq|rg|grep|"
    r"curl|\./|vendor/bin/|npx|dart|flutter|go|cargo|node|deno|mysql|psql|redis-cli|task\b|skiller\b|"
    r"plan\.py\b|mypy|ruff|eslint|tsc|vitest|pest|phpunit)", re.I)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_journal(text: str, source: str) -> list[dict]:
    events = []
    for number, line in enumerate(text.splitlines(), 1):
        if line.strip():
            record = json.loads(line)
            record["_source_line"] = number
            record["_source_file"] = source
            events.append(record)
    return events


def recover_authentic_journal(current: list[dict], archived: list[dict]) -> tuple[list[dict], str]:
    """Replace a synthetic 1970 current-state import with its preserved journal."""
    synthetic = lambda event: str(event.get("ts", "")).startswith("1970-") \
        and str(event.get("actor", "")).startswith("migration/")
    if not archived or not any(synthetic(event) for event in current):
        return current, "active"
    recovered = list(archived)
    seen = {
        json.dumps({key: value for key, value in event.items() if not key.startswith("_source_")},
                   ensure_ascii=False, sort_keys=True)
        for event in recovered
    }
    for event in current:
        if synthetic(event):
            continue
        identity = json.dumps({key: value for key, value in event.items() if not key.startswith("_source_")},
                              ensure_ascii=False, sort_keys=True)
        if identity not in seen:
            recovered.append(event)
            seen.add(identity)
    return recovered, "archived-authentic"


def file_timestamp(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def heading_sections(text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"^(#{1,6})\s+(.+?)\s*$", text, re.M))
    out = []
    if matches and text[:matches[0].start()].strip():
        out.append(("Preamble", text[:matches[0].start()].strip()))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        out.append((match[2].strip(), text[match.end():end].strip()))
    return out or [("Content", text.strip())]


def section_map(text: str) -> dict[str, str]:
    return {title: body for title, body in heading_sections(text)}


def bold_fields(text: str) -> dict[str, str]:
    matches = list(re.finditer(r"^\*\*([^*\n]+?):\*\*\s*", text, re.M))
    return {match[1].strip(): text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(text)].strip()
            for index, match in enumerate(matches)}


def first_heading(text: str, fallback: str) -> str:
    match = re.search(r"^#{1,6}\s+(.+?)\s*$", text, re.M)
    value = match[1].strip() if match else fallback
    return re.sub(r"^(?:P\d+(?:\.\d+)?|D\d+)\s*[—-]\s*", "", value).strip() or fallback


def markdown_sections(values: list[tuple[str, str]]) -> list[dict]:
    used: dict[str, int] = {}
    rows = []
    for title, body in values:
        key = re.sub(r"[^A-Za-z0-9._-]+", "-", title.strip()).strip("-") or "section"
        used[key] = used.get(key, 0) + 1
        sid = key if used[key] == 1 else f"{key}-{used[key]}"
        rows.append({"id": sid, "title": title.strip() or "Section", "text": body})
    return rows


def meaningful(value: str | None) -> bool:
    return bool(value and value.strip().lower() not in EMPTY)


def chunks(value: str | None) -> list[str]:
    if not meaningful(value):
        return []
    value = value.strip()
    matches = list(re.finditer(r"^(?:[-*]|\d+[.)])\s+", value, re.M))
    if not matches:
        return [value]
    result = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(value)
        chunk = value[match.end():end].strip()
        if chunk:
            result.append(chunk)
    return result


def table_rows(text: str) -> list[tuple[list[str], list[list[str]]]]:
    lines = text.splitlines(); tables = []; index = 0
    while index + 1 < len(lines):
        if lines[index].lstrip().startswith("|") and lines[index + 1].lstrip().startswith("|") \
                and re.search(r":?-{2,}:?", lines[index + 1]):
            header = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
            index += 2; rows = []
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                rows.append([cell.strip() for cell in lines[index].strip().strip("|").split("|")])
                index += 1
            tables.append((header, rows)); continue
        index += 1
    return tables


def meta_table(text: str) -> dict[str, str]:
    section = next((body for title, body in heading_sections(text) if re.match(r"0\.\s*Meta", title, re.I)), "")
    result = {}
    for _header, rows in table_rows(section):
        for cells in rows:
            if len(cells) >= 2:
                result[cells[0].strip(" `")] = cells[1].strip()
    return result


def expand_items(value: str, known: set[str]) -> list[str]:
    result = []
    pattern = r"(P\d+)\.(\d+)\s*[–—-]\s*(?:(P\d+)\.)?(\d+)"
    for match in re.finditer(pattern, value):
        phase, start, other, finish = match.groups(); other = other or phase
        if phase == other:
            result.extend(f"{phase}.{number}" for number in range(int(start), int(finish) + 1))
    scrubbed = re.sub(pattern, "", value)
    result.extend(re.findall(r"P\d+\.\d+", scrubbed))
    for phase in re.findall(r"(P\d+)\.\*", value):
        result.extend(item for item in known if item.startswith(phase + "."))
    return [item for item in dict.fromkeys(result) if item in known]


def route_from(text: str, fallback: dict | None = None) -> dict | None:
    lower = text.lower()
    model_class = next((name for name in ("economy", "implementation", "frontier") if name in lower), None)
    if model_class is None:
        if any(name in lower for name in ("opus", "gpt-6", "gpt-5.6", "fable")):
            model_class = "frontier"
        elif any(name in lower for name in ("sonnet", "composer", "grok", "terra")):
            model_class = "implementation"
        elif "haiku" in lower:
            model_class = "economy"
    effort = next((name for name in reversed(EFFORTS) if re.search(rf"(?:/|\b){name}\b", lower)), None)
    if "effort" in lower and any(word in lower for word in ("unverified", "unavailable", "не аттестован")):
        effort = None
    if model_class is None and fallback:
        model_class = fallback["class"]
    if effort is None and fallback:
        effort = fallback["effort"]
    if model_class is None or effort is None:
        return None
    return {"class": model_class, "effort": effort}


def default_route(meta: dict[str, str]) -> dict | None:
    text = " ".join(value for key, value in meta.items() if "Operator" in key or "Model" in key)
    lower = text.lower()
    if "sonnet" in lower:
        return {"class": "implementation", "effort": "medium"}
    if "implementation/high" in lower:
        return {"class": "implementation", "effort": "high"}
    if "implementation" in lower:
        return {"class": "implementation", "effort": "medium"}
    if any(word in lower for word in ("opus", "frontier", "fable")):
        return {"class": "frontier", "effort": "high"}
    return None


def parse_routes(plan_text: str, items: set[str], fallback: dict | None) -> tuple[dict, dict, dict, dict]:
    routes, batches, reviews, notes = {}, {}, {}, {}
    routing = next((body for title, body in heading_sections(plan_text) if re.match(r"3\.\s*Routing", title, re.I)), "")
    for header, rows in table_rows(routing):
        normalized = [cell.lower() for cell in header]
        item_col = next((i for i, name in enumerate(normalized) if "item" in name), None)
        if item_col is None:
            continue
        batch_col = next((i for i, name in enumerate(normalized) if "batch" in name), None)
        route_col = next((i for i, name in enumerate(normalized)
                          if any(word in name for word in ("model", "route", "effort", "отклон"))), None)
        review_col = next((i for i, name in enumerate(normalized) if "review" in name), None)
        why_col = next((i for i, name in enumerate(normalized) if any(word in name for word in ("why", "почему"))), None)
        for row in rows:
            if item_col >= len(row):
                continue
            members = expand_items(row[item_col], items)
            route_text = row[route_col] if route_col is not None and route_col < len(row) else ""
            route = route_from(route_text, fallback)
            review_text = row[review_col].lower() if review_col is not None and review_col < len(row) else ""
            review = "requested" if any(word in review_text for word in ("full", "requested", "independent")) \
                else "self" if any(word in review_text for word in ("light", "self")) else "none"
            for item in members:
                if route is not None:
                    routes[item] = route
                batches[item] = row[batch_col].strip(" `") if batch_col is not None and batch_col < len(row) else "solo"
                reviews[item] = review
                notes[item] = row[why_col] if why_col is not None and why_col < len(row) else ""
    return routes, batches, reviews, notes


def actor(value: str | None) -> dict:
    raw = (value or "legacy source").strip()
    result = {"provider": "legacy", "model": raw}
    tail = raw.lower().rsplit("/", 1)[-1]
    if tail in EFFORTS:
        result["effort"] = tail
    return result


def source_status(text: str) -> str:
    match = re.search(r"^\*\*Status:\*\*\s*(.+?)\s*$", text, re.M)
    if not match:
        raise ValueError("state file has no Status")
    label = match[1]
    return next((target for source, target in STATUS.items() if source in label), None) \
        or (_ for _ in ()).throw(ValueError(f"unknown state {label!r}"))


def path_token(value: str) -> str | None:
    value = value.strip().strip("`'\"").split("#", 1)[0].rstrip(".,;:")
    if not value or any(char.isspace() for char in value) or value.startswith(("http://", "https://", "->", "::")):
        return None
    if value.startswith(("/", "~")) or ".." in Path(value).parts:
        return None
    return value if ("/" in value or "." in Path(value).name) else None


def is_command(value: str) -> bool:
    value = value.strip()
    return bool(COMMAND_START.search(value) or any(token in value for token in (" && ", " | ", "; ")))


def date_from(plan_id: str, events: list[dict], decisions: list[Path]) -> str:
    match = re.match(r"(\d{4})\.(\d{2})\.(\d{2})", plan_id)
    if match:
        return "-".join(match.groups())
    dates = [str(event.get("ts", ""))[:10] for event in events if re.match(r"\d{4}-\d{2}-\d{2}", str(event.get("ts", "")))]
    for path in decisions:
        match = re.search(r"^date:\s*(\d{4}-\d{2}-\d{2})\s*$", path.read_text(errors="replace"), re.M)
        if match:
            dates.append(match[1])
    if not dates:
        raise ValueError(f"{plan_id}: no authentic creation date")
    return min(dates)


def yaml_front(text: str) -> dict[str, str]:
    if not text.startswith("---") or text.count("---") < 2:
        return {}
    result = {}
    for line in text.split("---", 2)[1].splitlines():
        if ":" in line:
            key, value = line.split(":", 1); result[key.strip()] = value.strip()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project-name")
    args = parser.parse_args()
    root = args.plan.resolve(); repo = root.parent.parent
    consumed: dict[str, str] = {}

    def read(relative: str) -> str:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        consumed[relative] = sha(path)
        return text

    plan_text = read("plan.md")
    meta = meta_table(plan_text)
    journal = parse_journal(read("journal.jsonl"), "journal.jsonl")
    archived_journal_path = root / "artifacts/migration-source-v1/journal.jsonl"
    archived_journal = []
    if archived_journal_path.is_file() and any(str(event.get("ts", "")).startswith("1970-") for event in journal):
        archived_rel = archived_journal_path.relative_to(root).as_posix()
        archived_journal = parse_journal(read(archived_rel), archived_rel)
    journal, journal_mode = recover_authentic_journal(journal, archived_journal)
    event_items = defaultdict(list)
    for event in journal:
        if event.get("item_id"):
            event_items[event["item_id"]].append(event)

    phase_files = {path.stem: path for path in root.glob("phases/*/P*.md") if re.fullmatch(r"P\d+", path.stem)}
    item_files = {path.stem: path for path in root.glob("phases/*/P*.md") if re.fullmatch(r"P\d+\.\d+", path.stem)}
    decision_files = sorted(root.glob("decisions/D[0-9]*.md"), key=lambda path: id_sort_key(path.name.split("-")[0]))
    phase_order = sorted(phase_files, key=id_sort_key); item_ids = set(item_files)
    fallback_route = default_route(meta)
    routes, batch_ids, reviews, route_notes = parse_routes(plan_text, item_ids, fallback_route)

    # Build a complete mapping before normalizing any content.
    file_map: dict[str, str] = {
        "plan.md": "plan.json", "roadmap.md": "plan.json", "status.md": "plan.json",
        "handoff.md": "plan.json", "index.md": "plan.json", "open-questions.md": "plan.json",
        "journal.jsonl": "log.jsonl",
    }
    for phase, path in phase_files.items():
        file_map[path.relative_to(root).as_posix()] = f"phases/{phase}/phase.json"
        closed = path.with_name(f"{phase}.closed.md")
        if closed.is_file(): file_map[closed.relative_to(root).as_posix()] = f"phases/{phase}/phase.json"
    for item, path in item_files.items():
        file_map[path.relative_to(root).as_posix()] = f"phases/{item.split('.')[0]}/{item}.json"
        state = path.with_name(f"{item}.state.md")
        if state.is_file(): file_map[state.relative_to(root).as_posix()] = f"phases/{item.split('.')[0]}/{item}.json"
    for path in decision_files:
        file_map[path.relative_to(root).as_posix()] = f"decisions/{path.name.split('-')[0]}.json"
    for path in root.glob("brief/*.md"):
        file_map[path.relative_to(root).as_posix()] = "brief.json"

    # Some v2 plans kept the phase at phases/Pn/Pn.md but referenced the older
    # flattened phases/Pn.md identity.  Preserve the reference identity without
    # adding a nonexistent file to the retirement manifest.
    reference_aliases = {
        f"phases/{phase}.md": f"phases/{phase}/phase.json"
        for phase in phase_files
    }

    represented = set(file_map)
    supporting = []
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root).as_posix()
        if rel in represented or "views" in path.parts or ".plan-cache" in path.parts:
            continue
        if "artifacts" in path.parts and any(part in {"migration-source-v1", "preimages", "before"} for part in path.parts):
            continue
        supporting.append(path)
    used_docs = set()
    for path in supporting:
        rel = path.relative_to(root).as_posix()
        base = re.sub(r"[^A-Za-z0-9._-]+", "-", rel.removesuffix(".md")).strip("-") or "source"
        doc_id = base; serial = 2
        while doc_id in used_docs:
            doc_id = f"{base}-{serial}"; serial += 1
        used_docs.add(doc_id); file_map[rel] = f"knowledge/{doc_id}.json"

    def normalize(text: str) -> str:
        prefix = f"plans/{root.name}/"
        for old, new in sorted((file_map | reference_aliases).items(), key=lambda pair: len(pair[0]), reverse=True):
            text = text.replace(prefix + old, "@plan/" + new)
            text = re.sub(r"(?<![A-Za-z0-9_/@.-])" + re.escape(old) + r"(?![A-Za-z0-9_.-])",
                          "@plan/" + new, text)
        return text

    repo_files_by_name: dict[str, list[Path]] | None = None
    path_repairs: dict[str, str] = {}

    def resolve_repo_path(token: str) -> str:
        """Repair a stale repository path only when its basename is unambiguous."""
        nonlocal repo_files_by_name
        if (repo / token).is_file():
            return token
        if repo_files_by_name is None:
            repo_files_by_name = defaultdict(list)
            ignored = {".git", ".hg", ".svn", ".venv", "node_modules", "vendor", "plans", "dist"}
            for directory, names, files in os.walk(repo):
                names[:] = [name for name in names if name not in ignored]
                base = Path(directory)
                for name in files:
                    repo_files_by_name[name].append(base / name)
        candidates = repo_files_by_name.get(Path(token).name, [])
        parts = Path(token).parts
        if len(parts) >= 2:
            prefix_len = 1 if parts[0].casefold() == "docs" else 2
            prefix = tuple(part.casefold() for part in parts[:prefix_len])
            candidates = [candidate for candidate in candidates
                          if tuple(part.casefold() for part in candidate.relative_to(repo).parts[:prefix_len]) == prefix]
        if len(candidates) == 1:
            repaired = candidates[0].relative_to(repo).as_posix()
            path_repairs[token] = repaired
            return repaired
        return token

    def mapped_path(value: str) -> str | None:
        token = path_token(value)
        if token is None: return None
        prefix = f"plans/{root.name}/"
        if token.startswith(prefix): token = token[len(prefix):]
        if token.startswith("@plan/"): return token
        if token in file_map: return "@plan/" + file_map[token]
        if token in reference_aliases: return "@plan/" + reference_aliases[token]
        if token.startswith(("phases/", "decisions/", "research/", "findings/", "backlog/", "brief/", "artifacts/", "root/", "20_research/", "10_decisions/")):
            return "@plan/" + file_map.get(token, token)
        return resolve_repo_path(token)

    created = date_from(root.name, journal, decision_files)
    updated = max((event.get("ts") for event in journal if isinstance(event.get("ts"), str)), default=created + "T00:00:00Z")
    plan_actor = actor(journal[0].get("actor") if journal else meta.get("Authoring Model"))
    short = (meta.get("Short ID") or "").strip(" `") or None
    if short and not re.fullmatch(r"PLAN[1-9][0-9]*", short):
        raise ValueError(f"invalid source Short ID {short!r}")
    paused_by = (meta.get("Paused By") or "").strip()
    paused = meaningful(paused_by)
    plan_sections = [(title, normalize(body)) for title, body in heading_sections(plan_text)
                     if not re.match(r"^(?:0\.\s*Meta|1\.\s*Context)$", title, re.I)]
    for name in ROOT_CARRIERS - {"plan.md"}:
        path = root / name
        if path.is_file():
            plan_sections.append((f"Legacy {name}", normalize(read(name))))
    context_text = next((body for title, body in heading_sections(plan_text) if re.match(r"1\.\s*Context", title, re.I)), "")
    title = re.sub(r"^`|`$", "", meta.get("Title", first_heading(plan_text, root.name))).strip()
    repository = (meta.get("Repository") or args.project_name or repo.name).strip(" `")
    owner = (meta.get("Approval Owner") or "repository owner").strip(" `")
    rules_text = next((body for title, body in heading_sections(plan_text) if re.match(r"2\.\s*Execution Rules", title, re.I)), "")
    plan_doc = {
        "$schema": URN + "plan:v1", "id": root.name, "short_id": short, "title": title,
        "status": "paused" if paused else "active", "created": created, "updated_at": updated,
        "repository": repository, "owner": owner, "authoring": plan_actor,
        "goal": normalize(context_text or title), "context": normalize(context_text or title),
        "rules": [normalize(value) for value in chunks(rules_text)], "phases": phase_order,
        "settings": {"design_audit": "required" if "required" in (meta.get("Design Audit") or "").lower()
                     and "not-required" not in (meta.get("Design Audit") or "").lower() else "none",
                     "scout": "off", "language": "ru"},
        "orchestration": {"strategy": "dag"}, "sections": markdown_sections(plan_sections),
    }
    if paused:
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", paused_by)
        plan_doc["pause"] = {"reason": normalize(paused_by), "by": normalize(paused_by)}
        if date_match: plan_doc["pause"]["since"] = date_match[0]
    supersedes = (meta.get("supersedes") or "").strip()
    if meaningful(supersedes): plan_doc["links"] = {"supersedes": normalize(supersedes)}

    brief_paths = sorted(root.glob("brief/*.md"))
    messages, brief_sections = [], []
    if brief_paths:
        for number, path in enumerate(brief_paths, 1):
            rel = path.relative_to(root).as_posix(); text = read(rel)
            messages.append({"id": f"M{number}", "date": created, "text": normalize(text),
                             "channel": f"legacy source record {rel}; not asserted verbatim", "kind": "record"})
            brief_sections.append((rel, normalize(text)))
    else:
        messages.append({"id": "M1", "date": created, "text": "No separate owner brief existed in the source plan.",
                         "channel": "migration record", "kind": "record"})
    brief = {"$schema": URN + "brief:v1", "messages": messages, "requirements": [],
             "sections": markdown_sections(brief_sections or [("Source", messages[0]["text"])])}

    items = []
    item_dependencies: dict[str, list[str]] = {}
    item_statuses: dict[str, str] = {}
    item_timestamps: dict[str, str] = {}
    for item_id in sorted(item_files, key=id_sort_key):
        path = item_files[item_id]; rel = path.relative_to(root).as_posix(); text = read(rel); fields = bold_fields(text)
        state_path = path.with_name(f"{item_id}.state.md"); state_rel = state_path.relative_to(root).as_posix()
        state_text = read(state_rel); state_fields = bold_fields(state_text); status = source_status(state_text)
        source_events = event_items.get(item_id, [])
        projection_ts = re.findall(r'"ts"\s*:\s*"([^"]+)"', state_text)
        timestamp = (source_events[-1].get("ts") if source_events else None) or (projection_ts[-1] if projection_ts else None)
        if not timestamp: raise ValueError(f"{item_id}: no source timestamp")
        first_start = next((event.get("ts") for event in source_events if event.get("result") == "in-progress"), timestamp)
        last_terminal = next((event for event in reversed(source_events)
                              if event.get("result") in {"closed-green", "closed-deviations", "blocked"}), None)
        deps = []
        dependency_text = fields.get("Inputs", "") + "\n" + fields.get("Required Reads", "")
        for candidate in re.findall(r"P\d+\.\d+", dependency_text):
            if candidate in item_ids and candidate != item_id and candidate not in deps:
                deps.append(candidate)
        item_dependencies[item_id] = deps; item_statuses[item_id] = status; item_timestamps[item_id] = timestamp

        validation = []
        source_validation = fields.get("Validation", "")
        for token in dict.fromkeys(re.findall(r"`([^`\n]+)`", source_validation)):
            if is_command(token):
                validation.append({"id": f"V{len(validation) + 1}", "cmd": token.strip(),
                                   "expect": "Source acceptance condition preserved in Validation section.",
                                   "kind": "acceptance"})
        proof = (((last_terminal or {}).get("decision") or {}).get("terminal_evidence") or {}).get("validation", [])
        proof_checks = []
        for record in proof if isinstance(proof, list) else []:
            carrier = record.get("carrier") if isinstance(record, dict) else None
            if not meaningful(carrier): continue
            check_id = f"V{len(validation) + 1}"
            validation.append({"id": check_id, "procedure": str(carrier),
                               "expect": f"Source evidence status: {record.get('status', 'recorded')}", "kind": "acceptance"})
            if record.get("status") == "green":
                proof_checks.append({"id": check_id, "exit": 0, "at": last_terminal["ts"],
                                     "summary": "Authentic terminal evidence recorded green in the source journal."})
        if not validation and meaningful(source_validation):
            validation.append({"id": "V1", "procedure": normalize(source_validation),
                               "expect": "Source acceptance condition as written.", "kind": "acceptance"})

        reads = []
        required_tokens = set(re.findall(r"`([^`\n]+)`", fields.get("Required Reads", "")))
        for token in dict.fromkeys(re.findall(r"`([^`\n]+)`", dependency_text)):
            value = mapped_path(token)
            if value and not is_command(token):
                reads.append({"path": value, "why": "Source input; exact context is preserved in item sections.",
                              "required": token in required_tokens})
        task_files = []
        for token in dict.fromkeys(re.findall(r"`([^`\n]+)`", fields.get("Files", ""))):
            value = mapped_path(token)
            if value and not is_command(token): task_files.append({"path": value, "change": "any"})
        decisions = [value for value in dict.fromkeys(re.findall(r"D\d+", "\n".join(
            fields.get(name, "") for name in ("Inputs", "Implementation Rules", "Code Guidance"))))
                     if any(path.name.startswith(value + "-") or path.stem == value for path in decision_files)]

        combined = text + "\n" + route_notes.get(item_id, "")
        authority = {"kind": "routine"}
        gate = re.search(r"\[OWNER-GATE:([A-Z0-9][A-Z0-9._-]*)\]", combined, re.I)
        if gate:
            authority = {"kind": "owner_gate", "gate": gate[1].upper(), "scope": normalize(
                next((line.strip() for line in combined.splitlines() if gate[0] in line), gate[0]))}
        elif status not in {"done", "done_with_deviations", "skipped"}:
            line = next((line.strip() for line in combined.splitlines()
                         if re.search(r"owner[- ]gate|гейт владельца|owner (?:approval|authorization|sign-off)|разрешени[ея] владельца",
                                      line, re.I)), "")
            quote = re.search(r"[«\"]([^»\"]+)[»\"]", line)
            if line and quote:
                authority = {"kind": "owner_gate", "label": quote[1], "scope": normalize(line)}

        rag = {"need": "none", "status": "not_needed"}
        if "RAG:✅" in text: rag = {"need": "required", "status": "complete"}
        elif "RAG:⚠" in text: rag = {"need": "required", "status": "pending"}
        route = routes.get(item_id)
        if route is None and source_events:
            route = route_from(str(source_events[-1].get("actor", "")), fallback_route)
        if route is None: route = fallback_route
        scope_include = [normalize(value) for value in chunks(fields.get("Scope Included"))]
        scope_exclude = [normalize(value) for value in chunks(fields.get("Scope Excluded"))]
        deliverables = [normalize(value) for value in chunks(fields.get("Deliverables"))]
        item = {
            "$schema": URN + "item:v1", "id": item_id, "title": first_heading(text, item_id), "status": status,
            "summary": normalize(fields.get("Intent", first_heading(text, item_id))),
            "why": normalize(fields.get("Why", "Pending source rationale.")),
            "scope": {"include": scope_include, "exclude": scope_exclude}, "depends_on": deps,
            "decisions": decisions, "reads": reads, "task_files": task_files,
            "rules": [normalize(value) for value in chunks(fields.get("Implementation Rules"))],
            "guidance": normalize(fields.get("Code Guidance", "Source guidance is preserved in sections.")),
            "validation": validation, "deliverables": deliverables, "route": route,
            "review": {"mode": reviews.get(item_id, "none")}, "authority": authority, "rag": rag,
            "updated_at": timestamp, "sections": markdown_sections([(name, normalize(value)) for name, value in fields.items()]),
        }
        if status in {"done", "done_with_deviations", "blocked", "skipped", "in_progress"}:
            notes = state_fields.get("Completion Notes") or (last_terminal or {}).get("note") or "Source state retained."
            if notes.startswith("Layout v2 current-state import") and meaningful((last_terminal or {}).get("note")):
                notes = last_terminal["note"]
            deviation_values = chunks(state_fields.get("Known Deviations"))
            if deviation_values and all(value.startswith("Layout v2 current-state import") for value in deviation_values):
                deviation_values = chunks((last_terminal or {}).get("note")) if status == "done_with_deviations" else []
            result = {"started_at": first_start, "executor": actor((last_terminal or (source_events[-1] if source_events else {})).get("actor")),
                      "notes": normalize(notes), "checks": proof_checks,
                      "deviations": [normalize(value) for value in deviation_values],
                      "pending": [normalize(value) for value in chunks(state_fields.get("Pending Work"))]}
            if status != "in_progress": result["finished_at"] = timestamp
            if status == "blocked": result["escalation"] = normalize(state_fields.get("Escalation Needed", "Source reports blocked."))
            if status == "skipped":
                linked = decisions[0] if decisions else None
                if linked: result["decision"] = linked
                else: raise ValueError(f"{item_id}: skipped without a source decision")
            item["result"] = result
        items.append(item)

    phases = []
    for index, phase_id in enumerate(phase_order):
        path = phase_files[phase_id]; rel = path.relative_to(root).as_posix(); text = read(rel); sections = section_map(text)
        members = sorted((item for item in item_ids if item.startswith(phase_id + ".")), key=id_sort_key)
        outside = []
        for item in members:
            for dep in item_dependencies[item]:
                dep_phase = dep.split(".", 1)[0]
                if dep_phase != phase_id and dep_phase not in outside: outside.append(dep_phase)
        if not outside and index and not re.search(r"\bindependent\b|независим", text, re.I):
            outside = [phase_order[index - 1]]
        groups = []
        grouped: dict[str, list[str]] = {}
        for item in members:
            raw = batch_ids.get(item, "solo")
            batch = raw if meaningful(raw) and raw.lower() not in {"solo", "—"} else f"B{phase_id}-{item.split('.')[1]}"
            batch = re.sub(r"[^A-Za-z0-9-]", "-", batch).strip("-") or f"B{phase_id}-{item.split('.')[1]}"
            if not batch.startswith("B"): batch = "B-" + batch
            grouped.setdefault(batch, []).append(item)
        for batch, batch_members in grouped.items():
            required = any("required:" in route_notes.get(item, "").lower() for item in batch_members)
            groups.append({"id": batch, "items": batch_members, "mode": "required" if required else "recommended"})
        skeleton = bool(re.search(r"\bskeleton\b|скелет|не детализирован", text, re.I))
        phase = {"$schema": URN + "phase:v1", "id": phase_id, "title": first_heading(text, phase_id),
                 "design": "skeleton" if skeleton else "detailed",
                 "goal": normalize(sections.get("Phase Context", first_heading(text, phase_id))),
                 "context": normalize(sections.get("Phase Context", first_heading(text, phase_id))),
                 "depends_on": outside, "items": members, "batches": groups,
                 "orchestration": {"strategy": "sequential"},
                 "sections": markdown_sections([(name, normalize(value)) for name, value in heading_sections(text)])}
        statuses = [item_statuses[item] for item in members]
        result = phase_status(statuses) if statuses else None
        closed_path = path.with_name(f"{phase_id}.closed.md")
        if result is not None:
            if closed_path.is_file():
                closure_text = read(closed_path.relative_to(root).as_posix())
                summary = normalize(closure_text)
            else:
                summary = "Derived from authentic terminal item states during migration; no new phase checks claimed."
            phase["closed"] = {"at": max(item_timestamps[item] for item in members), "result": result, "summary": summary}
        phases.append(phase)

    decisions = []
    known_refs = set(phase_order) | item_ids
    for path in decision_files:
        rel = path.relative_to(root).as_posix(); text = read(rel); front = yaml_front(text); sections = section_map(text)
        decision_id = front.get("id") or path.name.split("-")[0]
        status = front.get("status", "accepted")
        if status not in {"open", "proposed", "accepted", "rejected", "superseded"}:
            raise ValueError(f"{rel}: unknown decision status {status!r}")
        decision_text = sections.get("Решение") or sections.get("Solution") or sections.get("Decision") or ""
        rationale = sections.get("Почему") or sections.get("Why") or sections.get("Rationale") or ""
        doc = {"$schema": URN + "decision:v1", "id": decision_id,
               "title": first_heading(text, path.stem.replace("-", " ")), "date": front.get("date", created),
               "status": status, "actor": actor((bold_fields(text).get("Actor") or meta.get("Authoring Model"))),
               "applies_to": [ref for ref in dict.fromkeys(re.findall(r"P\d+(?:\.\d+)?", front.get("items", "") + " " + front.get("item", ""))) if ref in known_refs],
               "supersedes": re.findall(r"D\d+", front.get("supersedes", "")),
               "sections": markdown_sections([(name, normalize(value)) for name, value in heading_sections(text)])}
        if meaningful(decision_text): doc["decision"] = normalize(decision_text)
        if meaningful(rationale): doc["rationale"] = normalize(rationale)
        if status == "open": doc["question"] = normalize(sections.get("Question", decision_text or doc["title"]))
        if status in {"accepted", "proposed"}:
            doc.setdefault("decision", normalize(text.split("---", 2)[-1]))
            doc.setdefault("rationale", "Rationale is preserved in the source decision sections.")
        superseded_by = front.get("superseded_by")
        if meaningful(superseded_by): doc["superseded_by"] = superseded_by
        decisions.append(doc)

    documents = []
    for path in supporting:
        rel = path.relative_to(root).as_posix(); text = read(rel); doc_id = Path(file_map[rel]).stem
        refs = [ref for ref in dict.fromkeys(re.findall(r"P\d+(?:\.\d+)?", path.name)) if ref in known_refs]
        documents.append({"$schema": URN + "document:v1", "id": doc_id, "title": first_heading(text, path.stem),
                          "sections": markdown_sections([(name, normalize(value)) for name, value in heading_sections(text)]),
                          "applies_to": refs, "provenance": {"path": rel, "sha256": consumed[rel]}})

    events = []
    for number, source in enumerate(journal, 1):
        target = source.get("item_id"); event_type = "note"
        if source.get("result") == "in-progress" and target in item_ids: event_type = "start"
        elif source.get("result") in {"closed-green", "closed-deviations"} and target in item_ids: event_type = "finish"
        elif source.get("result") in {"blocked", "block-candidate"}: event_type = "blocker"
        event = {"v": 1, "ts": source["ts"], "type": event_type,
                 "summary": normalize(str(source.get("note") or f"Source event {number}: {source.get('result', 'recorded')}")),
                 "actor": actor(source.get("actor")), "data": {"source_line": source.pop("_source_line", number),
                                                                  "source_record": source}}
        if target in item_ids: event["item"] = target; event["phase"] = target.split(".", 1)[0]
        elif target in phase_order: event["phase"] = target
        events.append(event)
    events.append(store.new_event("migrated", "Layout-v2 source converted to the current JSON graph; commands were not executed.",
                                  {"provider": "codex", "model": "gpt-6.1-sol"},
                                  data={"source_files": consumed, "source_plan_id": root.name}))

    value = {"$schema": URN + "snapshot:v1", "plan": plan_doc, "brief": brief, "phases": phases,
             "items": items, "units": [], "decisions": decisions, "documents": documents, "events": events}
    issues = schema.validate(value, "snapshot")
    if issues: raise ValueError("\n".join(str(issue) for issue in issues[:100]))
    snapshot._graph(root, value)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    handoff = (root / "handoff.md").read_text(errors="replace") if (root / "handoff.md").is_file() else ""
    next_lines = [line.strip() for line in handoff.splitlines() if re.search(r"\bnext\b|следующ", line, re.I)]
    report = {"plan": root.name, "source_path": str(root), "snapshot": str(args.output), "source_files": consumed,
              "file_mapping": file_map, "retire_files": sorted(file_map),
              "counts": {"phases": len(phases), "items": len(items), "decisions": len(decisions),
                         "documents": len(documents), "events": len(events)},
              "item_statuses": item_statuses, "source_next": next_lines[:20],
              "unresolved_routes": [item["id"] for item in items if item["route"] is None],
              "path_repairs": path_repairs, "journal_mode": journal_mode}
    args.output.with_name("source-map.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"] | {"unresolved_routes": len(report["unresolved_routes"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
