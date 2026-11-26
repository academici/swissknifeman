"""Exact, documented exceptions. Invalid or expired entries cannot suppress diagnostics."""

import ast
import tomllib
from dataclasses import dataclass
from datetime import date
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Protocol


class Diagnostic(Protocol):
    @property
    def rule(self) -> str: ...
    @property
    def path(self) -> str: ...
    @property
    def message(self) -> str: ...
    @property
    def detail(self) -> str: ...


ROOT = Path(__file__).resolve().parents[2]


def _statement_matches(statement: str, violation: Diagnostic, line: int | None, root: Path) -> bool:
    """The flagged call is exactly ``statement`` and no argument name is assigned in its function."""
    try:
        expected = ast.dump(ast.parse(statement.strip(), mode="eval").body)
        tree = ast.parse((root / violation.path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return False
    functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or node.lineno != line or ast.dump(node) != expected:
            continue
        arguments = [*node.args, *(kw.value for kw in node.keywords)]
        names = {n.id for arg in arguments for n in ast.walk(arg) if isinstance(n, ast.Name)}
        owners = [f for f in functions if f.lineno <= node.lineno <= (f.end_lineno or f.lineno)]
        if not owners:
            return False
        scope = min(owners, key=lambda f: (f.end_lineno or f.lineno) - f.lineno)
        assigned = {
            n.id for n in ast.walk(scope) if isinstance(n, ast.Name) and not isinstance(n.ctx, ast.Load)
        }
        return not names & assigned
    return False


@dataclass(frozen=True)
class Allowance:
    rule: str
    path: str
    detail: str
    reason: str
    adr: str
    until: date | None = None
    statement: str | None = None  # narrows a path-wide diagnostic to one exact call; see _statement_matches

    def matches(self, violation: Diagnostic, *, root: Path = ROOT) -> bool:
        if not (
            self.rule == violation.rule
            and fnmatchcase(violation.path, self.path)
            and self.detail == (violation.detail or violation.message)
        ):
            return False
        if self.statement is None:
            return True
        line = getattr(violation, "line", None)
        return _statement_matches(self.statement, violation, line if isinstance(line, int) else None, root)


def load(path: Path, *, today: date) -> tuple[Allowance, ...]:
    """The caller supplies the date, so expiry is deterministic in tests."""
    if not path.exists():
        return ()
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    if set(document) - {"allow"} or not isinstance(document.get("allow", []), list):
        raise ValueError(f"{path}: expected [[allow]] entries")
    result: list[Allowance] = []
    for index, entry in enumerate(document.get("allow", []), 1):
        location = f"{path}: allow[{index}]"
        required = {"rule", "path", "detail", "reason", "adr"}
        if not isinstance(entry, dict) or set(entry) - (required | {"until", "statement"}):
            raise ValueError(f"{location}: unknown fields")
        if any(not isinstance(entry.get(key), str) or not entry[key].strip() for key in required):
            raise ValueError(f"{location}: rule, path, detail, reason and adr are required")
        until = entry.get("until")
        if isinstance(until, str):
            until = date.fromisoformat(until)
        if until is not None and type(until) is not date:
            raise ValueError(f"{location}: until must be a date")
        if until is not None and until < today:
            raise ValueError(f"{location}: expired on {until}")
        statement = entry.get("statement")
        if statement is not None and (not isinstance(statement, str) or not statement.strip()):
            raise ValueError(f"{location}: statement must be a non-empty string")
        allowance = Allowance(
            entry["rule"], entry["path"], entry["detail"], entry["reason"], entry["adr"], until, statement
        )
        if allowance in result:
            raise ValueError(f"{location}: duplicate exception")
        result.append(allowance)
    return tuple(result)
