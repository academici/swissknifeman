"""Create separate Python value types for independently resolved settings chains."""

from copy import deepcopy

from .model import CodegenError, Declaration, Model, Type


def _chains(root: Declaration, document: dict) -> dict[str, str]:
    result: dict[str, str] = {}

    def collect(node, path):
        if "x-skm" in node:
            chain = node["x-skm"].get("chain")
            if chain in ("work", "host"):
                result[".".join((root.section, *path))] = chain
            return
        for name, child in node.get("properties", {}).items():
            collect(child, (*path, name))

    collect(document, ())
    return result


def _project_chain(
    model: Model, root: Declaration, original_name: str, chains: dict[str, str], chain: str
) -> None:
    owned = {d.key: d for d in model.declarations.values() if d.root == root.key}
    memo: dict[str, Declaration | None] = {}

    def belongs_to_chain(key: str) -> bool:
        source = owned[key]
        result = True
        for field in source.fields:
            if field.settings_key:
                if field.settings_key not in chains:
                    raise CodegenError(
                        source.location, f"settings key {field.settings_key} lacks a valid chain"
                    )
                result = result and chains[field.settings_key] == chain
            elif field.type.tag == "ref" and field.type.ref in owned and owned[field.type.ref].fields:
                child_matches = belongs_to_chain(field.type.ref)
                result = result and child_matches
            else:
                raise CodegenError(source.location, f"cannot scope settings group {field.name!r}")
        return result

    def clone(key: str) -> Declaration | None:
        source = owned[key]
        if key in memo:
            return memo[key]
        if key != root.key and belongs_to_chain(key):
            memo[key] = source
            return source
        memo[key] = None
        fields = []
        for field in source.fields:
            copied = deepcopy(field)
            if field.settings_key:
                if field.settings_key not in chains:
                    raise CodegenError(
                        source.location, f"settings key {field.settings_key} lacks a valid chain"
                    )
                if chains[field.settings_key] != chain:
                    continue
            elif field.type.tag == "ref" and field.type.ref in owned and owned[field.type.ref].fields:
                child = clone(field.type.ref)
                if child is None:
                    continue
                copied.type = Type("ref", ref=child.key)
            else:
                raise CodegenError(source.location, f"cannot scope settings group {field.name!r}")
            fields.append(copied)
        if not fields:
            return None
        result = deepcopy(source)
        result.key = key + "@scope:" + chain
        result.root = root.key + "@scope:" + chain
        result.fields = fields
        result.type = Type("record", ref=result.key)
        if key == root.key:
            result.name = (
                original_name if chain == "work" else original_name.removesuffix("Settings") + "HostView"
            )
        else:
            result.name = source.name + ("WorkView" if chain == "work" else "HostView")
        result.config_chain = chain if key == root.key else ""
        memo[key] = result
        model.declarations[result.key] = result
        return result

    clone(root.key)


def project(model: Model) -> None:
    roots = [d for d in model.declarations.values() if d.kind == "settings_view" and d.section]
    for root in roots:
        chains = _chains(root, model.documents[root.urn])
        if set(chains.values()) != {"work", "host"}:
            if len(set(chains.values())) == 1:
                root.config_chain = next(iter(chains.values()))
            continue
        original_name = root.name
        root.name = original_name.removesuffix("Settings") + "Document"
        for chain in ("work", "host"):
            _project_chain(model, root, original_name, chains, chain)
    names: dict[tuple[str, str], str] = {}
    for declaration in model.declarations.values():
        name = (declaration.module, declaration.name)
        previous = names.get(name)
        if previous is not None and previous != declaration.key:
            raise CodegenError(declaration.location, f"projected type name collision: {name}")
        names[name] = declaration.key
