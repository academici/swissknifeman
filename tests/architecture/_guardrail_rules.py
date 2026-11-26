"""Source hygiene, configuration access and neutral-core guardrails."""

from __future__ import annotations

import ast
import re
import sys
from functools import cache
from pathlib import Path

from ._import_rules import _target, _under
from ._layers import Layer
from ._rule_context import RuleContext, Violation, _schema_data_sites, _schema_default_allowed, _violation
from ._tree import (
    SourceFile,
    aliases,
    async_defs,
    calls,
    dotted,
    imports,
    resolve,
    string_constants,
)

PROVIDERS = frozenset(
    {"claude", "claude-code", "claude_code", "codex", "grok", "cursor", "kiro", "anthropic", "openai"}
)
GRAB_BAG_NAMES = frozenset(
    {"utils.py", "helpers.py", "common.py", "misc.py", "manager.py", "base.py", "service.py"}
)
LEGACY_PACKAGES = frozenset(
    {"aicore", "planner", "orch", "harness", "skiller", "maind", "analyst", "brain", "gui"}
)


def _product(file: SourceFile) -> bool:
    parts = Path(file.display_path).parts
    return parts[:2] == ("src", "skm") and not {"tests", "overlays", "__pycache__"}.intersection(parts[2:])


def rule_provider_literals(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    def symbolic_names(file: SourceFile) -> set[tuple[str, int]]:
        symbolic: set[tuple[str, int]] = set()
        for node in file.nodes:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
            ):
                symbolic.update(
                    (item.value, item.lineno)
                    for item in ast.walk(node.value)
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                )
            if isinstance(node, ast.Call) and dotted(node.func) == "NewType" and node.args:
                name = node.args[0]
                if isinstance(name, ast.Constant) and isinstance(name.value, str):
                    symbolic.add((name.value, name.lineno))
        return symbolic

    return [
        _violation(
            "provider-literals", file, line, f"provider name '{value}' outside adapters/bootstrap", value
        )
        for file in tree
        if file.layer not in {Layer.ADAPTER, Layer.BOOTSTRAP}
        for schema_sites in [_schema_data_sites(file, ctx)[0]]
        for value, line in string_constants(file)
        if value.casefold() in PROVIDERS
        and (value, line) not in schema_sites
        and (value, line) not in symbolic_names(file)
    ]


def rule_config_access(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    result = []
    for file in tree:
        if (
            file.layer == Layer.BOOTSTRAP
            or _under(file.name, "skm.platform.config.sources")
            or (file.layer == Layer.ENTRYPOINT and file.name == f"skm.entrypoints.{file.surface}.main")
        ):
            continue
        bindings = aliases(file)
        lines = {
            ref.line
            for ref in imports(file)
            for target in ref.targets
            if _under(target, "tomllib", "os.environ", "os.getenv", "os.putenv", "os.unsetenv")
        }
        lines.update(
            node.lineno
            for node in file.nodes
            if isinstance(node, (ast.Name, ast.Attribute))
            and _under(
                resolve(dotted(node), bindings),
                "os.environ",
                "os.getenv",
                "os.putenv",
                "os.unsetenv",
            )
        )
        result.extend(
            _violation(
                "config-access", file, line, "environment/TOML access outside config sources: use ctx.config"
            )
            for line in sorted(lines)
        )
    return result


def rule_async_placement(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    return [
        _violation(
            "async-placement", file, getattr(node, "lineno", 1), "async code outside the HTTP edge (ADR 0004)"
        )
        for file in tree
        if not _under(file.name, "skm.entrypoints.api", "skm.adapters.http_client")
        for node in async_defs(file)
    ]


def rule_print_free(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    root = (ctx.root or Path(__file__).resolve().parents[2]).resolve()
    return [
        _violation("print-free", file, call.line, "print outside CLI")
        for file in tree
        if not _under(file.name, "skm.entrypoints.cli")
        and not (root / file.path).is_relative_to(root / "tools")
        for call in calls(file)
        if call.name in {"print", "builtins.print"}
    ]


def rule_file_names(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    return [
        _violation("file-names", file, 1, f"grab-bag module name '{file.path.name}'", file.path.name)
        for file in tree
        if file.path.name in GRAB_BAG_NAMES
    ]


def _sized_files(tree: list[SourceFile]):
    return (
        (file, len(file.text.splitlines()))
        for file in tree
        if "generated" not in file.path.parts and file.path.suffix != ".sql"
    )


def rule_file_size(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    return [
        _violation("file-size", file, 1, f"{size} lines (> 900): split by responsibility")
        for file, size in _sized_files(tree)
        if size > 900
    ]


def size_warnings(tree: list[SourceFile]) -> tuple[str, ...]:
    """Printed by test_rules, not Python warnings (pytest uses filterwarnings=error)."""
    return tuple(
        f"{file.display_path}:1: [file-size] warning: {size} lines (> 600): consider splitting"
        for file, size in _sized_files(tree)
        if 600 < size <= 900
    )


def rule_generated_header(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    return [
        _violation(
            "generated-header", file, 1, "generated file without header (edit the schema, run make gen)"
        )
        for file in tree
        if "generated" in file.path.parts
        and file.path.name != "__init__.py"
        and file.path.suffix == ".py"
        and (
            not file.text.splitlines()
            or not file.text.splitlines()[0].startswith(
                ("# generated by tools/gen.py", "# generated by tools/codegen/error_catalog.py")
            )
        )
    ]


def rule_no_legacy(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    result = [
        _violation("no-legacy", file, ref.line, f"legacy reference '{ref.module}': v2 never uses legacy code")
        for file in tree
        for ref in imports(file)
        if ref.module.split(".")[0] in LEGACY_PACKAGES
    ]
    result.extend(
        _violation("no-legacy", file, line, f"legacy reference '{value}': v2 never uses legacy code")
        for file in tree
        for value, line in string_constants(file)
        if "packages/" in value or "bridges/" in value
    )
    return result


def rule_third_party_by_layer(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    result = []
    for file in tree:
        allowed = set()
        if _under(file.name, "skm.platform.schema"):
            allowed.update({"jsonschema", "referencing"})
        if file.layer == Layer.ADAPTER:
            allowed.update(
                {
                    "postgres": {"psycopg", "psycopg_pool"},
                    "http_client": {"httpx"},
                    "secrets": {"keyring"},
                }.get(file.tech or "", set())
            )
        if file.layer == Layer.ENTRYPOINT and file.surface == "api":
            allowed.update({"starlette", "uvicorn"})
        for ref in imports(file):
            package = ref.module.split(".")[0]
            if package not in sys.stdlib_module_names | {"skm", "__future__"} and package not in allowed:
                result.append(
                    _violation(
                        "third-party-by-layer",
                        file,
                        ref.line,
                        f"third-party '{package}' not allowed in {file.layer}",
                        package,
                    )
                )
    return result


def rule_no_test_overrides(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    return [
        _violation("no-test-overrides", file, node.lineno, "CompositionOverrides is test-only")
        for file in tree
        if file.layer in {Layer.ENTRYPOINT, Layer.BACKGROUND}
        for node in file.nodes
        if isinstance(node, ast.Call)
        and resolve(dotted(node.func), aliases(file)).rsplit(".", 1)[-1] == "build_app"
        and any(keyword.arg == "overrides" for keyword in node.keywords)
    ]


def _text_files(tree: list[SourceFile], root: Path | None):
    sources = {file.display_path: file.text for file in tree if _product(file)}
    if root is not None:
        for directory in (root / "src/skm", root / "resources/packs/core"):
            for path in sorted(directory.rglob("*")):
                relative = path.relative_to(root)
                if not path.is_file() or {"tests", "overlays", "__pycache__"}.intersection(relative.parts):
                    continue
                if relative.as_posix() in sources:
                    continue
                try:
                    content = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                if "\x00" not in content:
                    sources[relative.as_posix()] = content
    return sources.items()


@cache
def _neutral_regexes() -> tuple[tuple[re.Pattern[str], ...], re.Pattern[str], re.Pattern[str]]:
    raw_lines = [
        line
        for line in Path(__file__).with_name("neutral_literals.txt").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    branches = [line[3:] if line.startswith("re:") else re.escape(line) for line in raw_lines]
    patterns = tuple(re.compile(branch, re.IGNORECASE) for branch in branches)
    email_branch = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}"
    email = re.compile(email_branch, re.IGNORECASE)
    fast_gate = re.compile("|".join(f"(?:{b})" for b in (*branches, email_branch)), re.IGNORECASE)
    return patterns, email, fast_gate


def rule_neutral_literals(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    patterns, email, fast_gate = _neutral_regexes()
    by_path = {file.display_path: file for file in tree}
    result = []
    for path, content in _text_files(tree, ctx.root):
        if not fast_gate.search(content):
            continue
        file_obj = by_path.get(path)
        for number, line in enumerate(content.splitlines(), 1):
            if not fast_gate.search(line):
                continue
            matches = {match.group() for pattern in patterns for match in pattern.finditer(line)}
            matches.update(
                match.group()
                for match in email.finditer(line)
                if match.group().casefold().split("@", 1)[1] not in {"example.test", "example.com"}
                and not match.group().casefold().startswith("noreply@")
            )
            if not matches:
                continue
            if file_obj is None:
                file_obj = SourceFile.at(Path(path), content)
            result.extend(
                Violation(
                    "neutral-literals",
                    path,
                    number,
                    f"personal/organisation literal '{match}' in neutral core: move it to an overlay",
                    match,
                )
                for match in sorted(matches)
                if not _schema_default_allowed(file_obj, match, number, ctx)
            )
    return result


def rule_cli_thin(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    return [
        _violation("cli-thin", file, ref.line, "surfaces call public facades only")
        for file in tree
        if file.layer == Layer.ENTRYPOINT
        for ref in imports(file)
        for target in ref.targets
        if target.startswith("skm.modules.")
        and _target(target).layer in {Layer.APPLICATION, Layer.DOMAIN, Layer.PORTS}
    ]
