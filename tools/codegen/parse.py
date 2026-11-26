"""Parse the explicitly supported schema profile without discarding structural applicators."""

import copy
import keyword
import re
from pathlib import Path
from typing import Any

from skm.platform.schema.registry import SchemaRegistry

from .model import CodegenError, Declaration, Field, Model, Type, pascal, snake

ANNOTATIONS = {
    "$schema",
    "$id",
    "$defs",
    "title",
    "description",
    "default",
    "examples",
    "deprecated",
    "readOnly",
    "writeOnly",
    "$comment",
    "x-skm",
    "x-skm-codegen",
    "x-skm-enum-name",
    "x-skm-section",
    "x-skm-discriminator",
    "x-skm-order",
    "x-skm-hookable",
    "x-skm-secret",
    "x-skm-sensitive",
    "x-skm-example-only",
}
VALIDATION = {
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "pattern",
    "format",
    "minItems",
    "maxItems",
    "uniqueItems",
    "contains",
    "minContains",
    "maxContains",
    "minProperties",
    "maxProperties",
    "propertyNames",
    "dependentRequired",
    "contentEncoding",
    "contentMediaType",
}
STRUCTURE = {
    "$ref",
    "type",
    "enum",
    "const",
    "properties",
    "required",
    "additionalProperties",
    "patternProperties",
    "items",
    "prefixItems",
    "oneOf",
    "anyOf",
    "allOf",
    "if",
    "then",
    "else",
    "not",
    "dependentSchemas",
}
SINGLE = {"items", "additionalProperties", "contains", "propertyNames", "if", "then", "else", "not"}
MAPPINGS = {"properties", "$defs", "patternProperties", "dependentSchemas"}
LISTS = {"oneOf", "anyOf", "allOf", "prefixItems"}
KINDS = {"dataclass", "typeddict", "enum", "alias", "union", "settings_view"}


type ConditionalRule = tuple[str, str, str, bool]


def required_when_rules(node: dict[str, Any]) -> list[ConditionalRule]:
    """``(field, discriminator, const, matches_if_absent)`` for a single string discriminator.

    Additional guards and other conditions stay validation-only. A ``properties`` guard alone
    matches an absent discriminator.
    """
    rules = []
    for branch in [node, *node.get("allOf", [])]:
        if not isinstance(branch, dict):
            continue
        condition, then = branch.get("if"), branch.get("then")
        if not isinstance(condition, dict) or not isinstance(then, dict):
            continue
        props = condition.get("properties", {})
        if set(condition) - {"properties", "required"} or len(props) != 1:
            continue
        ((discriminator, schema),) = props.items()
        if not isinstance(schema, dict) or set(schema) != {"const"}:
            continue
        value = schema["const"]
        required = condition.get("required", [])
        if not isinstance(value, str) or any(field != discriminator for field in required):
            continue
        rules += [(wire, discriminator, value, not required) for wire in then.get("required", [])]
    return rules


def private_dependency(source: str, target: str) -> bool:
    """Generated declarations may share kernel types and their own module's types."""
    source_parts, target_parts = source.split("."), target.split(".")
    if target_parts[:2] == ["skm", "modules"]:
        return source_parts[:3] != target_parts[:3]
    return target_parts[:2] == ["skm", "platform"] and source_parts[:2] != target_parts[:2]


def escape(text: str) -> str:
    return text.replace("~", "~0").replace("/", "~1")


def nodes(node: Any, pointer: str = ""):
    if not isinstance(node, dict):
        return
    yield pointer, node
    for key, value in node.items():
        if key in MAPPINGS:
            for name, child in value.items():
                yield from nodes(child, f"{pointer}/{key}/{escape(name)}")
        elif key in SINGLE:
            yield from nodes(value, f"{pointer}/{key}")
        elif key in LISTS:
            for i, child in enumerate(value):
                yield from nodes(child, f"{pointer}/{key}/{i}")


def load(root: Path) -> Model:
    registry = SchemaRegistry.load(root)
    documents = {urn: copy.deepcopy(dict(registry.get(urn))) for urn in sorted(registry.urns())}
    return normalize(documents)


def normalize(documents: dict[str, Any]) -> Model:
    return Parser(documents).run()


class Parser:
    def __init__(self, documents: dict[str, Any], *, python_boundaries: bool = False):
        self.model = Model(documents)
        self.python_boundaries = python_boundaries
        self.annotated: dict[str, tuple[str, str, dict[str, Any]]] = {}
        self.names: dict[tuple[str, str], str] = {}
        self.ts_names: dict[tuple[str, str], str] = {}
        self.built: set[str] = set()
        self.conditional: dict[tuple[str, str], list[ConditionalRule]] = {}

    def fail(self, urn: str, pointer: str, reason: str):
        raise CodegenError(urn + "#" + pointer, reason)

    def run(self) -> Model:
        for urn, doc in self.model.documents.items():
            for pointer, node in nodes(doc):
                if "x-skm-codegen" in node:
                    self.annotated[urn + "#" + pointer] = (urn, pointer, node)
        for urn, pointer, node in self.annotated.values():
            self.declare(urn, pointer, node)
        for urn, pointer, node in self.annotated.values():
            self.build(self.model.declarations[urn + "#" + pointer], node)
        if self.python_boundaries:
            self.add_legacy_local_aliases()
        return self.model

    def add_legacy_local_aliases(self):
        # Older Python output used the root and pointer alone. Keep that export
        # only when exactly one local declaration can own it.
        candidates = {}
        declarations = list({d.key: d for d in self.model.declarations.values()}.values())
        for d in declarations:
            if not d.python_local or not d.pointer:
                continue
            root = self.model.declarations[d.root]
            qualified = root.name + pascal(d.urn) + pascal(d.pointer)
            if d.name != qualified:
                continue
            name = root.name + pascal(d.pointer)
            candidates.setdefault((d.module, name), []).append(d)
        occupied = {(d.module, d.name) for d in declarations}
        function_names = {(d.module, snake(d.name)) for d in declarations}
        for (module, name), matches in sorted(candidates.items()):
            if len(matches) != 1 or (module, name) in occupied or (module, snake(name)) in function_names:
                continue
            target = matches[0]
            key = target.key + "@legacy-export:" + name
            alias = Declaration(key, target.urn, target.pointer, module, name, target.ts_file, name, "alias")
            alias.root = target.root
            alias.json_mode = target.json_mode
            alias.type = Type("ref", ref=target.key)
            self.model.declarations[key] = alias
            occupied.add((module, name))
            function_names.add((module, snake(name)))

    def declare(self, urn, pointer, node, *, parent=None, name=None, json_mode=False, contextual=False):
        key = urn + "#" + pointer
        # Helpers are contextual: the same unannotated definition can be JSON or value-level.
        if parent is not None and (key not in self.annotated or contextual):
            key += "@" + (parent.root or parent.key)
        if key in self.model.declarations:
            return self.model.declarations[key]
        annotation = node.get("x-skm-codegen", {})
        py = annotation.get("python", {})
        ts = annotation.get("typescript", {})
        inferred = "typeddict" if json_mode else "dataclass"
        if parent is not None and not ("properties" in node and node.get("additionalProperties") is False):
            inferred = "alias"
        kind = py.get("kind", inferred)
        if kind not in KINDS:
            self.fail(urn, pointer, f"unknown kind {kind!r}")
        if parent is None:
            module, name = py.get("module", ""), py.get("class", "")
            ts_file = ts.get("file", urn.split(":")[2] + ".ts")
        else:
            module = parent.module
            ts_file = parent.ts_file
        if (
            not name
            or not name.isidentifier()
            or keyword.iskeyword(name)
            or not module.startswith("skm.")
            or "generated" not in module.split(".")
        ):
            self.fail(urn, pointer, "invalid generated Python module/class")
        if any(not part.isidentifier() or keyword.iskeyword(part) for part in module.split(".")):
            self.fail(urn, pointer, "invalid module path")
        if Path(ts_file).name != ts_file or not ts_file.endswith(".ts"):
            self.fail(urn, pointer, "TypeScript file must be a basename ending in .ts")
        ts_name = ts.get("name", name)
        if not re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", ts_name):
            self.fail(urn, pointer, "invalid generated TypeScript name")
        for table, ident in ((self.names, (module, name)), (self.ts_names, (ts_file, ts_name))):
            previous = table.get(ident)
            if previous and previous != key:
                old = self.model.declarations[previous]

                # Identical named declarations in distinct source schemas may share a name.
                def shape(n, owner):
                    if isinstance(n, dict):
                        return {
                            k: owner + v if k == "$ref" and v.startswith("#") else shape(v, owner)
                            for k, v in n.items()
                            if k not in ANNOTATIONS
                            or k in {"default", "x-skm-enum-name", "x-skm-section", "x-skm-secret"}
                        }
                    return [shape(v, owner) for v in n] if isinstance(n, list) else n

                old_owner, old_shape = self.deref(old.urn, self.source(old))
                new_owner, new_shape = self.deref(urn, node)
                if shape(old_shape, old_owner) != shape(new_shape, new_owner):
                    self.fail(urn, pointer, f"name collision {ident}: {old.location} and {urn}#{pointer}")
                if table is self.names:
                    self.model.declarations[key] = old
                    return old
                continue
            table[ident] = key
        d = Declaration(key, urn, pointer, module, name, ts_file, ts_name, kind, node.get("description", ""))
        d.root = (parent.root or parent.key) if parent else key
        d.json_mode = json_mode or kind == "typeddict"
        d.python_local = parent.python_local if parent else False
        self.model.declarations[key] = d
        return d

    def source(self, d):
        node = self.model.documents[d.urn]
        for part in d.pointer.strip("/").split("/") if d.pointer else []:
            node = (
                node[int(part)]
                if isinstance(node, list)
                else node[part.replace("~1", "/").replace("~0", "~")]
            )
        return node

    def resolve(self, urn, ref):
        owner, _, pointer = ref.partition("#")
        owner = owner or urn
        node = self.model.documents[owner]
        for part in pointer.strip("/").split("/") if pointer else []:
            node = (
                node[int(part)]
                if isinstance(node, list)
                else node[part.replace("~1", "/").replace("~0", "~")]
            )
        node = copy.deepcopy(node)
        for _, child in nodes(node):
            if isinstance(child.get("$ref"), str) and child["$ref"].startswith("#"):
                child["$ref"] = owner + child["$ref"]
        return owner, pointer, node

    def check(self, urn, pointer, node):
        for p, child in nodes(node, pointer):
            unknown = child.keys() - ANNOTATIONS - VALIDATION - STRUCTURE
            if unknown:
                self.fail(urn, p, f"unsupported schema keyword {sorted(unknown)[0]!r}")

    def deref(self, urn, node):
        seen = set()
        while isinstance(node, dict) and "$ref" in node:
            if (urn, node["$ref"]) in seen:
                break
            seen.add((urn, node["$ref"]))
            urn, _, target = self.resolve(urn, node["$ref"])
            siblings = {k: v for k, v in node.items() if k != "$ref"}
            if "properties" in siblings:
                siblings["properties"] = {**target.get("properties", {}), **siblings["properties"]}
            node = {**target, **siblings}
        return urn, node

    def constraint(self, urn, pointer, base, branch):  # noqa: PLR0912
        """Prove that a validation-only branch cannot introduce fields or change conversion."""
        if isinstance(branch, bool):
            return
        urn, base = self.deref(urn, base)
        if "$ref" in branch:
            _, branch = self.deref(urn, branch)
        branch_variants = branch.get("anyOf", branch.get("oneOf", []))
        if branch_variants and not base.get("properties") and ("anyOf" in base or "oneOf" in base):
            for variant in branch_variants:
                self.constraint(urn, pointer, base, variant)
            branch = {k: v for k, v in branch.items() if k not in ("anyOf", "oneOf")}
        variants = base.get("anyOf", base.get("oneOf", []))
        if variants and not base.get("properties"):
            errors = []
            for variant in variants:
                try:
                    self.constraint(urn, pointer, variant, branch)
                except CodegenError as error:
                    errors.append(error)
                else:
                    return
            raise errors[0]
        if not isinstance(base, dict):
            self.fail(urn, pointer, "constraint has no declared outer shape")
        if "type" in branch:
            outer = base.get("type")
            allowed = outer if isinstance(outer, list) else [outer]
            narrowed = branch["type"] if isinstance(branch["type"], list) else [branch["type"]]
            if outer and not set(narrowed) <= set(allowed):
                self.fail(urn, pointer, "constraint changes the declared type")
        props = base.get("properties", {})
        for key in branch.get("required", []):
            if key not in props and not base.get("patternProperties"):
                self.fail(urn, pointer, f"constraint introduces undeclared field {key!r}")
        for key, child in branch.get("properties", {}).items():
            if key not in props:
                self.fail(urn, pointer, f"constraint introduces undeclared field {key!r}")
            self.constraint(urn, pointer + "/properties/" + escape(key), props[key], child)
        if "items" in branch and isinstance(branch["items"], dict):
            if "items" not in base:
                self.fail(urn, pointer, "constraint introduces array items")
            self.constraint(urn, pointer + "/items", base["items"], branch["items"])
        for key in ("allOf", "anyOf", "oneOf"):
            for i, child in enumerate(branch.get(key, [])):
                self.constraint(urn, f"{pointer}/{key}/{i}", base, child)
        for key in ("if", "then", "else", "not"):
            if key in branch:
                self.constraint(urn, pointer + "/" + key, base, branch[key])
        for key in ("additionalProperties", "patternProperties", "prefixItems", "dependentSchemas"):
            if key in branch and branch[key] != base.get(key) and branch[key] is not False:
                self.fail(urn, pointer, f"structural {key} in validation-only branch")
        if "format" in branch and branch["format"] != base.get("format"):
            variants = base.get("anyOf", base.get("oneOf", []))
            if not any(self.deref(urn, variant)[1].get("format") == branch["format"] for variant in variants):
                self.fail(urn, pointer, "constraint changes format conversion")

    def compose(self, urn, pointer, node):  # noqa: PLR0912
        node = dict(node)
        if rules := required_when_rules(node):
            self.conditional[(urn, pointer)] = rules
        if "allOf" in node:
            branches = node.pop("allOf")
            # Merge structural object branches only when their property conversions agree.
            for i, raw_branch in enumerate(branches):
                _, branch = self.deref(urn, raw_branch)
                if not isinstance(branch, dict):
                    continue
                if "type" in branch and node.get("type") not in (None, branch["type"]):
                    self.fail(urn, pointer, "incompatible allOf types")
                if "properties" in branch and not node.get("properties"):
                    node.setdefault("type", "object")
                if "properties" in branch:
                    props = dict(node.get("properties", {}))
                    for key, value in branch["properties"].items():
                        if key in props:
                            self.constraint(urn, f"{pointer}/allOf/{i}", props[key], value)
                        else:
                            if node.get("additionalProperties") is False and "properties" in node:
                                self.fail(urn, pointer, "incompatible allOf adds a field to a closed object")
                            props[key] = value
                    node["properties"] = props
                    node["required"] = list(
                        dict.fromkeys(node.get("required", []) + branch.get("required", []))
                    )
                    if "additionalProperties" in branch:
                        node.setdefault("additionalProperties", branch["additionalProperties"])
                else:
                    self.constraint(urn, f"{pointer}/allOf/{i}", node, branch)
        for key in ("if", "then", "else", "not"):
            if key in node:
                self.constraint(urn, pointer + "/" + key, node, node[key])
        for key, child in node.get("dependentSchemas", {}).items():
            self.constraint(urn, pointer + "/dependentSchemas/" + key, node, child)
        return node

    def build(self, d, node):
        if d.key in self.built:
            return
        self.built.add(d.key)
        self.check(d.urn, d.pointer, node)
        if d.kind == "enum":
            if not node.get("enum") or any(not isinstance(v, str) for v in node["enum"]):
                self.fail(d.urn, d.pointer, "enum kind requires string enum")
            names = [v.upper().replace("-", "_").replace(".", "_") for v in node["enum"]]
            if len(set(names)) != len(names) or any(not n.isidentifier() for n in names):
                self.fail(d.urn, d.pointer, "invalid or colliding enum members")
            d.type = Type("literal", values=tuple(node["enum"]))
            return
        if d.kind == "settings_view":
            d.section = node.get("x-skm-section", {}).get("id", d.urn.split(":")[-2])
        py_disc = node.get("x-skm-codegen", {}).get("python", {}).get("discriminator", "")
        d.discriminator = py_disc or node.get("x-skm-discriminator", "")
        if py_disc and node.get("x-skm-discriminator", py_disc) != py_disc:
            self.fail(d.urn, d.pointer, "discriminator annotations disagree")
        expr = self.map(d, node, d.name, d.urn, d.pointer, top=True, json_mode=d.json_mode)
        d.type = expr
        if d.kind in ("dataclass", "settings_view") and expr.tag != "record":
            self.fail(d.urn, d.pointer, "dataclass/settings_view requires a closed record")

    @staticmethod
    def attach_required_when(fields: list[Field], rules: list[ConditionalRule]) -> None:
        # The codec needs to preserve null for these fields; the schema validates other conditions.
        for f in fields:
            nullable = f.type.tag == "union" and Type("null") in f.type.args
            if not f.required and nullable:
                f.required_when = tuple(
                    (disc, value, missing) for wire, disc, value, missing in rules if wire == f.wire
                )

    def record(self, d, node, name, urn, pointer, top, json_mode):
        if top:
            target = d
        else:
            target = self.declare(urn, pointer, node, parent=d, name=name, json_mode=json_mode)
            if target.key in self.built:
                return Type("ref", ref=target.key)
            self.built.add(target.key)
        target.section = (
            d.section if top or ("/additionalProperties" not in pointer and "/items" not in pointer) else ""
        )
        target.json_mode = json_mode
        props = node.get("properties", {})
        required = node.get("required", [])
        if set(required) - props.keys():
            self.fail(urn, pointer, "required field has no declared property")
        fields = []
        names = set()
        for wire, child in props.items():
            field_name = snake(wire)
            if field_name in names:
                self.fail(urn, pointer, f"field alias collision for {wire!r}")
            names.add(field_name)
            child_name = name + pascal(wire)
            if target.section:
                child_name = name.removesuffix("Settings") + pascal(wire)
                if "properties" in child:
                    child_name += "Settings"
            typ = self.map(
                target, child, child_name, urn, pointer + "/properties/" + escape(wire), json_mode=json_mode
            )
            if target.section and child.get("x-skm", {}).get("nullable"):
                typ = self.union([typ, Type("null")])
            is_required = wire in required or bool(target.section)
            default = child.get("default")
            has_default = "default" in child and (
                default is None or isinstance(default, (str, int, float, bool)) or default == []
            )
            # An optional field without a default is absent on the wire, never null: the schema decides
            # whether null is a value. Python spells the absence as ``None`` in the annotation only.
            settings_key = ""
            if target.section:
                path = [*pointer.split("/properties/")[1:], wire]
                settings_key = ".".join([d.section, *path])
                # Nested records represent groups; maps/arrays remain leaf settings values.
                if typ.tag == "ref" and self.model.declarations[typ.ref].fields:
                    settings_key = ""
            fields.append(Field(wire, field_name, typ, is_required, default, has_default, settings_key))
        if not target.section and not json_mode:
            self.attach_required_when(fields, self.conditional.get((urn, pointer), []))
        if not target.section:
            fields.sort(key=lambda f: not f.required)
        target.fields = fields
        target.type = Type("record", ref=target.key)
        return Type("record", ref=target.key) if top else Type("ref", ref=target.key)

    @staticmethod
    def union(types):
        unique = list(dict.fromkeys(types))
        return unique[0] if len(unique) == 1 else Type("union", tuple(unique))

    def map(self, d, node, name, urn, pointer, top=False, json_mode=False):  # noqa: PLR0911, PLR0912, PLR0915
        if node is True:
            return Type("any")
        if node is False:
            return Type("never")
        node = self.compose(urn, pointer, node)
        if "$ref" in node:
            owner, ptr, target = self.resolve(urn, node["$ref"])
            if (
                d.section or self.model.declarations[d.root].kind == "settings_view"
            ) and owner == "urn:skm:config:secret-ref:v1":
                return Type("secret")
            siblings = {k: v for k, v in node.items() if k != "$ref"}
            if siblings:
                self.constraint(urn, pointer, target, siblings)
            if "$ref" in target:
                return self.map(d, target, name, owner, ptr, top=top, json_mode=json_mode)
            if top and d.kind in ("dataclass", "settings_view"):
                return self.map(d, target, name, owner, ptr, top=True, json_mode=json_mode)
            key = owner + "#" + ptr
            if key in self.annotated:
                ref = self.model.declarations[key]
                external = self.python_boundaries and private_dependency(d.module, ref.module)
                if external and not json_mode and ref.kind not in ("typeddict", "alias"):
                    self.fail(urn, pointer, "foreign value type requires an owner public facade")
                if external or (json_mode and ref.kind not in ("typeddict",)):
                    root = self.model.declarations[d.root]
                    raw = {k: v for k, v in target.items() if k != "x-skm-codegen"}
                    helper = self.declare(
                        owner,
                        ptr,
                        raw,
                        parent=d,
                        name=root.name + pascal(ptr or ref.name),
                        json_mode=json_mode or ref.json_mode,
                        contextual=True,
                    )
                    helper.python_local = helper.python_local or external
                    self.build(helper, raw)
                    return Type("ref", ref=helper.key)
                self.build(ref, target)
                return Type("ref", ref=ref.key)
            _, shape = self.deref(owner, target)
            if isinstance(shape, dict) and (
                shape.get("properties") is not None or any(k in shape for k in ("oneOf", "anyOf"))
            ):
                root = self.model.declarations[d.root]
                helper_name = root.name + pascal(ptr) if ptr else name
                if self.python_boundaries and d.python_local:
                    helper_name = root.name + pascal(owner) + pascal(ptr)
                helper = self.declare(owner, ptr, target, parent=d, name=helper_name, json_mode=json_mode)
                self.build(helper, target)
                return Type("ref", ref=helper.key)
            return self.map(d, target, name, owner, ptr, json_mode=json_mode)
        for key in ("oneOf", "anyOf"):
            if key not in node:
                continue
            branches = node[key]
            rest = {k: v for k, v in node.items() if k != key}
            if rest.get("properties") is not None:
                for i, branch in enumerate(branches):
                    self.constraint(urn, f"{pointer}/{key}/{i}", rest, branch)
                return self.map(d, rest, name, urn, pointer, top=top, json_mode=json_mode)
            types = [
                self.map(d, b, name + f"Variant{i + 1}", urn, f"{pointer}/{key}/{i}", json_mode=json_mode)
                for i, b in enumerate(branches)
            ]
            if not json_mode:
                self.check_union(
                    types,
                    branches,
                    urn,
                    pointer,
                    node.get("x-skm-discriminator", d.discriminator if top else ""),
                )
            return self.union(types)
        if "const" in node or "enum" in node:
            values = node.get("enum", [node.get("const")])
            if any(isinstance(v, (dict, list, float)) for v in values):
                self.fail(urn, pointer, "non-literal enum/const")
            if (
                (d.section or node.get("x-skm-enum-name"))
                and not json_mode
                and "enum" in node
                and all(isinstance(v, str) for v in values)
            ):
                enum_node = {**node, "x-skm-codegen": {"python": {"kind": "enum"}}}
                enum = self.declare(urn, pointer, enum_node, parent=d, name=node.get("x-skm-enum-name", name))
                self.build(enum, enum_node)
                return Type("ref", ref=enum.key)
            return Type("literal", values=tuple(values))
        typ = node.get("type")
        if isinstance(typ, list):
            return self.union(
                [
                    self.map(
                        d, {**node, "type": t}, name + pascal(t), urn, pointer + "/" + t, json_mode=json_mode
                    )
                    for t in typ
                ]
            )
        typ = typ or ("object" if "properties" in node or "required" in node else "any")
        if typ == "string":
            fmt = node.get("format", "")
            if d.section and (
                node.get("x-skm", {}).get("sensitivity") == "secret_ref" or "secret-ref" in pointer
            ):
                return Type("secret")
            return Type({"uuid": "uuid", "date-time": "datetime", "date": "date"}.get(fmt, "str"))
        if typ in ("integer", "number", "boolean", "null", "any"):
            return Type({"integer": "int", "number": "float", "boolean": "bool"}.get(typ, typ))
        if typ == "array":
            if "prefixItems" in node:
                count = len(node["prefixItems"])
                if node.get("minItems") != count or node.get("maxItems") != count:
                    self.fail(urn, pointer, "prefixItems requires a fixed length")
                return Type(
                    "tuple",
                    tuple(
                        self.map(
                            d, b, name + f"Item{i}", urn, f"{pointer}/prefixItems/{i}", json_mode=json_mode
                        )
                        for i, b in enumerate(node["prefixItems"])
                    ),
                )
            return Type(
                "array",
                (
                    self.map(
                        d, node.get("items", {}), name + "Item", urn, pointer + "/items", json_mode=json_mode
                    ),
                ),
            )
        if typ == "object":
            if "properties" in node and node.get("additionalProperties") is False:
                return self.record(d, node, name, urn, pointer, top, json_mode)
            if node.get("properties"):
                self.fail(urn, pointer, "record with open additional properties")
            patterns = list(node.get("patternProperties", {}).values())
            additional = node.get("additionalProperties")
            if patterns:
                mapped = [
                    self.map(
                        d,
                        p,
                        name + "Entry",
                        urn,
                        pointer + "/patternProperties/" + str(i),
                        json_mode=json_mode,
                    )
                    for i, p in enumerate(patterns)
                ]
                if len(set(mapped)) != 1:
                    self.fail(urn, pointer, "patternProperties requires one value conversion")
                return Type("map", (mapped[0],))
            if isinstance(additional, dict):
                return Type(
                    "map",
                    (
                        self.map(
                            d,
                            additional,
                            name + "Entry",
                            urn,
                            pointer + "/additionalProperties",
                            json_mode=json_mode,
                        ),
                    ),
                )
            if additional is False:
                return self.record(d, node, name, urn, pointer, top, json_mode)
            return Type("object")
        raise CodegenError(urn + "#" + pointer, f"unsupported type {typ!r}")

    def check_union(self, types, branches, urn, pointer, discriminator=""):
        def flatten(t, branch, owner):
            owner, branch = self.deref(owner, branch)
            expression = self.model.declarations[t.ref].type if t.ref else t
            variants = branch.get("anyOf", branch.get("oneOf", []))
            if expression.tag == "union" and variants and len(expression.args) == len(variants):
                return [
                    pair
                    for a, b in zip(expression.args, variants, strict=True)
                    for pair in flatten(a, b, owner)
                ]
            return [(t, branch)]

        flattened = [pair for t, b in zip(types, branches, strict=True) for pair in flatten(t, b, urn)]
        types = [pair[0] for pair in flattened]
        branches = [pair[1] for pair in flattened]

        def signature(t):
            if t.tag == "ref":
                decl = self.model.declarations[t.ref]
                if decl.kind == "typeddict":
                    return "json-object"
                return "object" if decl.fields else signature(decl.type)
            return t.tag

        signatures = [signature(t) for t in types]
        resolved = [self.deref(urn, b)[1] for b in branches]
        if not discriminator and all(isinstance(b, dict) and "properties" in b for b in resolved):
            candidates = set(resolved[0]["properties"])
            for b in resolved[1:]:
                candidates &= set(b["properties"])
            for key in sorted(candidates):
                values = [b["properties"][key].get("const", object()) for b in resolved]
                if all(
                    "const" in b["properties"][key] and key in b.get("required", []) for b in resolved
                ) and len(set(values)) == len(values):
                    discriminator = key
                    break
        if discriminator:
            vals = []
            for b in resolved:
                prop = b.get("properties", {}).get(discriminator, {})
                if "const" not in prop or discriminator not in b.get("required", []):
                    self.fail(
                        urn,
                        pointer,
                        f"discriminator {discriminator!r} must be required and const in every branch",
                    )
                vals.append(prop["const"])
            if len(set(vals)) != len(vals):
                self.fail(urn, pointer, "duplicate discriminator value")
            return
        for i, sig in enumerate(signatures):
            for j in range(i):
                same_json_object = sig in ("object", "map", "json-object") and signatures[j] in (
                    "object",
                    "map",
                    "json-object",
                )
                if (
                    (sig == signatures[j] or same_json_object)
                    and types[i] != types[j]
                    and sig != "literal"
                    and not (sig == signatures[j] == "json-object")
                ):
                    left, right = resolved[i], resolved[j]
                    common = set(left.get("required", [])) & set(right.get("required", []))
                    if any(
                        "const" in left.get("properties", {}).get(k, {})
                        and "const" in right.get("properties", {}).get(k, {})
                        and left["properties"][k]["const"] != right["properties"][k]["const"]
                        for k in common
                    ):
                        continue
                    if (
                        sig == "object"
                        and all(b.get("additionalProperties") is False for b in (left, right))
                        and (
                            set(left.get("required", [])) - right.get("properties", {}).keys()
                            or set(right.get("required", [])) - left.get("properties", {}).keys()
                        )
                    ):
                        continue
                    self.fail(
                        urn,
                        pointer,
                        f"overlapping structural union branches {j}/{i} require "
                        f"an unambiguous discriminator ({signatures[j]}/{sig})",
                    )
