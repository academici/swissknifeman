"""The steps of ``orch.conductor.context`` (PLAN9 P5.4): each one without ``self``, returning data; the effects stay in
``stages/context.py``."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from orch.conductor.context import RuleCarrier, discover, rules, select, snapshot, validate

SECTIONS = ("# Rules\n\n## module-folders\n\nEvery   module\nis independent.\n\n## other\n\nskip me\n\n"
            "## orch.module-boundaries\n\nImport only orch.\n")


class RulesTests(unittest.TestCase):
    def carriers(self, *texts):
        return [RuleCarrier(Path(f"d{number}/CLAUDE.md"), text) for number, text in enumerate(texts)]

    def test_the_text_is_one_line_per_wanted_section_with_a_flat_body(self):
        block = rules.module_rules(self.carriers(SECTIONS), ["module-folders", "module-boundaries"], str)
        self.assertEqual(block["text"], "- `module-folders` (d0/CLAUDE.md): Every module is independent.\n"
                                        "- `orch.module-boundaries` (d0/CLAUDE.md): Import only orch.")
        self.assertEqual([row["name"] for row in block["included"]], ["module-folders", "orch.module-boundaries"])
        self.assertEqual(block["omitted"], [])

    def test_a_section_over_the_limit_is_listed_as_omitted_and_a_later_small_one_still_fits(self):
        text = "## big\n\n" + "x" * 3980 + "\n\n## wide\n\n" + "w" * 30 + "\n\n## last\n\nok\n"
        block = rules.module_rules(self.carriers(text), ["big", "wide", "last"], str)
        self.assertEqual([row["name"] for row in block["included"]], ["big", "last"])
        self.assertEqual([row["name"] for row in block["omitted"]], ["wide"])
        self.assertNotIn("www", block["text"])
        self.assertTrue(block["text"].endswith("`last` (d0/CLAUDE.md): ok"))

    def test_an_empty_section_is_neither_included_nor_omitted(self):
        block = rules.module_rules(self.carriers("## a\n\n## b\n\ntext\n"), ["a", "b"], str)
        self.assertEqual([row["name"] for row in block["included"]], ["b"])
        self.assertEqual(block["omitted"], [])


class DiscoverTests(unittest.TestCase):
    def test_carriers_are_listed_shallowest_first_and_stop_at_a_wildcard_or_a_climb(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "a" / "b").mkdir(parents=True)
            (project / "CLAUDE.md").write_text("root", encoding="utf-8")
            (project / "a" / "AGENTS.md").write_text("a", encoding="utf-8")
            (project / "a" / "b" / "CLAUDE.md").write_text("b", encoding="utf-8")
            (project / "a" / "b" / "AGENTS.md").write_text("ignored: CLAUDE.md wins", encoding="utf-8")
            found = discover.rule_carriers(project, ["a/b/f.py", "../x/y", "c/*/z.py"])
            self.assertEqual([path.relative_to(project).as_posix() for path in found],
                             ["CLAUDE.md", "a/AGENTS.md", "a/b/CLAUDE.md"])

    def test_the_bridge_answer_names_what_went_wrong(self):
        run = "orch.conductor.context.discover.subprocess.run"
        answer = mock.Mock(returncode=2, stdout="{}", stderr=" boom \n")
        with mock.patch(run, return_value=answer):
            self.assertEqual(discover.bridge_selection(["b"], ".", {}).failure, " exited 2: boom")
        with mock.patch(run, side_effect=OSError("no such file")):
            self.assertEqual(discover.bridge_selection(["b"], ".", {}).failure, ": OSError: no such file")
        with mock.patch(run, return_value=mock.Mock(returncode=0, stdout="not json", stderr="")):
            self.assertTrue(discover.bridge_selection(["b"], ".", {}).failure.startswith(": JSONDecodeError"))
        with mock.patch(run, side_effect=subprocess.TimeoutExpired(["b"], 120)):
            self.assertIn("TimeoutExpired", discover.bridge_selection(["b"], ".", {}).failure)
        with mock.patch(run, return_value=mock.Mock(returncode=0, stdout='{"skills": []}', stderr="")):
            self.assertEqual(discover.bridge_selection(["b"], ".", {}).chosen, {"skills": []})

    def test_an_auto_skill_must_name_an_absolute_skill_md(self):
        rows = [{"name": "a", "path": "relative/SKILL.md"}, {"name": "b", "path": "/x/other.md"}, {"name": "c"}]
        self.assertEqual([skill["reason"] for skill in discover.auto_candidates(rows)], ["outside"] * 3)


class ValidateAndSnapshotTests(unittest.TestCase):
    def skill_dir(self, tmp: str, name: str = "alpha", body: str = "---\nname: alpha\n---\nBody text.\n") -> Path:
        root = Path(tmp) / ".claude" / "skills" / name
        root.mkdir(parents=True)
        (root / "SKILL.md").write_text(body, encoding="utf-8")
        return root

    def test_a_skill_is_read_once_and_its_front_matter_is_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.skill_dir(tmp)
            found = list(validate.checked(discover.skill_candidates(Path(tmp), ["alpha"])))
            self.assertEqual([(skill["body"], skill.get("reason")) for skill in found], [("Body text.", None)])
            result = snapshot.skill_texts(found)
            self.assertEqual((result.texts, result.rejected), ({"alpha": "Body text."}, []))

    def test_names_that_break_the_pattern_or_climb_out_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            found = list(validate.checked(discover.skill_candidates(Path(tmp), ["../evil", "Bad Name", "missing"])))
            self.assertEqual([skill.get("reason") for skill in found], ["outside", "outside", None])
            self.assertIsNone(found[2]["path"])

    def test_a_symlinked_skill_file_is_refused_and_listed_as_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.skill_dir(tmp)
            outside = Path(tmp) / "elsewhere.md"
            outside.write_text("secret", encoding="utf-8")
            (root / "SKILL.md").unlink()
            (root / "SKILL.md").symlink_to(outside)
            result = snapshot.skill_texts(validate.checked(discover.skill_candidates(Path(tmp), ["alpha"])))
            self.assertEqual(result.texts, {})
            self.assertEqual([(skill["name"], skill["reason"]) for skill in result.rejected], [("alpha", "symlink")])

    def test_an_auto_skill_with_a_changed_digest_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.skill_dir(tmp) / "SKILL.md"
            row = {"name": "alpha", "id": "lib:alpha", "path": str(path.resolve()), "skill_md_sha256": "0" * 64}
            found = list(validate.checked(discover.auto_candidates([row])))
            self.assertEqual(found[0]["reason"], "digest_mismatch")
            self.assertEqual(list(validate.checked(discover.auto_candidates([dict(row, skill_md_sha256=None)])))[0]["reason"],
                             "digest_missing")

    def test_names_filter_the_candidates_to_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.skill_dir(tmp)
            self.skill_dir(tmp, "beta")
            found = list(validate.checked(discover.skill_candidates(Path(tmp), ["alpha", "beta"]), ["beta"]))
            self.assertEqual([skill["name"] for skill in found], ["beta"])

    def test_the_legacy_reader_turns_a_bad_file_into_an_oserror(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SKILL.md"
            path.write_bytes(b"\xff\xfe")
            with self.assertRaises(OSError):
                snapshot.read_body(path)

    def test_rule_files_outside_the_project_or_symlinked_are_skipped_with_a_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            outside = Path(tmp) / "CLAUDE.md"
            outside.write_text("## a\n\nx\n", encoding="utf-8")
            (project / "CLAUDE.md").symlink_to(outside)
            usable, skipped = validate.rule_texts(project, [project / "CLAUDE.md"])
            self.assertEqual(usable, [])
            self.assertEqual([(row.path.name, row.reason) for row in skipped], [("CLAUDE.md", "symlink")])


class SelectTests(unittest.TestCase):
    def test_a_conflict_of_two_kept_skills_is_returned_not_raised(self):
        rows = [{"name": "a", "id": "a", "selection": {"conflicts": ["b"]}, "tokens": None},
                {"name": "b", "id": "b", "selection": {}, "tokens": None}]
        chosen = select.select_skills(rows, tools=None, budget=1000)
        self.assertIsNotNone(chosen.conflict)

    def test_a_skill_over_the_budget_is_excluded_with_its_reason(self):
        rows = [{"name": "a", "id": "a", "selection": {}, "tokens": 10}, {"name": "b", "id": "b", "selection": {}, "tokens": 20}]
        chosen = select.select_skills(rows, tools=None, budget=15)
        self.assertEqual(chosen.names, ["a"])
        self.assertEqual([row["id"] for row in chosen.excluded], ["b"])
        self.assertEqual(set(chosen.excluded[0]), {"id", "reason"})
        self.assertIn("detail", chosen.rows[0])

    def test_a_candidate_is_weighed_only_for_an_isolated_role_with_a_file(self):
        skill = {"name": "a", "id": "a", "selection": {}, "body": "text", "path": Path("/x")}
        self.assertIsNotNone(select.candidate(skill, True)["tokens"])
        self.assertIsNone(select.candidate(skill, False)["tokens"])
        self.assertIsNone(select.candidate(dict(skill, path=None), True)["tokens"])


if __name__ == "__main__":
    unittest.main()
