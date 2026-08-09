"""Downstream-gate v1: discover consumers, run applicable Validation, record results."""
from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from task import plan_bundle, plan_gate_activation, plan_layout, plan_weight


class DownstreamError(ValueError):
    """The downstream gate cannot produce a trustworthy result."""


GATE_ID = "downstream-gate-v1"
VERSION = "1.0.0"
ACTIVATION_CHECK = "task.plan_gates._lint_downstream_records"
OUTCOMES = frozenset(("green", "red", "unknown"))
TERMINAL_STATUSES = frozenset(("🟢 Done", "🟠 Done with deviations", "⛔ Skipped by decision"))
_ITEM = re.compile(r"^P\d+\.\d+$")
_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")
_QUOTED_PATH = re.compile(r"['\"]([^'\"\s]+/[^'\"\s]+\.[A-Za-z][A-Za-z0-9_-]*)['\"]")
_UNITTEST = re.compile(r"(?:^|\s)-m\s+unittest\s+([^;&|]+)")
_CD = re.compile(r"(?:^|[;&|]\s*)cd\s+([^\s;&|]+)")
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _item_key(item_id: str) -> tuple[int, int]:
    phase, item = item_id[1:].split(".", 1)
    return int(phase), int(item)


def _repo_relative(token: str, *, plan_dir: Path, repo_root: Path, cwd: Path | None = None) -> str:
    token = token.strip().strip("'\"")
    if not token or "$" in token or "<" in token or ">" in token:
        raise DownstreamError(f"динамический путь не является repository input: {token!r}")
    raw = Path(token)
    if raw.is_absolute():
        candidate = raw
    elif token.startswith(("plans/", "packages/", "docs/", ".agents/", ".claude/")) or token in {
            "CHANGELOG.md", "README.md", "AGENTS.md"}:
        candidate = repo_root / raw
    elif cwd is not None:
        candidate = cwd / raw
    else:
        candidate = plan_dir / raw
    try:
        return candidate.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise DownstreamError(f"путь вне repository root: {token}") from exc


def _field_paths(value: str, *, plan_dir: Path, repo_root: Path) -> set[str]:
    paths = set()
    for token, declared in plan_weight.path_candidates(value or ""):
        if not declared:
            continue
        try:
            paths.add(_repo_relative(token, plan_dir=plan_dir, repo_root=repo_root))
        except DownstreamError:
            continue
    return paths


def _all_items(plan_dir: Path) -> dict[str, dict]:
    result = {}
    for phase_id in plan_layout.phase_paths(plan_dir):
        for path in plan_layout.item_spec_paths(plan_dir, phase_id):
            result[path.stem] = plan_bundle._fields(plan_dir, path.stem)
    return result


def consumer_spec_path(plan_dir, item_id: str) -> Path:
    plan_dir = Path(plan_dir)
    try:
        return plan_layout.carrier_path(plan_dir, "item-spec", item_id=item_id)
    except plan_layout.PlanLayoutError as exc:
        raise DownstreamError(str(exc)) from exc


def consumer_spec_sha256(plan_dir, item_id: str) -> str:
    path = consumer_spec_path(plan_dir, item_id)
    try:
        return _sha(path.read_bytes())
    except OSError as exc:
        raise DownstreamError(f"ТЗ потребителя не читается: {path}") from exc


def discover_consumers(plan_dir, producer_item: str) -> list[dict]:
    """Return consumers derived only from declared path equality."""
    plan_dir = Path(plan_dir)
    if not _ITEM.fullmatch(producer_item):
        raise DownstreamError("item должен иметь форму Pn.m")
    if plan_layout.layout_version(plan_dir) != "v2":
        raise DownstreamError("downstream-gate v1 существует только для Layout v2")
    repo_root = plan_weight.repo_root_for(plan_dir)
    items = _all_items(plan_dir)
    if producer_item not in items:
        raise DownstreamError(f"пункт-продюсер {producer_item} не найден")
    producer = items[producer_item]
    outputs = set()
    for field in ("Files", "Deliverables"):
        outputs.update(_field_paths(producer.get(field, ""), plan_dir=plan_dir, repo_root=repo_root))
    consumers = []
    for item_id, fields in sorted(items.items()):
        # A downstream dependency is directional: an already earlier item cannot
        # consume an output that this producer has not produced yet.
        if _item_key(item_id) <= _item_key(producer_item):
            continue
        inputs = set()
        for field in ("Inputs", "Required Reads"):
            inputs.update(_field_paths(fields.get(field, ""), plan_dir=plan_dir, repo_root=repo_root))
        matched = sorted(outputs & inputs)
        if matched:
            consumers.append({"item": item_id, "matched_paths": matched,
                              "validation": fields.get("Validation", "")})
    return consumers


def _validation_commands(value: str) -> list[str]:
    value = (value or "").strip()
    if not value or value == "—":
        return []
    commands = []
    for part in re.split(r"\s+·\s+", value):
        part = part.strip()
        if not part:
            continue
        # Validation is Markdown: execute the inline-code payload, never its
        # explanatory suffix ``(печатает …)`` or surrounding bold markers.
        first, last = part.find("`"), part.rfind("`")
        if first >= 0 and last > first:
            part = part[first + 1:last]
        commands.append(part.strip())
    return commands


def _command_cwd(command: str, repo_root: Path) -> Path:
    match = _CD.search(command)
    if not match:
        return repo_root
    raw = match.group(1).strip("'\"")
    path = Path(raw)
    return path if path.is_absolute() else repo_root / path


def _command_paths(command: str, *, plan_dir: Path, repo_root: Path) -> set[str]:
    cwd = _command_cwd(command, repo_root)
    # Command arguments are executable syntax, not plan prose: a bare ``foo.py``
    # is as explicit as a backticked path in an item field.
    raw_paths = {token for token, _declared in plan_weight.path_candidates(command)}
    raw_paths.update(_QUOTED_PATH.findall(command))
    match = _UNITTEST.search(command)
    if match:
        try:
            words = shlex.split(match.group(1))
        except ValueError:
            words = match.group(1).split()
        for word in words:
            if word.startswith("-") or "=" in word or "/" in word:
                continue
            if re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+", word):
                raw_paths.add(word.replace(".", "/") + ".py")
    result = set()
    for token in raw_paths:
        try:
            result.add(_repo_relative(token, plan_dir=plan_dir, repo_root=repo_root, cwd=cwd))
        except DownstreamError:
            continue
    return result


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(("git", *args), cwd=repo_root, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if completed.returncode:
        raise DownstreamError(completed.stderr.strip() or "git command failed")
    return completed.stdout.strip()


def _is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    completed = subprocess.run(("git", "merge-base", "--is-ancestor", ancestor, descendant),
                               cwd=repo_root, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    if completed.returncode in (0, 1):
        return completed.returncode == 0
    raise DownstreamError(completed.stderr.strip() or "git merge-base failed")


def _commit_tree(repo_root: Path, ref: str) -> tuple[str, set[str]]:
    commit = _git(repo_root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    paths = set(_git(repo_root, "ls-tree", "-r", "--name-only", commit).splitlines())
    return commit, paths


def _exists_in_tree(path: str, tree: set[str]) -> bool:
    normalized = PurePosixPath(path).as_posix().rstrip("/")
    return normalized in tree or any(row.startswith(normalized + "/") for row in tree)


def _default_runner(command: str, cwd: Path):
    return subprocess.run(command, cwd=cwd, shell=True, executable="/bin/bash", text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _bounded_output(value: str, limit: int = 4000) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    return value[-limit:], True


def evaluate(plan_dir, producer_item: str, *, producer_commit: str = "HEAD", runner=None) -> dict:
    """Execute the applicable Validation subset and return the three-valued result."""
    plan_dir = Path(plan_dir)
    repo_root = plan_weight.repo_root_for(plan_dir)
    commit, tree = _commit_tree(repo_root, producer_commit)
    run = runner or _default_runner
    consumer_results = []
    any_applicable = False
    any_red = False
    for consumer in discover_consumers(plan_dir, producer_item):
        commands = []
        applicable_count = 0
        consumer_red = False
        for command in _validation_commands(consumer["validation"]):
            addressed = sorted(_command_paths(command, plan_dir=plan_dir, repo_root=repo_root))
            missing = [path for path in addressed if not _exists_in_tree(path, tree)]
            row = {"command": command, "addressed_paths": addressed,
                   "applicable": not missing, "missing_paths": missing}
            if not missing:
                completed = run(command, repo_root)
                stdout, stdout_truncated = _bounded_output(completed.stdout)
                stderr, stderr_truncated = _bounded_output(completed.stderr)
                row.update({"returncode": completed.returncode, "stdout": stdout,
                            "stdout_truncated": stdout_truncated, "stderr": stderr,
                            "stderr_truncated": stderr_truncated})
                applicable_count += 1
                any_applicable = True
                if completed.returncode:
                    consumer_red = True
                    any_red = True
            commands.append(row)
        outcome = "red" if consumer_red else ("green" if applicable_count else "unknown")
        spec_sha = consumer_spec_sha256(plan_dir, consumer["item"])
        consumer_results.append({**consumer, "consumer_spec_sha256": spec_sha,
                                 "result_key": {"consumer_spec_sha256": spec_sha,
                                                "producer_commit": commit},
                                 "commands": commands, "outcome": outcome})
    outcome = "red" if any_red else ("green" if any_applicable else "unknown")
    return {"gate": GATE_ID, "version": VERSION, "producer_item": producer_item,
            "producer_commit": commit, "consumers": consumer_results, "outcome": outcome,
            "blocks": outcome == "red"}


def validate_result_record(fields: dict) -> None:
    required = {"item", "date", "gate", "producer_commit", "consumer_item",
                "consumer_spec_sha256", "outcome"}
    missing = sorted(required - set(fields))
    if missing:
        raise DownstreamError(f"запись результата: нет полей {', '.join(missing)}")
    if fields["gate"] != GATE_ID:
        raise DownstreamError("запись результата: неверный gate")
    if not _ITEM.fullmatch(fields["item"]) or not _ITEM.fullmatch(fields["consumer_item"]):
        raise DownstreamError("запись результата: item должен иметь форму Pn.m")
    if not _COMMIT.fullmatch(fields["producer_commit"]):
        raise DownstreamError("запись результата: producer_commit не является git hash")
    if not re.fullmatch(r"[0-9a-f]{64}", fields["consumer_spec_sha256"]):
        raise DownstreamError("запись результата: consumer_spec_sha256 не является sha256")
    if fields["outcome"] not in OUTCOMES:
        raise DownstreamError("запись результата: неизвестный outcome")
    try:
        datetime.strptime(fields["date"], "%Y-%m-%d")
    except ValueError as exc:
        raise DownstreamError("запись результата: date не является ISO-датой") from exc


def parse_result_record(path) -> tuple[dict, str]:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DownstreamError(f"запись результата не читается: {path}") from exc
    match = _FRONTMATTER.match(text)
    if not match:
        raise DownstreamError(f"{path}: нет YAML-frontmatter")
    fields = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line or line.startswith((" ", "\t")):
            raise DownstreamError(f"{path}: недопустимая строка frontmatter {line!r}")
        key, value = line.split(":", 1)
        key = key.strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]*", key) or key in fields:
            raise DownstreamError(f"{path}: недопустимый или повторный ключ {key!r}")
        fields[key] = value.strip().strip("'\"")
    return fields, text[match.end():]


def record(plan_dir, result: dict, *, date: str | None = None) -> list[Path]:
    """Write one append-only item-scoped finding per discovered consumer."""
    plan_dir = Path(plan_dir)
    date = date or datetime.now(timezone.utc).date().isoformat()
    directory = plan_dir / "findings"
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for consumer in result["consumers"]:
        fields = {"item": result["producer_item"], "date": date, "gate": GATE_ID,
                  "producer_commit": result["producer_commit"],
                  "consumer_item": consumer["item"],
                  "consumer_spec_sha256": consumer["consumer_spec_sha256"],
                  "outcome": consumer["outcome"]}
        validate_result_record(fields)
        name = (f"{result['producer_item']}-downstream-{consumer['item']}-"
                f"{consumer['consumer_spec_sha256'][:12]}-{result['producer_commit'][:12]}.md")
        target = directory / name
        lines = ["---", *(f"{key}: {value}" for key, value in fields.items()), "---", "",
                 f"# Downstream gate — {result['producer_item']} → {consumer['item']}", "",
                 f"Outcome: `{consumer['outcome']}`.", "", "| Applicable | Return | Command |",
                 "|:--|:--|:--|"]
        for command in consumer["commands"]:
            code = command.get("returncode", "—")
            escaped = command["command"].replace("|", "\\|")
            lines.append(f"| {'yes' if command['applicable'] else 'no'} | {code} | `{escaped}` |")
        if not consumer["commands"]:
            lines.append("| no | — | Validation не объявлена |")
        text = "\n".join(lines) + "\n"
        if target.exists():
            if target.read_text(encoding="utf-8") != text:
                raise DownstreamError(f"append-only finding уже существует с другим содержимым: {target}")
        else:
            target.write_text(text, encoding="utf-8")
        written.append(target)
    return written


def _records(plan_dir: Path) -> list[tuple[Path, dict]]:
    records = []
    for path in sorted((plan_dir / "findings").rglob("*.md")):
        try:
            fields, _body = parse_result_record(path)
        except DownstreamError:
            continue
        if fields.get("gate") == GATE_ID:
            records.append((path, fields))
    return records


def lint_records(plan_dir, layout: str, diag) -> None:
    """Check only post-cutoff layout-v2 producers from the registry carrier."""
    if layout != "v2":
        return
    plan_dir = Path(plan_dir)
    try:
        active = plan_gate_activation.active_items(plan_dir, ACTIVATION_CHECK)
    except plan_gate_activation.ActivationError as exc:
        diag.error(plan_dir / "plan.md", None, f"{GATE_ID}: {exc}")
        return
    repo_root = plan_weight.repo_root_for(plan_dir)
    try:
        head = _git(repo_root, "rev-parse", "--verify", "HEAD^{commit}")
    except DownstreamError as exc:
        diag.error(plan_dir / "plan.md", None, f"{GATE_ID}: {exc}")
        return
    records = _records(plan_dir)
    for item_id, fields in sorted(_all_items(plan_dir).items()):
        if item_id not in active or fields.get("Status") not in TERMINAL_STATUSES:
            continue
        for consumer in discover_consumers(plan_dir, item_id):
            current_sha = consumer_spec_sha256(plan_dir, consumer["item"])
            matches = []
            for path, record_fields in records:
                if (record_fields.get("item") != item_id
                        or record_fields.get("consumer_item") != consumer["item"]
                        or record_fields.get("consumer_spec_sha256") != current_sha):
                    continue
                try:
                    validate_result_record(record_fields)
                except DownstreamError as exc:
                    diag.error(path, None, f"{GATE_ID}: {exc}")
                    continue
                try:
                    commit = _git(repo_root, "rev-parse", "--verify",
                                  f"{record_fields['producer_commit']}^{{commit}}")
                    if not _is_ancestor(repo_root, commit, head):
                        diag.error(path, None, f"{GATE_ID}: producer_commit не входит в ancestry HEAD")
                        continue
                except DownstreamError as exc:
                    diag.error(path, None, f"{GATE_ID}: producer_commit не разрешается: {exc}")
                    continue
                matches.append((path, record_fields, commit))
            if not matches:
                diag.error(plan_dir / "plan.md", None,
                           f"{GATE_ID}: пункт {item_id}: нет текущей записи результата "
                           f"для потребителя {consumer['item']}")
                continue
            commits = sorted({commit for _path, _record, commit in matches})
            newest = [candidate for candidate in commits
                      if not any(candidate != other
                                 and _is_ancestor(repo_root, candidate, other)
                                 for other in commits)]
            if len(newest) != 1:
                diag.error(plan_dir / "plan.md", None,
                           f"{GATE_ID}: пункт {item_id}: записи producer_commit имеют "
                           "несравнимые ветви")
                continue
            latest = [(path, record) for path, record, commit in matches if commit == newest[0]]
            if any(record["outcome"] == "red" for _path, record in latest):
                diag.error(latest[-1][0], None,
                           f"{GATE_ID}: пункт {item_id}: red блокирует закрытие продюсера")


def dumps(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n"


__all__ = ("ACTIVATION_CHECK", "DownstreamError", "GATE_ID", "OUTCOMES",
           "consumer_spec_sha256", "discover_consumers", "dumps", "evaluate", "lint_records",
           "parse_result_record", "record", "validate_result_record")
