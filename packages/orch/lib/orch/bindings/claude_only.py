"""Claude-only binding: nothing is started; a Claude session receives the prompt and returns a report."""
from __future__ import annotations

from orch import render
from orch.bindings import Binding


class ClaudeOnly(Binding):
    binding = "claude-only"

    def project(self, input_doc: dict, base: dict, manifest: dict, cap: dict, resolved: dict) -> dict:
        _, text = render.load_role(manifest["role_id"], self.roles_dir)
        prompt = render.render_prompt(input_doc, manifest, text)
        return {"transport": "prompt", "prompt_ref": self._write(f"prompt-{base['stage_id']}.md", prompt)}
