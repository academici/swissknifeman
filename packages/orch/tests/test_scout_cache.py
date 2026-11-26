"""The cache of the scout map: keyed by what the map depends on (the content of the input, not the writes of the plan
journal that move ``provenance`` and ``digest``), written whole or not at all, and used only when the file is a
non-empty UTF-8 text."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from orch.conductor.domain.stop import Stop
from orch.conductor.stages import scout as scout_stage


class OptionalScoutPolicyTest(unittest.TestCase):
    def test_optional_scout_can_be_disabled_but_required_scout_cannot(self):
        stage = {"role": "context-scout"}
        self.assertEqual(scout_stage.stage(None, SimpleNamespace(policy={"stages": [stage]}, options={})), stage)
        self.assertIsNone(scout_stage.stage(None, SimpleNamespace(policy={"stages": [stage]}, options={"scout_enabled": False})))
        with self.assertRaises(Stop) as error:
            scout_stage.stage(None, SimpleNamespace(policy={"stages": [dict(stage, required=True)]}, options={"scout_enabled": False}))
        self.assertEqual(error.exception.code, "SCOUT_REQUIRED")

from orch.conductor import engine
from orch.conductor.stages import scout
from tests.test_conductor import GREEN, INPUT, ConductorCase, executor_ok

ROUTE = {"provider": "claude-code", "model": "haiku", "effort": "low"}


def owner(skill_files=(), names=(), stub=("stub", "")) -> SimpleNamespace:
    return SimpleNamespace(roles_dir=None, _skills=lambda item, role: list(names),
                           _skill_files=lambda item, role: list(skill_files), _skill_body=lambda path: Path(path).read_text(),
                           _stub=lambda role, route: stub)


def item_of(**fields) -> SimpleNamespace:
    doc = json.loads(INPUT.read_text(encoding="utf-8"))
    doc.update(fields)
    return SimpleNamespace(input_doc=doc)


class CacheKeyTests(unittest.TestCase):
    def key(self, who=None, item=None, route=None) -> str:
        return scout.cache_key(who or owner(), item or item_of(), route or ROUTE)

    def test_the_writes_of_the_plan_journal_do_not_change_the_key(self):
        before = item_of()
        after = item_of()
        after.input_doc["provenance"] = dict(after.input_doc["provenance"], source_digest="f" * 64)
        after.input_doc["digest"] = "a" * 64
        after.input_doc["input_id"] = after.input_doc["input_id"].rsplit("@", 1)[0] + "@" + "a" * 12
        self.assertNotEqual(before.input_doc["provenance"], after.input_doc["provenance"])
        self.assertEqual(self.key(item=before), self.key(item=after))

    def test_what_the_map_depends_on_changes_the_key(self):
        base = self.key()
        self.assertNotEqual(base, self.key(item=item_of(goal="another goal")))
        self.assertNotEqual(base, self.key(item=item_of(scope={"include": ["other"]})))
        self.assertNotEqual(base, self.key(route=dict(ROUTE, model="other")))
        self.assertNotEqual(base, self.key(route=dict(ROUTE, effort="high")))
        self.assertNotEqual(base, self.key(who=owner(stub=("stub:x", "## Extra\n\nrules"))))

    def test_a_lesson_timestamp_does_not_change_the_key_and_its_text_does(self):
        lesson = {"type": "friction", "summary": "read the fixture", "ts": "2026-10-22T00:00:00Z"}
        base = self.key(item=item_of(lessons=[lesson]))
        moved = dict(lesson, ts="2026-10-22T01:00:00Z")
        self.assertEqual(base, self.key(item=item_of(lessons=[moved])))
        self.assertNotEqual(base, self.key(item=item_of(lessons=[dict(lesson, summary="read the other fixture")])))

    def test_the_text_of_a_selected_skill_changes_the_key(self):
        with __import__("tempfile").TemporaryDirectory() as tmp:
            path = Path(tmp) / "SKILL.md"
            path.write_text("use the map", encoding="utf-8")
            who = owner(skill_files=[("demo", "demo", path)], names=["demo"])
            first = self.key(who=who)
            self.assertEqual(first, self.key(who=who))
            path.write_text("use the other map", encoding="utf-8")
            self.assertNotEqual(first, self.key(who=who))
            self.assertNotEqual(self.key(), first)  # the skill itself counts
            other = owner(skill_files=[("demo", "demo", path)], names=[])  # a skill that is not selected does not
            self.assertEqual(self.key(who=other), self.key())

    def test_a_skill_file_that_cannot_be_read_gives_a_key_of_its_own(self):
        who = owner(skill_files=[("demo", "demo", Path("/nonexistent/SKILL.md"))], names=["demo"])
        self.assertNotEqual(self.key(who=who), self.key())


class CachedTests(unittest.TestCase):
    def test_only_a_regular_non_empty_utf8_file_is_a_hit(self):
        with __import__("tempfile").TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.assertIsNone(scout.cached(base / "missing.txt"))
            (base / "empty.txt").write_bytes(b"")
            self.assertIsNone(scout.cached(base / "empty.txt"))
            (base / "blank.txt").write_text("  \n", encoding="utf-8")
            self.assertIsNone(scout.cached(base / "blank.txt"))
            (base / "binary.txt").write_bytes(b"\xff\xfe\x00map")
            self.assertIsNone(scout.cached(base / "binary.txt"))
            (base / "folder.txt").mkdir()
            self.assertIsNone(scout.cached(base / "folder.txt"))
            (base / "link.txt").symlink_to(base / "good.txt")
            (base / "good.txt").write_text("a map\n", encoding="utf-8")
            self.assertIsNone(scout.cached(base / "link.txt"))
            self.assertEqual(scout.cached(base / "good.txt"), "a map\n")


class ScoutCacheRunTests(ConductorCase):
    def test_explicit_prose_opt_in_accepts_complete_green_without_retry(self):
        options = self.project.parent / "no-scout-prose.json"
        options.write_text(json.dumps({"scout_enabled": False}), encoding="utf-8")
        body = ("### Findings\n\nNone.\n\n### Questions\n\nNone.\n\n"
                "### Verdict\n\n**GREEN** — Checks reviewed.\n\n"
                "### Material Residual Risk\n\n- A race remains.\n")
        self.script({"executor": [executor_ok("W1")], "reviewer": [{"text": body}]})
        with mock.patch.dict("os.environ", {"SKM_ORCH_ACCEPT_PROSE_REVIEW": "1"}):
            code, _, err = self.run_items("W1", extra=("--options", options))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("reviewer"), 1)
        receipt = self.state(err)["items"]["W1"]["steps"]["review.1"]["result"]["findings"]
        self.assertIn("A race remains.", receipt["residual_risk"])

    def test_prose_opt_in_does_not_accept_a_finding_as_green(self):
        options = self.project.parent / "no-scout-prose-negative.json"
        options.write_text(json.dumps({"scout_enabled": False, "limits": {"repairs": 0, "retries": 0}}), encoding="utf-8")
        body = ("### Findings\n\nA real defect.\n\n### Questions\n\nNone.\n\n"
                "### Verdict\n\n**GREEN**\n\n### Material Residual Risk\n\n- A race remains.\n")
        self.script({"executor": [executor_ok("W1")], "reviewer": [{"text": body}]})
        with mock.patch.dict("os.environ", {"SKM_ORCH_ACCEPT_PROSE_REVIEW": "1"}):
            code, _, err = self.run_items("W1", extra=("--options", options))
        self.assertNotEqual(code, 0, err)
        self.assertNotEqual(self.outcome(err), ("finished", None))

    def test_explicit_fast_path_skips_scout_but_keeps_independent_review(self):
        options = self.project.parent / "no-scout.json"
        options.write_text(json.dumps({"scout_enabled": False}), encoding="utf-8")
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=("--options", options))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("context-scout"), 0)
        self.assertEqual(self.calls("reviewer"), 1)

    def cache_files(self) -> list:
        return sorted((engine.runs_root(self.project) / "cache" / "scout" / "W1").glob("*"))

    def again(self, **env) -> tuple:
        """The same piece again, as after a resume of the plan: the work of the first run undone."""
        self.set_items({"W1": {}})
        self.git("reset", "-q", "--hard", "HEAD~1")
        with mock.patch.dict("os.environ", env):
            return self.run_items("W1")

    def first(self) -> str:
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("context-scout"), 1)
        return err

    def verdict(self, err: str) -> str:
        return [line for line in self.lines(err) if line.get("stage") == "scout" and line["event"] == "stage.end"][0]["verdict"]

    def test_a_changed_provenance_of_the_input_is_still_a_hit(self):
        self.first()
        moved = json.loads(INPUT.read_text(encoding="utf-8"))
        moved["provenance"]["source_digest"] = "1" * 64  # the plan journal got a write: the brief is rebuilt
        path = self.project.parent / "moved-input.json"
        path.write_text(json.dumps(moved), encoding="utf-8")
        code, _, err = self.again(FAKE_CS_INPUT=str(path))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.calls("context-scout"), 1)  # not asked again
        self.assertEqual(self.verdict(err), "cache")

    def test_a_changed_goal_is_a_miss(self):
        self.first()
        self.set_items({"W1": {"goal": "Create something else."}})
        self.git("reset", "-q", "--hard", "HEAD~1")
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.calls("context-scout"), 2)
        self.assertEqual(self.verdict(err), "mapped")

    def test_a_changed_text_of_a_selected_skill_is_a_miss(self):
        skill = self.project / ".claude" / "skills" / "demo" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("---\nname: demo\n---\n\nmap the files\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "skill")
        options = self.project.parent / "skills.json"
        options.write_text(json.dumps({"skills": [{"role": "context-scout", "names": ["demo"]}]}), encoding="utf-8")
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=("--options", options))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.calls("context-scout"), 1)
        self.set_items({"W1": {}})
        self.git("reset", "-q", "--hard", "HEAD~1")
        self.assertEqual(self.run_items("W1", extra=("--options", options))[0], 0)
        self.assertEqual(self.calls("context-scout"), 1)  # the same skill text: the map is reused
        self.set_items({"W1": {}})
        self.git("reset", "-q", "--hard", "HEAD~1")
        skill.write_text("---\nname: demo\n---\n\nmap the files and the tests\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "skill changed")
        self.assertEqual(self.run_items("W1", extra=("--options", options))[0], 0)
        self.assertEqual(self.calls("context-scout"), 2)  # another skill text: a new map

    def test_an_empty_or_broken_cache_file_is_a_miss_and_is_written_again(self):
        self.first()
        (target,) = self.cache_files()
        for damage in (b"", b"\xff\xfe\x00broken"):
            with self.subTest(damage=damage):
                target.write_bytes(damage)
                before = self.calls("context-scout")
                code, _, err = self.again()
                self.assertEqual(code, 0, err)
                self.assertEqual(self.calls("context-scout"), before + 1)
                self.assertEqual(self.verdict(err), "mapped")
                self.assertTrue(target.read_text(encoding="utf-8").strip())  # whole again

    def test_the_cache_is_written_with_durable_replace(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        with mock.patch.object(scout, "durable_replace", wraps=scout.durable_replace) as written:
            code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertGreaterEqual(written.call_count, 1)
        cache_call = next(call for call in written.call_args_list if str(call.args[0]).endswith(".txt"))
        path, data = cache_call.args
        self.assertEqual(Path(path), self.cache_files()[0])
        self.assertEqual(data, Path(path).read_bytes())
        self.assertEqual([p.name for p in Path(path).parent.iterdir() if p.name.endswith(".tmp")], [])

    def test_a_cache_that_cannot_be_written_does_not_stop_the_run(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        with mock.patch.object(scout, "durable_replace", side_effect=OSError("read-only")):
            code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.cache_files(), [])


if __name__ == "__main__":
    unittest.main()
