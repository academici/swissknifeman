"""unittest для task.plan_lint — по классу ошибок отдельный кейс (см. fixtures.py
для шаблонов plan.md/phases/Pn.md/handoff.md, байт-в-байт по snippets/*-template.md).
Запуск: cd packages/task && python3 -m unittest discover -s tests"""
import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path

try:  # package invocation used by the focused P4 command-projection gate
    from .fixtures import (  # noqa: E402
        active_md, closure_json, contracts_section, handoff_md, index_md, item_spec_path,
        item_spec_md, item_state_md, item_state_path, journal_jsonl, legacy_phase_md, phase_index_md,
        phase_index_path, plan_md, write_closure, write_decision_record, write_valid_plan,
        write_v2_carriers,
    )
except ImportError:  # direct discovery from packages/task remains supported
    from fixtures import (  # noqa: E402
        active_md, closure_json, contracts_section, handoff_md, index_md, item_spec_path,
        item_spec_md, item_state_md, item_state_path, journal_jsonl, legacy_phase_md, phase_index_md,
        phase_index_path, plan_md, write_closure, write_decision_record, write_valid_plan,
        write_v2_carriers,
    )
import task.plan_lint as plan_lint_module  # noqa: E402 — --conflicts: monkeypatch реестров
from task.plan_lint import (  # noqa: E402
    CANON_LITERALS, CONTEXT_VALUES, REQUIRED_ITEM_FIELDS, SEMANTIC_NEXT_RE, STATUSES,
    Diagnostics, _conflicts_context_values, _conflicts_i18n_literals, _conflicts_item_fields,
    _conflicts_launch_table_regex, _conflicts_layout_v2, _conflicts_next_forms,
    _conflicts_statuses, _find_skill,
    _resolve_next_form, discover_plan_dirs, lint_plan, lint_plans_root, main,
    run_conflicts_check,
)
from task.journal import append_exception, line_sha256, new_exception  # noqa: E402


def _lint(plan_dir):
    """lint_plan напрямую (без CLI/subprocess) — возвращает (model, diag)."""
    diag = Diagnostics()
    model = lint_plan(plan_dir, diag)
    return model, diag


def _errors_containing(diag, needle):
    return [e for e in diag.errors if needle in e]


class TmpPlanTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


__all__ = tuple(name for name in globals() if not name.startswith("__"))
