"""Корневой хаб скиллов в проекте (managed-блок CLAUDE.md / .ai/guidelines)."""
from .common import HUB_MARKER, run_cmd


def hub_artifacts_exist(target):
    if (target / ".ai" / "guidelines" / "swissknifeman-hub.md").is_file():
        return True
    claude_md = target / "CLAUDE.md"
    return claude_md.is_file() and HUB_MARKER in claude_md.read_text(encoding="utf-8")


def generate_hub(env, target):
    run_cmd([str(env.root / "scripts" / "generate-hub.sh"),
             "--target", str(target)])
