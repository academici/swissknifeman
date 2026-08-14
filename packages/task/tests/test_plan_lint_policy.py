"""Policy and forward-only gate cases for plan-lint."""
try:
    from .test_plan_lint_support import *
except ImportError:
    from test_plan_lint_support import *


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
        p1 = phase_index_path(plan_dir)
        text = p1.read_text(encoding="utf-8")
        marker = ("> СКЕЛЕТ — не детализирован, разворачивается "
                  "/task:plan-design 2026.07.16-DEMO P1\n\n")
        p1.write_text(text.replace("Демо-фаза.", "Демо-фаза.\n\n" + marker, 1),
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

    def test_dated_plan_next_table_without_command_row_or_fence_is_error(self):
        # P5.8: таблица есть (`| Model |`), но нет НИ строки `| Команда |`, НИ code-block'а —
        # ни один из двух носителей команды не назван, гейт остаётся ERROR.
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.16-DEMO")
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if "```" not in ln]
        handoff.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "Next без launch-block"), diag.errors)
        self.assertTrue(_errors_containing(diag, "Команда"), diag.errors)

    def test_dated_plan_next_command_row_without_fence_is_green(self):
        # P5.8: строка `| Команда |` в таблице параметров без отдельного code-block'а —
        # достаточный носитель, гейт зелёный (форма «команда в таблице»).
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.16-DEMO")
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        text = text.replace(
            "| Суть | закрыть следующий item |\n",
            "| Суть | закрыть следующий item |\n"
            "| Команда | `/task:plan-exec 2026.07.16-DEMO P1.1` |\n",
        )
        lines = [ln for ln in text.splitlines() if "```" not in ln
                 and not ln.startswith("/task:plan-exec")]
        handoff.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Next без launch-block"), [], diag.errors)

    def test_dated_plan_next_fence_without_command_row_is_green(self):
        # Back-compat: старая форма (только code-block, без строки `| Команда |`) остаётся
        # валидной — 26+ живых планов флота её несут (SKILL §8, аддитивность правила).
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.16-DEMO")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Next без launch-block"), [], diag.errors)

    def test_dated_plan_next_command_row_and_fence_both_present_is_green(self):
        # Оба носителя одновременно — НЕ ошибка: «ровно один из двух» = минимум один, не
        # запрет на оба сразу (решение зафиксировано этим тестом, см. plan_lint.py:2.0).
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.16-DEMO")
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        text = text.replace(
            "| Суть | закрыть следующий item |\n",
            "| Суть | закрыть следующий item |\n"
            "| Команда | `/task:plan-exec 2026.07.16-DEMO P1.1` |\n",
        )
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Next без launch-block"), [], diag.errors)

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
        write_decision_record(plan_dir, "D2", decision="historical schema exception")
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
        write_decision_record(plan_dir, "D2", decision="historical schema exception")
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
        write_decision_record(plan_dir, "D2", decision="historical schema exception")
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
        write_decision_record(plan_dir, "D2", decision="historical schema exception")
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
        write_decision_record(plan_dir, "D51", decision="owner")
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
        phase = phase_index_path(plan_dir)
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

    def test_batch_first_horizontal_launch_table_is_clean(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.16-DEMO")
        phase = phase_index_path(plan_dir)
        phase.write_text(
            phase.read_text(encoding="utf-8")
            + "\n## Audit P1 — 2026-07-17\n\n**Вердикт: RED**\n\n"
            "### Что запускать\n\n"
            "| Batch | Model | Thinking | Context | Суть | Команда |\n"
            "|:--|:--|:--|:--|:--|:--|\n"
            "| repair | frontier | high | cold-start-root | fix | `$ task:plan-run 2026.07.16-DEMO P1.1` |\n\n"
            "```text\n$ task:plan-run 2026.07.16-DEMO P1.1\n\n"
            "РЕЖИМ: bounded audit repair-forward\nВХОД: audit\nСКОУП: fix\nНЕ ТРОГАТЬ: other\n```\n",
            encoding="utf-8",
        )
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
        phase = phase_index_path(plan_dir)
        phase.write_text(phase.read_text(encoding="utf-8")
                         + "\n## Audit P1 — 2026-07-17\n\nСвободная заметка без вердикта.\n",
                         encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "launch-block неполон"), [], diag.errors)


class TestAuditTerminalPolicy(TmpPlanTestCase):
    """D24 runtime seam: audit prose cannot manufacture a repair/design successor."""

    @staticmethod
    def _terminal_decision(plan_dir):
        from task import terminal_policy
        return terminal_policy.build_decision(
            plan_dir, "P1.1", result="closed-green",
            validation=[{
                "carrier": "python3 -m unittest",
                "status": "green",
                "evidence_ids": ["unittest:green"],
            }],
        )

    def _append_block(self, plan_dir, *, verdict, semantic_next, audit_date="2026-08-14"):
        phase = phase_index_path(plan_dir)
        phase.write_text(
            phase.read_text(encoding="utf-8")
            + f"\n## Audit P1 — {audit_date}\n\n**Вердикт: {verdict}**\n\n"
            "### Что запускать\n\n"
            f"Semantic Next: `{semantic_next}`.\n",
            encoding="utf-8",
        )

    def _append_raw_event(self, plan_dir, event):
        journal_path = plan_dir / "journal.jsonl"
        with journal_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    def test_audit_red_to_plan_design_without_reducer_evidence_is_error(self):
        from task import journal
        plan = write_valid_plan(self.root, plan_id="2026.08.14-AUDIT-POLICY")
        self._append_block(
            plan, verdict="RED",
            semantic_next="design-phase: task:plan-design 2026.08.14-AUDIT-POLICY P1")
        self._append_raw_event(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1 — режим фазы", command="plan-audit",
            actor="frontier/xhigh", result="audit-red", fingerprint="a" * 64))

        _, diag = _lint(plan)

        self.assertTrue(
            _errors_containing(diag, "AUDIT_TERMINAL_EVIDENCE_REQUIRED"), diag.errors)

    def test_audit_green_requires_exact_close_successor(self):
        from task import journal
        plan = write_valid_plan(self.root, plan_id="2026.08.14-AUDIT-GREEN")
        self._append_block(
            plan, verdict="GREEN",
            semantic_next="design-phase: task:plan-design 2026.08.14-AUDIT-GREEN P1")
        self._append_raw_event(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1", command="plan-audit",
            actor="frontier/xhigh", result="audit-green", fingerprint="a" * 64))

        _, diag = _lint(plan)

        self.assertTrue(
            _errors_containing(diag, "AUDIT_TERMINAL_CONTINUATION_INVALID"), diag.errors)

    def test_audit_green_with_exact_close_successor_is_clean(self):
        from task import journal
        plan = write_valid_plan(self.root, plan_id="2026.08.14-AUDIT-CLOSE")
        self._append_block(
            plan, verdict="GREEN",
            semantic_next="close: task:plan-close 2026.08.14-AUDIT-CLOSE P1")
        self._append_raw_event(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1", command="plan-audit",
            actor="frontier/xhigh", result="audit-green", fingerprint="a" * 64))

        _, diag = _lint(plan)

        self.assertFalse(
            [error for error in diag.errors if "AUDIT_TERMINAL_" in error], diag.errors)

    def test_historical_audit_without_new_terminal_policy_is_readable(self):
        from task import journal
        plan = write_valid_plan(self.root, plan_id="2026.08.14-HISTORICAL-AUDIT")
        self._append_block(
            plan, verdict="RED",
            semantic_next="design-phase: task:plan-design 2026.08.14-HISTORICAL-AUDIT P1",
            audit_date="2026-08-13")
        self._append_raw_event(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1", command="plan-audit",
            actor="frontier/xhigh", result="audit-red", fingerprint="a" * 64,
            ts="2026-08-13T23:59:59Z"))

        _, diag = _lint(plan)

        self.assertEqual(
            _errors_containing(diag, "AUDIT_TERMINAL_EVIDENCE_REQUIRED"), [], diag.errors)
        self.assertTrue(
            [warning for warning in diag.warnings if "AUDIT_TERMINAL_EVIDENCE_REQUIRED" in warning],
            diag.warnings)

    def test_new_terminal_item_without_validation_evidence_is_error(self):
        from task import journal
        plan = write_valid_plan(self.root, plan_id="2026.08.14-TERMINAL-EVIDENCE")
        self._append_raw_event(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1.1", command="plan-run",
            actor="implementation/high", result="closed-deviations",
            ts="2026-08-14T00:00:00Z"))

        _, diag = _lint(plan)

        self.assertTrue(
            _errors_containing(diag, "TERMINAL_EVIDENCE_REQUIRED"), diag.errors)

    def test_historical_terminal_item_without_validation_evidence_is_readable(self):
        from task import journal
        plan = write_valid_plan(self.root, plan_id="2026.08.14-HISTORICAL-TERMINAL")
        self._append_raw_event(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1.1", command="plan-run",
            actor="implementation/high", result="closed-deviations",
            ts="2026-08-13T23:59:59Z"))

        _, diag = _lint(plan)

        self.assertEqual(
            _errors_containing(diag, "TERMINAL_EVIDENCE_REQUIRED"), [], diag.errors)

    def test_current_spec_requires_fresh_terminal_evidence(self):
        from task import journal
        plan = write_valid_plan(self.root, plan_id="2026.08.14-SPEC-STALE")
        self._append_raw_event(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1.1", command="plan-run",
            actor="implementation/high", result="closed-green",
            decision=self._terminal_decision(plan), ts="2026-08-14T01:00:00Z"))
        spec = item_spec_path(plan)
        spec.write_text(spec.read_text(encoding="utf-8") + "\nChanged acceptance.\n",
                        encoding="utf-8")

        _, diag = _lint(plan)

        self.assertTrue(_errors_containing(diag, "TERMINAL_SPEC_STALE"), diag.errors)

    def test_audit_repair_supersedes_old_spec_digest_without_rewriting_history(self):
        from task import journal
        plan = write_valid_plan(self.root, plan_id="2026.08.14-SPEC-REBOUND")
        self._append_raw_event(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1.1", command="plan-run",
            actor="implementation/high", result="closed-green",
            decision=self._terminal_decision(plan), ts="2026-08-14T01:00:00Z"))
        spec = item_spec_path(plan)
        spec.write_text(spec.read_text(encoding="utf-8") + "\nChanged acceptance.\n",
                        encoding="utf-8")
        self._append_raw_event(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1.1", command="plan-audit",
            actor="frontier/xhigh", result="closed-green",
            decision=self._terminal_decision(plan), ts="2026-08-14T02:00:00Z"))

        _, diag = _lint(plan)

        self.assertEqual(_errors_containing(diag, "TERMINAL_SPEC_STALE"), [], diag.errors)


class TestTieredPortability(TmpPlanTestCase):
    """P2.2/D26/D47: план с `handoff.md` (tier=committed-bundle по конструкции) обязан
    нести ≥1 committed execution input и не содержать внешний (host/chat/mAInd/tmp/foreign)
    путь В РОЛИ execution input (Inputs/Required Reads/Validation); упоминание того же пути
    ВНЕ ролевых полей (Why/Implementation Rules/…) — provenance и обязано проходить."""

    def _write(self, plan_id, *, required_reads="1) lib/pkg/config.py"):
        plan_dir = write_valid_plan(self.root, plan_id=plan_id)
        phase = item_spec_path(plan_dir)
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
        phase = item_spec_path(plan_dir)
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
        phase = item_spec_path(plan_dir)
        text = phase.read_text(encoding="utf-8")
        text = text.replace(
            "**Validation:** bash scripts/test.sh — зелёный.",
            "**Validation:** `bash scripts/test.sh >/tmp/scratch-output.txt` — зелёный.")
        phase.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "PORTABILITY_EXTERNAL_INPUT"), [], diag.errors)

    def test_dated_plan_without_any_committed_execution_input_is_error(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.27-DEMO")
        phase = item_spec_path(plan_dir)
        text = phase.read_text(encoding="utf-8")
        text = (text.replace("**Inputs:** `lib/pkg/config.py`.", "**Inputs:** ничего внешнего.")
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
        write_v2_carriers(
            plan_dir, item_state=item_state_md(
                item_status=item_status, completion_notes=completion_notes))
        journal = plan_dir / "journal.jsonl"
        entry = json.loads(journal.read_text(encoding="utf-8"))
        entry["ts"] = f"{updated}T00:00:00Z"
        journal.write_text(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n",
                           encoding="utf-8")
        from task import plan_status
        plan_status.build_status(plan_dir)
        return plan_dir

    def test_a_pre_cutoff_item_without_codes_is_silent(self):
        """(а) Updated < cutoff, без кодов → молчание (forward-only, И10)."""
        plan_dir = self._write(updated="2026-08-11")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "pre_mutation/pre_final"), [])

    def test_b_post_cutoff_item_without_codes_is_error(self):
        """(б) Updated ≥ cutoff, без кодов → ERROR."""
        plan_dir = self._write(updated="2026-08-12")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "без напечатанных кодов границ"), diag.errors)

    def test_c_post_cutoff_item_with_pre_final_na_is_error(self):
        """(в) Updated ≥ cutoff, `pre_final: n/a` → ERROR (D76: `n/a` — не зелёное).
        Фикстура конвертирована на каноническую строку `write-site:` (D102, P10.1) —
        старая свободная форма `` `pre_mutation: allow`, `pre_final: n/a` `` покраснела
        по плану после починки fail-open/ложного ERROR (гейт теперь матчит ТОЛЬКО
        каноническую строку); предмет проверки не изменился."""
        plan_dir = self._write(
            updated="2026-08-12",
            completion_notes="Сделано.\nwrite-site: pre_mutation: allow · pre_final: n/a")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "закрытие на не-allow"), diag.errors)

    def test_d_post_cutoff_item_with_both_allow_is_silent(self):
        """(г) Updated ≥ cutoff, оба `allow` → молчание. Фикстура конвертирована на
        каноническую строку `write-site:` (D102, P10.1) — см. докстринг test_c."""
        plan_dir = self._write(
            updated="2026-08-12",
            completion_notes="Сделано.\nwrite-site: pre_mutation: allow · pre_final: allow")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "pre_mutation"), [])
        self.assertEqual(_errors_containing(diag, "pre_final"), [])

    def test_e_fail_open_prose_citation_without_own_line_is_error(self):
        """(б, D88/D102): item БЕЗ своей канонической строки `write-site:`, но
        цитирующий чужие коды в прозе (разбор другого item'а) → ERROR, а не молчание.
        Fail-open дефекта: старый `re.search` по всему полю засчитывал цитату как
        собственные коды item'а."""
        plan_dir = self._write(
            updated="2026-08-12",
            completion_notes=(
                "Разбор соседнего item'а для контекста: там стояло "
                "`pre_mutation: allow`, `pre_final: allow` — у нас другая ситуация."))
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "без напечатанных кодов границ"), diag.errors)

    def test_f_own_allow_line_with_prose_block_citation_is_silent(self):
        """(в, D88/D102): item СО своей канонической строкой `write-site:` (оба
        `allow`), который выше по тексту ЦИТИРУЕТ `pre_final: block:X` чужого item'а
        (объясняя, почему тот не закрылся) → диагностик НЕТ. Ложный ERROR дефекта:
        старый `re.search` брал ПЕРВОЕ вхождение в поле — цитату, а не свою строку."""
        plan_dir = self._write(
            updated="2026-08-12",
            completion_notes=(
                "Для сравнения: соседний item был заблокирован (`pre_final: "
                "block:ACCEPTANCE_NOT_PUBLIC`). У этого item — иначе.\n"
                "write-site: pre_mutation: allow · pre_final: allow"))
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "pre_mutation"), [])
        self.assertEqual(_errors_containing(diag, "pre_final"), [])

    def test_g_markdown_wrapped_canonical_line_with_both_allow_passes(self):
        """(а, D88/D102): каноническая строка ДОПУСКАЕТ ведущую markdown-обёртку
        (буллет `- `, blockquote `> `, `**bold**` — Implementation Rules P10.1 (1)) —
        item проходит без диагностик, как и голая форма."""
        plan_dir = self._write(
            updated="2026-08-12",
            completion_notes=(
                "Готово.\n"
                "- **write-site:** `pre_mutation: allow` · `pre_final: allow`"))
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "pre_mutation"), [])
        self.assertEqual(_errors_containing(diag, "pre_final"), [])

    def test_h_own_line_pre_mutation_block_is_error(self):
        """(д, D88/D102): каноническая строка есть, но `pre_mutation:` ≠ `allow`
        (`block:*`) — ERROR по D76, симметрично test_c (там красный код был у
        `pre_final`). Различает поле, а не только «хоть один код неверный»."""
        plan_dir = self._write(
            updated="2026-08-12",
            completion_notes="write-site: pre_mutation: block:LOOP_BUDGET_EXCEEDED · pre_final: n/a")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "закрытие на не-allow"), diag.errors)

    def test_i_pre_cutoff_item_with_prose_citation_stays_silent_additivity(self):
        """(е, D88/D102): аддитивность по дате (И10) сохраняется даже когда
        Completion Notes несёт прозаическую цитату кодов — item с `Updated` < cutoff
        не диагностируется НИ ОДНОЙ новой строкой независимо от содержимого поля
        (план из трёх живых репо на 2026-07-27 не даёт ни одного item'а с
        `Updated ≥` cutoff — замер Inputs P10.1 — этот кейс синтетически
        воспроизводит «что если бы был», не текущее дерево)."""
        plan_dir = self._write(
            updated="2026-08-11",
            completion_notes=(
                "Сделано. Для контекста цитата соседнего item'а: `pre_mutation: "
                "allow`, `pre_final: block:X`."))
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "pre_mutation/pre_final"), [])
        self.assertEqual(_errors_containing(diag, "закрытие на не-allow"), [])

    def test_j_prose_quoting_the_form_template_does_not_shadow_the_real_line(self):
        """(D88/D102, найдено при закрытии самого P10.1): Completion Notes item'а
        МОЖЕТ прозой ЦИТИРОВАТЬ форму строки как шаблон (`write-site: pre_mutation:
        <код> · pre_final: <код>` — объясняя правило), и такая цитата ТОЖЕ начинается
        с префикса `write-site:` после markdown-обёртки. Она не должна «застолбить»
        поиск и скрыть настоящую каноническую строку ниже — гейт обязан продолжить
        перебор строк и найти реальную."""
        plan_dir = self._write(
            updated="2026-08-12",
            completion_notes=(
                "Форма — одна строка `write-site: pre_mutation: <код> · pre_final: "
                "<код>` (D88), это не сама сдача.\n"
                "write-site: pre_mutation: allow · pre_final: allow"))
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
        plan_dir = self._write(updated="2026-08-12", item_status="⬜ Not started",
                                completion_notes="—")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "pre_mutation/pre_final"), [])

    def test_v2_post_cutoff_item_without_codes_is_error(self):
        """Layout v2 uses journal-backed Updated instead of an inline phase table."""
        plan_dir = write_valid_plan(self.root, plan_id="2026.08.11-DEMO", layout="v2")
        journal = plan_dir / "journal.jsonl"
        event = json.loads(journal.read_text(encoding="utf-8"))
        event["ts"] = "2026-08-12T00:00:00Z"
        event["note"] = "закрыто без write-site evidence"
        journal.write_text(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n",
                           encoding="utf-8")
        from task import plan_bundle, plan_item_state, plan_status
        plan_item_state.build_states(plan_dir, item_id="P1.1")
        plan_status.build_status(plan_dir)
        plan_bundle.build(plan_dir, "P1.1")

        _, diag = _lint(plan_dir)

        self.assertTrue(_errors_containing(diag, "без напечатанных кодов границ"), diag.errors)


class TestClosureReports81(TmpPlanTestCase):
    """P8.1/D42: отчёт закрытия фазы `closure/<Pn>.json` (схема v1), включаемый opt-in
    полем `## 0. Meta` → `Closure Protocol | v1`. Пять проверок линтера + аддитивность.
    Каждый различающий кейс ниже проверен КРАСНЫМ на коде до этого item'а: `git show
    HEAD:packages/task/lib/task/plan_lint.py` не нёс ни `_lint_closure_reports_81`, ни
    вызова из `lint_plan` — старый код молчал на ВСЕХ кейсах (б)–(д), а (а)/(е) на нём
    зелены by construction (D79 — предмет теста именно РАЗЛИЧАЮЩИЙ, см. Completion Notes)."""

    def _plan(self, *, closure_protocol="v1", phase_status="🟢 Done"):
        plan_dir = write_valid_plan(self.root)
        (plan_dir / "plan.md").write_text(
            plan_md(plan_dir.name, phase_status=phase_status,
                    closure_protocol=closure_protocol),
            encoding="utf-8")
        return plan_dir

    def test_a_valid_closure_report_passes(self):
        """(а) валидный `closure/P1.json` при включённом протоколе — ни ERROR, ни WARNING."""
        plan_dir = self._plan()
        write_closure(plan_dir)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(diag.warnings, [])

    def test_b_terminal_phase_without_report_is_error_with_path(self):
        """(б) фаза терминальна, `Closure Protocol | v1` есть, файла нет → ERROR, и в тексте
        ERROR присутствует ОЖИДАЕМЫЙ путь `closure/P1.json` (fail-closed называет объект)."""
        plan_dir = self._plan()
        _, diag = _lint(plan_dir)
        hits = _errors_containing(diag, "отчёта закрытия нет")
        self.assertTrue(hits, diag.errors)
        self.assertTrue(any(str(Path("closure") / "P1.json") in e for e in hits), hits)

    def test_c_real_evidence_class_without_evidence_is_error_with_id(self):
        """(в) `evidence_class: "real"` при пустом `evidence` → ERROR с id записи."""
        plan_dir = self._plan()
        write_closure(plan_dir, evidence="")
        _, diag = _lint(plan_dir)
        hits = _errors_containing(diag, "«real» с пустым evidence")
        self.assertTrue(hits, diag.errors)
        self.assertTrue(any("P1.1" in e for e in hits), hits)

    def test_d_items_diverging_from_phase_status_is_error_with_id(self):
        """(г) `items[]` расходится с `## Phase Status`: и лишний/недостающий id, и иной
        статус — ERROR, каждый со своим id."""
        plan_dir = self._plan()
        write_closure(plan_dir, item_id="P1.9")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "«P1.9» есть в items[]"), diag.errors)
        self.assertTrue(_errors_containing(diag, "«P1.1» есть в «## Phase Status»"), diag.errors)

        plan_dir2 = write_valid_plan(self.root, plan_id="DEMO-2")
        (plan_dir2 / "plan.md").write_text(
            plan_md("DEMO-2", closure_protocol="v1"), encoding="utf-8")
        write_closure(plan_dir2, item_status="🟠 Done with deviations")
        _, diag2 = _lint(plan_dir2)
        self.assertTrue(_errors_containing(diag2, "статусу в «## Phase Status»"), diag2.errors)

    def test_e_phase_status_diverging_from_status_board_is_error(self):
        """(д) `phase_status` отчёта ≠ строке фазы в `## 4. Phase Index & Status Board`."""
        plan_dir = self._plan()
        write_closure(plan_dir, phase_status="⛔ Skipped by decision")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "≠ статусу фазы P1 в Status Board"), diag.errors)

    def test_f_additivity_plan_without_meta_field_gets_no_new_diagnostics(self):
        """(е) АДДИТИВНОСТЬ: тот же план БЕЗ Meta-поля даёт РОВНО тот же список диагностик,
        что и без каталога `closure/` вовсе (сравнение МНОЖЕСТВ, не количества) — даже когда
        на диске лежит заведомо битый отчёт. Без этого включение протокола у одного плана
        красило бы весь флот."""
        baseline_dir = write_valid_plan(self.root, plan_id="DEMO-BASE")
        _, baseline_diag = _lint(baseline_dir)
        baseline = set(baseline_diag.normalized_keys(baseline_dir))

        plan_dir = write_valid_plan(self.root, plan_id="DEMO-NOFIELD")
        (plan_dir / "closure").mkdir()
        (plan_dir / "closure" / "P1.json").write_text("{ битый json", encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(set(diag.normalized_keys(plan_dir)), baseline,
                         (diag.errors, diag.warnings))

    def test_missing_required_key_is_schema_error(self):
        """Отсутствие ключа схемы = ОШИБКА СХЕМЫ, а не «нет данных» (D42): «нет данных»
        выражается значением `baseline_pending`, а не пропуском строки."""
        plan_dir = self._plan()
        report = json.loads(closure_json(plan_dir.name))
        del report["limitations"]
        write_closure(plan_dir)
        (plan_dir / "closure" / "P1.json").write_text(
            json.dumps(report, ensure_ascii=False), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "нет обязательного ключа «limitations»"),
                        diag.errors)

    def test_evidence_class_outside_enum_is_error(self):
        """Класс свидетельства — enum РОВНО из трёх; чужой словарь классов доказательства
        (`recomputed`/`cross-checked`/…) сюда не подставляется (разные оси, реконсайл D86)."""
        plan_dir = self._plan()
        write_closure(plan_dir, evidence_class="recomputed")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "evidence_class «recomputed» вне enum"),
                        diag.errors)

    def test_unknown_meta_value_is_error(self):
        """`Closure Protocol` со значением ≠ `v1` — ERROR, а не молчаливое отключение
        (fail-open «протокол объявлен, но гейты спят» — ровно то, ради чего приём взят)."""
        plan_dir = self._plan(closure_protocol="v2")
        write_closure(plan_dir)
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "единственное легальное «v1»"), diag.errors)

    def test_non_terminal_phase_without_report_is_silent(self):
        """Нетерминальная фаза отчёта не обязана иметь — правило forward-only по СТАТУСУ
        фазы, а не «каждая фаза плана с включённым протоколом»."""
        plan_dir = self._plan(phase_status="🟡 In progress")
        write_v2_carriers(
            plan_dir, item_state=item_state_md(item_status="🟡 In progress", completion_notes="—"))
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "отчёта закрытия нет"), [])

    def test_broken_json_names_the_file(self):
        """Битый JSON при включённом протоколе — ERROR, НАЗЫВАЮЩИЙ файл и причину
        (рамка переноса: fail-closed без имени объекта запрещён, findings §8.3 #19)."""
        plan_dir = self._plan()
        (plan_dir / "closure").mkdir()
        (plan_dir / "closure" / "P1.json").write_text("{ битый json", encoding="utf-8")
        _, diag = _lint(plan_dir)
        hits = _errors_containing(diag, "не разбирается как JSON")
        self.assertTrue(hits, diag.errors)
        self.assertTrue(any("P1.json" in e for e in hits), hits)


class TestConsequencesGate82(TmpPlanTestCase):
    """P8.2/D103-D105: D-запись, чья ячейка `Решение` матчит измеренный предикат
    отмены/замены (`supersedes D`/`отменяет D`/причастие без «не» перед ним) и датирована
    (`Дата`) ≥ CONSEQUENCES_CANON_DATE, обязана нести `**Consequences:**` — иначе ERROR с
    номером D-записи. Активация — ДВОЙНОЙ opt-in: Meta `Closure Protocol | v1` И дата.
    Каждый различающий кейс проверен КРАСНЫМ на коде до этого item'а: `git show
    HEAD:packages/task/lib/task/plan_lint.py` не нёс ни `_lint_consequences_82`, ни
    CONSEQUENCES_STEMS_RE, ни вызова из `lint_plan` — старый код молчал на ВСЕХ кейсах."""

    def _plan(self, *, closure_protocol="v1", decision_log_rows):
        plan_dir = write_valid_plan(self.root)
        (plan_dir / "plan.md").write_text(
            plan_md(plan_dir.name, closure_protocol=closure_protocol,
                    decision_log_rows=decision_log_rows),
            encoding="utf-8")
        cells = [cell.strip() for cell in decision_log_rows.strip().strip("|").split("|")]
        if len(cells) >= 3:
            identifier, date, decision = cells[:3]
            has_consequences = "**Consequences:**" in decision
            decision = decision.replace("**Consequences:**", "").strip()
            path = write_decision_record(
                plan_dir, identifier, decision=decision, date=date[:10])
            if has_consequences:
                path.write_text(path.read_text(encoding="utf-8")
                                + "\n## Consequences\n\nТестовое последствие.\n",
                                encoding="utf-8")
        return plan_dir

    def test_a_supersedes_with_consequences_passes(self):
        """(a) `supersedes D30` + `**Consequences:**` → диагностик нет."""
        plan_dir = self._plan(decision_log_rows=(
            "| D40 | 2026-07-28 | supersedes D30 в части объёма. "
            "**Consequences:** старый носитель дублируется до реконсайла. | почему |"))
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Consequences"), [])

    def test_b_supersedes_without_consequences_is_error_with_id(self):
        """(б) `supersedes D30` без `Consequences` → ERROR, текст несёт номер D-записи."""
        plan_dir = self._plan(decision_log_rows=(
            "| D98 | 2026-07-28 | supersedes D30 в части объёма. | почему |"))
        _, diag = _lint(plan_dir)
        hits = _errors_containing(diag, "**Consequences:**")
        self.assertTrue(hits, diag.errors)
        self.assertTrue(any("D98" in e for e in hits), hits)

    def test_c_negated_participle_is_not_gated(self):
        """(в) «не отменена» (причастие, НО с отрицанием перед ним) → диагностик нет —
        негативный lookbehind снимает ложный ERROR (research/23 §1, D11/D19/D26-класс)."""
        plan_dir = self._plan(decision_log_rows=(
            "| D11 | 2026-07-28 | Уточняет D10 по факту сверки (не отменена, а расширена). "
            "| почему |"))
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Consequences"), [])

    def test_d_form_without_yo_is_caught(self):
        """(г) «отменена» (форма без «ё») без `Consequences` → ERROR — форма без «ё»
        ловится (D103: спека дословно её теряла)."""
        plan_dir = self._plan(decision_log_rows=(
            "| D98 | 2026-07-28 | Спека research/11 §2 отменена во всех носителях. "
            "| почему |"))
        _, diag = _lint(plan_dir)
        hits = _errors_containing(diag, "**Consequences:**")
        self.assertTrue(hits, diag.errors)
        self.assertTrue(any("D98" in e for e in hits), hits)

    def test_e_forward_only_before_cutoff_is_silent(self):
        """(д) та же запись, но `Дата` < CONSEQUENCES_CANON_DATE → диагностик нет
        (forward-only, D103: ни одна существующая запись не краснеет задним числом)."""
        plan_dir = self._plan(decision_log_rows=(
            "| D98 | 2026-07-27 | Спека research/11 §2 отменена во всех носителях. "
            "| почему |"))
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Consequences"), [])

    def test_f_unparsable_date_is_silent(self):
        """(е) непарсимая/суффиксная `Дата` (`2026-07-18 (финализирован P0.4)`, форма
        FOREMAN D7) → префиксный ISO-матч даёт «2026-07-18» < cutoff — диагностик нет."""
        plan_dir = self._plan(decision_log_rows=(
            "| D7 | 2026-07-18 (финализирован P0.4) | Спека отменена. | почему |"))
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Consequences"), [])

    def test_g_additivity_plan_without_meta_field_gets_no_new_diagnostics(self):
        """(ж) АДДИТИВНОСТЬ: тот же план БЕЗ Meta `Closure Protocol` даёт РОВНО тот же
        список диагностик, что базовый план (сравнение МНОЖЕСТВ), даже когда D-лог несёт
        заведомо гейтящуюся запись без `Consequences`."""
        baseline_dir = write_valid_plan(self.root, plan_id="DEMO-BASE")
        _, baseline_diag = _lint(baseline_dir)
        baseline = set(baseline_diag.normalized_keys(baseline_dir))

        plan_dir = self._plan(closure_protocol=None, decision_log_rows=(
            "| D98 | 2026-07-28 | Спека research/11 §2 отменена во всех носителях. "
            "| почему |"))
        _, diag = _lint(plan_dir)
        self.assertEqual(set(diag.normalized_keys(plan_dir)), baseline,
                         (diag.errors, diag.warnings))
