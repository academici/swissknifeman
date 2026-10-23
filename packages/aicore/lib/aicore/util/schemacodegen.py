"""``aicore schema codegen``: stdlib TypedDict modules from the closed-profile contract schemas.

``generate(root)`` reads every ``*.schema.json`` of one directory and returns the text of a Python module (stdlib
``typing`` only, Python 3.11). The module is deterministic: schema files and ``$defs`` are walked in sorted order, a
declaration follows the declarations it uses. A shape without a mapping fails closed with
``SCHEMA_CODEGEN_UNSUPPORTED: <file>:<pointer>``; nothing is simplified silently.

Mapping (the types are annotations; the validator stays the authority on the documents):

* closed object with ``properties`` -> ``class X(TypedDict)``, a key outside ``required`` is ``NotRequired[T]``; a key
  that is no identifier (``$schema``) selects the functional ``TypedDict("X", {...})`` form;
* open object (``additionalProperties`` absent), with or without ``properties`` -> ``Dict[str, Any]``;
* ``patternProperties`` on a closed object -> ``Dict[str, T]``, ``T`` is the type of the catch-all pattern (``^.+$``,
  it applies to every key) or else the union of all pattern types; a closed object with ``properties`` and
  ``patternProperties`` -> ``Dict[str, Union[...]]`` of both;
* ``enum`` / ``const`` -> ``Literal[...]``; ``type`` list -> ``Union`` (``Optional`` with null); ``items`` -> ``List``;
* ``oneOf`` of typed branches -> ``Union`` (an object branch becomes ``<Name>Variant<N>``);
* ``oneOf`` of constraint branches (only ``required``, ``properties``, ``not``) next to the properties of the same
  node chooses between key sets of one object: the class has the keys of ``properties`` and the keys that no branch
  requires are ``NotRequired``; a branch key the node does not declare is unsupported;
* ``$ref`` -> the class of the target in the same directory, else ``Any  # external: <urn>``; a ``$ref`` with ``properties``,
  ``required``, ``additionalProperties`` or ``oneOf`` beside it is the referenced object merged with them (a sibling that
  retypes a key, or a target that is no plain object, is unsupported); other siblings only narrow it; a node that has no type of its own is ``Any`` (``Dict[str, Any]`` when it
  requires keys);
* ``not``, ``dependentRequired``, ``uniqueItems``, ``minItems``, ``pattern``, ``minLength`` and the other bounds do not
  change the type.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import keyword
import re
import sys
from pathlib import Path
from typing import Any, Mapping, NoReturn, Optional, Sequence, TextIO, Union, cast

from .jsonschema_core import SchemaProfileError, _check_profile  # pyright: ignore[reportPrivateUsage]

Node = dict[str, Any]  # a JSON object of a schema

UNSUPPORTED = "SCHEMA_CODEGEN_UNSUPPORTED"
DRIFT = "SCHEMA_CODEGEN_DRIFT"
USAGE_CODE = "SCHEMA_CODEGEN_USAGE"

_KIND = re.compile(r".*:([a-z][a-z0-9-]*):v[1-9][0-9]*\Z")
_WORDS = re.compile(r"[A-Za-z0-9]+")
_CATCH_ALL = frozenset({"^.+$", "^.*$", ".+", ".*"})
# keywords that give a node a type of its own; any other keyword only constrains or annotates
_TYPED = ("type", "enum", "const", "items", "properties", "patternProperties", "$ref")
# siblings of a $ref that change the shape of the referenced object; the other siblings only constrain values
_SHAPE = ("properties", "required", "additionalProperties", "oneOf")
_ANNOTATION = frozenset({"description", "title", "default"})
_CONSTRAINT_BRANCH = frozenset({"description", "title", "required", "properties", "not", "default"})


class CodegenError(Exception):
    """A refusal with a stable code; ``str()`` is the line printed by the command."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _unsupported(file: str, pointer: str, reason: str) -> CodegenError:
    return CodegenError(UNSUPPORTED, f"{file}:{pointer or '/'} ({reason})")


# ---- type expressions ---------------------------------------------------------------------------------------------

class _Expr:
    """A type expression; rendering decides which class names need quotes (declared later or in a cycle)."""

    def render(self, emitted: set[str], used: set[str]) -> str:
        raise NotImplementedError

    def refs(self) -> set[str]:
        return set()

    def externals(self) -> set[str]:
        return set()


class _Prim(_Expr):
    def __init__(self, text: str, needs: str = ""):
        self.text, self.needs = text, needs

    def render(self, emitted: set[str], used: set[str]) -> str:
        if self.needs:
            used.add(self.needs)
        return self.text


class _Ref(_Expr):
    def __init__(self, name: str):
        self.name = name

    def render(self, emitted: set[str], used: set[str]) -> str:
        return self.name if self.name in emitted else f'"{self.name}"'

    def refs(self) -> set[str]:
        return {self.name}


class _External(_Expr):
    def __init__(self, urn: str):
        self.urn = urn

    def render(self, emitted: set[str], used: set[str]) -> str:
        used.add("Any")
        return "Any"

    def externals(self) -> set[str]:
        return {self.urn}


class _Wrap(_Expr):
    """``Head[args]`` for List, Dict, NotRequired, Optional, Union and Literal."""

    def __init__(self, head: str, *args: Union[str, _Expr]):
        self.head, self.args = head, args

    def render(self, emitted: set[str], used: set[str]) -> str:
        used.add(self.head)
        parts = [arg if isinstance(arg, str) else arg.render(emitted, used) for arg in self.args]
        return f"{self.head}[{', '.join(parts)}]"

    def refs(self) -> set[str]:
        return {name for arg in self.args if isinstance(arg, _Expr) for name in arg.refs()}

    def externals(self) -> set[str]:
        return {urn for arg in self.args if isinstance(arg, _Expr) for urn in arg.externals()}


_ANY = _Prim("Any", "Any")
_OPEN_OBJECT = _Wrap("Dict", "str", _ANY)


def _flat(members: Sequence[_Expr]) -> list[_Expr]:
    """The members of a union with the unions among them opened (``Optional[T]`` is ``T`` and ``None``)."""
    out: list[_Expr] = []
    for member in members:
        if isinstance(member, _Wrap) and member.head in ("Union", "Optional"):
            out.extend(_flat([arg for arg in member.args if isinstance(arg, _Expr)]))
            if member.head == "Optional":
                out.append(_Prim("None"))
        else:
            out.append(member)
    return out


def _union(members: Sequence[_Expr]) -> _Expr:
    unique: list[_Expr] = []
    seen: set[str] = set()
    for member in _flat(members):
        key = _key(member)
        if key not in seen:
            seen.add(key)
            unique.append(member)
    none = [m for m in unique if isinstance(m, _Prim) and m.text == "None"]
    rest = [m for m in unique if not (isinstance(m, _Prim) and m.text == "None")]
    if any(isinstance(m, _Prim) and m.text == "Any" for m in rest):
        return _ANY
    if not rest:
        return none[0]
    if len(rest) == 1 and not none:
        return rest[0]
    if len(rest) == 1:
        return _Wrap("Optional", rest[0])
    return _Wrap("Union", *rest, *none)


def _key(expr: _Expr) -> str:
    return expr.render(set(), set())


# ---- declarations -------------------------------------------------------------------------------------------------

class _Decl:
    def __init__(self, name: str, file: str):
        self.name, self.file = name, file
        self.fields: Optional[list[tuple[str, _Expr, bool]]] = None  # [(key, expr, required)] for a TypedDict
        self.alias: Optional[_Expr] = None
        self.note = ""

    def refs(self) -> set[str]:
        found: set[str] = set()
        for _name, expr, _required in self.fields or ():
            found |= expr.refs()
        if self.alias is not None:
            found |= self.alias.refs()
        found.discard(self.name)
        return found

    def externals(self) -> set[str]:
        found: set[str] = set()
        for _name, expr, _required in self.fields or ():
            found |= expr.externals()
        if self.alias is not None:
            found |= self.alias.externals()
        return found


def _camel(text: str) -> str:
    return "".join(word[:1].upper() + word[1:] for word in _WORDS.findall(text))


def _word(text: str) -> str:
    return _camel(text) or "Field"


class _Document:
    def __init__(self, file: str, schema: Node, kind: str):
        self.file, self.schema, self.kind = file, schema, kind
        self.name = _camel(kind)


class _Generator:
    def __init__(self, documents: list[_Document]):
        self.documents = documents
        self.by_id: dict[str, _Document] = {doc.schema["$id"]: doc for doc in documents}
        self.decls: dict[str, _Decl] = {}
        self.order: list[str] = []
        self.defs: dict[tuple[str, str], str] = {}  # (document id, def name) -> declaration name
        self.roots: dict[str, str] = {}  # document id -> declaration name (when the root maps to a type)
        self._top = ""  # the declaration being mapped; its object class takes the same name
        self._top_free = False

    def run(self) -> list[_Decl]:
        # names first, so that a reference may point forward
        for doc in self.documents:
            schema_id = doc.schema["$id"]
            if self._has_type(doc.schema) or "oneOf" in doc.schema:
                self.roots[schema_id] = doc.name
            for def_name in sorted(doc.schema.get("$defs", {})):
                self.defs[(schema_id, def_name)] = doc.name + _word(def_name)
        for doc in self.documents:
            schema_id = doc.schema["$id"]
            if schema_id in self.roots:
                self._declare_node(doc, self.roots[schema_id], doc.schema, "")
            for def_name in sorted(doc.schema.get("$defs", {})):
                self._declare_node(doc, self.defs[(schema_id, def_name)], doc.schema["$defs"][def_name],
                                   f"/$defs/{_escape(def_name)}")
        return [self.decls[name] for name in self.order]

    @staticmethod
    def _has_type(node: Node) -> bool:
        return any(key in node for key in _TYPED)

    def _declare(self, name: str, file: str, pointer: str) -> _Decl:
        if name in self.decls:
            raise _unsupported(file, pointer, f"class name {name} is used twice")
        decl = _Decl(name, file)
        self.decls[name] = decl
        self.order.append(name)
        return decl

    def _declare_node(self, doc: _Document, name: str, node: Node, pointer: str) -> None:
        decl = self._declare(name, doc.file, pointer)
        self._top, self._top_free = name, True
        expr = self._map(doc, node, name, pointer, top=True)
        if isinstance(expr, _Ref) and expr.name == name and decl.fields is not None:
            return  # the node is the class itself
        decl.alias = expr
        if expr in (_ANY, _OPEN_OBJECT) and not self._has_type(node):
            decl.note = "constraint-only schema: no type of its own"

    # -- mapping
    def _map(self, doc: _Document, node: Node, name: str, pointer: str, top: bool = False) -> _Expr:
        if "$ref" in node:
            for keyword_ in ("type", "enum", "const", "items", "patternProperties"):
                if keyword_ in node:
                    raise _unsupported(doc.file, pointer, f"{keyword_} next to $ref")
            if any(key in node for key in _SHAPE):
                return self._compose(doc, node, name, pointer, top)
            return self._ref(doc, node["$ref"], pointer)
        if "oneOf" in node:
            return self._one_of(doc, node, name, pointer)
        if "enum" in node or "const" in node:
            return self._literal(doc, node, pointer)
        types = node.get("type")
        if types is None:
            if "properties" in node or "patternProperties" in node:
                types = ["object"]
            elif "items" in node:
                types = ["array"]
            else:
                return _OPEN_OBJECT if "required" in node else _ANY
        if isinstance(types, str):
            types = [types]
        # the declared name is taken by the alias when the node is a union
        object_name = name + "Object" if top and len(types) > 1 else name
        return _union([self._of_type(doc, t, node, object_name if t == "object" else name, pointer)
                       for t in types])

    def _of_type(self, doc: _Document, type_name: str, node: Node, name: str, pointer: str) -> _Expr:
        if type_name == "string":
            return _Prim("str")
        if type_name == "integer":
            return _Prim("int")
        if type_name == "number":
            return _Prim("float")
        if type_name == "boolean":
            return _Prim("bool")
        if type_name == "null":
            return _Prim("None")
        if type_name == "array":
            if "items" not in node:
                return _Wrap("List", _ANY)
            return _Wrap("List", self._map(doc, node["items"], name + "Item", f"{pointer}/items"))
        return self._object(doc, node, name, pointer)

    def _object(self, doc: _Document, node: Node, name: str, pointer: str) -> _Expr:
        properties = node.get("properties", {})
        patterns = node.get("patternProperties", {})
        if node.get("additionalProperties") is not False:
            return _OPEN_OBJECT
        if patterns:
            members = [self._map(doc, child, name + "Value" + (str(n) if len(patterns) > 1 else ""),
                                 f"{pointer}/patternProperties/{_escape(key)}")
                       for n, (key, child) in enumerate(patterns.items(), 1)]
            catch_all = [m for key, m in zip(patterns, members) if key in _CATCH_ALL]
            own = [self._map(doc, child, name + _word(key), f"{pointer}/properties/{_escape(key)}")
                   for key, child in properties.items()]
            return _Wrap("Dict", "str", _union(own + (catch_all or members)))
        required = node.get("required", [])
        for key in required:
            if key not in properties:
                raise _unsupported(doc.file, pointer, f"required key {key!r} has no property")
        self._branch_keys(doc, node, pointer)
        if self._top_free and name == self._top:
            decl = self.decls[name]
            self._top_free = False
        else:
            decl = self._declare(name, doc.file, pointer)
        decl.fields = [(key, self._map(doc, child, name + _word(key), f"{pointer}/properties/{_escape(key)}"),
                        key in required) for key, child in properties.items()]
        return _Ref(name)

    @staticmethod
    def _branch_keys(doc: _Document, node: Node, pointer: str) -> None:
        """A constraint branch of ``oneOf`` may only speak of keys the node declares."""
        properties = node.get("properties")
        if properties is None:
            return
        for index, branch in enumerate(node.get("oneOf", ())):
            for key in list(branch.get("required", ())) + list(branch.get("properties", {})):
                if key not in properties:
                    raise _unsupported(doc.file, f"{pointer}/oneOf/{index}",
                                       f"branch key {key!r} is not a property of the object")

    @staticmethod
    def _literal(doc: _Document, node: Node, pointer: str) -> _Expr:
        values = node["enum"] if "enum" in node else [node["const"]]
        parts: list[str] = []
        for value in values:
            if value is None or isinstance(value, (bool, int)):
                parts.append(repr(value))
            elif isinstance(value, str):
                parts.append(json.dumps(value, ensure_ascii=False))
            else:
                raise _unsupported(doc.file, pointer, f"enum value {value!r} cannot be a Literal")
        return _Wrap("Literal", *dict.fromkeys(parts))

    def _one_of(self, doc: _Document, node: Node, name: str, pointer: str) -> _Expr:
        branches = node["oneOf"]
        constraint = [all(key in _CONSTRAINT_BRANCH for key in branch) for branch in branches]
        rest = {k: v for k, v in node.items() if k != "oneOf"}
        if all(constraint):
            if not self._has_type(rest):
                # no type of its own: the branches only choose between key sets of another schema
                return _OPEN_OBJECT if any("required" in b or "properties" in b for b in branches) else _ANY
            self._branch_keys(doc, node, pointer)
            return self._map(doc, rest, name, pointer)
        if any(constraint):
            raise _unsupported(doc.file, pointer, "oneOf mixes typed and constraint branches")
        if self._has_type(rest):
            raise _unsupported(doc.file, pointer, "oneOf next to the type of the same node")
        return _union([self._map(doc, branch, f"{name}Variant{index}", f"{pointer}/oneOf/{index - 1}")
                       for index, branch in enumerate(branches, 1)])

    def _compose(self, doc: _Document, node: Node, name: str, pointer: str, top: bool) -> _Expr:
        """A ``$ref`` whose siblings change the shape of the target: the target object with its keys, the extra
        ``required`` and the closing ``additionalProperties`` of the siblings, mapped as one object. A sibling
        ``properties`` entry only annotates a key the target declares, or adds a key it does not."""
        ref = node["$ref"]
        owner, target = self._target(doc, ref, pointer)
        if owner is None:
            raise _unsupported(doc.file, pointer, f"siblings of the external $ref {ref!r} cannot be composed")
        if not isinstance(target, dict) or target.get("type", "object") != "object" or "patternProperties" in target \
                or any(key in target for key in ("$ref", "oneOf", "enum", "const", "items")):
            raise _unsupported(doc.file, pointer, f"$ref {ref!r} with siblings needs an object target without "
                                                  "$ref, oneOf or patternProperties")
        properties: Node = dict(target.get("properties", {}))
        for key, child in node.get("properties", {}).items():
            if key in properties and not all(word in _ANNOTATION for word in child):
                raise _unsupported(doc.file, f"{pointer}/properties/{_escape(key)}",
                                   f"sibling of $ref {ref!r} retypes the key {key!r}")
            properties.setdefault(key, child)
        merged: Node = {key: value for key, value in target.items() if key not in ("description", "title")}
        merged.update({key: node[key] for key in ("additionalProperties", "oneOf") if key in node})
        merged["type"] = "object"
        merged["properties"] = properties
        merged["required"] = sorted(set(target.get("required", ())) | set(node.get("required", ())))
        return self._map(owner, merged, name, pointer, top)

    def _target(self, doc: _Document, ref: str, pointer: str) -> tuple[Optional[_Document], Optional[Node]]:
        """``(document, node)`` of a ``$ref`` into this directory, ``(None, None)`` outside it."""
        document, _, fragment = ref.partition("#")
        target = self.by_id.get(document or doc.schema["$id"])
        if target is None:
            return None, None
        if not fragment:
            return target, target.schema
        if fragment.startswith("/$defs/") and fragment.count("/") == 2:
            found = target.schema.get("$defs", {}).get(fragment[len("/$defs/"):])
            if found is not None:
                return target, found
        raise _unsupported(doc.file, pointer, f"$ref {ref!r} does not resolve")

    def _ref(self, doc: _Document, ref: str, pointer: str) -> _Expr:
        document, _, fragment = ref.partition("#")
        target = self.by_id.get(document or doc.schema["$id"])
        if target is None:
            return _External(document)
        schema_id = target.schema["$id"]
        if not fragment:
            if schema_id not in self.roots:
                raise _unsupported(doc.file, pointer, f"$ref {ref!r} names a root that has no type")
            return _Ref(self.roots[schema_id])
        if fragment.startswith("/$defs/") and fragment.count("/") == 2:
            found = self.defs.get((schema_id, fragment[len("/$defs/"):]))
            if found is not None:
                return _Ref(found)
        raise _unsupported(doc.file, pointer, f"$ref {ref!r} does not resolve")


def _escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


# ---- rendering ----------------------------------------------------------------------------------------------------

def _order(decls: list[_Decl]) -> list[_Decl]:
    """Declarations before their users; a reference that points forward or into a cycle is quoted when rendered."""
    by_name = {decl.name: decl for decl in decls}
    done: list[_Decl] = []
    state: dict[str, int] = {}

    def visit(decl: _Decl) -> None:
        if state.get(decl.name):
            return
        state[decl.name] = 1
        for dep in sorted(decl.refs()):
            visit(by_name[dep])
        done.append(decl)

    for decl in decls:
        visit(decl)
    return done


def _render_decl(decl: _Decl, emitted: set[str], used: set[str]) -> str:
    comment = ""
    externals = sorted(decl.externals())
    if externals:
        comment = "  # external: " + ", ".join(externals)
    if decl.fields is None:
        text = decl.alias.render(emitted, used) if decl.alias is not None else "Any"
        note = f"  # {decl.note}" if decl.note and not comment else ""
        return f"{decl.name} = {text}{comment}{note}\n"
    used.add("TypedDict")
    rows: list[tuple[str, str]] = []
    for key, expr, required in decl.fields:
        text = expr.render(emitted, used)
        if not required:
            used.add("NotRequired")
            text = f"NotRequired[{text}]"
        rows.append((key, text))
    functional = any(not key.isidentifier() or keyword.iskeyword(key) for key, _text in rows)
    if functional:
        body = "".join(f"    {json.dumps(key)}: {text},\n" for key, text in rows)
        return f'{decl.name} = TypedDict("{decl.name}", {{\n{body}}}){comment}\n'
    body = "".join(f"    {key}: {text}\n" for key, text in rows) or "    pass\n"
    return f"class {decl.name}(TypedDict):{comment}\n{body}"


_TYPING_ORDER = ("Any", "Dict", "List", "Literal", "NotRequired", "Optional", "TypedDict", "Union")


def load_documents(root: Path) -> list[_Document]:
    root = Path(root)
    files = sorted(root.glob("*.schema.json"))
    if not files:
        raise CodegenError(USAGE_CODE, f"no *.schema.json files in {root}")
    documents: list[_Document] = []
    for path in files:
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise _unsupported(path.name, "", f"cannot load schema: {exc}") from exc
        try:
            _check_profile(schema, path.name, "", root=True)
        except SchemaProfileError as exc:
            text = str(exc)
            reason, _, pointer = text.rpartition(" at ")
            raise _unsupported(path.name, pointer, reason.partition(": ")[2] or reason) from exc
        match = _KIND.fullmatch(str(schema.get("$id", "")))
        if match is None:
            raise _unsupported(path.name, "/$id", "$id must end with <kind>:v<N>")
        documents.append(_Document(path.name, schema, match.group(1)))
    return documents


def schema_digest(root: Path) -> str:
    """sha256 over the sorted schema file names and bytes: the same schemas give the same digest anywhere."""
    digest = hashlib.sha256()
    for path in sorted(Path(root).glob("*.schema.json")):
        digest.update(path.name.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def generate(root: Path, label: Optional[str] = None) -> str:
    """The module text for the schemas in ``root``; ``label`` is the directory as the header names it."""
    root = Path(root)
    documents = load_documents(root)
    decls = _order(_Generator(documents).run())
    emitted: set[str] = set()
    used: set[str] = set()
    blocks: list[str] = []
    for decl in decls:
        blocks.append(_render_decl(decl, emitted, used))
        emitted.add(decl.name)
    names = ", ".join(name for name in _TYPING_ORDER if name in used)
    header = (f"# Generated by aicore schema codegen from {label or root.as_posix()} "
              f"(sha256 {schema_digest(root)}); do not edit.\n")
    imports = f"from typing import {names}\n\n\n" if names else "\n\n"
    return header + imports + "\n\n".join(blocks)


# ---- command line -------------------------------------------------------------------------------------------------

class _Exit(Exception):
    def __init__(self, code: int):
        super().__init__(code)
        self.code = code


class _Parser(argparse.ArgumentParser):
    out: TextIO = sys.stdout
    err: TextIO = sys.stderr

    def _print_message(self, message: str, file: Any = None) -> None:
        if message:
            (self.err if file is sys.stderr else self.out).write(message)

    def error(self, message: str) -> NoReturn:
        self.err.write(f"{USAGE_CODE}: {message}\n")
        raise _Exit(2)

    def exit(self, status: int = 0, message: Optional[str] = None) -> NoReturn:
        if message:
            self.err.write(message)
        raise _Exit(status)


def build_parser(out: TextIO, err: TextIO) -> argparse.ArgumentParser:
    parser = _Parser(prog="aicore schema codegen", description="Generate a stdlib TypedDict module from the "
                     "contract schemas of one directory.")
    parser.out, parser.err = out, err
    parser.add_argument("--root", metavar="DIR", required=True, help="directory of the *.schema.json files")
    parser.add_argument("--out", metavar="FILE", required=True, help="Python module to write")
    parser.add_argument("--check", action="store_true",
                        help="write nothing; exit 1 SCHEMA_CODEGEN_DRIFT when FILE differs from the generated bytes")
    return parser


def main(argv: Optional[Sequence[str]] = None, *, env: Optional[Mapping[str, str]] = None,
         cwd: Optional[Path] = None, out: Optional[TextIO] = None, err: Optional[TextIO] = None) -> int:
    """``aicore schema codegen``; exit 0 written or in sync, 1 drift or unsupported schema, 2 usage."""
    out = out if out is not None else cast(TextIO, sys.stdout)
    err = err if err is not None else cast(TextIO, sys.stderr)
    parser = build_parser(out, err)
    try:
        options = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    except _Exit as stop:
        return stop.code
    base = Path(cwd) if cwd else Path.cwd()
    root, target = base / options.root, base / options.out
    if not root.is_dir():
        err.write(f"{USAGE_CODE}: --root {options.root} is not a directory\n")
        return 2
    try:
        text = generate(root, label=Path(options.root).as_posix())
    except CodegenError as refusal:
        err.write(f"{refusal}\n")
        return 1
    data = text.encode("utf-8")
    if options.check:
        try:
            current = target.read_bytes()
        except OSError:
            current = None
        if current != data:
            err.write(f"{DRIFT}: {options.out}\n")
            return 1
        out.write(f"schema codegen: {options.out} is in sync\n")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    out.write(f"schema codegen: wrote {options.out}\n")
    return 0
