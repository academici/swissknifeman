"""Native binding: the provider CLI is started directly; this projection holds its argv and prompt file."""
from __future__ import annotations

from orch import launch, render
from orch.bindings import LAUNCH_ROLES, Binding, Unmet
from orch.catalog import substitute

# The launch catalog says "text" for plain stdout; the launch-plan transport has no value for it.
TRANSPORTS = {"text": "none", "jsonl": "jsonl", "acp": "acp"}


class Native(Binding):
    binding = "native"

    def project(self, input_doc: dict, base: dict, manifest: dict, cap: dict, resolved: dict) -> dict:
        role = LAUNCH_ROLES.get(manifest["role_id"], manifest["role_id"])
        try:
            entry = self.catalog.launch_entry(role, base["provider"])
            if entry["model_set"] != "supported":
                raise Unmet("model.set", f"the launch catalog cannot pass a model to {base['provider']!r}")
            argv = substitute(entry["argv"], {"model": resolved["model"], "effort": resolved.get("effort", entry["effort"]),
                                              "cwd": self.cwd})
        except launch.LaunchError as error:
            raise Unmet("launch", str(error)) from error
        _, text = render.load_role(manifest["role_id"], self.roles_dir)
        prompt = render.render_prompt(input_doc, manifest, text)
        return {"transport": TRANSPORTS[entry["transport"]], "argv": argv,
                "prompt_ref": self._write(f"prompt-{base['stage_id']}.md", prompt)}
