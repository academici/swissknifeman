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
from pathlib import Path

try:  # package invocation used by the focused P4 command-projection gate
    from .fixtures import (  # noqa: E402
        active_md, contracts_section, handoff_md, index_md, journal_jsonl, phase_md,
        plan_md, write_valid_plan,
    )
except ImportError:  # direct discovery from packages/task remains supported
    from fixtures import (  # noqa: E402
        active_md, contracts_section, handoff_md, index_md, journal_jsonl, phase_md,
        plan_md, write_valid_plan,
    )
from task.plan_lint import (  # noqa: E402
    Diagnostics, _resolve_next_form, discover_plan_dirs, lint_plan, lint_plans_root, main,
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


class TestBriefLayer(TmpPlanTestCase):
    """Слой 0 «бриф» (SKILL §16): датовый план от 2026.07.16 без brief/ — ERROR,
    легаси/старее — WARNING; непустой brief/00-brief.md гасит проверку."""

    def test_dated_plan_without_brief_is_error(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.16-DEMO")
        shutil.rmtree(plan_dir / "brief")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "нет слоя 0"), diag.errors)

    def test_legacy_plan_without_brief_is_warning(self):
        plan_dir = write_valid_plan(self.root)
        shutil.rmtree(plan_dir / "brief")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "нет слоя 0"), [])
        self.assertTrue([w for w in diag.warnings if "нет слоя 0" in w], diag.warnings)

    def test_dated_fully_detailed_plan_without_roadmap_is_error(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.16-DEMO")
        (plan_dir / "roadmap.md").unlink()
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "roadmap.md"), diag.errors)

    def test_skeleton_phase_does_not_require_roadmap(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.16-DEMO")
        (plan_dir / "roadmap.md").unlink()
        p1 = plan_dir / "phases" / "P1.md"
        text = p1.read_text(encoding="utf-8")
        marker = ("> СКЕЛЕТ — не детализирован, разворачивается "
                  "/task:plan-design 2026.07.16-DEMO P1\n\n")
        p1.write_text(text.replace("## Phase Status", marker + "## Phase Status", 1),
                      encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "roadmap.md"), [])

    def test_dated_plan_next_without_launch_block_is_error(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.16-DEMO")
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        # выкидываем таблицу launch-block'а и code-block — остаётся голая строка Next
        lines = [ln for ln in text.splitlines()
                 if not ln.startswith("|") and not ln.startswith("```")]
        handoff.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "Next без launch-block"), diag.errors)

    def test_empty_brief_md_does_not_count(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.16-DEMO")
        (plan_dir / "brief" / "00-brief.md").write_text("", encoding="utf-8")
        (plan_dir / "brief" / "01-extra.md").unlink(missing_ok=True)
        # оставили только пустой 00-brief.md — проверка обязана сработать
        for f in (plan_dir / "brief").glob("*.md"):
            if f.name != "00-brief.md":
                f.unlink()
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "нет слоя 0"), diag.errors)


class TestJournalIndexLayer(TmpPlanTestCase):
    """journal.jsonl/index.md (P1.4/D22): датовый план от 2026.07.18 без валидного
    journal.jsonl — ERROR, старее/legacy — WARNING; index.md отсутствует — ВСЕГДА
    WARNING (не носитель факта, в отличие от журнала)."""

    def test_dated_plan_without_journal_is_error(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.18-DEMO")
        (plan_dir / "journal.jsonl").unlink()
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "journal.jsonl"), diag.errors)

    def test_legacy_plan_without_journal_is_warning(self):
        plan_dir = write_valid_plan(self.root)
        (plan_dir / "journal.jsonl").unlink()
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "journal.jsonl"), [])
        self.assertTrue([w for w in diag.warnings if "journal.jsonl" in w], diag.warnings)

    def test_dated_plan_with_empty_journal_is_error(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.18-DEMO")
        (plan_dir / "journal.jsonl").write_text("", encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "journal.jsonl"), diag.errors)

    def test_dated_plan_with_malformed_json_line_is_error(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.18-DEMO")
        (plan_dir / "journal.jsonl").write_text("{not valid json\n", encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "не валидный JSON"), diag.errors)

    def test_dated_plan_with_schema_violation_is_error(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.18-DEMO")
        (plan_dir / "journal.jsonl").write_text('{"plan_id":"x"}\n', encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "не проходит схему"), diag.errors)

    def test_owner_gated_historical_exception_suppresses_exact_field_only(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.18-DEMO")
        journal = plan_dir / "journal.jsonl"
        entry = json.loads(journal.read_text(encoding="utf-8"))
        entry["friction"] = ["Major: historical free-form value"]
        raw = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        journal.write_text(raw + "\n", encoding="utf-8")
        plan = plan_dir / "plan.md"
        plan.write_text(
            plan.read_text(encoding="utf-8").replace(
                "| D1 | 2026-07-02 | тест | тест |",
                "| D1 | 2026-07-02 | тест | тест |\n"
                "| D2 | 2026-07-19 | historical schema exception | owner gate |"),
            encoding="utf-8",
        )
        append_exception(plan_dir, new_exception(
            plan_id="2026.07.18-DEMO", target_line=1,
            target_sha256=line_sha256(raw), invalid_fields=["friction"],
            owner_decision="D2", actor="owner", reason="preserve historical bytes",
            ts="2026-07-19T20:00:00Z",
        ))
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "journal"), [], diag.errors)
        self.assertEqual([w for w in diag.warnings if "journal" in w], [], diag.warnings)

    def test_foreign_event_plan_id_is_non_exemptable_error(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.18-DEMO")
        journal = plan_dir / "journal.jsonl"
        entry = json.loads(journal.read_text(encoding="utf-8"))
        entry["plan_id"] = "2026.07.18-FOREIGN"
        journal.write_text(
            json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _, diag = _lint(plan_dir)
        self.assertTrue(
            _errors_containing(diag, "2026.07.18-FOREIGN")
            and _errors_containing(diag, "2026.07.18-DEMO"),
            diag.errors,
        )

    def test_foreign_event_and_sidecar_plan_ids_cannot_exempt_mismatch(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.18-DEMO")
        journal = plan_dir / "journal.jsonl"
        entry = json.loads(journal.read_text(encoding="utf-8"))
        entry["plan_id"] = "2026.07.18-FOREIGN"
        entry["friction"] = ["Major: historical free-form value"]
        raw = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        journal.write_text(raw + "\n", encoding="utf-8")
        plan = plan_dir / "plan.md"
        plan.write_text(
            plan.read_text(encoding="utf-8").replace(
                "| D1 | 2026-07-02 | тест | тест |",
                "| D1 | 2026-07-02 | тест | тест |\n"
                "| D2 | 2026-07-19 | historical schema exception | owner gate |"),
            encoding="utf-8",
        )
        exception = new_exception(
            plan_id="2026.07.18-FOREIGN", target_line=1,
            target_sha256=line_sha256(raw), invalid_fields=["friction"],
            owner_decision="D2", actor="owner", reason="foreign probe",
            ts="2026-07-19T20:00:00Z",
        )
        (plan_dir / "journal-exceptions.jsonl").write_text(
            json.dumps(exception, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "schema exception"), diag.errors)
        self.assertTrue(_errors_containing(diag, "2026.07.18-FOREIGN"), diag.errors)
        self.assertTrue(_errors_containing(diag, "2026.07.18-DEMO"), diag.errors)

    def test_historical_exception_rejects_inexact_invalid_field_set(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.18-DEMO")
        journal = plan_dir / "journal.jsonl"
        entry = json.loads(journal.read_text(encoding="utf-8"))
        entry["command"] = "plan-nope"
        entry["friction"] = ["Major: historical free-form value"]
        raw = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        journal.write_text(raw + "\n", encoding="utf-8")
        plan = plan_dir / "plan.md"
        plan.write_text(
            plan.read_text(encoding="utf-8").replace(
                "| D1 | 2026-07-02 | тест | тест |",
                "| D1 | 2026-07-02 | тест | тест |\n"
                "| D2 | 2026-07-19 | historical schema exception | owner gate |"),
            encoding="utf-8",
        )
        exception = new_exception(
            plan_id="2026.07.18-DEMO", target_line=1,
            target_sha256=line_sha256(raw), invalid_fields=["friction"],
            owner_decision="D2", actor="owner", reason="inexact probe",
            ts="2026-07-19T20:00:00Z",
        )
        (plan_dir / "journal-exceptions.jsonl").write_text(
            json.dumps(exception, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _, diag = _lint(plan_dir)
        self.assertTrue(
            _errors_containing(diag, "['command', 'friction']"), diag.errors)
        self.assertTrue(_errors_containing(diag, "не проходит схему"), diag.errors)

    def test_historical_exception_hash_mismatch_is_error(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.18-DEMO")
        journal = plan_dir / "journal.jsonl"
        entry = json.loads(journal.read_text(encoding="utf-8"))
        entry["friction"] = ["Major: historical free-form value"]
        raw = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        journal.write_text(raw + "\n", encoding="utf-8")
        plan = plan_dir / "plan.md"
        plan.write_text(
            plan.read_text(encoding="utf-8").replace(
                "| D1 | 2026-07-02 | тест | тест |",
                "| D1 | 2026-07-02 | тест | тест |\n"
                "| D2 | 2026-07-19 | historical schema exception | owner gate |"),
            encoding="utf-8",
        )
        exception = new_exception(
            plan_id="2026.07.18-DEMO", target_line=1,
            target_sha256="0" * 64, invalid_fields=["friction"],
            owner_decision="D2", actor="owner", reason="preserve historical bytes",
            ts="2026-07-19T20:00:00Z",
        )
        (plan_dir / "journal-exceptions.jsonl").write_text(
            json.dumps(exception, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "target_sha256"), diag.errors)
        self.assertTrue(_errors_containing(diag, "не проходит схему"), diag.errors)

    def test_dated_plan_before_cutoff_journal_gate_is_warning(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.16-DEMO")
        (plan_dir / "journal.jsonl").unlink()
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "journal.jsonl"), [])
        self.assertTrue([w for w in diag.warnings if "journal.jsonl" in w], diag.warnings)

    def test_missing_index_is_always_warning_not_error(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.18-DEMO")
        (plan_dir / "index.md").unlink()
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "index.md"), [])
        self.assertTrue([w for w in diag.warnings if "index.md" in w], diag.warnings)

    def test_valid_plan_with_journal_and_index_is_clean(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.18-DEMO")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "journal.jsonl"), [])
        self.assertEqual(_errors_containing(diag, "index.md"), [])
        self.assertEqual([w for w in diag.warnings if "journal.jsonl" in w], [])
        self.assertEqual([w for w in diag.warnings if "index.md" in w], [])

    def test_validated_exception_suppresses_only_exact_schema_error(self):
        plan_id = "2026.07.19-DEMO"
        plan_dir = write_valid_plan(self.root, plan_id=plan_id)
        entry = json.loads((plan_dir / "journal.jsonl").read_text(encoding="utf-8"))
        entry["friction"] = "legacy"
        raw = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        (plan_dir / "journal.jsonl").write_text(raw + "\n", encoding="utf-8")
        plan = (plan_dir / "plan.md").read_text(encoding="utf-8")
        (plan_dir / "plan.md").write_text(
            plan.replace("## 6. Update Log", "## 5. Decision Log\n\n| D# | Дата | Решение | Почему |\n|:--|:--|:--|:--|\n| D51 | 2026-07-20 | owner | test |\n\n## 6. Update Log"),
            encoding="utf-8")
        sidecar = {
            "ts": "2026-07-20T00:00:00Z", "plan_id": plan_id, "target_line": 1,
            "target_sha256": __import__("hashlib").sha256(raw.encode()).hexdigest(),
            "invalid_fields": ["friction"], "owner_decision": "D51",
            "actor": "owner", "reason": "test",
        }
        (plan_dir / "journal-exceptions.jsonl").write_text(
            json.dumps(sidecar, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "не проходит схему"), [], diag.errors)

    def test_malformed_exception_never_suppresses_journal_error(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.19-DEMO")
        entry = json.loads((plan_dir / "journal.jsonl").read_text(encoding="utf-8"))
        entry["friction"] = "legacy"
        (plan_dir / "journal.jsonl").write_text(
            json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        (plan_dir / "journal-exceptions.jsonl").write_text("{bad\n", encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "journal-exceptions.jsonl"), diag.errors)
        self.assertTrue(_errors_containing(diag, "не проходит схему"), diag.errors)

    def test_non_string_owner_exception_never_suppresses_journal_error(self):
        plan_id = "2026.07.19-DEMO"
        plan_dir = write_valid_plan(self.root, plan_id=plan_id)
        entry = json.loads((plan_dir / "journal.jsonl").read_text(encoding="utf-8"))
        entry["friction"] = "legacy"
        raw = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        (plan_dir / "journal.jsonl").write_text(raw + "\n", encoding="utf-8")
        sidecar = {
            "ts": "2026-07-20T00:00:00Z", "plan_id": plan_id, "target_line": 1,
            "target_sha256": __import__("hashlib").sha256(raw.encode()).hexdigest(),
            "invalid_fields": ["friction"], "owner_decision": 123,
            "actor": "owner", "reason": "test",
        }
        (plan_dir / "journal-exceptions.jsonl").write_text(
            json.dumps(sidecar, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "owner_decision"), diag.errors)
        self.assertTrue(_errors_containing(diag, "не проходит схему"), diag.errors)


class TestAuditScopePayload(TmpPlanTestCase):
    """Scope-payload launch-block'а в блоке `## Audit Pn` (SKILL §8, D-канон 2026-07-17).

    Инцидент-основание: аудит P0 плана 2026.07.16-INS-EVO выдал `/task:plan-design <ID> P0`
    голым — владелец прочитал это как «фазу разрабатывают заново». Вердикт RED/ATTENTION
    передаёт находки ⇒ launch-block обязан нести РЕЖИМ:/ВХОД:/СКОУП:/НЕ ТРОГАТЬ:.
    """

    PAYLOAD = (
        "\n## Audit P1 — 2026-07-17\n\n"
        "**Вердикт: {verdict}** · заход 1\n\n"
        "### Findings\n\nB1 · issue · P1.1 · `a.py:1` — сломано.\n\n"
        "### Что запускать\n\n"
        "| Параметр | Значение |\n|:--|:--|\n| Model | Opus |\n| Thinking | high |\n"
        "| Context | NEW SESSION — шаг-не-item |\n| Суть | Реопен |\n\n"
        "```\n/task:plan-design 2026.07.16-DEMO P1\n\n{payload}```\n"
    )
    FULL_PAYLOAD = ("РЕЖИМ: реопен по §3\n"
                    "ВХОД: phases/P1.md → блок `## Audit P1 — 2026-07-17`\n"
                    "СКОУП: 1) завести item под B1\n"
                    "НЕ ТРОГАТЬ: ТЗ закрытых items\n")

    def _write_audit(self, plan_id, verdict, payload):
        plan_dir = write_valid_plan(self.root, plan_id=plan_id)
        phase = plan_dir / "phases" / "P1.md"
        phase.write_text(phase.read_text(encoding="utf-8")
                         + self.PAYLOAD.format(verdict=verdict, payload=payload),
                         encoding="utf-8")
        return plan_dir

    def test_red_without_payload_is_error(self):
        plan_dir = self._write_audit("2026.07.16-DEMO", "RED", "")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "launch-block неполон"), diag.errors)

    def test_attention_without_payload_is_error(self):
        plan_dir = self._write_audit("2026.07.16-DEMO", "ATTENTION", "")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "launch-block неполон"), diag.errors)

    def test_partial_payload_names_the_missing_line(self):
        """Гейт называет ИМЕННО недостающую строку — иначе автор чинит наугад."""
        partial = "РЕЖИМ: реопен по §3\nВХОД: phases/P1.md → блок аудита\nСКОУП: 1) item\n"
        plan_dir = self._write_audit("2026.07.16-DEMO", "RED", partial)
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "НЕ ТРОГАТЬ"), diag.errors)

    def test_red_with_full_payload_is_clean(self):
        plan_dir = self._write_audit("2026.07.16-DEMO", "RED", self.FULL_PAYLOAD)
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "launch-block неполон"), [], diag.errors)

    def test_green_does_not_require_payload(self):
        """GREEN находок не несёт — payload'а не требуем (иначе маркеры = ритуал)."""
        plan_dir = self._write_audit("2026.07.16-DEMO", "GREEN", "")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "launch-block неполон"), [], diag.errors)

    def test_legacy_plan_is_warning_not_error(self):
        """Back-compat §2: планы старее канона красить задним числом нельзя."""
        plan_dir = self._write_audit("DEMO-LEGACY", "RED", "")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "launch-block неполон"), [], diag.errors)
        self.assertTrue([w for w in diag.warnings if "launch-block неполон" in w],
                        diag.warnings)

    def test_block_without_verdict_line_is_not_gated(self):
        """Граница: `## Audit …` без строки вердикта — свободная заметка, не отчёт."""
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.16-DEMO")
        phase = plan_dir / "phases" / "P1.md"
        phase.write_text(phase.read_text(encoding="utf-8")
                         + "\n## Audit P1 — 2026-07-17\n\nСвободная заметка без вердикта.\n",
                         encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "launch-block неполон"), [], diag.errors)


class TestTieredPortability(TmpPlanTestCase):
    """P2.2/D26/D47: план с `handoff.md` (tier=committed-bundle по конструкции) обязан
    нести ≥1 committed execution input и не содержать внешний (host/chat/mAInd/tmp/foreign)
    путь В РОЛИ execution input (Inputs/Required Reads/Validation); упоминание того же пути
    ВНЕ ролевых полей (Why/Implementation Rules/…) — provenance и обязано проходить."""

    def _write(self, plan_id, *, required_reads="1) lib/pkg/config.py"):
        plan_dir = write_valid_plan(self.root, plan_id=plan_id)
        phase = plan_dir / "phases" / "P1.md"
        text = phase.read_text(encoding="utf-8")
        text = text.replace("**Required Reads:** 1) lib/pkg/config.py",
                            f"**Required Reads:** {required_reads}")
        phase.write_text(text, encoding="utf-8")
        return plan_dir

    def test_committed_execution_input_is_clean(self):
        plan_dir = self._write("2026.07.27-DEMO")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "PORTABILITY"), [])
        self.assertEqual([w for w in diag.warnings if "PORTABILITY" in w], [])

    def test_dated_plan_with_tmp_execution_input_is_error(self):
        plan_dir = self._write("2026.07.27-DEMO", required_reads="1) tmp/scratch-notes.md")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "PORTABILITY_EXTERNAL_INPUT"), diag.errors)

    def test_dated_plan_with_absolute_execution_input_is_error(self):
        plan_dir = self._write("2026.07.27-DEMO", required_reads="1) /etc/passwd")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "PORTABILITY_EXTERNAL_INPUT"), diag.errors)

    def test_dated_plan_with_home_execution_input_is_error(self):
        plan_dir = self._write("2026.07.27-DEMO", required_reads="1) ~/.codex/session.json")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "PORTABILITY_EXTERNAL_INPUT"), diag.errors)

    def test_legacy_plan_with_external_execution_input_is_warning_not_error(self):
        """Back-compat §2: планы старее канона красить задним числом нельзя."""
        plan_dir = self._write("DEMO-LEGACY", required_reads="1) tmp/scratch-notes.md")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "PORTABILITY_EXTERNAL_INPUT"), [], diag.errors)
        self.assertTrue([w for w in diag.warnings if "PORTABILITY_EXTERNAL_INPUT" in w],
                        diag.warnings)

    def test_tmp_mention_outside_role_fields_is_provenance_and_passes(self):
        """D47: `tmp/`-упоминание в Why/Implementation Rules (не Inputs/Required
        Reads/Validation) — provenance, не execution input; та же дисциплина, что
        закрепляет self-conformance фикстура этого плана на `brief/00-brief.md`."""
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.27-DEMO")
        phase = plan_dir / "phases" / "P1.md"
        text = phase.read_text(encoding="utf-8")
        text = text.replace(
            "**Why:** Диагностика дорогая.",
            "**Why:** Диагностика дорогая; см. user-owned `tmp/scratch-notes.md` "
            "как provenance.")
        phase.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "PORTABILITY"), [])
        self.assertEqual([w for w in diag.warnings if "PORTABILITY" in w], [])

    def test_shell_redirect_target_in_validation_is_not_an_execution_input(self):
        """Скретч-редирект (`> файл`) в поле Validation — цель записи диагностики
        собственной команды item'а, не execution input (P4.2-инцидент на этом самом
        плане до фикса regex'а)."""
        plan_dir = self._write(
            "2026.07.27-DEMO",
            required_reads="1) lib/pkg/config.py",
        )
        phase = plan_dir / "phases" / "P1.md"
        text = phase.read_text(encoding="utf-8")
        text = text.replace(
            "**Validation:** bash scripts/test.sh — зелёный.",
            "**Validation:** `bash scripts/test.sh >/tmp/scratch-output.txt` — зелёный.")
        phase.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "PORTABILITY_EXTERNAL_INPUT"), [], diag.errors)

    def test_dated_plan_without_any_committed_execution_input_is_error(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.27-DEMO")
        phase = plan_dir / "phases" / "P1.md"
        text = phase.read_text(encoding="utf-8")
        text = (text.replace("**Inputs:** список ключей.", "**Inputs:** ничего внешнего.")
                    .replace("**Required Reads:** 1) lib/pkg/config.py",
                             "**Required Reads:** прочитать контекст владельца.")
                    .replace("**Validation:** bash scripts/test.sh — зелёный.",
                             "**Validation:** проверить руками."))
        phase.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "PORTABILITY_INPUT_MISSING"), diag.errors)


class TestWriteSiteCodesGate(TmpPlanTestCase):
    """P4.4/D91 (ремонт находки Ф2, findings/P3.11-terminal-audit-2.md § Ф2): item со
    статусом 🟢/🟠, чей `Updated` (Phase Status) ≥ cutoff, обязан нести оба кода
    `pre_mutation:`/`pre_final:` со значением `allow` в Completion Notes; item ДО cutoff'а
    не диагностируется вовсе (forward-only, D91). Каждый различающий кейс (b)/(c) ниже
    проверен КРАСНЫМ на коде до этого item'а (`git show HEAD:packages/task/lib/task/
    plan_lint.py` не нёс ни `_lint_write_site_codes_44`, ни вызова из `lint_plan` —
    старый код молчал на ОБОИХ кейсах; см. Completion Notes P4.4 за точным прогоном, D79)."""

    def _write(self, *, updated, item_status="🟢 Done",
               completion_notes="сделано, тест зелёный"):
        plan_dir = write_valid_plan(self.root)
        phase = plan_dir / "phases" / "P1.md"
        phase.write_text(
            phase_md(item_status=item_status, completion_notes=completion_notes,
                      updated=updated),
            encoding="utf-8")
        return plan_dir

    def test_a_pre_cutoff_item_without_codes_is_silent(self):
        """(а) Updated < cutoff, без кодов → молчание (forward-only, И10)."""
        plan_dir = self._write(updated="2026-07-26")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "pre_mutation/pre_final"), [])

    def test_b_post_cutoff_item_without_codes_is_error(self):
        """(б) Updated ≥ cutoff, без кодов → ERROR."""
        plan_dir = self._write(updated="2026-07-27")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "без напечатанных кодов границ"), diag.errors)

    def test_c_post_cutoff_item_with_pre_final_na_is_error(self):
        """(в) Updated ≥ cutoff, `pre_final: n/a` → ERROR (D76: `n/a` — не зелёное)."""
        plan_dir = self._write(
            updated="2026-07-27",
            completion_notes="Сделано. `pre_mutation: allow`, `pre_final: n/a`.")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "закрытие на не-allow"), diag.errors)

    def test_d_post_cutoff_item_with_both_allow_is_silent(self):
        """(г) Updated ≥ cutoff, оба `allow` → молчание."""
        plan_dir = self._write(
            updated="2026-07-27",
            completion_notes="Сделано. `pre_mutation: allow`, `pre_final: allow`.")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "pre_mutation"), [])
        self.assertEqual(_errors_containing(diag, "pre_final"), [])

    def test_malformed_updated_date_is_out_of_scope_not_error(self):
        """Непарсимая/нестрогая дата (не ISO `YYYY-MM-DD`) = вне скоупа — fail-open по дате
        (Implementation Rules P4.4 (1)), не ERROR/WARNING."""
        plan_dir = self._write(updated="2026.07.27")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "pre_mutation/pre_final"), [])

    def test_not_done_status_is_never_gated(self):
        """Статус вне `🟢`/`🟠` (напр. `⬜ Not started`) — правило не применяется, каким бы
        ни был Updated."""
        plan_dir = self._write(updated="2026-07-27", item_status="⬜ Not started",
                                completion_notes="—")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "pre_mutation/pre_final"), [])


class TestValidPlan(TmpPlanTestCase):
    def test_valid_plan_ok(self):
        plan_dir = write_valid_plan(self.root)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(diag.warnings, [])

    def test_json_model_shape(self):
        plan_dir = write_valid_plan(self.root)
        model, diag = _lint(plan_dir)
        self.assertTrue(diag.ok)
        self.assertEqual(model["id"], "DEMO-1")
        self.assertEqual(model["meta"]["Plan ID"], "DEMO-1")
        self.assertIn("P1", model["phases"])
        self.assertIn("P1.1", model["phases"]["P1"]["items"])
        self.assertEqual(model["phases"]["P1"]["items"]["P1.1"]["fields"]["Status"], "🟢 Done")
        # модель должна сериализоваться в JSON без потерь (--json дампит именно её)
        json.dumps(model, ensure_ascii=False)


class TestPlanMdStructure(TmpPlanTestCase):
    def test_missing_plan_md(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "phases" / "P1.md").write_text(phase_md(), encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "plan.md отсутствует"))

    def test_meta_missing_required_field(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| Plan ID | DEMO-1 |\n", "")
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "нет обязательного поля «Plan ID»"))

    def test_status_board_section_missing(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("## 4. Phase Index & Status Board", "## 4. Что-то другое")
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "нет секции «## 4. Phase Index & Status Board»"))

    def test_status_board_invalid_status(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| P1 | Фаза раз | 1/1 | 🟢 Done |",
                             "| P1 | Фаза раз | 1/1 | Готово |")
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "Status Board: недопустимый статус «Готово»"))

    def test_status_board_malformed_phase_token(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| P1 | Фаза раз |", "| Phase1 | Фаза раз |")
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "не похож на Pn"))


class TestPhaseBoardCorrespondence(TmpPlanTestCase):
    def test_phase_in_board_without_file(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "plan.md").write_text(plan_md("DEMO-1"), encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        # phases/P1.md сознательно не создан
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "есть в Status Board, но нет phases/P1.md"))

    def test_phase_file_without_board_row(self):
        plan_dir = write_valid_plan(self.root)
        (plan_dir / "phases" / "P2.md").write_text(phase_md("P2", item_id="P2.1"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "есть как phases/P2.md, но нет в Status Board"))


class TestItemHeaderAndFields(TmpPlanTestCase):
    def test_malformed_item_header(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "phases" / "P1.md").read_text(encoding="utf-8")
        text = text.replace("### P1.1 — Валидация конфига", "### P1.1 Валидация конфига")
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "заголовок item не соответствует regex"))

    def test_missing_required_item_field(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "phases" / "P1.md").read_text(encoding="utf-8")
        text = text.replace("**Code Guidance:** ручная проверка dict-ключей.\n", "")
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "нет обязательного поля «Code Guidance»"))

    def test_missing_required_item_field_message_is_actionable(self):
        # ERROR скелет-item'а обязана называть путь починки (D11: ERROR не ослабляется,
        # меняется только текст) — /task:plan-design <ID> Pn.
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "phases" / "P1.md").read_text(encoding="utf-8")
        text = text.replace("**Code Guidance:** ручная проверка dict-ключей.\n", "")
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "/task:plan-design <ID> P1"))

    def test_invalid_item_status(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "plan.md").write_text(plan_md("DEMO-1"), encoding="utf-8")
        text = phase_md().replace("**Status:** 🟢 Done", "**Status:** Готово")
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "item P1.1: недопустимый статус «Готово»"))

    def test_item_prefix_mismatch(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "phases" / "P1.md").read_text(encoding="utf-8")
        # переименовываем item P1.1 -> P2.1, но он остаётся физически в файле phases/P1.md
        text = text.replace("P1.1", "P2.1")
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "префикс «P2» не совпадает с файлом фазы «P1»"))


class TestCompletionAndDeviations(TmpPlanTestCase):
    def test_done_without_completion_notes(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "plan.md").write_text(plan_md("DEMO-1"), encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(
            phase_md(item_status="🟢 Done", completion_notes="—"), encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "требует непустых Completion Notes"))

    def test_deviations_without_known_deviations(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "plan.md").write_text(
            plan_md("DEMO-1", phase_status="🟠 Done with deviations"), encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(
            phase_md(item_status="🟠 Done with deviations",
                      completion_notes="сделано с оговоркой", known_deviations="—"),
            encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "требует непустых Known Deviations"))


class TestEscalationConsistency(TmpPlanTestCase):
    def _write(self, item_status, escalation_needed, extra_blockquote=None,
               completion_notes="—", known_deviations="—"):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "plan.md").write_text(
            plan_md("DEMO-1", phase_status=item_status if item_status != "🟢 Done" else "🟢 Done"),
            encoding="utf-8")
        text = phase_md(item_status=item_status, escalation_needed=escalation_needed,
                         completion_notes=completion_notes, known_deviations=known_deviations)
        if extra_blockquote:
            text = text.replace("## Phase Handoff", f"{extra_blockquote}\n\n## Phase Handoff")
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        return plan_dir

    def test_blocked_without_escalation_block_or_flag(self):
        plan_dir = self._write("🔴 Blocked", "—")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "рассогласованы"))

    def test_escalation_flag_yes_without_blocked_status(self):
        plan_dir = self._write("🟢 Done", "yes", completion_notes="сделано")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "рассогласованы"))

    def test_escalation_needed_invalid_value(self):
        plan_dir = self._write("⬜ Not started", "maybe")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "ожидается yes/no/—"))

    def test_blocked_with_full_escalation_triple_passes(self):
        plan_dir = self._write(
            "🔴 Blocked", "yes",
            extra_blockquote="> 🔴 ESCALATION P1.1: неясная архитектура | trigger: неясная "
                              "архитектура | нужен: plan-design",
        )
        _, diag = _lint(plan_dir)
        self.assertFalse(_errors_containing(diag, "рассогласованы"))


class TestPhaseStatusConsistency(TmpPlanTestCase):
    def test_phase_status_table_vs_item_status_mismatch(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "phases" / "P1.md").read_text(encoding="utf-8")
        # таблица говорит Done, а сам item ниже — In progress
        text = text.replace(
            "| P1.1 | Валидация конфига | 🟢 Done | 2026-07-02 |",
            "| P1.1 | Валидация конфига | 🟡 In progress | 2026-07-02 |",
        )
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "статус в Phase Status «🟡 In progress» ≠ статусу item «🟢 Done»"))


class TestStatusBoardConsistency(TmpPlanTestCase):
    def test_items_cell_wrong_count(self):
        plan_dir = write_valid_plan(self.root, )
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| P1 | Фаза раз | 1/1 | 🟢 Done |", "| P1 | Фаза раз | 0/1 | 🟢 Done |")
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "≠ фактическому 1/1"))

    def test_items_cell_bad_format(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| P1 | Фаза раз | 1/1 | 🟢 Done |", "| P1 | Фаза раз | one | 🟢 Done |")
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "ожидается формат N/M"))

    def test_all_done_but_board_status_not_done(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| P1 | Фаза раз | 1/1 | 🟢 Done |", "| P1 | Фаза раз | 1/1 | 🟡 In progress |")
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "все items 🟢 Done, но статус фазы"))

    def test_blocked_item_but_board_status_not_blocked(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "plan.md").write_text(
            plan_md("DEMO-1", items_cell="0/1", phase_status="🟢 Done"), encoding="utf-8")
        text = phase_md(item_status="🔴 Blocked", escalation_needed="yes",
                         completion_notes="—", known_deviations="—")
        text = text.replace(
            "## Phase Handoff",
            "> 🔴 ESCALATION P1.1: причина | trigger: неясная архитектура | "
            "нужен: plan-design\n\n## Phase Handoff",
        )
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "есть 🔴 Blocked item, но статус фазы"))


class TestPhaseHandoffGating(TmpPlanTestCase):
    def test_done_phase_with_empty_phase_handoff(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "plan.md").write_text(plan_md("DEMO-1"), encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(phase_md(handoff_text="—"), encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "Phase Handoff» пуст"))

    def test_missing_phase_handoff_section(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "phases" / "P1.md").read_text(encoding="utf-8")
        text = text.replace("## Phase Handoff", "## Что-то другое")
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "нет секции «## Phase Handoff»"))


class TestStalePhaseHandoff(TmpPlanTestCase):
    """P2.15/D34 (H2): реопен инвалидирует `## Phase Handoff` маркером; блок, переживший
    реопен и утверждающий закрытие фазы, — WARNING. Гейт УЗКИЙ: заготовка/скелет молчит."""

    STALE_TEXT = ("Фаза P1 закрыта: **1/1 терминальны**.\n\n"
                  "**Сдано:** валидация конфига.\n\n**Дальше:** `/task:plan-audit DEMO-1 P1`.")

    def _write_reopened_phase(self, handoff_text):
        """Фаза 🟡 (реопенена: item снова в работе) с заданным `## Phase Handoff`."""
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "plan.md").write_text(
            plan_md("DEMO-1", items_cell="0/1", phase_status="🟡 In progress"), encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(
            phase_md(item_status="🟡 In progress", completion_notes="—",
                     handoff_text=handoff_text), encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        return plan_dir

    def _stale_warnings(self, diag):
        return [w for w in diag.warnings if "Phase Handoff протух" in w]

    def test_nonterminal_phase_with_closure_claim_warns(self):
        plan_dir = self._write_reopened_phase(self.STALE_TEXT)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)  # именно WARNING, не ERROR (D34)
        self.assertEqual(len(self._stale_warnings(diag)), 1, diag.warnings)
        self.assertIn("> УСТАРЕЛ — фаза реопенена <D#>", self._stale_warnings(diag)[0])

    def test_stale_marker_silences_the_gate(self):
        plan_dir = self._write_reopened_phase(
            "> **УСТАРЕЛ — фаза реопенена (D9, 2026-07-14).** Блок ниже записан plan-close\n"
            "> до реопена; факт: 0/1, фаза 🟡.\n\n" + self.STALE_TEXT)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._stale_warnings(diag), [])

    def test_placeholder_handoff_of_unfinished_phase_is_silent(self):
        # анти-регресс: скелеты/заготовки флота (наивная формулировка била 104 фазы)
        for text in ("—", "Заполняется при закрытии фазы."):
            with self.subTest(handoff=text):
                plan_dir = self._write_reopened_phase(text)
                _, diag = _lint(plan_dir)
                self.assertEqual(self._stale_warnings(diag), [])
                shutil.rmtree(plan_dir.parent)

    # --- P3.7/D50 (J1): гейт судит по СУБЪЕКТУ утверждения, а не по встреченному слову.
    # Обе фикстуры — ДОСЛОВНЫЕ формы флота (findings/P3-reopen-gates-and-fleet.md §1),
    # не «удобные» синтетические строки: ровно на них гейт разошёлся с истиной.

    def test_honest_interim_handoff_is_silent(self):
        """themeon/2026.07.12-BASE/P5: первая строка ОТРИЦАЕТ закрытие фазы, а слово
        «Терминальны» относится к ITEMS → ложно-положительный WARNING (J1, Blocker)."""
        plan_dir = self._write_reopened_phase(
            "**Фаза P5 НЕ закрыта.** Терминальны только P5.1 и P5.2 (2/10); P5.3–P5.10 (8/10) — "
            "🟠⬜ `Not started`\n(dterema: breakpoints/runtime-switch; vintera: весь пилот).\n\n"
            "**Что сдано (dterema, ветка `themeon-migration/P5`, НЕ смержена):** 3 коммита.")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._stale_warnings(diag), [], diag.warnings)

    def test_delivery_claim_of_nonterminal_phase_still_warns(self):
        """vaulter/VLT-REMED/P5: первая строка УТВЕРЖДАЕТ сдачу фазы при нетерминальном
        статусе → истинно-положительный WARNING обязан сохраниться (анти-подгонка предиката)."""
        plan_dir = self._write_reopened_phase(
            "**Сдано:** Фаза P5 (сквозной adversarial code review всех изменений VLT-REMED) — "
            "**терминальна (3/3)**:\nP5.1 (🔴 Blocked) → P5.2 (🟠 Done with deviations) → "
            "**P5.3 (🟢 Done)**.")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(len(self._stale_warnings(diag)), 1, diag.warnings)

    def test_negation_below_first_line_does_not_silence_the_gate(self):
        """Отрицание судится по ТОЙ ЖЕ первой строке: «фаза закрыта … но P1.2 не закрыта»
        ниже по тексту не гасит истинное срабатывание (Implementation Rules P3.7)."""
        plan_dir = self._write_reopened_phase(
            "**Сдано:** фаза закрыта, 1/1.\n\nОстаток: P1.2 не закрыта — переносится в P2.")
        _, diag = _lint(plan_dir)
        self.assertEqual(len(self._stale_warnings(diag)), 1, diag.warnings)


class TestHandoffMd(TmpPlanTestCase):
    def test_missing_handoff_file(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "plan.md").write_text(plan_md("DEMO-1"), encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(phase_md(), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "handoff.md отсутствует"))

    def test_handoff_missing_title(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("# HANDOFF — 2026-07-02 — after P1.1\n", "")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "нет заголовка «# HANDOFF"))

    def test_handoff_title_after_item_valid(self):
        # форма `after Pn.m` (закрыт item) — базовая, остаётся валидной (D30)
        plan_dir = write_valid_plan(self.root)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_handoff_title_after_phase_valid(self):
        # вторая форма `after Pn` (закрыта/проаудирована ФАЗА) — D30/G10
        plan_dir = write_valid_plan(self.root)
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        text = text.replace("— after P1.1\n", "— after P1\n")
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_handoff_title_after_nonexistent_phase(self):
        # анти-подгонка: `after Pn` обязан РЕЗОЛВИТЬСЯ, а не просто матчиться regex'ом
        plan_dir = write_valid_plan(self.root)
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        text = text.replace("— after P1.1\n", "— after P9\n")
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "заголовок: фаза «P9» не существует в плане"))

    def test_handoff_title_item_form_nonexistent_phase(self):
        # D37/H10: item-форма `after Pn.m` больше не обходит гейт резолва — ФАЗА обязана быть
        plan_dir = write_valid_plan(self.root)
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        text = text.replace("— after P1.1\n", "— after P9.1\n")
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "заголовок: фаза «P9» не существует в плане"))

    def test_handoff_title_bootstrap_item_form_allowed(self):
        # D37: whitelist — РОВНО `P0.0` (стартовый handoff, фазы P0 в плане не бывает) → тихо
        plan_dir = write_valid_plan(self.root)
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        text = text.replace("— after P1.1\n", "— after P0.0\n")
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_handoff_title_prose_form_rejected(self):
        # `after phase 2` — вне обеих форм enum'а
        plan_dir = write_valid_plan(self.root)
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        text = text.replace("— after P1.1\n", "— after phase 1\n")
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "заголовок не соответствует ни одной из двух форм"))

    def test_handoff_missing_required_field(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("**Remaining:** ничего.\n", "")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "нет обязательного поля «Remaining»"))

    def test_handoff_next_missing_reference(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("/task:plan-exec DEMO-1 P1.1", "сделай что-нибудь")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "не соответствует ни одной из допустимых форм"))

    def test_handoff_next_wrong_plan_id(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("/task:plan-exec DEMO-1 P1.1", "/task:plan-exec OTHER-ID P1.1")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "PLAN-ID «OTHER-ID» ≠ фактическому «DEMO-1»"))

    def test_handoff_next_nonexistent_item(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("/task:plan-exec DEMO-1 P1.1", "/task:plan-exec DEMO-1 P9.9")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "item «P9.9» не существует ни в одной фазе"))

    def test_handoff_next_plan_closed_allowed(self):
        # все items терминальны → Next «план закрыт» без ссылки plan-exec — валиден
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("/task:plan-exec DEMO-1 P1.1", "план закрыт — все фазы терминальны.")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok)

    def test_handoff_next_plan_design_phase_allowed(self):
        # фаза-скелет впереди → Next «/task:plan-design <ID> Pn» (ссылка на фазу, не item) — валиден
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("/task:plan-exec DEMO-1 P1.1", "/task:plan-design DEMO-1 P1")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok)

    def test_handoff_next_plan_design_wrong_plan_id(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("/task:plan-exec DEMO-1 P1.1", "/task:plan-design OTHER-ID P1")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "PLAN-ID «OTHER-ID» ≠ фактическому «DEMO-1»"))

    def test_handoff_next_plan_design_nonexistent_phase(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("/task:plan-exec DEMO-1 P1.1", "/task:plan-design DEMO-1 P9")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "фаза «P9» не существует в плане"))

    def test_handoff_next_plan_closed_rejected_when_items_active(self):
        # «план закрыт» при живом 🟡 item — не оправдание, ERROR остаётся
        plan_dir = write_valid_plan(self.root)
        p1 = plan_dir / "phases" / "P1.md"
        text = p1.read_text(encoding="utf-8")
        text = text.replace("**Status:** 🟢 Done", "**Status:** 🟡 In progress")
        text = text.replace("| P1.1 | Валидация конфига | 🟢 Done |",
                            "| P1.1 | Валидация конфига | 🟡 In progress |")
        p1.write_text(text, encoding="utf-8")
        plan = plan_dir / "plan.md"
        text = plan.read_text(encoding="utf-8")
        text = text.replace("| P1 | Фаза раз | 1/1 | 🟢 Done |",
                            "| P1 | Фаза раз | 0/1 | 🟡 In progress |")
        plan.write_text(text, encoding="utf-8")
        ho = plan_dir / "handoff.md"
        text = ho.read_text(encoding="utf-8")
        text = text.replace("/task:plan-exec DEMO-1 P1.1", "план закрыт.")
        ho.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "«план закрыт», но не все items терминальны"))


class TestNextFormsEnum(TmpPlanTestCase):
    """m8/B1/N1/N2 — enum 8 форм handoff.Next (SKILL §8): по кейсу на форму
    (принимается) + мусорная форма (ERROR) + plan-audit нетерминальной фазы (WARNING)."""

    def _next(self, plan_dir, new_next):
        ho = plan_dir / "handoff.md"
        text = ho.read_text(encoding="utf-8")
        text = text.replace("/task:plan-exec DEMO-1 P1.1", new_next)
        ho.write_text(text, encoding="utf-8")

    def test_plan_design_item_form_accepted(self):
        # item эскалирован/требует ре-дизайна — ссылка на существующий item Pn.m
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "/task:plan-design DEMO-1 P1.1")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_plan_design_item_form_nonexistent_item_is_error(self):
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "/task:plan-design DEMO-1 P9.9")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "item «P9.9» не существует ни в одной фазе"))

    def test_plan_audit_terminal_phase_accepted(self):
        # фаза P1 терминальна (🟢 Done в фикстуре) — plan-audit допустим без warning
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "/task:plan-audit DEMO-1 P1")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual([w for w in diag.warnings if "не терминальна" in w], [])

    def test_plan_audit_nonterminal_phase_warns(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "plan.md").write_text(
            plan_md("DEMO-1", items_cell="0/1", phase_status="🟡 In progress"), encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(
            phase_md(item_status="🟡 In progress", completion_notes="—", handoff_text="—"),
            encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        self._next(plan_dir, "/task:plan-audit DEMO-1 P1")
        _, diag = _lint(plan_dir)
        self.assertTrue(any("не терминальна" in w for w in diag.warnings), diag.warnings)

    def test_plan_close_phase_form_accepted(self):
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "/task:plan-close DEMO-1 P1")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_plan_close_item_form_accepted(self):
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "/task:plan-close DEMO-1 P1.1")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_plan_close_item_form_nonexistent_item_is_error(self):
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "/task:plan-close DEMO-1 P9.9")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "item «P9.9» не существует ни в одной фазе"))

    def test_plan_close_archive_form_accepted_when_closed(self):
        # план целиком терминален (единственный item 🟢 Done) — форма допустима
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "/task:plan-close archive DEMO-1")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_plan_close_archive_form_warns_when_not_closed(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "plan.md").write_text(
            plan_md("DEMO-1", items_cell="0/1", phase_status="🟡 In progress"), encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(
            phase_md(item_status="🟡 In progress", completion_notes="—", handoff_text="—"),
            encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        self._next(plan_dir, "/task:plan-close archive DEMO-1")
        _, diag = _lint(plan_dir)
        self.assertTrue(any("план ещё не терминален целиком" in w for w in diag.warnings), diag.warnings)

    def test_manual_run_form_accepted(self):
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "ЗАПУСК ВРУЧНУЮ: fable/high — item требует public-контракт решения")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_garbage_next_form_is_error(self):
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "сделай что-нибудь по вдохновению")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "не соответствует ни одной из допустимых форм"))


class TestNextDeclarationLine(TmpPlanTestCase):
    """D40 — форма `Next` объявляется ПЕРВОЙ строкой поля; проза launch-block'а (в т.ч.
    ячейка «Суть») законно ЦИТИРУЕТ другие формы enum'а и резолвер не перехватывает."""

    def _activate_item(self, plan_dir):
        """Делает единственный item 🟡 (план перестаёт быть терминальным целиком)."""
        p1 = plan_dir / "phases" / "P1.md"
        text = p1.read_text(encoding="utf-8")
        text = text.replace("**Status:** 🟢 Done", "**Status:** 🟡 In progress")
        text = text.replace("| P1.1 | Валидация конфига | 🟢 Done |",
                            "| P1.1 | Валидация конфига | 🟡 In progress |")
        p1.write_text(text, encoding="utf-8")
        plan = plan_dir / "plan.md"
        text = plan.read_text(encoding="utf-8")
        text = text.replace("| P1 | Фаза раз | 1/1 | 🟢 Done |",
                            "| P1 | Фаза раз | 0/1 | 🟡 In progress |")
        plan.write_text(text, encoding="utf-8")

    def _sut(self, plan_dir, next_decl, sut_cell):
        """Переписывает handoff: объявление формы + ячейка «Суть» launch-block'а."""
        ho = plan_dir / "handoff.md"
        text = ho.read_text(encoding="utf-8")
        text = text.replace("**Next:** /task:plan-exec DEMO-1 P1.1", f"**Next:** {next_decl}")
        text = text.replace("| Суть | закрыть следующий item |", f"| Суть | {sut_cell} |")
        ho.write_text(text, encoding="utf-8")

    def test_manual_declaration_beats_closed_literal_in_prose(self):
        # Дефект: греп «план закрыт» по ВСЕМУ полю ловил упоминание формы в «Сути»
        # и давал ложный ERROR «не все items терминальны», перебивая маркер manual.
        plan_dir = write_valid_plan(self.root)
        self._activate_item(plan_dir)
        self._sut(plan_dir, "«ЗАПУСК ВРУЧНУЮ: opus/high»",
                  "свести формы enum'а: «план закрыт» vs slash-команды")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_manual_declaration_beats_slash_form_in_prose(self):
        # Та же природа: slash-команда, ПРОЦИТИРОВАННАЯ в «Сути» manual-формы, не объявление —
        # резолв её ссылок дал бы ERROR по несуществующему item'у P9.9.
        plan_dir = write_valid_plan(self.root)
        self._sut(plan_dir, "«ЗАПУСК ВРУЧНУЮ: opus/high»",
                  "команды `/task:plan-design DEMO-1 P9.9` для этого item'а не существует")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_closed_literal_on_declaration_line_still_gated(self):
        # Анти-ослабление: объявленная первой строкой форма «план закрыт» гейтится как прежде.
        plan_dir = write_valid_plan(self.root)
        self._activate_item(plan_dir)
        self._sut(plan_dir, "«план закрыт»", "следующий шаг вне протокола")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "«план закрыт», но не все items терминальны"))


class TestWaitingForm(TmpPlanTestCase):
    """P2.1/D8 — 9-я форма Next «ОЖИДАНИЕ» (waiting): резолв ДО exec, требует
    launch-block; C2-WARNING на прозаическую gate-оговорку в runnable-форме."""

    def _waiting_handoff(self, plan_id="DEMO-1", *, cond="≥2026-07-16",
                         target="/task:plan-exec DEMO-1 P1.1", guard=True):
        guard_line = f"# НЕ раньше: {cond}\n" if guard else ""
        return f"""# HANDOFF — 2026-07-02 — after P1.1

**Next:** ОЖИДАНИЕ: {cond} → {target}

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium |
| Context | continue (/clear) — ручной item |
| Суть | закрыть целевой item по снятии гейта |

````
{guard_line}{target}
````

**Done:** P1.1 закрыт.
**Remaining:** целевой шаг ждёт гейта.
**Sources of truth:** plans/{plan_id}/plan.md · plans/{plan_id}/phases/P1.md
**Open risks:** —
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: —
- open_questions: —
"""

    def test_waiting_form_accepted(self):
        plan_dir = write_valid_plan(self.root)
        (plan_dir / "handoff.md").write_text(self._waiting_handoff(), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_waiting_resolves_before_exec_no_item_ref_error(self):
        # целевой /task:plan-exec … P9.9 в ОБЪЯВЛЕНИИ не должен резолвиться как exec и ловить
        # ERROR по несуществующему item'у — форма waiting перехватывает резолвер раньше (D8).
        plan_dir = write_valid_plan(self.root)
        ho = self._waiting_handoff(target="/task:plan-exec DEMO-1 P9.9")
        (plan_dir / "handoff.md").write_text(ho, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual([e for e in diag.errors if "P9.9" in e], [], diag.errors)

    def test_waiting_guard_line_no_c2_warning(self):
        # guard-строка `# НЕ раньше:` в code-block'е НЕ триггерит C2: сканируется только
        # строка-объявление, а она резолвится в waiting (не в runnable-форму).
        plan_dir = write_valid_plan(self.root)
        (plan_dir / "handoff.md").write_text(self._waiting_handoff(guard=True), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual([w for w in diag.warnings if "прозу-оговорку" in w], [], diag.warnings)

    def test_waiting_without_launch_block_warns(self):
        # waiting несёт launch-block как прочие runnable-формы — не exempt (в отличие от «план закрыт»)
        plan_dir = write_valid_plan(self.root)
        text = self._waiting_handoff()
        head, _, tail = text.partition("\n| Параметр | Значение |")
        _, _, after = tail.partition("````\n\n")
        (plan_dir / "handoff.md").write_text(head + "\n" + after, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(any("launch-block" in w for w in diag.warnings), diag.warnings)

    def test_c2_prose_oговорка_in_runnable_form_warns(self):
        # runnable-форма (exec) + прозаический стем в объявлении = C2-WARNING (не ERROR)
        plan_dir = write_valid_plan(self.root)
        ho = plan_dir / "handoff.md"
        text = ho.read_text(encoding="utf-8")
        text = text.replace(
            "**Next:** /task:plan-exec DEMO-1 P1.1",
            "**Next:** /task:plan-exec DEMO-1 P1.1 — НО не раньше ~2026-07-16 (тайм-гейт)")
        ho.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(any("прозу-оговорку" in w for w in diag.warnings), diag.warnings)

    def test_clean_runnable_form_no_c2_warning(self):
        # чистый exec без стемов — C2 молчит
        plan_dir = write_valid_plan(self.root)
        _, diag = _lint(plan_dir)
        self.assertEqual([w for w in diag.warnings if "прозу-оговорку" in w], [], diag.warnings)


class TestArchivePlansNotPhantomPlan(TmpPlanTestCase):
    """N3/D14 — `plans/archive/` сама планом не является (не должна требовать
    plan.md/handoff.md), а `plans/archive/<ID>` линтуется как обычный план."""

    def _write_archived_plan(self, plan_id="DEMO-OLD"):
        plan_dir = self.root / "plans" / "archive" / plan_id
        (plan_dir / "phases").mkdir(parents=True, exist_ok=True)
        (plan_dir / "plan.md").write_text(plan_md(plan_id), encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(phase_md(), encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md(plan_id), encoding="utf-8")
        return plan_dir

    def test_archive_container_produces_no_phantom_errors(self):
        write_valid_plan(self.root, "DEMO-1")
        self._write_archived_plan("DEMO-OLD")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self.root / "plans")])
        self.assertEqual(code, 0, err.getvalue())
        self.assertNotIn("archive/plan.md", err.getvalue())
        self.assertNotIn("archive/handoff.md", err.getvalue())

    def test_archived_plan_still_linted(self):
        write_valid_plan(self.root, "DEMO-1")
        archived_dir = self._write_archived_plan("DEMO-OLD")
        text = (archived_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| Plan ID | DEMO-OLD |\n", "")
        (archived_dir / "plan.md").write_text(text, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self.root / "plans")])
        self.assertEqual(code, 1)
        self.assertIn("нет обязательного поля «Plan ID»", err.getvalue())

    def test_discover_plan_dirs_excludes_archive_container_includes_children(self):
        write_valid_plan(self.root, "DEMO-1")
        self._write_archived_plan("DEMO-OLD")
        found = discover_plan_dirs(self.root / "plans")
        names = sorted(p.name for p in found)
        self.assertEqual(names, ["DEMO-1", "DEMO-OLD"])


class TestGlobalUniqueness(TmpPlanTestCase):
    def test_duplicate_item_id_across_phases(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        text = plan_md("DEMO-1").replace(
            "| P1 | Фаза раз | 1/1 | 🟢 Done |",
            "| P1 | Фаза раз | 1/1 | 🟢 Done |\n| P2 | Фаза два | 1/1 | 🟢 Done |",
        )
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(phase_md("P1", item_id="P1.1"), encoding="utf-8")
        # умышленный баг: во второй фазе снова P1.1 (должно быть P2.1)
        (plan_dir / "phases" / "P2.md").write_text(phase_md("P2", item_id="P1.1"), encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "переиспользован в фазах"))

    def test_duplicate_item_id_within_one_file(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "phases" / "P1.md").read_text(encoding="utf-8")
        block = text.split("### P1.1", 1)[1]
        text = text + "\n### P1.1" + block
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "повторяется в файле"))


class TestWarnings(TmpPlanTestCase):
    def test_duplicate_title_warning(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        text = plan_md("DEMO-1").replace(
            "| P1 | Фаза раз | 1/1 | 🟢 Done |",
            "| P1 | Фаза раз | 2/2 | 🟢 Done |",
        )
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")

        # второй item с ТЕМ ЖЕ Title, что и P1.1 ("Валидация конфига") — добавляем
        # его строку в Phase Status и сам item-блок перед `## Phase Handoff`.
        second_item_block = """### P1.2 — Валидация конфига

**Status:** 🟢 Done
**Intent:** —
**Why:** —
**Scope Included:** —
**Scope Excluded:** —
**Inputs:** —
**Files:** —
**Required Reads:** —
**Implementation Rules:** —
**Code Guidance:** —
**Validation:** —
**Deliverables:** —
**Completion Notes:** сделано
**Pending Work:** —
**Known Deviations:** —
**Escalation Needed:** —

## Phase Handoff"""
        phase_text = phase_md("P1", item_id="P1.1")
        phase_text = phase_text.replace(
            "| P1.1 | Валидация конфига | 🟢 Done | 2026-07-02 |",
            "| P1.1 | Валидация конфига | 🟢 Done | 2026-07-02 |\n"
            "| P1.2 | Валидация конфига | 🟢 Done | 2026-07-02 |",
        )
        phase_text = phase_text.replace("## Phase Handoff", second_item_block)
        (plan_dir / "phases" / "P1.md").write_text(phase_text, encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(any("дубль Title" in w for w in diag.warnings))

    def test_phase_first_warning(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        text = plan_md("DEMO-1", items_cell="0/1", phase_status="🟡 In progress")
        text = text.replace(
            "| P1 | Фаза раз | 0/1 | 🟡 In progress |",
            "| P1 | Фаза раз | 0/1 | 🟡 In progress |\n| P2 | Фаза два | 0/1 | 🟡 In progress |",
        )
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(
            phase_md("P1", item_id="P1.1", item_status="⬜ Not started",
                      completion_notes="—", known_deviations="—"),
            encoding="utf-8")
        (plan_dir / "phases" / "P2.md").write_text(
            phase_md("P2", item_id="P2.1", item_status="🟡 In progress",
                      completion_notes="—", known_deviations="—"),
            encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1", item_id="P2.1"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(any("phase-first" in w for w in diag.warnings), diag.warnings)

    def test_empty_required_reads_warning_for_active_item(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "phases" / "P1.md").read_text(encoding="utf-8")
        text = text.replace("**Status:** 🟢 Done", "**Status:** 🟡 In progress")
        text = text.replace("| P1.1 | Валидация конфига | 🟢 Done |", "| P1.1 | Валидация конфига | 🟡 In progress |")
        text = text.replace("**Required Reads:** 1) lib/pkg/config.py", "**Required Reads:** —")
        text = text.replace("**Completion Notes:** сделано, тест зелёный", "**Completion Notes:** —")
        board = (plan_dir / "plan.md").read_text(encoding="utf-8")
        board = board.replace("| P1 | Фаза раз | 1/1 | 🟢 Done |", "| P1 | Фаза раз | 0/1 | 🟡 In progress |")
        (plan_dir / "plan.md").write_text(board, encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(any("пустые Required Reads" in w for w in diag.warnings))


class TestSemanticNextCarrier(TmpPlanTestCase):
    """P4.4: neutral Next is canonical; frozen slash syntax remains compatible."""

    def test_semantic_audit_phase_resolves_the_same_plan_and_phase(self):
        plan_dir = write_valid_plan(self.root)
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8").replace(
            "/task:plan-exec DEMO-1 P1.1",
            "audit-phase: task:plan-audit DEMO-1 P1")
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertFalse(any("Next не соответствует" in item for item in diag.errors))

    def test_historical_slash_next_remains_accepted(self):
        plan_dir = write_valid_plan(self.root)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertFalse(any("Next не соответствует" in item for item in diag.errors))

    def test_semantic_kind_command_mismatch_is_rejected(self):
        plan_dir = write_valid_plan(self.root)
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8").replace(
            "/task:plan-exec DEMO-1 P1.1",
            "audit-phase: task:plan-exec DEMO-1 P1.1")
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(any("Next не соответствует" in item for item in diag.errors),
                        diag.errors)

    def test_all_closed_semantic_kinds_resolve_before_provider_rendering(self):
        fixture = Path(__file__).with_name("fixtures_data") / "provider-plan-cases.json"
        declarations = json.loads(fixture.read_text(encoding="utf-8"))["next_declarations"]
        expected = {
            "exec-items": "exec", "run-items": "run", "audit-design": "audit-design",
            "design-phase": "design-phase", "design-item": "design-item",
            "audit-phase": "audit", "close": "close", "archive": "close-archive",
            "terminal": "closed", "manual": "manual", "waiting": "waiting",
        }
        self.assertEqual(
            {kind: _resolve_next_form(value)[0] for kind, value in declarations.items()},
            expected,
        )


class TestPlansRoot(TmpPlanTestCase):
    """Root-level проверки (path = plans/ целиком): ACTIVE.md + черновики (P1.5)."""

    def _plans_root(self):
        return self.root / "plans"

    def test_valid_active_pointing_to_existing_plan_ok(self):
        write_valid_plan(self.root, "DEMO-1")
        (self._plans_root() / "ACTIVE.md").write_text(active_md("DEMO-1"), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self._plans_root())])
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(err.getvalue(), "")

    def test_active_dash_means_no_active_plan_ok(self):
        write_valid_plan(self.root, "DEMO-1")
        (self._plans_root() / "ACTIVE.md").write_text(active_md("—"), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self._plans_root())])
        self.assertEqual(code, 0, err.getvalue())

    def test_active_pointing_to_nonexistent_plan_is_error(self):
        write_valid_plan(self.root, "DEMO-1")
        (self._plans_root() / "ACTIVE.md").write_text(active_md("NO-SUCH-PLAN"), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self._plans_root())])
        self.assertEqual(code, 1)
        self.assertIn("не указывает на существующий план", err.getvalue())

    def test_active_md_without_active_field_is_error(self):
        write_valid_plan(self.root, "DEMO-1")
        (self._plans_root() / "ACTIVE.md").write_text("# ACTIVE\n\nничего полезного\n", encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self._plans_root())])
        self.assertEqual(code, 1)
        self.assertIn("нет поля «**Active:**»", err.getvalue())

    def test_two_in_progress_plans_without_active_warns(self):
        write_valid_plan(self.root, "DEMO-1")
        write_valid_plan(self.root, "DEMO-2")
        # дефолт фикстуры — Meta Status «🟢 Done»; переводим оба плана в «🟡 In progress»
        # (только Meta-строку — консистентность items/board эта проверка не трогает).
        for pid in ("DEMO-1", "DEMO-2"):
            p = self._plans_root() / pid / "plan.md"
            text = p.read_text(encoding="utf-8").replace(
                "| Status | 🟢 Done |", "| Status | 🟡 In progress |")
            p.write_text(text, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self._plans_root())])
        self.assertEqual(code, 0, err.getvalue())  # WARNING, не ERROR
        self.assertIn("активный план неоднозначен", err.getvalue())

    def test_single_in_progress_plan_without_active_is_clean(self):
        write_valid_plan(self.root, "DEMO-1")  # дефолт Meta Status «🟢 Done» — не 🟡
        diag = Diagnostics()
        model = lint_plan(self._plans_root() / "DEMO-1", diag)
        lint_plans_root(self._plans_root(), {"DEMO-1": model}, diag)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(diag.warnings, [])

    def test_draft_flat_md_warns_with_from_draft_hint(self):
        write_valid_plan(self.root, "DEMO-1")
        (self._plans_root() / "sketch.md").write_text("# черновик\n", encoding="utf-8")
        (self._plans_root() / "ACTIVE.md").write_text(active_md("DEMO-1"), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self._plans_root())])
        self.assertEqual(code, 0, err.getvalue())
        self.assertIn("черновики plan mode", err.getvalue())
        self.assertIn("sketch.md", err.getvalue())
        self.assertIn("/task:plan-design from-draft", err.getvalue())

    def test_readme_and_active_are_not_drafts(self):
        write_valid_plan(self.root, "DEMO-1")
        (self._plans_root() / "README.md").write_text("# readme\n", encoding="utf-8")
        (self._plans_root() / "ACTIVE.md").write_text(active_md("DEMO-1"), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self._plans_root())])
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(err.getvalue(), "")

    def test_single_plan_mode_ignores_sibling_active_md(self):
        # plan-lint.py plans/<ID> (одиночный режим) не видит ACTIVE.md вовсе — даже
        # битый (указывающий на несуществующий план) не должен на него влиять.
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        (self._plans_root() / "ACTIVE.md").write_text(active_md("NO-SUCH-PLAN"), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(plan_dir)])
        self.assertEqual(code, 0, err.getvalue())


class TestDiscoveryAndCli(TmpPlanTestCase):
    def test_discover_single_plan_dir(self):
        plan_dir = write_valid_plan(self.root)
        found = discover_plan_dirs(plan_dir)
        self.assertEqual(found, [plan_dir])

    def test_discover_plans_root_multiple(self):
        write_valid_plan(self.root, "DEMO-1")
        write_valid_plan(self.root, "DEMO-2")
        found = discover_plan_dirs(self.root / "plans")
        self.assertEqual(sorted(p.name for p in found), ["DEMO-1", "DEMO-2"])

    def test_discover_nonexistent_path(self):
        self.assertIsNone(discover_plan_dirs(self.root / "no-such-dir"))

    def test_discover_empty_plans_root_is_not_error(self):
        (self.root / "plans").mkdir()
        self.assertEqual(discover_plan_dirs(self.root / "plans"), [])

    def test_main_exit_code_ok(self):
        write_valid_plan(self.root, "DEMO-1")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self.root / "plans" / "DEMO-1")])
        self.assertEqual(code, 0)
        self.assertIn("OK", out.getvalue())

    def test_main_exit_code_fail(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| Plan ID | DEMO-1 |\n", "")
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(plan_dir)])
        self.assertEqual(code, 1)
        self.assertIn("ПРОВАЛ", out.getvalue())
        self.assertIn("ERROR:", err.getvalue())

    def test_main_json_flag_emits_parseable_json(self):
        write_valid_plan(self.root, "DEMO-1")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self.root / "plans" / "DEMO-1"), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertIn("DEMO-1", payload["plans"])

    def test_main_nonexistent_path_exit_1(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self.root / "no-such-plans")])
        self.assertEqual(code, 1)
        self.assertIn("ERROR:", err.getvalue())


if __name__ == "__main__":
    unittest.main()


class TestLint20Warnings(TmpPlanTestCase):
    """Проверки схемы 2.0 (ECOSYSTEM P5.2 блок 13) — ВСЕ warning-уровня:
    диагностика попадает в diag.warnings, diag.ok остаётся True."""

    def _warnings_containing(self, diag, needle):
        return [w for w in diag.warnings if needle in w]

    def test_plan_sections_out_of_order_warning(self):
        plan_dir = write_valid_plan(self.root)
        plan = plan_dir / "plan.md"
        text = plan.read_text(encoding="utf-8")
        # меняем местами Decision Log (5) и Update Log (6) — номера не по возрастанию
        text = text.replace("## 5. Decision Log", "## X-TMP")
        text = text.replace("## 6. Update Log", "## 5. Decision Log… нет, Update Log")
        text = text.replace("## X-TMP", "## 6. Update Log")
        plan.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "не по порядку"), diag.warnings)

    def test_plan_section_title_mismatch_warning(self):
        plan_dir = write_valid_plan(self.root)
        plan = plan_dir / "plan.md"
        text = plan.read_text(encoding="utf-8")
        text = text.replace("## 3. Routing", "## 3. Маршрутизация")
        plan.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "≠ канонической"), diag.warnings)

    def test_update_log_too_long_warning(self):
        plan_dir = write_valid_plan(self.root)
        plan = plan_dir / "plan.md"
        text = plan.read_text(encoding="utf-8")
        text = text.replace("| 2026-07-02 | issue-planner/opus | План создан |",
                            "| 2026-07-02 | issue-planner/opus | " + "х" * 301 + " |")
        plan.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "Update Log"), diag.warnings)

    def test_decision_log_without_rag_markers_warning(self):
        plan_dir = write_valid_plan(self.root)
        plan = plan_dir / "plan.md"
        text = plan.read_text(encoding="utf-8")
        extra = ("| D2 | 2026-07-02 | ещё решение | так надо |\n"
                 "| D3 | 2026-07-02 | третье решение | и так надо |\n")
        text = text.replace("| D1 | 2026-07-02 | тест | тест |\n",
                            "| D1 | 2026-07-02 | тест | тест |\n" + extra)
        plan.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "RAG:✅"), diag.warnings)

    def test_decision_log_with_rag_marker_no_warning(self):
        plan_dir = write_valid_plan(self.root)
        plan = plan_dir / "plan.md"
        text = plan.read_text(encoding="utf-8")
        extra = ("| D2 | 2026-07-02 | ещё решение | RAG:✅ 2026-07-02 запрос |\n"
                 "| D3 | 2026-07-02 | третье решение | [UNVERIFIED] |\n")
        text = text.replace("| D1 | 2026-07-02 | тест | тест |\n",
                            "| D1 | 2026-07-02 | тест | тест |\n" + extra)
        plan.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(self._warnings_containing(diag, "RAG:✅»/«[UNVERIFIED]"), [])

    def test_decision_log_with_rag_dash_marker_no_warning(self):
        # третий маркер enum'а §7 (D29): `RAG:—` — repo-grounded факт, WARNING'а быть не должно
        plan_dir = write_valid_plan(self.root)
        plan = plan_dir / "plan.md"
        text = plan.read_text(encoding="utf-8")
        extra = ("| D2 | 2026-07-02 | ещё решение | RAG:— (repo-grounded: lib/pkg/config.py) |\n"
                 "| D3 | 2026-07-02 | третье решение | RAG:— |\n")
        text = text.replace("| D1 | 2026-07-02 | тест | тест |\n",
                            "| D1 | 2026-07-02 | тест | тест |\n" + extra)
        plan.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "Decision Log:"), [])

    def test_item_fields_out_of_order_warning(self):
        plan_dir = write_valid_plan(self.root)
        p1 = plan_dir / "phases" / "P1.md"
        text = p1.read_text(encoding="utf-8")
        # Intent и Why меняем местами — канонический порядок нарушен
        text = text.replace("**Intent:** Добавить проверку.\n**Why:** Диагностика дорогая.",
                            "**Why:** Диагностика дорогая.\n**Intent:** Добавить проверку.")
        p1.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "не в каноническом порядке"), diag.warnings)

    def _make_hollow_item(self, plan_dir):
        """P1.1 с ⬜ и ≥50% пустых полей (скелетоподобный item)."""
        p1 = plan_dir / "phases" / "P1.md"
        text = p1.read_text(encoding="utf-8")
        for field, val in (("Intent", "Добавить проверку."), ("Why", "Диагностика дорогая."),
                           ("Scope Included", "load_config()."), ("Scope Excluded", "формат конфига."),
                           ("Inputs", "список ключей."), ("Files", "lib/pkg/config.py"),
                           ("Required Reads", "1) lib/pkg/config.py"),
                           ("Implementation Rules", "stdlib-only."),
                           ("Code Guidance", "ручная проверка dict-ключей.")):
            text = text.replace(f"**{field}:** {val}", f"**{field}:** —")
        text = text.replace("**Status:** 🟢 Done", "**Status:** ⬜ Not started")
        text = text.replace("| P1.1 | Валидация конфига | 🟢 Done |",
                            "| P1.1 | Валидация конфига | ⬜ Not started |")
        p1.write_text(text, encoding="utf-8")
        plan = plan_dir / "plan.md"
        ptext = plan.read_text(encoding="utf-8")
        ptext = ptext.replace("| P1 | Фаза раз | 1/1 | 🟢 Done |",
                              "| P1 | Фаза раз | 0/1 | ⬜ Not started |")
        ptext = ptext.replace("| Status | 🟢 Done |", "| Status | 🟡 In progress |")
        plan.write_text(ptext, encoding="utf-8")
        return p1

    def test_hollow_item_without_skeleton_marker_warning(self):
        plan_dir = write_valid_plan(self.root)
        self._make_hollow_item(plan_dir)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "СКЕЛЕТ"), diag.warnings)

    def test_hollow_item_with_skeleton_marker_no_warning(self):
        plan_dir = write_valid_plan(self.root)
        p1 = self._make_hollow_item(plan_dir)
        text = p1.read_text(encoding="utf-8")
        text = text.replace(
            "Демо-фаза.",
            "Демо-фаза.\n\n> СКЕЛЕТ — не детализирован, разворачивается /task:plan-design DEMO-1 P1")
        p1.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(self._warnings_containing(diag, "СКЕЛЕТ"), [], diag.warnings)

    def test_needs_clarification_in_active_phase_warning(self):
        plan_dir = write_valid_plan(self.root)
        p1 = plan_dir / "phases" / "P1.md"
        text = p1.read_text(encoding="utf-8")
        text = text.replace("**Why:** Диагностика дорогая.",
                            "**Why:** Диагностика дорогая. [NEEDS CLARIFICATION: какой формат ошибок?]")
        p1.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)  # фаза 🟢 Done — точно «ушла из дизайна»
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "NEEDS CLARIFICATION"), diag.warnings)

    def test_handoff_next_without_launch_block_warning(self):
        plan_dir = write_valid_plan(self.root)
        ho = plan_dir / "handoff.md"
        text = handoff_md("DEMO-1")
        # выпиливаем launch-block целиком: остаётся голый Next без таблицы/code-block
        head, _, tail = text.partition("\n| Параметр | Значение |")
        _, _, after = tail.partition("````\n\n")
        ho.write_text(head + "\n" + after, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "launch-block"), diag.warnings)

    def test_handoff_plan_closed_launch_block_not_required(self):
        # план закрыт → запускать нечего, launch-block не требуется
        plan_dir = write_valid_plan(self.root)
        ho = plan_dir / "handoff.md"
        text = ho.read_text(encoding="utf-8")
        text = text.replace("/task:plan-exec DEMO-1 P1.1", "план закрыт — все фазы терминальны.")
        head, _, tail = text.partition("\n| Параметр | Значение |")
        _, _, after = tail.partition("````\n\n")
        ho.write_text(head + "\n" + after, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "launch-block"), [], diag.warnings)


class TestPlanIdentity43Warnings(TmpPlanTestCase):
    """P4.3 (D24/D27/D28) — три WARNING-проверки идентичности плана: регулярка PLAN-ID,
    место/имя workflow-скрипта, supersedes-преемственность. ВСЕ warning: diag.ok=True."""

    def _warnings_containing(self, diag, needle):
        return [w for w in diag.warnings if needle in w]

    def _add_js(self, plan_dir, rel, with_marker=True):
        p = plan_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        body = "export const meta = {\n  name: 'x',\n}\n" if with_marker else "// не workflow\n"
        p.write_text(body, encoding="utf-8")
        return p

    # --- (1) регулярка PLAN-ID (D24) -----------------------------------------
    def test_legacy_id_no_warning(self):
        plan_dir = write_valid_plan(self.root, "OLD-STYLE")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "канону PLAN-ID"), [], diag.warnings)

    def test_dated_id_no_warning(self):
        plan_dir = write_valid_plan(self.root, "2026.07.10-DEMO")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "канону PLAN-ID"), [], diag.warnings)

    def test_noncanonical_id_warning(self):
        # строчные буквы → не матчит ни старый `[A-Z]…`, ни датовый паттерн
        plan_dir = write_valid_plan(self.root, "demo-lower")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "канону PLAN-ID"), diag.warnings)

    # --- (2) место/имя workflow-скрипта (D28) --------------------------------
    def test_canonical_workflow_script_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")  # codename = demo-1
        self._add_js(plan_dir, "workflows/wf-demo-1-drive.js")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "workflow-скрипт"), [], diag.warnings)

    def test_workflow_script_outside_workflows_dir_warns_place(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._add_js(plan_dir, "wf-demo-1-drive.js")  # каноничное имя, но не под workflows/
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        w = self._warnings_containing(diag, "workflow-скрипт")
        self.assertTrue(any("вне" in x for x in w), diag.warnings)
        self.assertFalse(any("неканоничным именем" in x for x in w), diag.warnings)

    def test_workflow_script_noncanonical_name_warns_name(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._add_js(plan_dir, "workflows/wf-bad.js")  # под workflows/, но имя неканонично
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        w = self._warnings_containing(diag, "workflow-скрипт")
        self.assertTrue(any("неканоничным именем" in x for x in w), diag.warnings)
        self.assertFalse(any("вне" in x for x in w), diag.warnings)

    def test_js_without_marker_ignored(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._add_js(plan_dir, "helpers/util.js", with_marker=False)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "workflow-скрипт"), [], diag.warnings)

    # --- (2b) dev-loop.js — резидентный agent-pack класс, exempt (P3.3/findings A4) ---
    def test_dev_loop_js_exempt_by_name(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._add_js(plan_dir, "dev-loop.js")  # вне workflows/, неканоничное имя — оба триггера
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "workflow-скрипт"), [], diag.warnings)

    # --- (3) supersedes-преемственность (D27) --------------------------------
    def test_supersedes_missing_with_archived_codename_warns(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        (self.root / "plans" / "archive" / "DEMO-1").mkdir(parents=True)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "supersedes"), diag.warnings)

    def test_supersedes_present_silences(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        (self.root / "plans" / "archive" / "DEMO-1").mkdir(parents=True)
        plan = plan_dir / "plan.md"
        text = plan.read_text(encoding="utf-8").replace(
            "| Status | 🟢 Done |", "| Status | 🟢 Done |\n| supersedes | DEMO-OLD |")
        plan.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "supersedes"), [], diag.warnings)

    def test_no_archive_dir_no_warning(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")  # plans/archive/ отсутствует
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "supersedes"), [], diag.warnings)


class TestWorkflowDoRWarning46(TmpPlanTestCase):
    """P4.6 (D29) — workflow-как-DoR: фаза со статусом 🟡+, ЗАЯВЛЯЮЩАЯ оркестрацию
    (грепаемый признак multi-agent/fan-out), но без workflow-скрипта в
    `plans/<ID>/workflows/` = WARNING. Условность: без признака / при статусе ⬜ /
    при наличии скрипта — тишина. Всё warning-only: diag.ok=True."""

    _NEEDLE = "заявляет оркестрацию"

    def _warnings_containing(self, diag, needle):
        return [w for w in diag.warnings if needle in w]

    def _inject_orchestration(self, plan_dir, phase="P1"):
        """Добавляет грепаемый признак оркестрации в Phase Context фазы."""
        p = plan_dir / "phases" / f"{phase}.md"
        text = p.read_text(encoding="utf-8").replace(
            "Демо-фаза.", "Демо-фаза. Оркестрация fan-out субагентов, launch-block по scriptPath.")
        p.write_text(text, encoding="utf-8")

    def _add_workflow(self, plan_dir, name="wf-demo-1-drive.js"):
        wf = plan_dir / "workflows"
        wf.mkdir(parents=True, exist_ok=True)
        (wf / name).write_text("export const meta = {\n  phases: [],\n}\n", encoding="utf-8")

    # --- позитив: фаза заявляет оркестрацию, статус 🟢, скрипта нет → warning -----
    def test_orchestration_phase_without_script_warns(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._inject_orchestration(plan_dir)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)  # warning-only, не error
        self.assertTrue(self._warnings_containing(diag, self._NEEDLE), diag.warnings)

    # --- негатив: признак есть, но скрипт в workflows/ лежит → тишина -------------
    def test_orchestration_phase_with_script_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._inject_orchestration(plan_dir)
        self._add_workflow(plan_dir)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, self._NEEDLE), [], diag.warnings)

    # --- негатив: признака оркестрации в фазе нет → тишина (ручное исполнение) ----
    def test_phase_without_orchestration_marker_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")  # green-path, без маркера
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, self._NEEDLE), [], diag.warnings)

    # --- негатив: бумерное `fan-out` в прозе (не декларация) → тишина ------------
    # регрессия на ложный warning SKM-MASTER-002/P3 (fan-out в Known Deviations про
    # токен-учёт): консервативный набор маркеров намеренно НЕ ловит одиночное слово.
    def test_bare_fanout_in_prose_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        p = plan_dir / "phases" / "P1.md"
        text = p.read_text(encoding="utf-8").replace(
            "Демо-фаза.", "Демо-фаза. Искажение метрики при fan-out субагентов — допущено.")
        p.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, self._NEEDLE), [], diag.warnings)

    # --- негатив: фаза заявляет оркестрацию, но статус ⬜ → тишина (не в exec) -----
    def test_orchestration_phase_not_started_silent(self):
        plan_dir = Path(self.root) / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True, exist_ok=True)
        (plan_dir / "plan.md").write_text(
            plan_md("DEMO-1", items_cell="0/1", phase_status="⬜ Not started"), encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(
            phase_md(item_status="⬜ Not started", completion_notes="—",
                     handoff_text="—"), encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        self._inject_orchestration(plan_dir)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, self._NEEDLE), [], diag.warnings)


class TestContractsSection(TmpPlanTestCase):
    """m7/D10 — опциональная секция `## 7. Contracts` + cross-plan сверка версий (§11)."""

    CONTRACT = "root/contracts/module-manifest.md"

    def _write_pair(self, donor_version, pinned):
        """Донор DONOR (Exported) + потребитель CONSUMER (Consumed) в одном корне plans/."""
        donor = write_valid_plan(self.root, "DONOR")
        consumer = write_valid_plan(self.root, "CONSUMER")
        (donor / "plan.md").write_text(
            plan_md("DONOR") + contracts_section(
                exported=[(self.CONTRACT, donor_version, "CONSUMER (P1.1)")]),
            encoding="utf-8")
        (consumer / "plan.md").write_text(
            plan_md("CONSUMER") + contracts_section(
                consumed=[(f"DONOR/{self.CONTRACT}", "DONOR", pinned)]),
            encoding="utf-8")
        (self.root / "plans" / "ACTIVE.md").write_text(active_md("DONOR"), encoding="utf-8")
        return self.root / "plans"

    def _lint_root(self, plans_root):
        diag = Diagnostics()
        models = {d.name: lint_plan(d, diag) for d in discover_plan_dirs(plans_root)}
        lint_plans_root(plans_root, models, diag)
        return models, diag

    def test_versions_in_sync_no_warning(self):
        models, diag = self._lint_root(self._write_pair("v2.0.2", "v2.0.2"))
        self.assertEqual(diag.errors, [])
        self.assertEqual([w for w in diag.warnings if "уведомление не разнесено" in w], [])
        self.assertEqual(models["DONOR"]["contracts"]["exported"][0]["Версия"], "v2.0.2")

    def test_version_drift_warns_once(self):
        _, diag = self._lint_root(self._write_pair("v2.0.2", "v2.0.0"))
        hits = [w for w in diag.warnings if "уведомление не разнесено" in w]
        self.assertEqual(len(hits), 1, diag.warnings)
        self.assertIn("потребитель CONSUMER запинен на v2.0.0", hits[0])
        self.assertEqual(diag.errors, [])  # только WARNING — механизм молод (D10)

    def test_no_section_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        model, diag = _lint(plan_dir)
        self.assertEqual(diag.errors, [])
        self.assertEqual(diag.warnings, [])
        self.assertEqual(model["contracts"], {"exported": [], "consumed": []})

    def test_donor_outside_root_silent(self):
        # Донор в другом репо (в этом корне его нет) — линтер честно молчит (граница §11).
        consumer = write_valid_plan(self.root, "CONSUMER")
        (consumer / "plan.md").write_text(
            plan_md("CONSUMER") + contracts_section(
                consumed=[(f"REGHUB/{self.CONTRACT}", "REGHUB", "v2.0.0")]),
            encoding="utf-8")
        (self.root / "plans" / "ACTIVE.md").write_text(active_md("CONSUMER"), encoding="utf-8")
        _, diag = self._lint_root(self.root / "plans")
        self.assertEqual(diag.errors, [])
        self.assertEqual([w for w in diag.warnings if "уведомление не разнесено" in w], [])

    def test_wrong_columns_warn_not_error(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        broken = contracts_section(
            exported=[(self.CONTRACT, "v1.0.0", "—")]).replace("| Статус |", "| State |")
        (plan_dir / "plan.md").write_text(plan_md("DEMO-1") + broken, encoding="utf-8")
        model, diag = _lint(plan_dir)
        self.assertEqual(diag.errors, [])
        self.assertTrue(any("колонки" in w for w in diag.warnings), diag.warnings)
        self.assertEqual(model["contracts"]["exported"], [])  # кривая таблица не парсится


class TestBaselineGate(TmpPlanTestCase):
    """P1.2/B1/D5/D6 — `--baseline`/`--gate`: детерминированный счёт новых ошибок K."""

    def _git(self, *args):
        subprocess.run(["git", *args], cwd=str(self.root), check=True, capture_output=True)

    def _init_repo_with_valid_plan(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._git("init", "-q")
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "Test")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "init")
        return plan_dir

    @unittest.skipUnless(shutil.which("git"), "git недоступен")
    def test_baseline_no_new_errors_on_clean_tree(self):
        plan_dir = self._init_repo_with_valid_plan()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(plan_dir), "--baseline"])
        self.assertEqual(code, 0, err.getvalue())
        self.assertIn("новых от рабочего дерева: 0", out.getvalue())

    @unittest.skipUnless(shutil.which("git"), "git недоступен")
    def test_baseline_counts_new_error_and_gate_new_fails(self):
        plan_dir = self._init_repo_with_valid_plan()
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| Plan ID | DEMO-1 |\n", "")
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(plan_dir), "--baseline", "HEAD", "--gate", "new"])
        self.assertEqual(code, 1)
        self.assertIn("новых от рабочего дерева: 1", out.getvalue())

    @unittest.skipUnless(shutil.which("git"), "git недоступен")
    def test_baseline_default_gate_stays_all_even_when_k_zero(self):
        # --gate=all (дефолт, back-compat CI) — exit по N, даже если сам baseline-дифф
        # чист (K==0), а план несёт остаточную ошибку вне диффа этого коммита.
        plan_dir = self._init_repo_with_valid_plan()
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| Plan ID | DEMO-1 |\n", "")
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "broken baseline too")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(plan_dir), "--baseline"])
        self.assertEqual(code, 1)
        self.assertIn("новых от рабочего дерева: 0", out.getvalue())

    def test_baseline_unavailable_without_git_repo(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")  # НЕТ git init
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(plan_dir), "--baseline"])
        self.assertEqual(code, 0, err.getvalue())  # exit по N (план валиден), не по K
        self.assertIn("baseline", err.getvalue())
        self.assertIn("недоступен", err.getvalue())
        self.assertNotIn("новых от рабочего дерева", out.getvalue())


class TestAuditBlockOutsidePhaseGates(TmpPlanTestCase):
    """P3.8/A4/D52 — append-only блок `## Audit Pn` ВНЕ региона грепов по фазе.
    Аудитор обязан назвать маркер, о проверке которого отчитывается («маркеров X — 0»);
    греп по всему файлу фазы ронял гейт на его собственной строке. Регион кончается на
    первом `## Audit`; тот же маркер в ТЕЛЕ item'а по-прежнему даёт WARNING."""

    def _warnings_containing(self, diag, needle):
        return [w for w in diag.warnings if needle in w]

    def _append_audit_block(self, plan_dir, body, phase="P1"):
        p = plan_dir / "phases" / f"{phase}.md"
        p.write_text(p.read_text(encoding="utf-8")
                     + f"\n## Audit {phase} — 2026-07-15\n\n**Вердикт:** 🟢 GREEN\n\n{body}\n",
                     encoding="utf-8")

    # --- A4: DoR-маркер ТОЛЬКО в блоке аудита → гейт молчит -----------------------
    def test_clarification_marker_inside_audit_block_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._append_audit_block(
            plan_dir, "- Проверено: маркеров `[NEEDS CLARIFICATION: …]` в фазе — 0.")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "NEEDS CLARIFICATION"), [], diag.warnings)

    # --- контроль: тот же маркер в ТЕЛЕ item'а → WARNING (гейт не ослаблен) -------
    def test_clarification_marker_in_item_body_still_warns(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        p1 = plan_dir / "phases" / "P1.md"
        p1.write_text(p1.read_text(encoding="utf-8").replace(
            "**Why:** Диагностика дорогая.",
            "**Why:** Диагностика дорогая. [NEEDS CLARIFICATION: какой формат?]"),
            encoding="utf-8")
        self._append_audit_block(plan_dir, "- Проверено: маркеров уточнения — 0.")
        _, diag = _lint(plan_dir)
        self.assertTrue(self._warnings_containing(diag, "NEEDS CLARIFICATION"), diag.warnings)

    # --- тот же регион у второго грепа по фазе: признак оркестрации в блоке аудита -
    def test_orchestration_marker_inside_audit_block_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._append_audit_block(
            plan_dir, "- Оркестрация фазой не заявлена: `scriptPath` в launch-block отсутствует.")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "заявляет оркестрацию"), [], diag.warnings)
