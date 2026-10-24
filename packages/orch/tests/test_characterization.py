"""Characterization of conductor state, argv, prompt manifests, events and routes on fake roles.

Each scenario runs the conductor on the fake roles of ``tests/fixtures/conductor/fake_role.py`` and compares the run
with a snapshot in ``tests/golden/characterization/<scenario>.json``. The snapshot holds the journal and the state of
the run without what changes from run to run: times, durations, the run id, the temporary paths. Tokens stay as the
fixtures give them. A refactoring of the conductor must leave every snapshot as it is.

Recapture a snapshot only on purpose, with the reason::

    python3 tests/test_characterization.py --recapture --reason "why the behaviour changed"

The coverage test lists every stop code and beacon of ``docs/conductor.md`` and names the scenario or the test that
meets it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock

if __name__ == "__main__":  # run as a script: the package root is the parent of tests/
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "aicore" / "lib"))

from aicore.ext import events as event_journal

from orch import adhoc
from orch.conductor import checks, engine
from orch.conductor.infrastructure import clock
from tests import test_conductor as tc
from tests.test_conductor import FINDING, FIXTURES, GREEN, ROLES, ConductorCase, executor_ok, report
from tests.test_conductor_advisor import ENABLED, advice
from tests.test_conductor_questions import ASK, asking

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "characterization"
DOCS = ROOT / "docs" / "conductor.md"
TESTS = ROOT / "tests"
RECAPTURE = "CHARACTERIZATION_RECAPTURE_REASON"  # set by --recapture --reason; a bare environment never recaptures
VOLATILE = {"ts", "run", "duration_s", "started", "finished", "created", "updated", "at", "last_ts", "active_s", "wait_s", "retry_after_s"}
TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?")
RUN_ID = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{6}")
DIGEST = re.compile(r"(?<![0-9a-f])[0-9a-f]{24,64}(?![0-9a-f])")  # git commits, content digests, orch run ids
WAITING = re.compile(r"waiting \d+ s")  # the reset of a fake quota is "now + 3 s": the wait is rounded by the clock
SHORT_DIGEST = re.compile(r"(?<=@)[0-9a-f]{12}\b")  # the digest suffix of an input id
SHORT_FINGERPRINT = re.compile(r"(?<=fingerprint=)[0-9a-f]{12}\b")  # reuse_miss names the environment hash


def normalize(value, paths: dict):
    """A copy of a journal or state document without times, durations, run ids and temporary paths.

    ``paths`` maps a text that varies (the run id, the temporary folders) to a stable name; longer texts go first."""
    if isinstance(value, dict):
        return {key: normalize(item, paths) for key, item in sorted(value.items()) if key not in VOLATILE}
    if isinstance(value, list):
        return [normalize(item, paths) for item in value]
    if isinstance(value, str):
        for text in sorted(paths, key=len, reverse=True):
            value = value.replace(text, paths[text])
        value = TIME.sub("<time>", value)
        value = WAITING.sub("waiting <n> s", RUN_ID.sub("<run>", value))
        return SHORT_FINGERPRINT.sub("<digest>", SHORT_DIGEST.sub("<digest>", DIGEST.sub("<digest>", value)))
    return value


def event_data(value):
    """Remove event clocks and digest values before applying the shared normalization."""
    if isinstance(value, dict):
        return {key: event_data(item) for key, item in value.items()
                if key not in VOLATILE | {"id", "time", "duration_ms"}
                and "digest" not in key and "sha256" not in key}
    if isinstance(value, list):
        return [event_data(item) for item in value]
    return value


def projections(run: Path, fake: Path, project: Path, paths: dict) -> dict:
    """Keep item and manifest file identities; block texts and event envelope IDs stay out."""
    argv = []
    for path in fake.glob("*.argv"):
        role, number = path.stem.rsplit("-", 1)
        # The extra-paths fixture also records the guard prefix, which the child CLI cannot see.
        launch = path.with_suffix(".launch-argv")
        argv.append({"role": role, "n": int(number),
                     "argv": json.loads((launch if launch.exists() else path).read_text(encoding="utf-8"))})
    argv.sort(key=lambda row: (row["role"], row["n"]))
    manifests, routes = {}, {}
    for path in sorted(run.glob("*/prompts/*.manifest.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        projected = {key: doc[key] for key in ("step", "role", "route", "excluded", "budgets") if key in doc}
        projected["blocks"] = [{key: row[key] for key in ("kind", "origin", "id", "tokens") if key in row}
                               for row in doc["blocks"]]
        manifests[path.relative_to(run).as_posix()] = projected
    for path in sorted(run.glob("*/routes.json")):
        routes[path.parent.name] = json.loads(path.read_text(encoding="utf-8"))
    events, problems = event_journal.read_events(project, types=["orch.*"])
    if problems:
        raise AssertionError(f"event journal is unreadable: {problems}")
    return normalize({"argv": argv, "manifests": manifests, "routes": routes,
                      "events": [{"type": event.type, "data": event_data(event.data)} for event in events]}, paths)


class CharacterizationCase(ConductorCase):
    """Runs a scenario and keeps the normalized journal and state under its name."""

    def setUp(self):
        # Parallel unittest workers nest TMPDIR under their own home. Absolute paths enter prompt text and its
        # token estimates, so keep fixture paths the same length as the direct recapture command's paths.
        with mock.patch.object(tempfile, "tempdir", "/tmp"):
            super().setUp()
        self.slept = []
        for name, value in (("sleep", self.slept.append), ("unit_random", lambda: 0.5)):
            patcher = mock.patch.object(clock, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        # The partner roots of the environment (SKM_*_ROOT) are read as git repositories to fingerprint a check; where
        # they are not (a standalone copy, a sandbox) the fingerprint is unknown and a row gains a `reuse_miss`. The
        # snapshots must not depend on that: the partners are a fixed state here.
        patcher = mock.patch.object(checks, "_external_state", lambda path, known=None: "partner-state")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.captured = {}

    def options(self, **layer) -> None:
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": layer}]}})

    def snapshot(self, name: str, err: str) -> None:
        """Compare (or recapture) the run whose first call wrote ``err``; a resume appends to the same run."""
        run = self.run_dir(err)
        paths = {run.name: "<run>", str(self.project.parent): "<tmp>", str(self.project): "<project>",
                 str(self.home): "<home>"}
        resolved = {str(Path(key).resolve()): value for key, value in paths.items() if key.startswith("/")}
        paths.update(resolved)
        journal = [normalize(line, paths) for line in json.loads("[" + ",".join(
            (run / "progress.jsonl").read_text(encoding="utf-8").splitlines()) + "]")]
        state_doc = json.loads((run / engine.STATE_FILE).read_text(encoding="utf-8"))
        state_doc.pop("ended", None)  # volatile UTC bound of the run segment, tested in test_observer
        state_doc.pop("$schema", None)  # the records/v1 tag (P4.3), tested in test_records_contract
        for item in state_doc.get("items", {}).values():
            item.pop("usage_by_agent", None)  # replay bookkeeping; totals are covered here, receipts in test_usage_normalization
        state = normalize(state_doc, paths)
        projection_paths = {**paths, str(ROOT): "<orch>", sys.executable: "<python>"}
        compare(self, name, {"progress": journal, "state": state,
                             **projections(run, self.fake, self.project, projection_paths)})


def compare(case: unittest.TestCase, name: str, document: dict) -> None:
    path = GOLDEN / f"{name}.json"
    text = json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    reason = os.environ.get(RECAPTURE, "").strip()
    if reason:
        GOLDEN.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return
    case.assertTrue(path.exists(), f"no snapshot {path.name}: capture it with --recapture --reason")
    case.assertEqual(text, path.read_text(encoding="utf-8"),
                     f"{name} differs from its snapshot; a change on purpose is recaptured with --reason")


def repro(cmd="cat out/W1.txt", observed="ok") -> dict:
    return {"cmd": cmd, "exit": 0, "observed": observed}


class ProjectionTests(unittest.TestCase):
    def test_fixture_paths_do_not_grow_under_a_parallel_worker_tmpdir(self):
        with tempfile.TemporaryDirectory(prefix="characterization-parent-") as directory:
            with mock.patch.object(tempfile, "tempdir", directory):
                case = CharacterizationCase()
                try:
                    case.setUp()
                    self.assertEqual(case.project.parent.parent, Path("/tmp").resolve())
                finally:
                    case.doCleanups()

    def test_projection_keeps_arguments_item_identity_and_block_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake, run = root / "fake", root / "run"
            fake.mkdir()
            for role, number in (("executor", 10), ("reviewer", 1), ("executor", 2)):
                (fake / f"{role}-{number}.argv").write_text(json.dumps([str(root / "output")]))
            (fake / "executor-2.launch-argv").write_text(json.dumps(["--rw", str(root / "output"), "--", "fake"]))
            manifest = {"step": "executor.1", "role": "executor", "route": {"provider": "fake"},
                        "blocks": [{"kind": "skill", "origin": str(root / "skill"), "id": "demo", "tokens": 7,
                                    "sha256": "a" * 64, "text": "a block text must never enter the projection"}],
                        "excluded": [{"id": "other", "reason": "budget"}], "budgets": {"skill": {"tokens": 7, "limit": 9}}}
            for item in ("W1", "W2"):
                prompts = run / item / "prompts"
                prompts.mkdir(parents=True)
                (prompts / "executor.1.manifest.json").write_text(json.dumps(manifest))
                (prompts.parent / "routes.json").write_text(json.dumps({"executor": {"model": item}}))
            events = [mock.Mock(type=kind, data={"id": "volatile", "time": "volatile", "ts": "volatile",
                                               "duration_ms": 12, "prompt_sha256": "b" * 64,
                                               "nested": {"config_digest": "c" * 64, "status": "done"}})
                      for kind in ("orch.agent.started", "orch.agent.finished")]
            with mock.patch.object(event_journal, "read_events", return_value=(events, [])) as read:
                actual = projections(run, fake, root, {str(root): "<tmp>"})
            read.assert_called_once_with(root, types=["orch.*"])
            self.assertEqual([(row["role"], row["n"]) for row in actual["argv"]],
                             [("executor", 2), ("executor", 10), ("reviewer", 1)])
            self.assertEqual(actual["argv"][0]["argv"], ["--rw", "<tmp>/output", "--", "fake"])
            self.assertEqual(actual["routes"], {"W1": {"executor": {"model": "W1"}}, "W2": {"executor": {"model": "W2"}}})
            self.assertEqual(set(actual["manifests"]), {f"{item}/prompts/executor.1.manifest.json" for item in ("W1", "W2")})
            projected = actual["manifests"]["W1/prompts/executor.1.manifest.json"]
            self.assertEqual(projected["blocks"], [{"kind": "skill", "origin": "<tmp>/skill", "id": "demo", "tokens": 7}])
            self.assertEqual(projected["budgets"], manifest["budgets"])
            self.assertEqual(projected["excluded"], manifest["excluded"])
            self.assertEqual(actual["events"], [{"type": kind, "data": {"nested": {"status": "done"}}}
                                                 for kind in ("orch.agent.started", "orch.agent.finished")])

    def test_unreadable_event_journal_fails_instead_of_capturing_empty_events(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(event_journal, "read_events", return_value=([], [{"code": "BROKEN"}])):
                with self.assertRaisesRegex(AssertionError, "event journal is unreadable"):
                    projections(root, root, root, {})


class ScenarioTests(CharacterizationCase):
    def test_green(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.snapshot("green", err)

    def test_red_check_correction(self):
        self.script({"executor": [{"result": report("W1")}, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.snapshot("red-check-correction", err)

    def test_finding_triage_correction(self):
        triage = {"result": {"confirmed": [{"finding": "F1", "reproduction": repro(), "fix": "write done"}],
                             "rejected": []}}
        fixed = {"write": {"out/W1.txt": "done\n"}, "result": report("W1")}
        self.script({"executor": [executor_ok("W1"), fixed], "reviewer": [FINDING, GREEN], "triager": [triage]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.snapshot("finding-triage-correction", err)

    def test_quota_wait(self):
        self.script({"executor": [tc.quota_failure(3), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.snapshot("quota-wait", err)

    def test_route_fallback(self):
        self.options(fallback_routes=[{"role": "executor", "provider": "codex", "model_class": "implementation"}])
        self.script({"executor": [tc.quota_failure(3600), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.snapshot("route-fallback", err)

    def test_resume_after_stop(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        missing = {role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES}
        missing["reviewer"] = [str(self.project / "no-such-grok")]
        self.write_config(missing)
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "PROVIDER_UNAVAILABLE")), err)
        self.write_config()
        code, _, err2 = self.conduct("resume", "--run", self.run_dir(err).name, "--json-lines")
        self.assertEqual((code, self.outcome(err2)), (0, ("finished", None)), err2)
        self.snapshot("resume-after-stop", err)

    def test_input_rebuilt(self):
        state = self.source()
        state["items"]["W1"].update(status="in_progress", goal="Create the amended output of W1.")
        amend = {"result": report("W1"), "write": {str(self.state_file): json.dumps(state)}}
        self.script({"executor": [amend, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.snapshot("input-rebuilt", err)

    def test_question_answer_resume(self):
        self.script({"executor": [asking(dict(ASK)), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (4, ("waiting", "WAITING_DECISION")), err)
        run = self.run_dir(err).name
        code, out, _ = self.conduct("answer", "--run", run, "--item", "W1", "--question", "Q1", "--option", "rename",
                                    "--by", "owner")
        self.assertEqual(code, 0, out)
        doc = self.source()
        doc["items"]["W1"]["status"] = "todo"
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")
        # The reason of a resumed session compares two second-granular stamps (``retry`` when the piece was taken back
        # after the session was last used): a run this fast would record either. The session was used a day ago.
        state_path = self.run_dir(err) / engine.STATE_FILE
        kept = json.loads(state_path.read_text(encoding="utf-8"))
        for slot in kept["executor_sessions"].values():
            slot["last_used_at"] = "2020-01-01T00:00:00Z"
        state_path.write_text(json.dumps(kept), encoding="utf-8")
        code, _, err2 = self.conduct("continue", "--run", run, "--json-lines")
        self.assertEqual((code, self.outcome(err2)), (0, ("finished", None)), err2)
        self.snapshot("question-answer-resume", err)

    def test_adhoc_input(self):
        doc = adhoc.build_adhoc_input("Make out/adhoc.txt", ["out/adhoc.txt"], checks=["V1=test -f out/adhoc.txt"])
        path = self.project.parent / "input.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        done = {**report("adhoc"), "checks_run": [{"id": "V1", "cmd": "test -f out/adhoc.txt", "exit": 0}]}
        self.script({"executor": [{"write": {"out/adhoc.txt": "ok\n"}, "result": done}], "reviewer": [GREEN]})
        code, _, err = self.conduct("run", "--input", path, "--json-lines", "--scenario", "full")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.snapshot("adhoc-input", err)

    def test_dynamic_review(self):
        self.write_config(extra="[orch.conductor.risk.weights]\nschema = 70")
        self.set_items({"W1": {"write_set": ["out/W1.txt", "out/schemas/*.json"]}}, )
        doc = self.source()
        doc["items"]["W1"]["scenario"] = "scout-solo"
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")
        schema = {"write": {"out/W1.txt": "ok\n", "out/schemas/W1.json": "{}\n"},
                  "result": report("W1", changed_paths=["out/W1.txt", "out/schemas/W1.json"])}
        self.script({"executor": [schema], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.snapshot("dynamic-review", err)

    def test_advisor(self):
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in (*ROLES, "advisor")},
                          extra=ENABLED)
        self.script({"executor": [asking(dict(ASK)), executor_ok("W1")], "advisor": [advice("question:Q1@1")],
                     "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.snapshot("advisor", err)

    def test_session_handoff(self):
        self.options(session={"executor": "handoff"})
        self.script({"executor": [{"result": report("W1")}, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        argv = json.loads((self.fake / "executor-2.argv").read_text(encoding="utf-8"))
        self.assertEqual(argv[argv.index("--resume") + 1], "executor-session-1")
        self.snapshot("session-handoff", err)

    def test_report_fixer_repair(self):
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role]
                           for role in (*ROLES, "report-fixer")})
        broken = {**executor_ok("W1"), "result": report("W1", changed_paths=["out/W1.txt", "out/W1.txt"])}
        self.script({"executor": [broken], "reviewer": [GREEN],
                     "report-fixer": [{"result": report("W1"), "tag": "stage-report"}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("executor"), self.calls("report-fixer")), (1, 1))
        self.assertIn("RESULT_REPAIRED", err)
        self.snapshot("report-fixer-repair", err)

    def test_isolated_skills(self):
        skill = self.project / ".claude/skills/characterization/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("---\nname: characterization\n---\n\nKeep the output deterministic.\n", encoding="utf-8")
        self.git("add", ".claude")
        self.git("commit", "-qm", "skill fixture")
        self.options(instructions=tc.opts.DEFAULT_INSTRUCTIONS,
                     skills=[{"role": "executor", "names": ["characterization"]}])
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        argv = json.loads((self.fake / "executor-1.argv").read_text(encoding="utf-8"))
        self.assertIn("--safe-mode", argv)
        manifest = json.loads((self.run_dir(err) / "W1/prompts/executor.1.manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(any(row.get("id") == "characterization" for row in manifest["blocks"]), manifest)
        self.assertIn("Keep the output deterministic.", self.prompt("executor", 1))
        self.snapshot("isolated-skills", err)

    def test_extra_paths(self):
        allowed = self.project.parent / "extra-output"
        allowed.mkdir()
        wrapper = self.project.parent / "ro-run.py"
        wrapper.write_text(
            "import json, os, subprocess, sys\nfrom pathlib import Path\n"
            "state = Path(os.environ['FAKE_ROLE_STATE'])\nstate.mkdir(exist_ok=True)\n"
            "counter = state / 'executor.count'\n"
            "n = int(counter.read_text()) + 1 if counter.exists() else 1\n"
            "(state / f'executor-{n}.launch-argv').write_text(json.dumps([sys.executable, *sys.argv]))\n"
            "sys.exit(subprocess.run(sys.argv[sys.argv.index('--') + 1:]).returncode)\n", encoding="utf-8")
        argv = {role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES}
        argv["executor"] = [sys.executable, str(wrapper), "--rw", str(self.project), "--", *argv["executor"]]
        self.write_config(argv)
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=("--allow-path", allowed))
        self.assertEqual(code, 0, err)
        launched = json.loads((self.fake / "executor-1.launch-argv").read_text(encoding="utf-8"))
        self.assertIn(["--rw", str(allowed)], [launched[n:n + 2] for n in range(launched.index("--"))])
        self.snapshot("extra-paths", err)

    def test_budget_stop(self):
        self.options(limits={"tokens_hard_max": 110})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "TOKEN_BUDGET")), err)
        self.assertEqual((self.calls("executor"), self.calls("reviewer")), (1, 0))
        self.assertEqual(self.state(err)["items"]["W1"]["steps"]["executor.1"]["status"], "done")
        self.snapshot("budget-stop", err)

    def test_group_review(self):
        self.set_items({ref: {} for ref in ("W1", "W2")})
        options = self.project.parent / "group-options.json"
        options.write_text(json.dumps({"review": {"strategy": "groups"}}), encoding="utf-8")
        self.script({"executor": [executor_ok("W1"), executor_ok("W2")],
                     "reviewer": [GREEN]})
        # Group review persists its wall time in both state and a message; fix only that module's timer.
        with mock.patch("orch.conductor.application.review_plan.time") as timer:
            timer.monotonic.return_value = 0.0
            code, _, err = self.run_items("W1", "W2", extra=("--options", options))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("reviewer"), 1)
        self.assertEqual(self.state(err)["group_reviews"]["1"]["refs"], ["W1", "W2"])
        self.assertIn("GROUP_REVIEW", err)
        self.snapshot("group-review", err)


class EventSequenceTests(CharacterizationCase):
    """The ``orch.*`` events that stand next to a beacon (knowledge/p12-observability#types), in the order of a scenario.
    The run and agent events are left out: they are the subject of the contract tests of ``test_events``."""

    SKIPPED = ("orch.run.started", "orch.run.stage.finished", "orch.run.finished", "orch.run.refused")

    def sequence(self) -> list:
        from aicore.ext import events as journal
        stored, problems = journal.read_events(self.project)
        self.assertEqual(problems, [])
        return [event.type for event in stored
                if event.type not in self.SKIPPED and not event.type.startswith("orch.agent.") or
                event.type == "orch.agent.questioned"]

    def test_green_has_no_beacon_event(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.sequence(), [])

    def test_quota_wait(self):
        self.script({"executor": [tc.quota_failure(3), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.sequence(), ["orch.provider.quota-exhausted"])

    def test_route_fallback(self):
        self.options(fallback_routes=[{"role": "executor", "provider": "codex", "model_class": "implementation"}])
        self.script({"executor": [tc.quota_failure(3600), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.sequence(), ["orch.provider.fallback"])

    def test_input_rebuilt(self):
        state = self.source()
        state["items"]["W1"].update(status="in_progress", goal="Create the amended output of W1.")
        amend = {"result": report("W1"), "write": {str(self.state_file): json.dumps(state)}}
        self.script({"executor": [amend, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.sequence(), ["orch.input.rebuilt"])

    def test_question_blocks_the_piece(self):
        self.script({"executor": [asking(dict(ASK))], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (4, ("waiting", "WAITING_DECISION")), err)
        self.assertEqual(self.sequence(), ["orch.agent.questioned", "orch.run.waiting", "orch.work.blocked"])

    def test_dynamic_review(self):
        self.write_config(extra="[orch.conductor.risk.weights]\nschema = 70")
        self.set_items({"W1": {"write_set": ["out/W1.txt", "out/schemas/*.json"]}}, )
        doc = self.source()
        doc["items"]["W1"]["scenario"] = "scout-solo"
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")
        schema = {"write": {"out/W1.txt": "ok\n", "out/schemas/W1.json": "{}\n"},
                  "result": report("W1", changed_paths=["out/W1.txt", "out/schemas/W1.json"])}
        self.script({"executor": [schema], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.sequence(), ["orch.review.added"])


class CodeScenarioTests(CharacterizationCase):
    """Stops and beacons that no other test of the conductor reaches by name; each runs on the fake roles."""

    def stops(self, err: str, code: str) -> None:
        self.assertEqual(self.outcome(err), ("stopped", code), err)

    def beacons(self, err: str) -> set:
        return {line.get("reason_code") for line in self.lines(err) if line["event"] == "info"}

    def test_an_empty_answer_stops_as_role_output_empty(self):
        self.options(limits={"retries": 0, "repairs": 0})
        self.script({"executor": [{"text": ""}], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        self.stops(err, "ROLE_OUTPUT_EMPTY")

    def test_a_refused_operation_stops_as_provider_authz(self):
        failed = {"stream": [tc.api_retry("permission_denied", 403)], "is_error": True, "text": "403",
                  "api_error_status": 403, "exit": 1}
        self.script({"executor": [failed, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        self.stops(err, "PROVIDER_AUTHZ")

    def test_a_silent_role_prints_stage_slow(self):
        from orch.conductor import process
        old = process.POLL_S
        process.POLL_S = 0.2
        self.addCleanup(setattr, process, "POLL_S", old)
        self.options(limits={"stage_warn_s": 1})
        self.script({"executor": [dict(executor_ok("W1"), sleep=2.5)], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertIn("STAGE_SLOW", self.beacons(err))

    def test_a_report_the_fixer_cannot_mend_prints_repair_failed(self):
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES + ("report-fixer",)})
        broken = {"write": {"out/W1.txt": "ok\n"},
                  "result": report("W1", checks_run=[{"id": "V1", "cmd": "test -f out/W1.txt", "exit": "zero"}])}
        self.script({"executor": [broken, executor_ok("W1")], "reviewer": [GREEN],
                     "report-fixer": [{"result": broken["result"], "tag": "stage-report"}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertIn("REPAIR_FAILED", self.beacons(err))

    def test_a_gate_that_cannot_be_written_prints_gate_not_written(self):
        failure = tc.gates.GateError("GATE_WRITE", "read-only")
        with mock.patch.object(tc.gates, "set_gate", side_effect=failure):
            self.script({"executor": [tc.quota_failure(3), executor_ok("W1")], "reviewer": [GREEN]})
            code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertIn("GATE_NOT_WRITTEN", self.beacons(err))

    def test_a_role_that_outlives_its_answer_prints_role_lingered(self):
        real = engine.process.run_role

        def lingering(*args, **kwargs):
            run = real(*args, **kwargs)
            run.lingered = True
            return run

        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        with mock.patch.object(engine.process, "run_role", lingering):
            code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertIn("ROLE_LINGERED", self.beacons(err))

    def refuse(self, verb: str, answer, err_text: str = "refused"):
        real = engine.Conductor._orch

        def orch(conductor, *args):
            if args[:2] == ("source", verb):
                return answer[0], answer[1], err_text
            return real(conductor, *args)

        return mock.patch.object(engine.Conductor, "_orch", orch)

    def test_a_blocked_claim_stops_as_claim_blocked(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        with self.refuse("claim", (0, {"status": "blocked", "ref": "W1", "reason_code": "ITEM_OWNED", "message": "held"})):
            code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        self.assertIn("CLAIM_BLOCKED", err)

    def test_a_refused_brief_stops_as_brief_refused(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        with self.refuse("brief", (1, None)):
            code, _, err = self.run_items("W1")
        self.stops(err, "BRIEF_REFUSED")

    def test_a_refused_prepare_stops_as_prepare_refused(self):
        """Prepare is bound in-process, so a refusal is the conductor call, not the public ``source prepare`` verb."""
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})

        def refuse_prepare(*_args, **_kwargs):
            print("refused", file=sys.stderr)
            return 1

        with mock.patch("orch.cli._source_prepare", refuse_prepare):
            code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        self.stops(err, "PREPARE_REFUSED")


C = "test_characterization.py"
T = "test_conductor.py"
# every stop code and beacon of docs/conductor.md -> where it is met: ``snapshot:<scenario>`` (the code is a value in that
# snapshot) or ``test:<file>`` (the file of tests/ that names it). WORK_SOURCE_* stands for the whole family.
COVERAGE = {
    # Stops
    "RUN_BUSY": "test:test_run_lease.py", "WORKTREE_BUSY": "test:test_run_lease.py",
    "QUESTIONS_LOCKED": "test:test_run_lease.py",
    "QUESTION_ANSWERED_NOT_RETRIED": "test:test_conductor_questions.py",
    "CONDUCTOR_CRASHED": "test:test_observer.py",
    "STAGE_RECOVERY_UNKNOWN": "test:test_resume_reconcile.py",
    "REVIEW_LIMIT": f"test:{T}", "RUN_TIMEOUT": f"test:{T}", "ITEM_BLOCKED": f"test:{T}",
    "WAITING_DECISION": "snapshot:question-answer-resume", "QUESTIONS_OPEN": "test:test_waiting_decision.py",
    "NOT_WAITING": "test:test_waiting_decision.py",
    "ROUTE_UNDERSHOOT": f"test:{T}", "SANDBOX_UNAVAILABLE": f"test:{T}",
    "PROVIDER_UNAVAILABLE": "snapshot:resume-after-stop", "TRANSPORT_UNSUPPORTED": f"test:{T}",
    "LAUNCH_UNKNOWN": "test:test_launch.py", "ROLE_FAILED": f"test:{T}", "ROLE_OUTPUT_EMPTY": f"test:{C}",
    "LAUNCH_REFUSED": f"test:{T}",
    "ROLE_OUTPUT_INVALID": f"test:{T}", "PROVIDER_AUTH": f"test:{T}", "PROVIDER_AUTHZ": f"test:{C}",
    "PROVIDER_QUOTA": "snapshot:quota-wait", "PROVIDER_REFUSED": f"test:{T}", "PROVIDER_CONTEXT": f"test:{T}",
    "MODEL_UNAVAILABLE": f"test:{T}", "TIMEOUT": f"test:{T}", "WORKTREE_DIRTY": f"test:{T}",
    "CLAIM_BLOCKED": f"test:{C}", "BRIEF_REFUSED": f"test:{C}", "PREPARE_REFUSED": f"test:{C}",
    "REGISTER_REFUSED": f"test:{T}", "COMMIT_REFUSED": f"test:{T}", "WORK_SOURCE_*": "test:test_worksource.py",
    "OPTIONS_INVALID": f"test:{T}", "POLICY_UNKNOWN": "test:test_policies.py",
    "POLICY_STAGE_UNSUPPORTED": "test:test_policy_stages.py",
    "OPTIONS_UNTRUSTED": f"test:{T}", "OPTIONS_UNSAFE_PATH": f"test:{T}", "STATE_CORRUPT": "test:test_durable_state.py",
    "STUBS_INVALID": "test:test_conductor_stubs.py",
    "GROUP_REVIEW_BLOCKER": "test:test_conductor_review_plan.py", "GROUP_REVIEW_FAILED": "test:test_conductor_review_plan.py",
    "GROUP_UNKNOWN": "test:test_conductor_review_plan.py", "GROUP_FOLLOWUP_MISMATCH": "test:test_conductor_review_plan.py",
    "GROUP_FOLLOWUP_NOT_DONE": "test:test_conductor_review_plan.py",
    "TOKEN_BUDGET": "snapshot:budget-stop", "TOKEN_BUDGET_UNMETERED": "test:test_budget_hard.py",
    "BRIEF_TOO_LARGE": "test:test_budget_hard.py",
    "MODEL_CATALOG_UNAVAILABLE": "test:test_prepare.py",
    "OUTSIDE_MODULE": "test:test_write_fence.py", "OUTSIDE_RUNTIME_ARTIFACT": "test:test_write_fence.py",
    "CHECKS_MUTATED": "test:test_write_fence.py",
    "RUN_INVALID": "test:test_records_migration.py", "STATE_INVALID": "test:test_records_migration.py",
    "QUESTIONS_INVALID": "test:test_records_contract.py", "RECORD_INVALID": "test:test_records_contract.py",
    "BRIEF_INVALID": "test:test_worksource.py", "REGISTER_REPORT_INVALID": "test:test_worksource.py",
    # Beacons
    "RUN_ORPHANED": "test:test_run_lease.py",
    "STAGE_SLOW": f"test:{C}", "STAGE_IDLE": f"test:{T}", "CHECK_SLOW": f"test:{T}", "RUN_SLOW": f"test:{T}",
    "BUDGET_OVER": f"test:{T}", "LIMIT_OVER": f"test:{T}", "RESULT_HEALED": "snapshot:green",
    "RESULT_REPAIRED": "snapshot:report-fixer-repair", "REPAIR_FAILED": f"test:{C}", "REPAIR_SEMANTIC_DRIFT": "test:test_repair_semantics.py",
    "INPUT_REBUILT": "snapshot:input-rebuilt",
    "PROVIDER_WAIT": "snapshot:quota-wait", "ROUTE_FALLBACK": "snapshot:route-fallback",
    "ROUTE_UPGRADED": "test:test_conductor_focus.py", "CAPACITY_GATED": f"test:{T}",
    "RESULT_SILENT_DENIAL": "test:test_conductor_agents.py", "GATE_NOT_WRITTEN": f"test:{C}", "DISK_LOW": "test:test_polish.py",
    "WRITE_PROTECTED_PATH": "test:test_protected_writes.py",
    "SESSION_ROUTE_CHANGED": "test:test_polish.py", "DEPENDENCY_BLOCKED": "test:test_conductor_session.py",
    "ROLE_LINGERED": f"test:{C}", "ISOLATION_PARTIAL": f"test:{T}", "CHECK_CHANGED_TREE": "test:test_conductor_checks.py",
    "STUBS_CHANGED": "test:test_conductor_stubs.py",
    "SKILL_PATH_INVALID": "test:test_instruction_paths.py", "RULES_PATH_INVALID": "test:test_instruction_paths.py",
    "TRIAGE_REPRO_TRIVIAL": "test:test_triage_repro.py", "TRIAGE_REPRO_MISMATCH": "test:test_triage_repro.py",
    "TRIAGE_REPRO_UNVERIFIED": "test:test_triage_repro.py", "REVIEW_MODE_NONE_SKIPPED": "test:test_conductor_review_plan.py",
    "GROUP_REVIEW_RESOLVED": "test:test_conductor_review_plan.py",
    "RUNTIME_ARTIFACT_RELOCATED": "test:test_write_fence.py",
    "QUESTION_OWNER_ONLY": "test:test_conductor_questions.py",
    "ADVICE_HELD": "test:test_conductor_advisor.py",
    "POLICY_STAGE_SKIPPED": "test:test_policy_stages.py",
    "CONCURRENT_RUN": f"test:{T}", "RESULT_INCOMPLETE": f"test:{T}", "REVIEW_DEBT": f"test:{T}",
    "ANSWER_SCHEMA_IGNORED": "test:test_records_contract.py",
    "PROGRESS_LINE_INVALID": "test:test_progress_lines.py",
    "CHECK_IDLE": "test:test_heartbeat_health.py", "STALL_SUSPECTED": "test:test_heartbeat_health.py",
    "HEARTBEAT_NOT_WRITTEN": "test:test_heartbeat_health.py",
}


def documented_codes() -> list:
    """The codes in the first column of the tables of ``### Stops`` and ``### Beacons`` of docs/conductor.md."""
    text = DOCS.read_text(encoding="utf-8")
    codes = []
    for start, end in (("### Stops", "### Beacons"), ("### Beacons", "### Provider availability")):
        body = text[text.index(start):text.index(end, text.index(start))]
        for line in body.splitlines():
            if line.startswith("|") and not line.startswith(("| ---", "| Code")):
                codes += re.findall(r"`([A-Z][A-Z_*]+)`", line.split("|")[1])
    return list(dict.fromkeys(codes))


class CoverageTests(unittest.TestCase):
    def test_every_documented_code_is_listed_and_every_listed_code_is_documented(self):
        documented = documented_codes()
        self.assertGreater(len(documented), 40, documented)
        self.assertEqual(sorted(documented), sorted(COVERAGE), "docs/conductor.md and COVERAGE differ: list the new code")

    def test_every_code_is_met_where_the_list_says(self):
        for code, where in COVERAGE.items():
            kind, _, name = where.partition(":")
            with self.subTest(code=code):
                if kind == "snapshot":
                    self.assertIn(f'"{code}"', (GOLDEN / f"{name}.json").read_text(encoding="utf-8"))
                else:
                    self.assertEqual(kind, "test")
                    self.assertIn(code.rstrip("*"), (TESTS / name).read_text(encoding="utf-8"))

    def test_every_snapshot_belongs_to_a_scenario_and_back(self):
        wanted = {name[len("test_"):].replace("_", "-") for name in dir(ScenarioTests) if name.startswith("test_")}
        self.assertEqual({path.stem for path in GOLDEN.glob("*.json")}, wanted)
        for name in sorted(wanted):
            with self.subTest(scenario=name):
                document = json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))
                self.assertEqual(set(document), {"progress", "state", "argv", "manifests", "events", "routes"})
                for key in ("argv", "manifests", "events", "routes"):
                    self.assertTrue(document[key], f"{name}: empty {key} projection")


def main() -> int:
    argv = sys.argv[1:]
    default = None
    if "--recapture" in argv:
        argv.remove("--recapture")
        reason = ""
        if "--reason" in argv:
            at = argv.index("--reason")
            reason = argv[at + 1] if at + 1 < len(argv) else ""
            del argv[at:at + 2]
        if not reason.strip():
            print("recapture needs --reason TEXT", file=sys.stderr)
            return 2
        os.environ[RECAPTURE] = reason
        print(f"recapturing the snapshots: {reason}")
        # New snapshots must exist before CoverageTests checks the scenario/snapshot bijection.
        default = sorted((name for name, value in globals().items() if isinstance(value, type)
                          and issubclass(value, unittest.TestCase) and value.__module__ == __name__),
                         key=lambda name: (name != "ScenarioTests", name))
    unittest.main(argv=[sys.argv[0], *argv], module=__name__, defaultTest=default)
    return 0


if __name__ == "__main__":
    sys.exit(main())
