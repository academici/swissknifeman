"""``skm plugins list|show|lint`` (mechanisms/02-plugins §9): an inert view of the installed plugins.

No command here imports plugin code: discovery reads entry point metadata, runtime data files are found
through RECORD and read as text (step 2a), and ``lint`` parses sources (AST). Whether a plugin is allowed,
loaded or degraded is a fact of a running process (``plugins.allowed`` of its instance layer,
``App.plugins``); these commands report what is installed, its RECORD digest and its provenance, ``unknown``
where it cannot be known."""

import argparse
import ast
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from importlib.metadata import Distribution, EntryPoint, PackageNotFoundError, distribution
from pathlib import Path
from typing import Final

from skm.bootstrap.plugin_distribution import (
    default_entry_points,
    provenance,
    read_runtime_data,
    record_digest,
)
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.output import kv_lines, render, render_table
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.kernel.outcomes import Diagnostic, Severity
from skm.platform.schema.registry import SchemaRegistry

__all__ = ["GROUP", "lint_sources", "register"]

_HELP: Final = {
    "list": "list installed skm.plugins entry points without importing them",
    "show": "show one plugin: distribution, RECORD digest, provenance and runtime data",
    "lint": "check that a plugin imports only skm.plugin_api and its data files are valid",
}
_STABLE: Final = "skm.plugin_api"
EXIT_FINDINGS: Final = 1


@dataclass(frozen=True, slots=True)
class InstalledPlugin:
    plugin_id: str  # entry point name
    target: str  # "module:attribute", not imported
    dist_name: str
    dist_version: str
    record_digest: str
    source: str
    install: str
    dependency_lock: str
    runtimes: tuple[str, ...]  # valid runtime data of step 2a
    status: str = "installed"  # allowed/loaded is decided by a process's plugins.allowed


@dataclass(frozen=True, slots=True)
class InstalledPlugins:
    items: tuple[InstalledPlugin, ...]


@dataclass(frozen=True, slots=True)
class LintReport:
    target: str
    files: int
    findings: int


def _installed(entry: EntryPoint, schemas: SchemaRegistry) -> tuple[InstalledPlugin, list[Diagnostic]]:
    dist = entry.dist
    data, problems = read_runtime_data(dist, schemas)
    origin = provenance(dist)
    item = InstalledPlugin(
        plugin_id=entry.name,
        target=entry.value,
        dist_name="unknown" if dist is None else str(dist.metadata["Name"]),
        dist_version="unknown" if dist is None else dist.version,
        record_digest=record_digest(dist),
        source=origin.source,
        install=origin.install,
        dependency_lock=origin.dependency_lock,
        runtimes=tuple(sorted(data)),
    )
    return item, problems


def _list(args: argparse.Namespace, ctx: CliContext) -> int:
    schemas = SchemaRegistry.load_default()
    found = [_installed(entry, schemas) for entry in default_entry_points()]
    result = InstalledPlugins(tuple(item for item, _ in found))
    diagnostics = [problem for _, problems in found for problem in problems]

    def human(value: InstalledPlugins) -> list[str]:
        if not value.items:
            return ["no skm.plugins entry points are installed"]
        rows = [
            [item.plugin_id, item.dist_name, item.dist_version, item.status, ",".join(item.runtimes) or "-"]
            for item in value.items
        ]
        return render_table(ctx, ["id", "distribution", "version", "status", "runtimes"], rows)

    return render(ctx, result, human=human, command=args.command_name, diagnostics=diagnostics)


def _show(args: argparse.Namespace, ctx: CliContext) -> int:
    entries = [entry for entry in default_entry_points() if entry.name == args.plugin_id]
    if not entries:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            f"no skm.plugins entry point named {args.plugin_id!r} is installed",
            details={"kind": "plugin", "plugin_id": args.plugin_id},
        )
    item, problems = _installed(entries[0], SchemaRegistry.load_default())

    def human(value: InstalledPlugin) -> list[str]:
        pairs: list[tuple[str, object]] = [
            ("id", value.plugin_id),
            ("entry point", f"{value.target} (not imported)"),
            ("distribution", f"{value.dist_name} {value.dist_version}"),
            ("record digest", value.record_digest),
            ("source", value.source),
            ("install", value.install),
            ("dependency lock", value.dependency_lock),
            ("runtimes", ", ".join(value.runtimes) or "none"),
            ("status", value.status),
        ]
        return kv_lines(ctx, pairs)

    return render(ctx, item, human=human, command=args.command_name, diagnostics=problems)


def _imported_modules(tree: ast.AST) -> Iterator[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from ((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            if node.module == "skm":  # "from skm import x" imports skm.x
                yield from ((node.lineno, f"skm.{alias.name}") for alias in node.names)
            else:
                yield node.lineno, node.module


def lint_sources(files: Iterable[tuple[str, str]]) -> tuple[Diagnostic, ...]:
    """Findings for ``(path, source)``: every ``skm`` import outside ``skm.plugin_api`` (02-plugins §2)."""
    findings: list[Diagnostic] = []
    for path, source in files:
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError as exc:
            findings.append(
                Diagnostic("PLUGIN_LINT_SYNTAX", f"{path}:{exc.lineno}: not Python", Severity.ERROR, path)
            )
            continue
        for line, module in _imported_modules(tree):
            unstable = (module == "skm" or module.startswith("skm.")) and not (
                module == _STABLE or module.startswith(_STABLE + ".")
            )
            if unstable:
                message = f"{path}:{line}: imports {module}; plugins may import only {_STABLE}"
                details = {"line": line, "module": module}
                finding = Diagnostic("PLUGIN_UNSTABLE_IMPORT", message, Severity.WARNING, path, details)
                findings.append(finding)
    return tuple(findings)


def _sources_of(target: str) -> tuple[list[tuple[str, str]], Distribution | None]:
    path = Path(target)
    if path.exists():
        files = [path] if path.is_file() else sorted(path.rglob("*.py"))
        return [(str(file), file.read_text(encoding="utf-8")) for file in files], None
    try:
        dist = distribution(target)
    except PackageNotFoundError:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            f"{target!r} is neither a path nor an installed distribution",
            details={"kind": "plugin_distribution", "target": target},
        ) from None
    sources = [
        (file.as_posix(), file.read_text(encoding="utf-8"))
        for file in dist.files or ()
        if file.suffix == ".py"
    ]
    return sources, dist


def _entry_point_findings(dist: Distribution) -> list[Diagnostic]:
    """The manifest each ``skm.plugins`` entry point names is assigned at module level (no import)."""
    findings: list[Diagnostic] = []
    files = {file.as_posix(): file for file in dist.files or ()}
    for entry in (item for item in dist.entry_points if item.group == "skm.plugins"):
        module, _, attribute = entry.value.partition(":")
        stem = module.strip().replace(".", "/")
        source = files.get(f"{stem}.py") or files.get(f"{stem}/__init__.py")
        body = [] if source is None else ast.parse(source.read_text(encoding="utf-8")).body
        names: set[str] = {
            target.id
            for node in body
            if isinstance(node, ast.Assign | ast.AnnAssign)
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
            if isinstance(target, ast.Name)
        }
        if attribute.strip() not in names:
            message = f"entry point {entry.name} = {entry.value}: no module-level {attribute.strip() or '?'}"
            findings.append(Diagnostic("PLUGIN_LOAD_FAILED", message, Severity.ERROR, entry.name))
    return findings


def _lint(args: argparse.Namespace, ctx: CliContext) -> int:
    sources, dist = _sources_of(args.target)
    findings = list(lint_sources(sources))
    if dist is not None:
        findings.extend(_entry_point_findings(dist))
        findings.extend(read_runtime_data(dist, SchemaRegistry.load_default())[1])
    report = LintReport(args.target, len(sources), len(findings))

    def human(value: LintReport) -> list[str]:
        verdict = "clean" if not value.findings else f"{value.findings} finding(s)"
        return [f"{value.target}: {value.files} Python file(s), {verdict}"]

    render(ctx, report, human=human, command=args.command_name, diagnostics=findings)
    return EXIT_FINDINGS if findings else 0


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("plugins", help="inspect installed plugins without importing them")
    verbs = parser.add_subparsers(dest="plugins_verb", required=True)
    for verb in ("list", "show", "lint"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.set_defaults(run=_RUN[verb], command_name=f"plugins.{verb}")
        command.add_argument(
            "--json",
            default=argparse.SUPPRESS,
            action="store_true",
            help="machine-readable output (as global --json)",
        )
        if verb == "show":
            command.add_argument("plugin_id", metavar="ID", help="entry point name (the plugin id)")
        elif verb == "lint":
            command.add_argument("target", metavar="DIST_OR_PATH", help="distribution name or source path")


_RUN = {"list": _list, "show": _show, "lint": _lint}

GROUP = CommandGroup(
    "plugins",
    "inspect installed plugins without importing them",
    register,
    requires_backend=False,
    order=45,
)
