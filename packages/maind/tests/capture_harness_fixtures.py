"""Re-capture ``tests/fixtures/harness/*.json`` from the real harness JSON commands.

    SKM_HARNESS_ROOT=<harness package> PYTHONPATH=lib:<aicore>/lib:. python3 tests/capture_harness_fixtures.py

The hub-relative harness package prefix is stored as ``@HARNESS_PKG@`` so no test file names a
module path; the fake harness expands it again when it answers.
"""
import json
import sys
import tempfile
from pathlib import Path

from aicore.util.partners import run_partner_json

OUT = Path(__file__).resolve().parent / "fixtures" / "harness"
PREFIX = "/".join(("packages", "harness"))
TOKEN = "@HARNESS_PKG@"


def harness(*args):
    return run_partner_json("harness", list(args), legacy_env=("MAIND_HARNESS_BIN",))


def write(name, document):
    text = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    (OUT / name).write_text(text.replace(PREFIX, TOKEN), encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    write("mcp-catalog.json", harness("mcp", "catalog", "--json"))
    fragment = harness("hooks", "codex-lifecycle", "fragment", "--json")
    write("codex-lifecycle-fragment.json", fragment)
    memory = {"hooks": [{"type": "command", "command": "bash memory.sh"}]}
    composed = json.dumps({"hooks": {"SessionStart": [memory, fragment["fragment"]["group"]]}}, indent=2)
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "hooks.json"
        path.write_text(composed + "\n", encoding="utf-8")
        write("codex-lifecycle-valid.json", harness(
            "hooks", "codex-lifecycle", "validate", "--document", str(path),
            "--memory-command", "bash memory.sh", "--json"))
        write("codex-lifecycle-invalid.json", harness(
            "hooks", "codex-lifecycle", "validate", "--document", str(path),
            "--memory-command", "bash other.sh", "--json"))
    write("instruction-scopes.json", harness("instructions", "scopes", "--json"))
    base = ("profiles", "resolve", "--provider", "codex", "--target-scope", "project", "--json")
    write("profile-resolution-green.json",
          harness(*base, "--profile", "workspace-contained", "--trusted"))
    write("profile-resolution-untrusted.json", harness(*base, "--profile", "workspace-contained"))
    write("profile-resolution-full-access.json",
          harness(*base, "--profile", "trusted-full-access", "--trusted"))
    print(f"captured into {OUT}")


if __name__ == "__main__":
    sys.exit(main())
