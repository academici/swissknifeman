"""Render the resolved target's guidance for an agent preparing a delegation."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape


@dataclass(frozen=True, slots=True)
class DelegationCompiler:
    model: str
    strengths: tuple[str, ...]
    delegation_notes: tuple[str, ...]
    prompt_shape: str
    instructions: tuple[str, ...]
    forbidden_params: tuple[str, ...]

    def compile(self) -> str:
        lines = ["<target_model_delegation_brief>", f"<model>{escape(self.model)}</model>"]
        for tag, values in (
            ("strength", self.strengths),
            ("delegation_note", self.delegation_notes),
            ("prompt_shape", (self.prompt_shape,)),
            ("instruction", self.instructions),
            ("forbidden_param", self.forbidden_params),
        ):
            lines.extend(f"<{tag}>{escape(value)}</{tag}>" for value in values)
        return "\n".join([*lines, "</target_model_delegation_brief>"])
