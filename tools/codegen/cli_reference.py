"""Generate CLI reference from declarations, without importing commands or running handlers."""

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import cast

from skm.platform.storage.verify import CATALOG, LEVELS

CONFIG_GUIDE = """## CLI configuration operations

See [CLI reference](cli.md) for the generated command and flag inventory.
The CLI uses only `settings.public` DTOs through `SkmClient`; scope resolution,
permissions, locks, narrowing, validation, history and atomic import remain facade behavior.
The production backend still requires the public authorizer and acting-principal owners;
tests use an explicit test composition, without adding a production fallback.

`get` uses the owner's `settings.get_value` contract. `explain` accepts multiple keys,
`--section`, `--detail value|full` and `--all` (defaults are included).
Secret values are never resolved; the facade returns references only, including when
`--show-secrets-refs` is supplied. Registered credentials and terminal controls use the
shared CLI redaction and escaping boundary in human, raw, export and JSON output.
Canonical `secret://` references are not credentials: get, explain, entries, history
and both export formats preserve them, and an exported reference reimports unchanged.
A plaintext value in a reference field is rejected with `CONFIG_INVALID`.
Raw `get` and plain `export` escape terminal controls as `\\uXXXX` inside strings,
so the document stays valid JSON or TOML and reimports unchanged.

Scope defaults to the selected project, then workspace, then instance. Explicit UUID
selectors work for workspace, project, plan, run and host; aliases, slugs and host names
remain unavailable until their owning reference resolvers exist. No direct repository
lookup or authority fallback is used. `--scope`, `--json` and `--yes` work before the
group or after the verb. Other global flags precede the group.

`set` parses text by the declared key type (settings §B.11.3): strings remain strings,
booleans accept true/false, yes/no, on/off and 1/0; arrays accept JSON or comma-separated
items; objects require JSON. `--append` selects append mode. `--lock`, `--reason`,
`--expect-version` (alias `--expected-version`) and `--yes` map to the owner DTO.
Version 0 means create only. Confirmed writes still require the bus permissions.
The key type comes from `settings.get_schema` with the write's scope, so `config.read`
is checked there, before any metadata; a project writer needs no instance right.
`config schema` keeps the instance scope. The CLI sets no nesting limit of its own: the
facade judges every value and document, and input the request cannot recurse through
is refused with `CONFIG_INVALID` before dispatch.
`unset` stores an explicit reset to the schema default; `remove` deletes the contribution
and reveals inheritance. Locks and unlocks are validated by the facade.

`import` reads `.toml` or `.json` files, at most 1 MiB, and passes their document to
`settings.import_config`. `--replace`, `--dry-run`, `--expect-digest`, `--reason` and
`--yes` map to its contract. A dry run displays changes and problems without applying
them; problems return exit 1. Special document fields are top-level `schema`, `unset`,
`lock` and `append`; nested tables contain section values. `export` writes a scope's
stored entries (not effective values), defaults to TOML, supports JSON and
`--portable-only`, and keeps secret references. Global `--json` always returns one
CLI envelope; `export --format json` selects the document format inside it.

`entries --prefix` and `history [KEY]` accept `--after` and `--limit` (at most 500).
History defaults to 20 rows. A returned `next` cursor continues the page. Human output is
a table: entries show `key op value locked version updated reason`, history shows
`at actor op key old → new reason`; `--json` keeps the `{items, next}` page.

### Doctor

`config doctor [--only CHECK]…` asks the public `platform.doctor` query (permission
`config.read` at the instance; it takes no `--scope` because it covers every scope). It
reports the registry, stored entries of all scopes (unknown and deprecated keys, scope,
pack, override and operation violations, entries below a lock, narrowing violations and
values that no longer validate) and the restart-pending state of the process that
answers, then the recorded checks of enabled modules. Each check prints `status id
message [target]`, its identifier-only detail and hint. `warn` marks what could not be
established (no process snapshot, uncollected or failed checks); it is never reported as
`ok`, and restart-pending is not claimed for other processes or hosts. Output carries
identifiers and error codes only, never configured values or secrets. Exit 6 when any
check is `fail`; `--only` selects exact check ids and an unknown id is refused.
"""


_OWNERS = {
    "settings": "settings",
    "platform_queries": "platform",
    "knowledge": "knowledge",
    "learning": "learning",
    "exports": "exports",
}


def _assignments(tree):
    return {
        target.id: node.value
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None
        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, ast.Name)
    }


def _value(node, env):
    if isinstance(node, ast.Name):
        return env[node.id]
    if isinstance(node, ast.IfExp):
        return _value(node.body if _condition(node.test, env) else node.orelse, env)
    return ast.literal_eval(node)


def _condition(node, env):
    if not isinstance(node, ast.Compare) or len(node.ops) != 1:
        raise ValueError("unsupported CLI declaration condition")
    left, right = _value(node.left, env), _value(node.comparators[0], env)
    op = node.ops[0]
    if isinstance(op, ast.Eq):
        return left == right
    if isinstance(op, ast.NotEq):
        return left != right
    if isinstance(op, ast.In):
        return left in right
    raise ValueError("unsupported CLI declaration comparison")


def _arguments(statements, env, parsers=frozenset({"command"}), helpers=None):  # noqa: PLR0912
    """Read argument declarations, including shared parser builders, without executing product code."""
    helpers = helpers or {}
    result = []
    for node in statements:
        if isinstance(node, ast.If):
            result.extend(
                _arguments(node.body if _condition(node.test, env) else node.orelse, env, parsers, helpers)
            )
        elif isinstance(node, ast.For) and isinstance(node.target, ast.Name):
            # The outer operation loop is handled by the caller.
            if isinstance(node.iter, (ast.Tuple, ast.List)):
                for value in _value(node.iter, env):
                    result.extend(_arguments(node.body, {**env, node.target.id: value}, parsers, helpers))
        elif (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id in helpers
            and len(node.value.args) == 1
            and isinstance(node.value.args[0], ast.Name)
            and node.value.args[0].id in parsers
        ):
            helper = helpers[node.value.func.id]
            result.extend(_arguments(helper.body, env, frozenset({helper.args.args[0].arg})))
        elif (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id in parsers
            and node.value.func.attr == "add_mutually_exclusive_group"
        ):
            parsers |= {target.id for target in node.targets if isinstance(target, ast.Name)}
        elif (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id in parsers
            and node.value.func.attr == "add_argument"
        ):
            call = node.value
            names = [_value(arg, env) for arg in call.args]
            options = {}
            for keyword in call.keywords:
                if keyword.arg is None:
                    options.update(_value(keyword.value, env))
                elif keyword.arg in {"nargs", "choices"}:
                    options[keyword.arg] = _value(keyword.value, env)
            if names[0].startswith("--"):
                shown = ", ".join(names)
                if "choices" in options:
                    shown += " " + "|".join(options["choices"])
                result.append(shown)
            else:
                shown = names[0].upper()
                if options.get("nargs") in {"?", "*"}:
                    shown = "[" + shown + ("…" if options["nargs"] == "*" else "") + "]"
                result.append(shown)
    return result


def _direct_commands(body, stem, helpers):
    parsers = {}
    for node in body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "add_parser"
        ):
            parsers[node.targets[0].id] = node.value
    for node in body:
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "set_defaults"
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id in parsers
        ):
            name = node.value.func.value.id
            declaration = parsers[name]
            verb = ast.literal_eval(declaration.args[0])
            help_text = ast.literal_eval(next(k.value for k in declaration.keywords if k.arg == "help"))
            operation = ast.literal_eval(
                next(k.value for k in node.value.keywords if k.arg == "command_name")
            )
            command = f"skm {stem}" if verb == stem else f"skm {stem} {verb}"
            arguments = _arguments(body, {}, frozenset({name}), helpers)
            yield command, operation, help_text, "; ".join(arguments)


def _parser_helpers(path, tree, sources):
    def parser_builder(name):
        return (name.startswith("register_") and name.endswith("_args")) or name == "register_args"

    helpers = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and parser_builder(node.name)
    }
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
            wanted = {
                alias.name: alias.asname or alias.name for alias in node.names if parser_builder(alias.name)
            }
            if not wanted:
                continue
            source = path.with_name(node.module + ".py")
            if source.is_file():
                text = source.read_text(encoding="utf-8")
                sources[source.name] = text
                helpers.update(
                    (wanted[fn.name], fn)
                    for fn in ast.parse(text).body
                    if isinstance(fn, ast.FunctionDef) and fn.name in wanted
                )
    return helpers


def outputs(root: Path) -> dict[Path, str]:
    directory = root / "src/skm/entrypoints/cli"
    parser = directory / "parser.py"
    if not parser.is_file():
        return {}
    sources = {"parser.py": parser.read_text(encoding="utf-8")}
    rows = []
    for path in sorted((directory / "commands").glob("*.py")):
        if path.name.startswith("_"):
            continue
        sources[path.name] = path.read_text(encoding="utf-8")
        tree = ast.parse(sources[path.name])
        assigned = _assignments(tree)
        if path.stem == "version":
            rows.append(("skm version", "local", "print package, schema and Python versions", "—"))
            continue
        if "COMMAND" in assigned and "HELP" in assigned:
            # Standalone host commands expose the same parser builder for their group alias.
            builder = next(
                node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "add_parser"
            )
            arguments = [
                ", ".join(ast.literal_eval(arg) for arg in node.args)
                for node in ast.walk(builder)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"
            ]
            operation = ast.literal_eval(assigned["COMMAND"])
            help_text = ast.literal_eval(assigned["HELP"])
            rows.extend(
                (f"{prefix} {path.stem}", operation, help_text, "; ".join(arguments))
                for prefix in ("skm", "skm integrations")
            )
            continue
        register = next(
            node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "register"
        )
        helpers = _parser_helpers(path, tree, sources)
        if "_HELP" not in assigned:
            rows.extend(_direct_commands(register.body, path.stem, helpers))
            continue
        help_text = ast.literal_eval(assigned["_HELP"])
        loop = next(node for node in register.body if isinstance(node, ast.For))
        if "_OPERATIONS" not in assigned:
            # A local group (no bus operation): the verbs are the literal tuple the register loop walks.
            for verb in _value(loop.iter, {}):
                arguments = _arguments(loop.body, {"verb": verb}, helpers=helpers)
                rows.append((f"skm {path.stem} {verb}", "local", help_text[verb], "; ".join(arguments)))
            continue
        rows.extend(_direct_commands(register.body, path.stem, helpers))
        operations = cast("ast.Dict", assigned["_OPERATIONS"])
        env = {"LEVELS": LEVELS, "_CODES": tuple(CATALOG)} if path.stem == "storage" else {}
        if "_WRITES" in assigned:
            env["_WRITES"] = _value(cast("ast.Call", assigned["_WRITES"]).args[0], {})
        for key, operation in zip(operations.keys, operations.values, strict=True):
            verb = ast.literal_eval(cast("ast.expr", key))
            if isinstance(operation, ast.Constant) and isinstance(operation.value, str):
                operation_name = operation.value
            else:
                attribute = cast("ast.Attribute", operation)
                name = re.sub(r"(?<!^)(?=[A-Z])", "_", attribute.attr).lower()
                owner = _OWNERS[cast("ast.Name", attribute.value).id]
                operation_name = f"{owner}.{name}"
            arguments = _arguments(loop.body, {**env, "verb": verb}, helpers=helpers)
            rows.append((f"skm {path.stem} {verb}", operation_name, help_text[verb], "; ".join(arguments)))
    sha = hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()
    flags = ast.literal_eval(_assignments(ast.parse(sources["parser.py"]))["GLOBAL_FLAGS"])
    lines = [
        f"<!-- generated by tools/gen.py; sources sha256:{sha}; do not edit -->",
        "",
        "# CLI reference",
        "",
        "Derived from command declarations without importing commands, building an App or invoking handlers.",
        "",
        "## Global flags",
        "",
        "Global flags precede the group. `--version` prints the package version without a backend.",
        "",
        "| Flags | Meaning |",
        "| --- | --- |",
        *(f"| `{', '.join(names)}` | {options['help']} |" for names, options in flags),
        "",
        "## Commands",
        "",
        "| Command | Operation | Purpose | Arguments and flags |",
        "| --- | --- | --- | --- |",
    ]
    lines.extend("| " + " | ".join(str(cell).replace("|", "\\|") for cell in row) + " |" for row in rows)
    # CONFIG_GUIDE supplies the final newline; another empty line would leave a blank line at EOF.
    lines.extend(["", CONFIG_GUIDE])
    return {Path("docs/reference/cli.md"): "\n".join(lines)}
