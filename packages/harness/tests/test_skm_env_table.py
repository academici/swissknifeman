"""The hook libraries (stdlib only, no aicore) carry copies of the SKM environment variable names; they stay equal to the table."""
import importlib.util
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from aicore.state import envtable

PKG = Path(__file__).resolve().parents[1]
HOOKS = PKG / "configs/claude-code/hooks"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EnvTableCopies(unittest.TestCase):
    def test_the_safe_dirs_hook_uses_the_names_of_the_table(self):
        hook = load(HOOKS / "auto-approve/lib/safedirs.py", "hook_safedirs_env_table")
        self.assertEqual(hook.SKM_ENV, envtable.NAMES)
        self.assertEqual(hook.ENV_HOME, envtable.ENV_HOME)

    def test_the_memory_hook_library_lists_the_names_of_the_table(self):
        text = (HOOKS / "memory/lib/common.sh").read_text(encoding="utf-8")
        found = re.search(r'^SKM_ENV_NAMES="([^"]*)"$', text, re.M)
        self.assertIsNotNone(found)
        self.assertEqual(tuple(found.group(1).split()), envtable.NAMES)

    def test_the_hooks_do_not_spell_a_variable_that_is_not_in_the_table(self):
        known = set(envtable.NAMES)
        for path in (HOOKS / "auto-approve/lib/safedirs.py", HOOKS / "memory/lib/common.sh"):
            for name in re.findall(r"\bSKM_(?:HOME|WORKSPACES?)(?:_ROOT)?\b", path.read_text(encoding="utf-8")):
                self.assertIn(name, known | {envtable.ENV_WORKSPACES_ROOT}, f"{path.name}: {name}")


if __name__ == "__main__":
    unittest.main()
