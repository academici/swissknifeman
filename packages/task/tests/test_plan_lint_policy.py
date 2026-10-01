"""Policy and forward-only gate cases for plan-lint."""
try:
    from .test_plan_lint_support import *
except ImportError:
    from test_plan_lint_support import *

from task import terminal_admission


class TestTerminalAdmissionSchemaContract(TmpPlanTestCase):
    def test_runtime_contracts_match_committed_schemas(self):
        self.assertTrue(terminal_admission.validate_contracts())


class TestBriefLayer(TmpPlanTestCase):
    """Layer 0 «brief» (SKILL §16): date plan from 07/2026/16 without brief/ — ERROR,
    legacy/older - WARNING; non-empty brief/00-brief.md suppresses the check."""

    def test_dated_plan_without_brief_is_error(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.16-DEMO")
        shutil.rmtree(plan_dir / "brief")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "no layer 0"), diag.errors)

    def test_legacy_plan_without_brief_is_warning(self):
        plan_dir = write_valid_plan(self.root)
        shutil.rmtree(plan_dir / "brief")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "no layer 0"), [])
        self.assertTrue([w for w in diag.warnings if "no layer 0" in w], diag.warnings)

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
        marker = ("> SKELETON — not detailed, unfolds "
                  "/task:plan-design 2026.07.16-DEMO P1\n\n")
        p1.write_text(text.replace("Demo phase.", "Demo phase.\n\n" + marker, 1),
                      encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "roadmap.md"), [])

    def test_dated_plan_next_without_launch_block_is_error(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.16-DEMO")
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        # throw out the table launch-block'a and code-block — remains a bare line Next
        lines = [ln for ln in text.splitlines()
                 if not ln.startswith("|") and not ln.startswith("```")]
        handoff.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "Next without launch-block"), diag.errors)

    def test_dated_continue_root_next_does_not_require_a_fresh_launch_block(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.16-DEMO")
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8").replace(
            "| Context | fresh session |",
            "| Context | continue-root |",
        )
        lines = [line for line in text.splitlines()
                 if (not line.startswith("|") or line.startswith("| Context |"))
                 and not line.startswith("```")
                 and not line.startswith("/task:plan-run")]
        handoff.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Next without launch-block"), [], diag.errors)

    def test_dated_plan_next_table_without_command_row_or_fence_is_error(self):
        # P5.8: table exists (`| Model |`), but there is NO line `| Command |`, NOR code-block'a —
        # neither of the two command bearers is named, the gate remains ERROR.
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.16-DEMO")
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if "```" not in ln]
        handoff.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "Next without launch-block"), diag.errors)
        self.assertTrue(_errors_containing(diag, "Command"), diag.errors)

    def test_dated_plan_next_command_row_without_fence_is_green(self):
        # P5.8: string `| Command |` in the parameter table without a separate code-block'a —
        # sufficient carrier, gate green (form «command in the table»).
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.16-DEMO")
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        text = text.replace(
            "| The bottom line | close next item |\n",
            "| The bottom line | close next item |\n"
            "| Command | `/task:plan-run 2026.07.16-DEMO P1.1` |\n",
        )
        lines = [ln for ln in text.splitlines() if "```" not in ln
                 and not ln.startswith("/task:plan-run")]
        handoff.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Next without launch-block"), [], diag.errors)

    def test_dated_plan_next_fence_without_command_row_is_green(self):
        # Back-compat: old form (only code-block, without line `| Command |`) remains
        # valid - 26+ living plans of the fleet carry her (SKILL §8, additivity rule).
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.16-DEMO")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Next without launch-block"), [], diag.errors)

    def test_dated_plan_next_command_row_and_fence_both_present_is_green(self):
        # Both media at the same time - NOT an error: «exactly one of two» = at least one, not
        # ban on both at once (the solution is fixed by this test, see. plan_lint.py:2.0).
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.16-DEMO")
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        text = text.replace(
            "| The bottom line | close next item |\n",
            "| The bottom line | close next item |\n"
            "| Command | `/task:plan-run 2026.07.16-DEMO P1.1` |\n",
        )
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Next without launch-block"), [], diag.errors)

    def test_empty_brief_md_does_not_count(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.16-DEMO")
        (plan_dir / "brief" / "00-brief.md").write_text("", encoding="utf-8")
        (plan_dir / "brief" / "01-extra.md").unlink(missing_ok=True)
        # left only empty 00-brief.md — check should work
        for f in (plan_dir / "brief").glob("*.md"):
            if f.name != "00-brief.md":
                f.unlink()
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "no layer 0"), diag.errors)


class TestJournalIndexLayer(TmpPlanTestCase):
    """journal.jsonl/index.md: date plan from 07/2026/18 without a valid
    journal.jsonl — ERROR, older/legacy — WARNING; index.md missing - ALWAYS
    WARNING (is not a carrier of fact, unlike a journal)."""

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
        self.assertTrue(_errors_containing(diag, "not valid JSON"), diag.errors)

    def test_dated_plan_with_schema_violation_is_error(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.18-DEMO")
        (plan_dir / "journal.jsonl").write_text('{"plan_id":"x"}\n', encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "does not pass the schema"), diag.errors)

    def test_owner_gated_historical_exception_suppresses_exact_field_only(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.18-DEMO")
        decision_path = write_decision_record(
            plan_dir, "D2", decision="historical schema exception")
        journal = plan_dir / "journal.jsonl"
        entry = json.loads(journal.read_text(encoding="utf-8"))
        entry["friction"] = ["Major: historical free-form value"]
        raw = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        journal.write_text(raw + "\n", encoding="utf-8")
        decision_path.write_text(
            decision_path.read_text(encoding="utf-8").replace(
                "historical schema exception",
                "historical schema exception\n\n"
                f"[JOURNAL-EXCEPTION:{line_sha256(raw)}]\n"
                "fields=`friction`;\nplan=`2026.07.18-DEMO`;\nitem=`P1.1`"),
            encoding="utf-8")
        plan = plan_dir / "plan.md"
        plan.write_text(
            plan.read_text(encoding="utf-8").replace(
                "| D1 | 2026-07-02 | test | test |",
                "| D1 | 2026-07-02 | test | test |\n"
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
        entry["plan_id"] = "2026.07.18-DEMO-FOREIGN"
        journal.write_text(
            json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _, diag = _lint(plan_dir)
        self.assertTrue(
            _errors_containing(diag, "2026.07.18-DEMO-FOREIGN")
            and _errors_containing(diag, "2026.07.18-DEMO"),
            diag.errors,
        )

    def test_foreign_event_and_sidecar_plan_ids_cannot_exempt_mismatch(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.18-DEMO")
        write_decision_record(plan_dir, "D2", decision="historical schema exception")
        journal = plan_dir / "journal.jsonl"
        entry = json.loads(journal.read_text(encoding="utf-8"))
        entry["plan_id"] = "2026.07.18-DEMO-FOREIGN"
        entry["friction"] = ["Major: historical free-form value"]
        raw = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        journal.write_text(raw + "\n", encoding="utf-8")
        plan = plan_dir / "plan.md"
        plan.write_text(
            plan.read_text(encoding="utf-8").replace(
                "| D1 | 2026-07-02 | test | test |",
                "| D1 | 2026-07-02 | test | test |\n"
                "| D2 | 2026-07-19 | historical schema exception | owner gate |"),
            encoding="utf-8",
        )
        exception = new_exception(
            plan_id="2026.07.18-DEMO-FOREIGN", target_line=1,
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
        self.assertTrue(_errors_containing(diag, "2026.07.18-DEMO-FOREIGN"), diag.errors)
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
                "| D1 | 2026-07-02 | test | test |",
                "| D1 | 2026-07-02 | test | test |\n"
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
        self.assertTrue(_errors_containing(diag, "does not pass the schema"), diag.errors)

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
                "| D1 | 2026-07-02 | test | test |",
                "| D1 | 2026-07-02 | test | test |\n"
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
        self.assertTrue(_errors_containing(diag, "does not pass the schema"), diag.errors)

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
        decision_path = write_decision_record(plan_dir, "D51", decision="owner")
        entry = json.loads((plan_dir / "journal.jsonl").read_text(encoding="utf-8"))
        entry["friction"] = "legacy"
        raw = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        (plan_dir / "journal.jsonl").write_text(raw + "\n", encoding="utf-8")
        decision_path.write_text(
            decision_path.read_text(encoding="utf-8").replace(
                "owner", "owner\n\n"
                f"[JOURNAL-EXCEPTION:{__import__('hashlib').sha256(raw.encode()).hexdigest()}]\n"
                f"fields=`friction`;\nplan=`{plan_id}`;\nitem=`P1.1`"),
            encoding="utf-8")
        plan = (plan_dir / "plan.md").read_text(encoding="utf-8")
        (plan_dir / "plan.md").write_text(
            plan.replace("## 6. Update Log", "## 5. Decision Log\n\n| D# | Date | Solution | Why |\n|:--|:--|:--|:--|\n| D51 | 2026-07-20 | owner | test |\n\n## 6. Update Log"),
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
        self.assertEqual(_errors_containing(diag, "does not pass the schema"), [], diag.errors)

    def test_malformed_exception_never_suppresses_journal_error(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.19-DEMO")
        entry = json.loads((plan_dir / "journal.jsonl").read_text(encoding="utf-8"))
        entry["friction"] = "legacy"
        (plan_dir / "journal.jsonl").write_text(
            json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        (plan_dir / "journal-exceptions.jsonl").write_text("{bad\n", encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "journal-exceptions.jsonl"), diag.errors)
        self.assertTrue(_errors_containing(diag, "does not pass the schema"), diag.errors)

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
        self.assertTrue(_errors_containing(diag, "does not pass the schema"), diag.errors)


class TestAuditScopePayload(TmpPlanTestCase):
    """Scope-payload launch-block'and in the block `## Audit Pn` (SKILL §8, D-canon 2026-07-17).

    Causing incident: audit P0 plan issued `/task:plan-design <ID> P0`
    naked - the owner read it as «phase is being developed anew». Verdict RED/ATTENTION
    reports findings ⇒ launch-block is required to bear the MODE:/ENTRANCE:/SCORE:/DO NOT TOUCH:.
    """

    PAYLOAD = (
        "\n## Audit P1 — 2026-07-17\n\n"
        "**Verdict: {verdict}** · entry 1\n\n"
        "### Findings\n\nB1 · issue · P1.1 · `a.py:1` — broken.\n\n"
        "### What to run\n\n"
        "| Parameter | Meaning |\n|:--|:--|\n| Model | Opus |\n| Thinking | high |\n"
        "| Context | NEW SESSION — step-not-item |\n| The bottom line | Reopen |\n\n"
        "```\n/task:plan-design 2026.07.16-DEMO P1\n\n{payload}```\n"
    )
    FULL_PAYLOAD = ("MODE: reopen by §3\n"
                    "ENTRANCE: phases/P1.md → block `## Audit P1 — 2026-07-17`\n"
                    "SCORE: 1) start item under B1\n"
                    "DO NOT TOUCH: TK closed items\n")

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
        self.assertTrue(_errors_containing(diag, "launch-block incomplete"), diag.errors)

    def test_attention_without_payload_is_error(self):
        plan_dir = self._write_audit("2026.07.16-DEMO", "ATTENTION", "")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "launch-block incomplete"), diag.errors)

    def test_partial_payload_names_the_missing_line(self):
        """Gate names EXACTLY the missing line - otherwise the author is fixing it at random."""
        partial = "MODE: reopen by §3\nENTRANCE: phases/P1.md → audit block\nSCORE: 1) item\n"
        plan_dir = self._write_audit("2026.07.16-DEMO", "RED", partial)
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "DO NOT TOUCH"), diag.errors)

    def test_red_with_full_payload_is_clean(self):
        plan_dir = self._write_audit("2026.07.16-DEMO", "RED", self.FULL_PAYLOAD)
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "launch-block incomplete"), [], diag.errors)

    def test_batch_first_horizontal_launch_table_is_clean(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.16-DEMO")
        phase = phase_index_path(plan_dir)
        phase.write_text(
            phase.read_text(encoding="utf-8")
            + "\n## Audit P1 — 2026-07-17\n\n**Verdict: RED**\n\n"
            "### What to run\n\n"
            "| Batch | Model | Thinking | Context | The bottom line | Command |\n"
            "|:--|:--|:--|:--|:--|:--|\n"
            "| repair | frontier | high | cold-start-root | fix | `$ task:plan-run 2026.07.16-DEMO P1.1` |\n\n"
            "```text\n$ task:plan-run 2026.07.16-DEMO P1.1\n\n"
            "MODE: bounded audit repair-forward\nENTRANCE: audit\nSCORE: fix\nDO NOT TOUCH: other\n```\n",
            encoding="utf-8",
        )
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "launch-block incomplete"), [], diag.errors)

    def test_green_does_not_require_payload(self):
        """GREEN does not contain any finds - payload'and not required (otherwise markers = ritual)."""
        plan_dir = self._write_audit("2026.07.16-DEMO", "GREEN", "")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "launch-block incomplete"), [], diag.errors)

    def test_legacy_plan_is_warning_not_error(self):
        """Back-compat §2: plans older than canon cannot be painted retroactively."""
        plan_dir = self._write_audit("DEMO-LEGACY", "RED", "")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "launch-block incomplete"), [], diag.errors)
        self.assertTrue([w for w in diag.warnings if "launch-block incomplete" in w],
                        diag.warnings)

    def test_block_without_verdict_line_is_not_gated(self):
        """Border: `## Audit …` without a verdict line is a free note, not a report."""
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.16-DEMO")
        phase = phase_index_path(plan_dir)
        phase.write_text(phase.read_text(encoding="utf-8")
                         + "\n## Audit P1 — 2026-07-17\n\nFree note without a verdict.\n",
                         encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "launch-block incomplete"), [], diag.errors)


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
            + f"\n## Audit P1 — {audit_date}\n\n**Verdict: {verdict}**\n\n"
            "### What to run\n\n"
            f"Semantic Next: `{semantic_next}`.\n",
            encoding="utf-8",
        )

    def _append_raw_event(self, plan_dir, event):
        journal_path = plan_dir / "journal.jsonl"
        with journal_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    def test_audit_red_to_plan_design_without_reducer_evidence_is_error(self):
        from task import journal
        plan = write_valid_plan(self.root, plan_id="2026.08.14-DEMO-AUDIT-POLICY")
        self._append_block(
            plan, verdict="RED",
            semantic_next="design-phase: task:plan-design 2026.08.14-DEMO-AUDIT-POLICY P1")
        self._append_raw_event(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1 — phase mode", command="plan-audit",
            actor="frontier/xhigh", result="audit-red", fingerprint="a" * 64))

        _, diag = _lint(plan)

        self.assertTrue(
            _errors_containing(diag, "AUDIT_TERMINAL_EVIDENCE_REQUIRED"), diag.errors)

    def test_audit_green_requires_exact_close_successor(self):
        from task import journal
        plan = write_valid_plan(self.root, plan_id="2026.08.14-DEMO-AUDIT-GREEN")
        self._append_block(
            plan, verdict="GREEN",
            semantic_next="design-phase: task:plan-design 2026.08.14-DEMO-AUDIT-GREEN P1")
        self._append_raw_event(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1", command="plan-audit",
            actor="frontier/xhigh", result="audit-green", fingerprint="a" * 64))

        _, diag = _lint(plan)

        self.assertTrue(
            _errors_containing(diag, "AUDIT_TERMINAL_CONTINUATION_INVALID"), diag.errors)

    def test_audit_green_with_exact_close_successor_is_clean(self):
        from task import journal
        plan = write_valid_plan(self.root, plan_id="2026.08.14-DEMO-AUDIT-CLOSE")
        self._append_block(
            plan, verdict="GREEN",
            semantic_next="close: task:plan-close 2026.08.14-DEMO-AUDIT-CLOSE P1")
        self._append_raw_event(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1", command="plan-audit",
            actor="frontier/xhigh", result="audit-green", fingerprint="a" * 64))

        _, diag = _lint(plan)

        self.assertFalse(
            [error for error in diag.errors if "AUDIT_TERMINAL_" in error], diag.errors)

    def test_historical_audit_without_new_terminal_policy_is_readable(self):
        from task import journal
        plan = write_valid_plan(self.root, plan_id="2026.08.14-DEMO-HISTORICAL-AUDIT")
        self._append_block(
            plan, verdict="RED",
            semantic_next="design-phase: task:plan-design 2026.08.14-DEMO-HISTORICAL-AUDIT P1",
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
        plan = write_valid_plan(self.root, plan_id="2026.08.14-DEMO-TERMINAL-EVIDENCE")
        self._append_raw_event(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1.1", command="plan-run",
            actor="implementation/high", result="closed-deviations",
            ts="2026-08-14T00:00:00Z"))

        _, diag = _lint(plan)

        self.assertTrue(
            _errors_containing(diag, "TERMINAL_EVIDENCE_REQUIRED"), diag.errors)

    def test_historical_terminal_item_without_validation_evidence_is_readable(self):
        from task import journal
        plan = write_valid_plan(self.root, plan_id="2026.08.14-DEMO-HISTORICAL-TERMINAL")
        self._append_raw_event(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1.1", command="plan-run",
            actor="implementation/high", result="closed-deviations",
            ts="2026-08-13T23:59:59Z"))

        _, diag = _lint(plan)

        self.assertEqual(
            _errors_containing(diag, "TERMINAL_EVIDENCE_REQUIRED"), [], diag.errors)

    def test_current_spec_requires_fresh_terminal_evidence(self):
        from task import journal
        plan = write_valid_plan(self.root, plan_id="2026.08.14-DEMO-SPEC-STALE")
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
        plan = write_valid_plan(self.root, plan_id="2026.08.14-DEMO-SPEC-REBOUND")
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

    def test_terminal_phase_design_handoff_requires_reentry_evidence(self):
        plan = write_valid_plan(self.root, plan_id="2026.09.09-№1-DEMO-REENTRY-LINT")
        handoff = plan / "handoff.md"
        handoff.write_text(handoff.read_text(encoding="utf-8").replace(
            "/task:plan-run 2026.09.09-№1-DEMO-REENTRY-LINT P1.1",
            "/task:plan-design 2026.09.09-№1-DEMO-REENTRY-LINT P1"), encoding="utf-8")

        _, diag = _lint(plan)

        self.assertTrue(
            _errors_containing(diag, "PHASE_REENTRY_UNJUSTIFIED"), diag.errors)


class TestTieredPortability(TmpPlanTestCase):
    """P2.2/D26/D47: plan with `handoff.md` (tier=committed-bundle by design) obliged
    carry ≥1 committed execution input and do not contain external (host/chat/mAInd/tmp/foreign)
    path IN ROLE execution input (Inputs/Required Reads/Validation); mention of the same path
    OUTSIDE role fields (Why/Implementation Rules/…) — provenance and must pass."""

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
        """Back-compat §2: plans older than canon cannot be painted retroactively."""
        plan_dir = self._write("DEMO-LEGACY", required_reads="1) tmp/scratch-notes.md")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "PORTABILITY_EXTERNAL_INPUT"), [], diag.errors)
        self.assertTrue([w for w in diag.warnings if "PORTABILITY_EXTERNAL_INPUT" in w],
                        diag.warnings)

    def test_tmp_mention_outside_role_fields_is_provenance_and_passes(self):
        """D47: `tmp/`-mentioned in Why/Implementation Rules (not Inputs/Required
        Reads/Validation) — provenance, not execution input; same discipline as
        pins self-conformance fixture of this plan on `brief/00-brief.md`."""
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.27-DEMO")
        phase = item_spec_path(plan_dir)
        text = phase.read_text(encoding="utf-8")
        text = text.replace(
            "**Why:** Diagnostics are expensive.",
            "**Why:** Diagnostics are expensive; see user-owned `tmp/scratch-notes.md` "
            "like provenance.")
        phase.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "PORTABILITY"), [])
        self.assertEqual([w for w in diag.warnings if "PORTABILITY" in w], [])

    def test_shell_redirect_target_in_validation_is_not_an_execution_input(self):
        """Scratch redirect (`> file`) in the field Validation — diagnostic record target
        own team item'ah, no execution input (P4.2-incident on this very
        plan to fix regex'a)."""
        plan_dir = self._write(
            "2026.07.27-DEMO",
            required_reads="1) lib/pkg/config.py",
        )
        phase = item_spec_path(plan_dir)
        text = phase.read_text(encoding="utf-8")
        text = text.replace(
            "**Validation:** bash scripts/test.sh — green.",
            "**Validation:** `bash scripts/test.sh >/tmp/scratch-output.txt` — green.")
        phase.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "PORTABILITY_EXTERNAL_INPUT"), [], diag.errors)

    def test_dated_plan_without_any_committed_execution_input_is_error(self):
        plan_dir = write_valid_plan(self.root, plan_id="2026.07.27-DEMO")
        phase = item_spec_path(plan_dir)
        text = phase.read_text(encoding="utf-8")
        text = (text.replace("**Inputs:** `lib/pkg/config.py`.", "**Inputs:** nothing external.")
                    .replace("**Required Reads:** 1) lib/pkg/config.py",
                             "**Required Reads:** read owner context.")
                    .replace("**Validation:** bash scripts/test.sh — green.",
                             "**Validation:** check by hand."))
        phase.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "PORTABILITY_INPUT_MISSING"), diag.errors)


class TestWriteSiteCodesGate(TmpPlanTestCase):
    """P4.4/D91 (repair of find F2): item with
    status 🟢/🟠, whose `Updated` (Phase Status) ≥ cutoff, is required to carry both codes
    `pre_mutation:`/`pre_final:` with value `allow` in Completion Notes; item BEFORE cutoff'a
    is not diagnosed at all (forward-only, D91). Each distinguishing case (b)/(c) below
    checked RED on the code before item'a (`git show HEAD:packages/task/lib/task/
    plan_lint.py` did not carry any `_lint_write_site_codes_44`, no call from `lint_plan` —
    the old code was silent on BOTH cases; see Completion Notes P4.4 for an exact run, D79)."""

    def _write(self, *, updated, item_status="🟢 Done",
               completion_notes="done, test green"):
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
        """(a) Updated < cutoff, without codes → silence (forward-only)."""
        plan_dir = self._write(updated="2026-08-11")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "pre_mutation/pre_final"), [])

    def test_b_post_cutoff_item_without_codes_is_error(self):
        """(b) Updated ≥ cutoff, without codes → ERROR."""
        plan_dir = self._write(updated="2026-08-12")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "without printed boundary codes"), diag.errors)

    def test_c_post_cutoff_item_with_pre_final_na_is_error(self):
        """(in) Updated ≥ cutoff, `pre_final: n/a` → ERROR (D76: `n/a` — not green).
        Fixture converted to canonical string `write-site:` —
        old free form `` `pre_mutation: allow`, `pre_final: n/a` `` blushed
        according to plan after repair fail-open/false ERROR (gate now matches ONLY
        canonical string); the subject of the test has not changed."""
        plan_dir = self._write(
            updated="2026-08-12",
            completion_notes="Done.\nwrite-site: pre_mutation: allow · pre_final: n/a")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "closing on non-allow"), diag.errors)

    def test_d_post_cutoff_item_with_both_allow_is_silent(self):
        """(g) Updated ≥ cutoff, both `allow` → silence. The fixture has been converted to
        canonical string `write-site:` — see docstring test_c."""
        plan_dir = self._write(
            updated="2026-08-12",
            completion_notes="Done.\nwrite-site: pre_mutation: allow · pre_final: allow")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "pre_mutation"), [])
        self.assertEqual(_errors_containing(diag, "pre_final"), [])

    def test_e_fail_open_prose_citation_without_own_line_is_error(self):
        """(b, D88/D102): item WITHOUT its canonical line `write-site:`, but
        quoting other people's codes in prose (parsing another item'a) → ERROR, and not silence.
        Fail-open defect: old `re.search` throughout the field counted the quote as
        own codes item'a."""
        plan_dir = self._write(
            updated="2026-08-12",
            completion_notes=(
                "Parsing adjacent item'and for context: there stood "
                "`pre_mutation: allow`, `pre_final: allow` — we have a different situation."))
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "without printed boundary codes"), diag.errors)

    def test_f_own_allow_line_with_prose_block_citation_is_silent(self):
        """(in, D88/D102): item WITH its canonical string `write-site:` (both
        `allow`), which is quoted above in the text `pre_final: block:X` alien item'a
        (explaining why it didn't close) → NO diagnostics. False ERROR defect:
        old `re.search` took the FIRST occurrence of the field - a quote, not its own string."""
        plan_dir = self._write(
            updated="2026-08-12",
            completion_notes=(
                "For comparison: neighboring item has been blocked (`pre_final: "
                "block:ACCEPTANCE_NOT_PUBLIC`). This one item — otherwise.\n"
                "write-site: pre_mutation: allow · pre_final: allow"))
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "pre_mutation"), [])
        self.assertEqual(_errors_containing(diag, "pre_final"), [])

    def test_g_markdown_wrapped_canonical_line_with_both_allow_passes(self):
        """(ah, D88/D102): canonical string ALLOWS leading markdown-wrapper
        (bulletin `- `, blockquote `> `, `**bold**` — Implementation Rules P10.1 (1)) —
        item passes without diagnostics, just like the naked form."""
        plan_dir = self._write(
            updated="2026-08-12",
            completion_notes=(
                "Done.\n"
                "- **write-site:** `pre_mutation: allow` · `pre_final: allow`"))
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "pre_mutation"), [])
        self.assertEqual(_errors_containing(diag, "pre_final"), [])

    def test_h_own_line_pre_mutation_block_is_error(self):
        """(d, D88/D102): there is a canonical line, but `pre_mutation:` ≠ `allow`
        (`block:*`) — ERROR by D76, symmetrical test_c (there was a red code
        `pre_final`). Distinguishes the field, not just «at least one code is incorrect»."""
        plan_dir = self._write(
            updated="2026-08-12",
            completion_notes="write-site: pre_mutation: block:LOOP_BUDGET_EXCEEDED · pre_final: n/a")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "closing on non-allow"), diag.errors)

    def test_i_pre_cutoff_item_with_prose_citation_stays_silent_additivity(self):
        """(e): date-based additivity is retained even when
        Completion Notes carries a prosaic quotation of codes - item with `Updated` < cutoff
        is not diagnosed by ANY new line, regardless of the contents of the field
        (plan of three live repos for 2026-07-27 does not give any item'a
        `Updated ≥` cutoff — froze Inputs P10.1 — this case is synthetic
        plays «what if there was», not current tree)."""
        plan_dir = self._write(
            updated="2026-08-11",
            completion_notes=(
                "Done. For context, a quote from the neighbor item'a: `pre_mutation: "
                "allow`, `pre_final: block:X`."))
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "pre_mutation/pre_final"), [])
        self.assertEqual(_errors_containing(diag, "closing on non-allow"), [])

    def test_j_prose_quoting_the_form_template_does_not_shadow_the_real_line(self):
        """(D88/D102, found when closing itself P10.1): Completion Notes item'a
        CAN prose QUOTE the line form as a pattern (`write-site: pre_mutation:
        <code> · pre_final: <code>` — explaining the rule), and this quote ALSO begins
        from prefix `write-site:` after markdown-wrappers. She shouldn't «stake out»
        search and hide the real canonical line below - the gate must continue
        iterate over strings and find the real one."""
        plan_dir = self._write(
            updated="2026-08-12",
            completion_notes=(
                "Form - one line `write-site: pre_mutation: <code> · pre_final: "
                "<code>` (D88), is not the change itself.\n"
                "write-site: pre_mutation: allow · pre_final: allow"))
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "pre_mutation"), [])
        self.assertEqual(_errors_containing(diag, "pre_final"), [])

    def test_malformed_updated_date_is_out_of_scope_not_error(self):
        """Unparsimable/loose date (not ISO `YYYY-MM-DD`) = outside the scope - fail-open by date
        (Implementation Rules P4.4 (1)), not ERROR/WARNING."""
        plan_dir = self._write(updated="2026.07.27")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "pre_mutation/pre_final"), [])

    def test_not_done_status_is_never_gated(self):
        """Status out `🟢`/`🟠` (e.g. `⬜ Not started`) — rule does not apply, no matter how
        was not Updated."""
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
        event["note"] = "closed without write-site evidence"
        journal.write_text(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n",
                           encoding="utf-8")
        from task import plan_bundle, plan_item_state, plan_status
        plan_item_state.build_states(plan_dir, item_id="P1.1")
        plan_status.build_status(plan_dir)
        plan_bundle.build(plan_dir, "P1.1")

        _, diag = _lint(plan_dir)

        self.assertTrue(_errors_containing(diag, "without printed boundary codes"), diag.errors)


class TestClosureReports81(TmpPlanTestCase):
    """P8.1/D42: phase closing report `closure/<Pn>.json` (diagram v1), included opt-in
    field `## 0. Meta` → `Closure Protocol | v1`. Five linter checks + additivity.
    Each distinguishing case below is tested by RED on the code before item'a: `git show
    HEAD:packages/task/lib/task/plan_lint.py` did not carry any `_lint_closure_reports_81`, neither
    call from `lint_plan` — the old code was silent on ALL cases (b)–(d), a (a)/(e) on it
    green by construction (D79 — the subject of the test is DISCITING, see. Completion Notes)."""

    def _plan(self, *, closure_protocol="v1", phase_status="🟢 Done"):
        plan_dir = write_valid_plan(self.root)
        (plan_dir / "plan.md").write_text(
            plan_md(plan_dir.name, phase_status=phase_status,
                    closure_protocol=closure_protocol),
            encoding="utf-8")
        return plan_dir

    def test_a_valid_closure_report_passes(self):
        """(a) valid `closure/P1.json` when the protocol is enabled - neither ERROR, neither WARNING."""
        plan_dir = self._plan()
        write_closure(plan_dir)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(diag.warnings, [])

    def test_b_terminal_phase_without_report_is_error_with_path(self):
        """(b) phase is terminal, `Closure Protocol | v1` yes, no file → ERROR, and in the text
        ERROR EXPECTED path present `closure/P1.json` (fail-closed names an object)."""
        plan_dir = self._plan()
        _, diag = _lint(plan_dir)
        hits = _errors_containing(diag, "no closing report")
        self.assertTrue(hits, diag.errors)
        self.assertTrue(any(str(Path("closure") / "P1.json") in e for e in hits), hits)

    def test_c_real_evidence_class_without_evidence_is_error_with_id(self):
        """(in) `evidence_class: "real"` when empty `evidence` → ERROR with id records."""
        plan_dir = self._plan()
        write_closure(plan_dir, evidence="")
        _, diag = _lint(plan_dir)
        hits = _errors_containing(diag, "«real» with empty evidence")
        self.assertTrue(hits, diag.errors)
        self.assertTrue(any("P1.1" in e for e in hits), hits)

    def test_d_items_diverging_from_phase_status_is_error_with_id(self):
        """(g) `items[]` diverges from `## Phase Status`: and extra/missing id, and others
        status - ERROR, each with his own id."""
        plan_dir = self._plan()
        write_closure(plan_dir, item_id="P1.9")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "«P1.9» is in items[]"), diag.errors)
        self.assertTrue(_errors_containing(diag, "«P1.1» is in «## Phase Status»"), diag.errors)

        plan_dir2 = write_valid_plan(self.root, plan_id="DEMO-2")
        (plan_dir2 / "plan.md").write_text(
            plan_md("DEMO-2", closure_protocol="v1"), encoding="utf-8")
        write_closure(plan_dir2, item_status="🟠 Done with deviations")
        _, diag2 = _lint(plan_dir2)
        self.assertTrue(_errors_containing(diag2, "status in «## Phase Status»"), diag2.errors)

    def test_e_phase_status_diverging_from_status_board_is_error(self):
        """(d) `phase_status` report ≠ phase line in `## 4. Phase Index & Status Board`."""
        plan_dir = self._plan()
        write_closure(plan_dir, phase_status="⛔ Skipped by decision")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "≠ phase status P1 in Status Board"), diag.errors)

    def test_f_additivity_plan_without_meta_field_gets_no_new_diagnostics(self):
        """(e) ADDITIVITY: same plan WITHOUT Meta-fields gives EXACTLY the same list of diagnostics,
        as without the catalog `closure/` at all (comparison of SETs, not quantities) — even when
        there is a obviously broken report on the disk. Without this, enabling the protocol for one plan
        would paint the entire fleet."""
        baseline_dir = write_valid_plan(self.root, plan_id="DEMO-BASE")
        _, baseline_diag = _lint(baseline_dir)
        baseline = set(baseline_diag.normalized_keys(baseline_dir))

        plan_dir = write_valid_plan(self.root, plan_id="DEMO-NOFIELD")
        (plan_dir / "closure").mkdir()
        (plan_dir / "closure" / "P1.json").write_text("{ broken json", encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(set(diag.normalized_keys(plan_dir)), baseline,
                         (diag.errors, diag.warnings))

    def test_missing_required_key_is_schema_error(self):
        """Missing schema key = SCHEMA ERROR, not «no data»: «no data»
        is expressed by the value `baseline_pending`, rather than line skipping."""
        plan_dir = self._plan()
        report = json.loads(closure_json(plan_dir.name))
        del report["limitations"]
        write_closure(plan_dir)
        (plan_dir / "closure" / "P1.json").write_text(
            json.dumps(report, ensure_ascii=False), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "no required key «limitations»"),
                        diag.errors)

    def test_evidence_class_outside_enum_is_error(self):
        """Certificate class - enum EXACTLY out of three; alien proof class dictionary
        (`recomputed`/`cross-checked`/…) is not inserted here (different axes, reconsider D86)."""
        plan_dir = self._plan()
        write_closure(plan_dir, evidence_class="recomputed")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "evidence_class «recomputed» out enum"),
                        diag.errors)

    def test_unknown_meta_value_is_error(self):
        """`Closure Protocol` with value ≠ `v1` — ERROR, rather than silent shutdown
        (fail-open «protocol declared, but gates are sleeping» — exactly what the technique was taken for)."""
        plan_dir = self._plan(closure_protocol="v2")
        write_closure(plan_dir)
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "the only legal one is «v1»"), diag.errors)

    def test_non_terminal_phase_without_report_is_silent(self):
        """The non-terminal phase of the report is not required to have - rule forward-only by STATUS
        phases, not «each phase of the plan with protocol enabled»."""
        plan_dir = self._plan(phase_status="🟡 In progress")
        write_v2_carriers(
            plan_dir, item_state=item_state_md(item_status="🟡 In progress", completion_notes="—"))
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "no closing report"), [])

    def test_broken_json_names_the_file(self):
        """Broken JSON when the protocol is enabled - ERROR, NAMED file and reason
        (transfer frame: fail-closed without an object name is prohibited, findings §8.3 #19)."""
        plan_dir = self._plan()
        (plan_dir / "closure").mkdir()
        (plan_dir / "closure" / "P1.json").write_text("{ broken json", encoding="utf-8")
        _, diag = _lint(plan_dir)
        hits = _errors_containing(diag, "invalid JSON")
        self.assertTrue(hits, diag.errors)
        self.assertTrue(any("P1.json" in e for e in hits), hits)


class TestConsequencesGate82(TmpPlanTestCase):
    """P8.2/D103-D105: D-record whose cell `Solution` match measured predicate
    cancel/replacements (`supersedes D`/`cancels D`/participle without «not» in front of him) and dated
    (`Date`) ≥ CONSEQUENCES_CANON_DATE, is required to bear `**Consequences:**` — otherwise ERROR with
    number D-entries. Activation - DOUBLE opt-in: Meta `Closure Protocol | v1` And the date.
    Each distinguishing case is checked by RED on the code before item'a: `git show
    HEAD:packages/task/lib/task/plan_lint.py` did not carry any `_lint_consequences_82`, neither
    CONSEQUENCES_STEMS_RE, no call from `lint_plan` — the old code was silent on ALL cases."""

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
                                + "\n## Consequences\n\nTest consequence.\n",
                                encoding="utf-8")
        return plan_dir

    def test_a_supersedes_with_consequences_passes(self):
        """(a) `supersedes D30` + `**Consequences:**` → no diagnostics."""
        plan_dir = self._plan(decision_log_rows=(
            "| D40 | 2026-07-28 | supersedes D30 in terms of volume. "
            "**Consequences:** old media is duplicated before reconsolidation. | why |"))
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Consequences"), [])

    def test_b_supersedes_without_consequences_is_error_with_id(self):
        """(b) `supersedes D30` without `Consequences` → ERROR, text carries a number D-records."""
        plan_dir = self._plan(decision_log_rows=(
            "| D98 | 2026-07-28 | supersedes D30 in terms of volume. | why |"))
        _, diag = _lint(plan_dir)
        hits = _errors_containing(diag, "**Consequences:**")
        self.assertTrue(hits, diag.errors)
        self.assertTrue(any("D98" in e for e in hits), hits)

    def test_c_negated_participle_is_not_gated(self):
        """(in) «not canceled» (participle, BUT with a negation in front of it) → no diagnostics -
        negative lookbehind clears false ERROR (research/23 §1, D11/D19/D26-class)."""
        plan_dir = self._plan(decision_log_rows=(
            "| D11 | 2026-07-28 | Clarifies D10 upon reconciliation (is not cancelled, but expanded). "
            "| why |"))
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Consequences"), [])

    def test_d_form_without_yo_is_caught(self):
        """(g) The alternate spelling of `cancelled` without `Consequences` → ERROR.
        is caught (D103: specka literally lost it)."""
        plan_dir = self._plan(decision_log_rows=(
            "| D98 | 2026-07-28 | Speck research/11 §2 has been canceled in all media. "
            "| why |"))
        _, diag = _lint(plan_dir)
        hits = _errors_containing(diag, "**Consequences:**")
        self.assertTrue(hits, diag.errors)
        self.assertTrue(any("D98" in e for e in hits), hits)

    def test_e_forward_only_before_cutoff_is_silent(self):
        """(d) same entry, but `Date` < CONSEQUENCES_CANON_DATE → no diagnostics
        (forward-only, D103: no existing entry blushes in retrospect)."""
        plan_dir = self._plan(decision_log_rows=(
            "| D98 | 2026-07-27 | Speck research/11 §2 has been canceled in all media. "
            "| why |"))
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Consequences"), [])

    def test_f_unparsable_date_is_silent(self):
        """(e) unparsable/suffix `Date` (`2026-07-18 (finalized The P0.4)`, form
        FOREMAN D7) → prefix ISO-match gives «2026-07-18» < cutoff — no diagnostics."""
        plan_dir = self._plan(decision_log_rows=(
            "| D7 | 2026-07-18 (finalized The P0.4) | Spec has been cancelled. | why |"))
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Consequences"), [])

    def test_g_additivity_plan_without_meta_field_gets_no_new_diagnostics(self):
        """(w) ADDITIVITY: same plan WITHOUT Meta `Closure Protocol` gives EXACTLY the same
        list of diagnostics that the baseline (SET comparison), even when D-log carries
        obviously gated record without `Consequences`."""
        baseline_dir = write_valid_plan(self.root, plan_id="DEMO-BASE")
        _, baseline_diag = _lint(baseline_dir)
        baseline = set(baseline_diag.normalized_keys(baseline_dir))

        plan_dir = self._plan(closure_protocol=None, decision_log_rows=(
            "| D98 | 2026-07-28 | Speck research/11 §2 has been canceled in all media. "
            "| why |"))
        _, diag = _lint(plan_dir)
        self.assertEqual(set(diag.normalized_keys(plan_dir)), baseline,
                         (diag.errors, diag.warnings))
