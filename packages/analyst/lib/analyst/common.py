"""analyst launch context: the environment (Env) and the project-path helper.

Shared primitives come straight from `aicore` (the launcher and test runner put it on
PYTHONPATH); modules import them from their owner, not through this file."""
import os
from dataclasses import dataclass

from aicore.state import resolve_with_legacy
from aicore.state import state_dir as aicore_state_dir
from aicore.util.env import BaseEnv


@dataclass(frozen=True)
class Env(BaseEnv):
    """Launch context analyst: root/cmd/home come from BaseEnv; here only the path
    property. The cross-project layer lives in the machine state directory (see state_dir);
    per-project lessons - in <project>/.swissknifeman/analyst (see lessons.project_dir)."""

    @property
    def state_dir(self):
        """Single cross-project layer (clusters/suggestions): the analyst folder under the machine state
        directory (``aicore.state``; under ``SKM_HOME`` when set). An existing legacy
        ``~/.swissknifeman/analyst`` is used, with one warning, until it is moved."""
        return resolve_with_legacy(aicore_state_dir("analyst", home=self.home),
                                   [self.home / ".swissknifeman" / "analyst"], home=self.home)


def project_path_from_opts(env, opts):
    """Project path from --cwd (current directory) or default (cwd). --project (by the
    maind project registry) is resolved by the cross-project commands."""
    _ = env, opts
    return os.getcwd()
