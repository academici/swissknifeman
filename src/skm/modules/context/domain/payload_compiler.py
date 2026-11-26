"""Apply a target's declared prompt and payload constraints before dispatch."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.modules.context.domain.blocks import BlockType
from skm.modules.context.domain.reasons import IncludeReason
from skm.modules.context.domain.render import substitute

if TYPE_CHECKING:
    from skm.modules.context.domain.manifest import DraftAssembler


def _parameter_paths(params: Mapping[str, object], prefix: str = "") -> set[str]:
    paths: set[str] = set()
    for name, value in params.items():
        path = f"{prefix}{name}"
        paths.add(path)
        if isinstance(value, Mapping):
            paths.update(_parameter_paths(cast("Mapping[str, object]", value), f"{path}."))
    return paths


@dataclass(frozen=True, slots=True)
class PayloadCompiler:
    forbidden_params: tuple[str, ...]
    legacy_prompt_phrases: tuple[str, ...]

    def validate_parameters(
        self, params: Mapping[str, object], incompatible_groups: Sequence[Sequence[str]] = ()
    ) -> None:
        paths = _parameter_paths(params)
        conflicts = paths.intersection(self.forbidden_params)
        for group in incompatible_groups:
            if group and paths.issuperset(group):
                conflicts.update(group)
        if conflicts:
            raise ValidationFailed(
                ErrorCode.RUNTIME_INVALID_REQUEST,
                "request parameters conflict with the target model guideline",
                details={"parameters": list[JsonValue](sorted(conflicts))},
            )

    @staticmethod
    def validate_role(model: str, role: str, suited_roles: Sequence[str]) -> None:
        if role in {"executor", "advisor"} and suited_roles and role not in suited_roles:
            raise ValidationFailed(
                ErrorCode.RUNTIME_INVALID_REQUEST,
                "model guideline is incompatible with the requested role",
                details={"model": model, "role": role},
            )

    @staticmethod
    def validate_advisor(
        executor_model: str,
        executor_roles: Sequence[str],
        advisor_model: str,
        compatible_advisor_models: Sequence[str] | None,
        *,
        advisor_profile_model: str | None = None,
    ) -> None:
        PayloadCompiler.validate_role(executor_model, "executor", executor_roles)
        if compatible_advisor_models is not None and not any(
            model in compatible_advisor_models for model in (advisor_model, advisor_profile_model) if model
        ):
            raise ValidationFailed(
                ErrorCode.RUNTIME_INVALID_REQUEST,
                "executor guideline is incompatible with the requested advisor",
                details={"executor": executor_model, "advisor": advisor_model},
            )

    def clean_prompt(self, text: str) -> str:
        """Remove complete instruction sentences, preserving surrounding prose and fenced examples."""
        if not self.legacy_prompt_phrases and not self.forbidden_params:
            return text
        phrases = {p.strip().rstrip(".!").casefold() for p in self.legacy_prompt_phrases}
        names = "|".join(re.escape(p) for p in self.forbidden_params)
        assignment = re.compile(
            rf"(?:set\s+|use\s+)?`?(?:{names})`?\s*(?:=|:|\s+to\s+)\s*"
            r"(?:[-+]?\d+(?:\.\d+)?|true|false|null)\b",
            re.IGNORECASE,
        )
        kept: list[str] = []
        fence = ""
        for line in text.splitlines(keepends=True):
            stripped = line.lstrip()
            if marker := re.match(r"(`{3,}|~{3,})", stripped):
                if not fence:
                    fence = marker[0]
                elif stripped.rstrip().startswith(fence) and not stripped.rstrip().strip(fence[0]):
                    fence = ""
                kept.append(line)
                continue
            if fence:
                kept.append(line)
                continue
            # Split at the end of the list marker. Keep its indentation and the original line ending.
            _, bullet, body = re.split(r"^([ \t]*(?:[-*+][ \t]+)?)", line.rstrip("\r\n"), maxsplit=1)
            sentences = re.split(r"(?<=[.!?])(?=\s)", body)
            retained: list[str] = []
            for sentence in sentences:
                directive = sentence.strip().rstrip(".!")
                if directive.casefold() in phrases or (names and assignment.fullmatch(directive)):
                    continue
                retained.append(sentence)
            if len(retained) == len(sentences):
                kept.append(line)
            elif any(part.strip() for part in retained):
                ending = line[len(line.rstrip("\r\n")) :]
                kept.append(bullet + "".join(retained).lstrip() + ending)
        return "".join(kept)

    def emit_runtime_notes(
        self,
        assembler: DraftAssembler,
        *,
        runtime_id: str,
        notes: Sequence[str],
        template_keys: Sequence[str],
    ) -> None:
        notes_text = "\n".join(
            f"- {n}" for n in dict.fromkeys(self.clean_prompt(n).strip() for n in notes) if n
        )
        source = f"runtime_notes:{runtime_id}"
        variables: dict[str, JsonValue] = {
            **assembler.variables,
            "block": {"content": notes_text, "title": "Runtime Notes", "source": source},
        }
        templates = [assembler.templates[k] for k in template_keys]
        parts = [substitute(template, variables).strip() for template in templates]
        if not any(re.search(r"{{\s*block\.content\s*}}", t) for t in templates):
            parts.append(notes_text)
        if content := "\n\n".join(p for p in parts if p):
            assembler.add(
                BlockType.RUNTIME_NOTES,
                "" if templates else "Runtime Notes",
                content,
                "core",
                source,
                mandatory=True,
                reason=IncludeReason.EXPLICIT_PROFILE,
            )
