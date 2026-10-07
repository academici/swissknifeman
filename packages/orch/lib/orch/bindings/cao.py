"""CAO binding: each model stage becomes an agent profile (Markdown with YAML frontmatter); only declared here."""
from __future__ import annotations

import json

from orch import render
from orch.bindings import Binding

CAO_PROVIDERS = {"claude-code": "claude_code", "codex": "codex", "grok": "grok_cli"}
EFFORT_KEYS = {"claude-code": "claudeConfig", "codex": "codexConfig"}
EFFORT_FIELDS = {"claude-code": "effort", "codex": "model_reasoning_effort"}
GOAL_CHARS = 120


def _profile(front: dict, body: str) -> str:
    """Frontmatter values are JSON, which is valid YAML."""
    lines = [f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in front.items()]
    return "---\n" + "\n".join(lines) + "\n---\n" + body


class Cao(Binding):
    binding = "cao"

    def project(self, input_doc: dict, base: dict, manifest: dict, cap: dict, resolved: dict) -> dict:
        provider = base["provider"]
        name = f"skm-{manifest['role_id']}-{input_doc['digest'][:8]}"
        goal = " ".join(input_doc["goal"].split())[:GOAL_CHARS]
        front = {"name": name, "description": f"{manifest['title']}: {goal}", "provider": CAO_PROVIDERS.get(provider, provider)}
        if "model" in resolved:
            front["model"] = resolved["model"]
        front["role"] = "reviewer" if manifest["role_id"] == "reviewer" else "developer"
        skills = [item["name"].split(":", 1)[-1] for item in manifest.get("skills") or []]
        if skills:
            front["skills"] = skills
        if provider in EFFORT_KEYS and "effort" in resolved:
            front[EFFORT_KEYS[provider]] = {EFFORT_FIELDS[provider]: resolved["effort"]}
        _, text = render.load_role(manifest["role_id"], self.roles_dir)
        body = render.render_prompt(input_doc, manifest, text)
        return {"transport": "tui", "argv": ["cao", "launch", "--agents", name],
                "profile_ref": self._write(f"profile-{base['stage_id']}.md", _profile(front, body))}
