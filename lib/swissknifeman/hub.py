"""Корневой хаб скиллов в проекте (managed-блок CLAUDE.md / .ai/guidelines)."""
import subprocess

from .common import HUB_MARKER


def hub_artifacts_exist(target):
    if (target / ".ai" / "guidelines" / "swissknifeman-hub.md").is_file():
        return True
    claude_md = target / "CLAUDE.md"
    return claude_md.is_file() and HUB_MARKER in claude_md.read_text(encoding="utf-8")


def generate_hub(env, target):
    subprocess.run([str(env.root / "scripts" / "generate-hub.sh"),
                    "--target", str(target)], check=True)
