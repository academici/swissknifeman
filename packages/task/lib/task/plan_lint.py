"""Thin compatibility coordinator for the bounded plan-lint implementation.

Public imports remain available from ``task.plan_lint`` while parsing, policy,
engine, conflict/baseline and CLI responsibilities live in separate readable
modules under ``task.plan_lint_checks``.
"""
from task.plan_lint_checks.common import *
from task.plan_lint_checks.policy import *
from task.plan_lint_checks.parsing import *
from task.plan_lint_checks.engine import *
from task.plan_lint_checks.conflicts import *
from task.plan_lint_checks.cli import *

# The mechanical split preserves the original single-module lookup semantics:
# top-level functions still resolve shared constants/helpers at call time.  A
# unified internal namespace keeps those lookups stable without duplicating
# definitions or making the public coordinator own behavior.
from task.plan_lint_checks import common as _common
from task.plan_lint_checks import policy as _policy
from task.plan_lint_checks import parsing as _parsing
from task.plan_lint_checks import engine as _engine
from task.plan_lint_checks import conflicts as _conflicts
from task.plan_lint_checks import cli as _cli

_modules = (_common, _policy, _parsing, _engine, _conflicts, _cli)
_shared = {}
for _module in _modules:
    _shared.update({name: value for name, value in vars(_module).items()
                    if not name.startswith("__")})
for _module in _modules:
    vars(_module).update(_shared)

del _module, _modules, _shared
