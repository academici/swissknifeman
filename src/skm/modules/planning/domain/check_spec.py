"""Checks: typed records and their document form (planning §4.2)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, cast

from skm.modules.planning.domain.reads import compact, entity_id_of

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.kernel.ids import EntityId
    from skm.kernel.json_types import JsonObject, JsonValue


class CheckKind(StrEnum):
    COMMAND = "command"
    SHELL = "shell"
    MANUAL = "manual"
    EXTERNAL = "external"


class CheckCategory(StrEnum):
    ACCEPTANCE = "acceptance"
    IMPACT = "impact"
    LIVE = "live"


@dataclass(frozen=True, slots=True)
class EvidencePolicy:
    stdout: bool
    stderr: bool
    report_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Cwd:
    mount: str
    path: str = "."


@dataclass(frozen=True, slots=True)
class CommandDefinition:
    argv: tuple[str, ...]
    cwd: Cwd
    timeout_seconds: int
    env_allow: tuple[str, ...]
    expect: str | None
    expected_exit: int = 0


@dataclass(frozen=True, slots=True)
class ShellDefinition:
    script: str
    cwd: Cwd
    timeout_seconds: int
    env_allow: tuple[str, ...]
    expect: str | None
    risk_ack: str
    expected_exit: int = 0


@dataclass(frozen=True, slots=True)
class ManualDefinition:
    instructions_md: str
    actor_role: Literal["owner", "maintainer", "member"]
    allowed_verdicts: tuple[Literal["pass", "fail"], ...]


@dataclass(frozen=True, slots=True)
class ExternalDefinition:
    provider: str
    ref: str
    params: Mapping[str, str | int | bool]


type CheckDefinition = CommandDefinition | ShellDefinition | ManualDefinition | ExternalDefinition


@dataclass(frozen=True, slots=True)
class CheckSpec:
    id: EntityId
    key: str
    owner: str
    title: str | None
    category: CheckCategory
    kind: CheckKind
    required: bool
    rerun_after_integration: bool
    evidence: EvidencePolicy
    definition: CheckDefinition


DEFAULT_TIMEOUT_SECONDS = 600


def _cwd(doc: Mapping[str, JsonValue]) -> Cwd:
    return Cwd(str(doc["mount"]), str(doc.get("path", ".")))


def _strs(doc: Mapping[str, JsonValue], name: str) -> tuple[str, ...]:
    return tuple(str(value) for value in cast("list[JsonValue]", doc.get(name, [])))


def definition_from_doc(kind: CheckKind, doc: Mapping[str, JsonValue]) -> CheckDefinition:
    expect = doc.get("expect")
    expect_text = None if expect is None else str(expect)
    match kind:
        case CheckKind.COMMAND:
            return CommandDefinition(
                _strs(doc, "argv"),
                _cwd(cast("JsonObject", doc["cwd"])),
                int(cast("int", doc.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))),
                _strs(doc, "env_allow"),
                expect_text,
                cast("int", doc.get("expected_exit", 0)),
            )
        case CheckKind.SHELL:
            return ShellDefinition(
                str(doc["script"]),
                _cwd(cast("JsonObject", doc["cwd"])),
                int(cast("int", doc.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))),
                _strs(doc, "env_allow"),
                expect_text,
                str(doc["risk_ack"]),
                cast("int", doc.get("expected_exit", 0)),
            )
        case CheckKind.MANUAL:
            verdicts = doc.get("allowed_verdicts", ["pass", "fail"])
            return ManualDefinition(
                str(doc["instructions_md"]),
                cast("Literal['owner', 'maintainer', 'member']", doc["actor_role"]),
                cast("tuple[Literal['pass', 'fail'], ...]", tuple(cast("list[JsonValue]", verdicts))),
            )
        case CheckKind.EXTERNAL:
            params = cast("Mapping[str, str | int | bool]", doc.get("params", {}))
            return ExternalDefinition(str(doc["provider"]), str(doc["ref"]), dict(params))


def definition_to_doc(definition: CheckDefinition) -> JsonObject:
    match definition:
        case CommandDefinition():
            return compact(
                {
                    "argv": list(definition.argv),
                    "cwd": {"mount": definition.cwd.mount, "path": definition.cwd.path},
                    "timeout_seconds": definition.timeout_seconds,
                    "env_allow": list(definition.env_allow),
                    "expect": definition.expect,
                    **({"expected_exit": definition.expected_exit} if definition.expected_exit else {}),
                }
            )
        case ShellDefinition():
            return compact(
                {
                    "script": definition.script,
                    "cwd": {"mount": definition.cwd.mount, "path": definition.cwd.path},
                    "timeout_seconds": definition.timeout_seconds,
                    "env_allow": list(definition.env_allow),
                    "expect": definition.expect,
                    **({"expected_exit": definition.expected_exit} if definition.expected_exit else {}),
                    "risk_ack": definition.risk_ack,
                }
            )
        case ManualDefinition():
            return {
                "instructions_md": definition.instructions_md,
                "actor_role": definition.actor_role,
                "allowed_verdicts": list(definition.allowed_verdicts),
            }
        case ExternalDefinition():
            doc: JsonObject = {"provider": definition.provider, "ref": definition.ref}
            if definition.params:
                doc["params"] = dict(definition.params)
            return doc


def check_from_doc(doc: Mapping[str, JsonValue]) -> CheckSpec:
    kind = CheckKind(str(doc["kind"]))
    category = CheckCategory(str(doc["category"]))
    evidence = cast("Mapping[str, JsonValue]", doc.get("evidence", {}))
    title = doc.get("title")
    return CheckSpec(
        id=entity_id_of(doc),
        key=str(doc["key"]),
        owner=str(doc["owner"]),
        title=None if title is None else str(title),
        category=category,
        kind=kind,
        required=bool(doc.get("required", category is CheckCategory.ACCEPTANCE)),
        rerun_after_integration=bool(doc.get("rerun_after_integration", False)),
        evidence=EvidencePolicy(
            bool(evidence.get("stdout", True)),
            bool(evidence.get("stderr", True)),
            _strs(evidence, "report_files"),
        ),
        definition=definition_from_doc(kind, cast("Mapping[str, JsonValue]", doc["definition"])),
    )


def check_to_doc(check: CheckSpec) -> JsonObject:
    evidence: JsonObject = {"stdout": check.evidence.stdout, "stderr": check.evidence.stderr}
    if check.evidence.report_files:
        evidence["report_files"] = list(check.evidence.report_files)
    return compact(
        {
            "id": str(check.id),
            "key": check.key,
            "owner": check.owner,
            "title": check.title,
            "category": check.category.value,
            "kind": check.kind.value,
            "required": check.required,
            "rerun_after_integration": check.rerun_after_integration,
            "evidence": evidence,
            "definition": definition_to_doc(check.definition),
        }
    )
