"""Language independent codegen model. Locations always identify the authoritative schema."""

import keyword
import re
from dataclasses import dataclass, field
from typing import Any


class CodegenError(ValueError):
    code = "SCHEMA_CODEGEN_UNSUPPORTED"

    def __init__(self, location: str, reason: str):
        super().__init__(f"{self.code}: {location or '/'}: {reason}")


def pascal(text: str) -> str:
    return "".join(word[:1].upper() + word[1:] for word in re.findall(r"[A-Za-z0-9]+", text)) or "Value"


def snake(text: str) -> str:
    text = text.rsplit(".", 1)[-1]
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
    text = re.sub(r"\W", "_", text).lower()
    if not text or text[0].isdigit():
        text = "field_" + text
    return text + "_" if keyword.iskeyword(text) else text


@dataclass(frozen=True)
class Type:
    tag: str
    args: tuple["Type", ...] = ()
    values: tuple[Any, ...] = ()
    ref: str = ""


@dataclass
class Field:
    wire: str
    name: str
    type: Type
    required: bool
    default: Any = None
    has_default: bool = False
    settings_key: str = ""
    # (discriminator, const, matches_if_absent) for a nullable field required by an if/then branch.
    required_when: tuple[tuple[str, str, bool], ...] = ()


@dataclass
class Declaration:
    key: str
    urn: str
    pointer: str
    module: str
    name: str
    ts_file: str
    ts_name: str
    kind: str
    description: str = ""
    fields: list[Field] = field(default_factory=list)
    type: Type = field(default_factory=lambda: Type("any"))
    section: str = ""
    discriminator: str = ""
    root: str = ""
    json_mode: bool = False
    python_local: bool = False
    config_chain: str = ""

    @property
    def location(self) -> str:
        return self.urn + "#" + self.pointer


@dataclass
class Model:
    documents: dict[str, Any]
    declarations: dict[str, Declaration] = field(default_factory=dict)
    python_model: "Model | None" = field(default=None, repr=False)

    def ordered(self, declarations: list[Declaration]) -> list[Declaration]:
        """Dependency order, stable name order for ties; cycles retain forward references."""
        local = {d.key: d for d in declarations}
        result: list[Declaration] = []
        visited: set[str] = set()

        def visit(d: Declaration) -> None:
            if d.key in visited:
                return
            visited.add(d.key)

            def refs(t: Type) -> set[str]:
                return ({t.ref} if t.ref else set()) | {r for a in t.args for r in refs(a)}

            deps = refs(d.type) | {r for f in d.fields for r in refs(f.type)}
            for key in sorted(deps, key=lambda k: self.declarations[k].name):
                if key in local:
                    visit(local[key])
            result.append(d)

        for d in sorted(declarations, key=lambda d: d.name):
            visit(d)
        return result
