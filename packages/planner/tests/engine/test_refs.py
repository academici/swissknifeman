"""refs.resolve (T4): other plans of the same repository (live, archived), foreign repositories, failures, context."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from planner.plan import context, lifecycle, ops, refs, store  # noqa: E402

try:
    from . import test_lifecycle
except ImportError:  # run as `discover -s tests/engine` (no parent package)
    import test_lifecycle

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "plan.py"
OPUS = test_lifecycle.OPUS


def new_plan(plans_root: Path, codename: str, repository: str) -> Path:
    plan = ops.new_plan(codename, codename.title(), plans_root=plans_root, repository=repository, owner="o",
                        authoring=OPUS, message="m", date="2026.10.08")
    return plan.root


def accepted(root: Path, title: str, text: str = "A", why: str = "because") -> str:
    key = ops.add_decision(root, title, data={"options": [{"id": "A", "text": text}]})
    lifecycle.decide(root, key, "A", why, by="owner", actor=OPUS)
    return key


class RefsCase(test_lifecycle.LifeCase):
    """LIFE (PLAN1, repository ``r``) plus OTHER (PLAN2, same repository) with decision D1 and a phase/item."""

    def setUp(self):
        super().setUp()
        self.other = new_plan(self.plans, "OTHER", "r")
        accepted(self.other, "Wire format", "JSON")  # OTHER.D1
        ops.add_phase(self.other, "Only")
        ops.add_item(self.other, "P1", "Work")
        self.short = store.load_plan(self.other).plan["short_id"]
        self.assertEqual(self.short, "PLAN2")

    def resolve(self, ref, **kwargs):
        return refs.resolve(self.load(), ref, **kwargs)

    def foreign_repo(self) -> tuple[Path, Path]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name) / "ext"
        (repo / "plans").mkdir(parents=True)
        root = new_plan(repo / "plans", "EXTERNAL", "ext")
        accepted(root, "Shared rule", "no network")
        return repo, root


class SameRepositoryTests(RefsCase):
    def test_live_decision_has_facts_and_source_digest(self):
        entry = self.resolve("PLAN2.D1")
        self.assertEqual((entry["ref"], entry["loaded"], entry["plan"], entry["kind"], entry["status"]),
                         ("PLAN2.D1", True, "PLAN2", "decision", "accepted"))
        self.assertEqual((entry["title"], entry["decision"], entry["rationale"]),
                         ("Wire format", "A — JSON", "because"))
        plan_dir = f"plans/{self.other.name}"
        self.assertEqual(entry["plan_dir"], plan_dir)
        self.assertEqual(entry["source"]["path"], f"{plan_dir}/decisions/D1.json")
        data = (self.other / "decisions" / "D1.json").read_bytes()
        self.assertEqual(entry["source"]["sha256"], hashlib.sha256(data).hexdigest())

    def test_own_repository_prefix_is_the_same_repository(self):
        self.assertTrue(self.resolve("r:PLAN2.D1")["loaded"])

    def test_item_and_phase_targets(self):
        item, phase = self.resolve("PLAN2.P1.1"), self.resolve("PLAN2.P1")
        self.assertEqual((item["kind"], item["title"], item["status"]), ("item", "Work", "todo"))
        self.assertEqual((phase["kind"], phase["loaded"]), ("phase", True))
        self.assertNotIn("decision", item)

    def test_archived_plan_resolves(self):
        archive = self.plans / store.ARCHIVE
        archive.mkdir()
        shutil.move(str(self.other), str(archive / self.other.name))
        entry = self.resolve("PLAN2.D1")
        self.assertTrue(entry["loaded"], entry)
        self.assertEqual(entry["plan_dir"], f"plans/archive/{self.other.name}")

    def test_archived_plan_resolves_from_an_archived_plan(self):
        archive = self.plans / store.ARCHIVE
        archive.mkdir()
        shutil.move(str(self.root), str(archive / self.root.name))
        entry = refs.resolve(store.load_plan(archive / self.root.name), "PLAN2.D1")
        self.assertTrue(entry["loaded"], entry)

    def test_missing_plan_and_target(self):
        self.assertEqual(self.resolve("PLAN9.D1")["reason"].split(":")[0], "PLAN_NOT_FOUND")
        missing = self.resolve("PLAN2.D9")
        self.assertEqual((missing["loaded"], missing["reason"].split(":")[0]), (False, "TARGET_NOT_FOUND"))
        self.assertEqual(self.resolve("PLAN2.P7.1")["reason"].split(":")[0], "TARGET_NOT_FOUND")

    def test_local_reference_is_left_alone(self):
        self.assertEqual(self.resolve("D1"), {"ref": "D1", "loaded": False})

    def test_resolution_is_read_only_and_takes_no_lock(self):
        before = {p: p.read_bytes() for p in self.other.rglob("*") if p.is_file()}
        with mock.patch.object(store.PlanLock, "__enter__", side_effect=AssertionError("locked")):
            self.assertTrue(self.resolve("PLAN2.D1")["loaded"])
        self.assertEqual({p: p.read_bytes() for p in self.other.rglob("*") if p.is_file()}, before)

    def test_superseded_chain_follows_to_the_current_decision(self):
        new = accepted(self.other, "Wire format v2", "YAML")
        lifecycle.supersede(self.other, "D1", new, OPUS)
        entry = self.resolve("PLAN2.D1")
        self.assertEqual((entry["loaded"], entry["status"], entry["id"], entry["superseded"]),
                         (True, "accepted", new, ["D1"]))
        self.assertEqual(entry["decision"], "A — YAML")
        self.assertTrue(entry["source"]["path"].endswith(f"decisions/{new}.json"))

    def test_superseded_cycle_is_reported(self):
        second = accepted(self.other, "Second")
        lifecycle.supersede(self.other, "D1", second, OPUS)
        for key, other in (("D1", second), (second, "D1")):
            path = self.other / "decisions" / f"{key}.json"
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc.update(status="superseded", superseded_by=other)
            path.write_text(json.dumps(doc), encoding="utf-8")
        entry = self.resolve("PLAN2.D1")
        self.assertEqual((entry["loaded"], entry["reason"].split(":")[0]), (False, "CYCLE"))

    def test_long_superseded_chain_is_cut(self):
        keys = ["D1"] + [accepted(self.other, f"v{n}") for n in range(2, 12)]
        for old, new in zip(keys, keys[1:]):
            lifecycle.supersede(self.other, old, new, OPUS)
        self.assertEqual(self.resolve("PLAN2.D1")["reason"].split(":")[0], "CYCLE")

    def test_ambiguous_short_id(self):
        shutil.copytree(self.other, self.plans / "2026.10.08-№9-COPY")
        self.assertEqual(self.resolve("PLAN2.D1")["reason"].split(":")[0], "PLAN_AMBIGUOUS")


class ForeignRepositoryTests(RefsCase):
    def test_repo_mapping_flag(self):
        repo, root = self.foreign_repo()
        entry = self.resolve("ext:PLAN1.D1", repos={"ext": str(repo)})
        self.assertTrue(entry["loaded"], entry)
        self.assertEqual(entry["plan_dir"], str(root))
        self.assertEqual(entry["source"]["path"], str(root / "decisions" / "D1.json"))
        self.assertEqual(entry["decision"], "A — no network")

    def test_environment_mapping(self):
        repo, _ = self.foreign_repo()
        with mock.patch.dict(os.environ, {refs.ENV_REPOS: json.dumps({"ext": str(repo)})}):
            self.assertTrue(self.resolve("ext:PLAN1.D1")["loaded"])

    def test_flag_wins_over_environment(self):
        repo, _ = self.foreign_repo()
        with mock.patch.dict(os.environ, {refs.ENV_REPOS: json.dumps({"ext": "/nonexistent"})}):
            self.assertTrue(self.resolve("ext:PLAN1.D1", repos={"ext": str(repo)})["loaded"])

    def test_unknown_repository(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(refs.ENV_REPOS, None)
            entry = self.resolve("ext:PLAN1.D1")
        self.assertEqual((entry["loaded"], entry["reason"].split(":")[0]), (False, "REPO_UNKNOWN"))
        self.assertEqual(set(entry), {"ref", "loaded", "reason"})

    def test_refs_of_other_kinds_are_reported_unsupported_not_raised(self):
        for ref in ("PLAN1.P1.1/U1", "PLAN1.knowledge/design", "PLAN1.artifact/catalog"):
            entry = self.resolve(ref)
            self.assertEqual((entry["loaded"], entry["reason"].split(":")[0]), (False, "REF_UNSUPPORTED"), ref)

    def test_invalid_environment_json_makes_every_foreign_repository_unknown(self):
        repo, _ = self.foreign_repo()
        with mock.patch.dict(os.environ, {refs.ENV_REPOS: "{not json"}):
            entry = self.resolve("ext:PLAN1.D1")
            self.assertEqual(entry["reason"], f"REPO_UNKNOWN: {refs.ENV_REPOS} is not valid JSON")
            self.assertTrue(self.resolve("ext:PLAN1.D1", repos={"ext": str(repo)})["loaded"])

    def test_mapped_repository_without_plans(self):
        with tempfile.TemporaryDirectory() as empty:
            entry = self.resolve("ext:PLAN1.D1", repos={"ext": empty})
        self.assertEqual((entry["loaded"], entry["reason"].split(":")[0]), (False, "PLAN_NOT_FOUND"))


class WorkspaceRefsTests(RefsCase):
    """A plan whose folder is outside the checkout; a foreign checkout is a path whose marker names its plans."""

    def test_a_foreign_checkout_with_a_workspace_marker_is_read_from_the_workspace(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(os.path.realpath(tmp.name))
        pid = "billium"
        repo, ws = base / "ext", base / "wss" / "axioma"
        marker = repo / ".swissknifeman" / "project.json"
        marker.parent.mkdir(parents=True)
        marker.write_text(json.dumps({"$schema": "urn:swissknifeman:aicore:project-marker:v1", "workspace": "axioma", "project_id": pid,
                                      "plans_store": "workspace"}), encoding="utf-8")
        plans = ws / "projects" / pid / "plans"
        plans.mkdir(parents=True)
        root = new_plan(plans, "EXTERNAL", "ext")
        accepted(root, "Shared rule", "no network")
        env = {"SKM_HOME": str(base / "home"), "SKM_WORKSPACES_ROOT": str(ws.parent)}
        with mock.patch.dict(os.environ, env):
            entry = self.resolve("ext:PLAN1.D1", repos={"ext": str(repo)})
        self.assertTrue(entry["loaded"], entry)
        self.assertEqual(entry["source"]["path"], str(root / "decisions" / "D1.json"))

    def test_the_own_repository_uses_the_folder_of_the_plan_even_without_a_checkout(self):
        plan = self.load()
        plan.__dict__["source_root"] = None
        entry = refs.resolve(plan, f"{self.short}.D1")
        self.assertTrue(entry["loaded"], entry)
        self.assertEqual(entry["plan_dir"], f"plans/{self.other.name}")


class ContextTests(RefsCase):
    def test_context_inlines_resolved_decisions_and_keeps_the_old_keys(self):
        ops.patch(self.root, "P1.2", {"decisions": ["PLAN2.D1", "PLAN7.D4", "r:PLAN2.D9"]})
        by_ref = {d["ref"]: d for d in context.collect(self.load(), "P1.2")["decisions"] if "ref" in d}
        self.assertTrue(by_ref["PLAN2.D1"]["loaded"])
        self.assertEqual(by_ref["PLAN2.D1"]["decision"], "A — JSON")
        for ref in ("PLAN7.D4", "r:PLAN2.D9"):
            self.assertIs(by_ref[ref]["loaded"], False)
            self.assertIn("reason", by_ref[ref])
        self.assertTrue(all("ref" in d and "loaded" in d for d in by_ref.values()))

    def test_context_does_not_fail_on_a_broken_foreign_plan(self):
        ops.patch(self.root, "P1.2", {"decisions": ["PLAN2.D1"]})
        (self.other / "plan.json").write_text("{broken", encoding="utf-8")
        entry = context.collect(self.load(), "P1.2")["decisions"][-1]
        self.assertEqual((entry["ref"], entry["loaded"]), ("PLAN2.D1", False))

    def test_context_cli_takes_repeatable_repo_flags(self):
        repo, _ = self.foreign_repo()
        ops.patch(self.root, "P1.2", {"decisions": ["ext:PLAN1.D1"]})
        run = subprocess.run([sys.executable, str(SCRIPT), "context", str(self.root), "P1.2", "--stdout",
                              "--repo", "other=/nowhere", "--repo", f"ext={repo}"],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        entry = json.loads(run.stdout)["decisions"][-1]
        self.assertTrue(entry["loaded"], entry)

    def test_malformed_repo_flag_is_a_usage_error(self):
        run = subprocess.run([sys.executable, str(SCRIPT), "context", str(self.root), "P1.2", "--repo", "oops"],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 2, run.stderr)


if __name__ == "__main__":
    unittest.main()
