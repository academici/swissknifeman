"""aicore.delivery.materialize: managed skill copies, marker, manifest, lock and the sync of a plan."""
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aicore.delivery import materialize as m

SKILL = b"---\nname: demo\ndescription: d\n---\nbody\n"


def write(path, data="x\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)


def quiet(call, *args, **kwargs):
    """Run ``call`` with stdout and stderr captured; return (result, stderr text)."""
    err = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
        return call(*args, **kwargs), err.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()


class MarkerCase(Base):
    def marked(self, raw):
        write(self.root / "SKILL.md", raw)
        m.mark_skill_managed(self.root)
        return (self.root / "SKILL.md").read_bytes()

    def test_marker_follows_the_closing_fence_and_strip_restores_the_bytes(self):
        for name, raw in (("lf", SKILL),
                          ("crlf", SKILL.replace(b"\n", b"\r\n")),
                          ("bom", b"\xef\xbb\xbf" + SKILL)):
            with self.subTest(name):
                out = self.marked(raw)
                self.assertIn(m.SKILL_MANAGED_MARKER.encode("utf-8"), out)
                self.assertNotEqual(out, raw)
                self.assertEqual(m.strip_skill_managed_marker(out), raw)

    def test_marking_is_idempotent_and_ignores_files_without_frontmatter(self):
        once = self.marked(SKILL)
        m.mark_skill_managed(self.root)
        self.assertEqual((self.root / "SKILL.md").read_bytes(), once)
        self.assertEqual(self.marked(b"no frontmatter\n"), b"no frontmatter\n")
        self.assertEqual(self.marked(b"---\nunclosed\n"), b"---\nunclosed\n")
        m.mark_skill_managed(self.root / "missing")  # no file: quiet no-op

    def test_strip_is_the_identity_without_a_marker(self):
        self.assertEqual(m.strip_skill_managed_marker(SKILL), SKILL)

    def test_split_bom(self):
        self.assertEqual(m.split_bom(b"\xef\xbb\xbfabc"), (b"\xef\xbb\xbf", b"abc"))
        self.assertEqual(m.split_bom(b"abc"), (b"", b"abc"))


class SafeCopyCase(Base):
    def setUp(self):
        super().setUp()
        self.src = self.root / "lib" / "demo"
        write(self.src / "SKILL.md", SKILL)
        write(self.src / "refs" / "a.md")
        write(self.src / "__pycache__" / "x.pyc")
        self.dest_root = self.root / "project" / ".claude" / "skills"
        self.dest_root.mkdir(parents=True)

    def test_copies_without_the_ignored_files(self):
        dst = self.dest_root / "demo"
        self.assertTrue(m.safe_copy_skill(self.src, dst, self.dest_root))
        self.assertEqual((dst / "SKILL.md").read_bytes(), SKILL)
        self.assertTrue((dst / "refs" / "a.md").is_file())
        self.assertFalse((dst / "__pycache__").exists())

    def test_refuses_a_destination_outside_the_root(self):
        for name in ("../escape", "../../escape"):
            with self.subTest(name):
                dst = self.dest_root / name
                copied, stderr = quiet(m.safe_copy_skill, self.src, dst, self.dest_root)
                self.assertFalse(copied)
                self.assertIn("outside the destination directory", stderr)
                self.assertFalse(dst.resolve().exists())

    def test_replaces_a_symlink_without_following_it(self):
        outside = self.root / "outside"
        write(outside / "keep.txt")
        dst = self.dest_root / "demo"
        dst.symlink_to(outside, target_is_directory=True)
        self.assertTrue(m.safe_copy_skill(self.src, dst, self.dest_root))
        self.assertFalse(dst.is_symlink())
        self.assertTrue((outside / "keep.txt").is_file())
        self.assertFalse((outside / "SKILL.md").exists())

    def test_refuses_parent_and_root_destinations_without_deleting_files(self):
        sibling = self.dest_root / "other" / "SKILL.md"
        outside = self.dest_root.parent / "keep.txt"
        write(sibling, "other skill")
        write(outside, "outside the skills directory")
        for dst in (self.dest_root / "..", self.dest_root,
                    self.dest_root / "child" / "..", self.dest_root / "."):
            with self.subTest(dst=str(dst)):
                copied, _stderr = quiet(m.safe_copy_skill, self.src, dst, self.dest_root)
                self.assertFalse(copied)
                self.assertEqual(sibling.read_text(), "other skill")
                self.assertEqual(outside.read_text(), "outside the skills directory")
                self.assertEqual((self.src / "SKILL.md").read_bytes(), SKILL)

    def test_refuses_a_cyclic_parent_symlink_without_deleting_files(self):
        loop = self.dest_root / "loop"
        loop.symlink_to("loop")
        copied, _stderr = quiet(m.safe_copy_skill, self.src, loop / "demo", self.dest_root)
        self.assertFalse(copied)
        self.assertTrue(loop.is_symlink())
        self.assertEqual((self.src / "SKILL.md").read_bytes(), SKILL)

    def test_replaces_an_existing_directory_and_a_file(self):
        dst = self.dest_root / "demo"
        write(dst / "old.txt")
        self.assertTrue(m.safe_copy_skill(self.src, dst, self.dest_root))
        self.assertFalse((dst / "old.txt").exists())
        dst2 = self.dest_root / "demo2"
        write(dst2)
        self.assertTrue(m.safe_copy_skill(self.src, dst2, self.dest_root))
        self.assertTrue((dst2 / "SKILL.md").is_file())


class ManifestCase(Base):
    def test_manifest_has_version_first_and_is_kept_when_nothing_changes(self):
        path = self.root / m.MANIFEST
        args = dict(profile="php", agent="claude", layout="flat",
                    installed=[{"flat_name": "demo", "source_path": "php/demo"}])
        with mock.patch.object(m, "now_iso", return_value="2026-01-01T00:00:00Z"):
            m.write_skill_manifest(path, **args)
        first = path.read_bytes()
        data = json.loads(first)
        self.assertEqual(list(data)[0], "version")
        self.assertEqual((data["version"], data["installed_at"], data["layout"]),
                         (m.MANIFEST_VERSION, "2026-01-01T00:00:00Z", "flat"))
        with mock.patch.object(m, "now_iso", return_value="2030-01-01T00:00:00Z") as clock:
            m.write_skill_manifest(path, **args)
            clock.assert_not_called()
        self.assertEqual(path.read_bytes(), first)
        with mock.patch.object(m, "now_iso", return_value="2030-01-01T00:00:00Z"):
            m.write_skill_manifest(path, **{**args, "profile": "node"})
        self.assertEqual(json.loads(path.read_text())["installed_at"], "2030-01-01T00:00:00Z")

    def test_support_files_are_part_of_the_stable_data(self):
        path = self.root / m.MANIFEST
        m.write_skill_manifest(path, profile="", agent="claude", layout="flat", installed=[],
                               support_files=["a.md"])
        self.assertEqual(json.loads(path.read_text())["support_files"], ["a.md"])

    def test_agent_defaults(self):
        self.assertEqual(m.AGENT_DEFAULTS["claude"], ".claude/skills")
        self.assertEqual(m.MANIFEST, ".swissknifeman-manifest.json")
        self.assertEqual(m.SKILL_MANAGED_MARKER, "<!-- swissknifeman:managed -->")


class LockCase(Base):
    def lock_file(self):
        return self.root / m.LOCK_FILE

    def test_missing_lock_is_empty(self):
        self.assertEqual(m.load_lock(self.root), {})
        self.assertIsNone(m.lock_problem(self.root))

    def test_round_trip(self):
        lock = {"version": 1, "skills": {"a": {"managed": True}}}
        m.write_lock(self.root, lock)
        self.assertEqual(m.load_lock(self.root), lock)
        self.assertTrue(self.lock_file().read_text().endswith("\n"))

    def test_broken_lock_warns_and_reads_as_empty(self):
        for text in ("{broken", json.dumps({"skills": []}), "[]"):
            with self.subTest(text=text):
                self.lock_file().write_text(text)
                loaded, stderr = quiet(m.load_lock, self.root)
                self.assertEqual(loaded, {})
                self.assertIn("skills-lock", stderr)

    def digest(self):
        return "a" * 64

    def record(self, **over):
        record = {"source": m.SOURCE, "managed": True, "sha256": self.digest(),
                  "installed_path": ".claude/skills/a"}
        record.update(over)
        return record

    def problem(self, data):
        self.lock_file().write_text(json.dumps(data))
        return m.lock_problem(self.root)

    def test_lock_problem_codes(self):
        self.lock_file().write_text("{broken")
        self.assertEqual(m.lock_problem(self.root), "invalid-json")
        self.assertEqual(self.problem([]), "root-not-object")
        self.assertEqual(self.problem({"version": 2, "skills": {}}), "unsupported-version")
        self.assertEqual(self.problem({"skills": []}), "skills-map-invalid")
        self.assertEqual(self.problem({"skills": {}, "providers": {"codex": []}}), "provider-map-invalid")
        self.assertEqual(self.problem({"skills": {"a": 1}}), "record-invalid")
        for bad in ({"source": "other"}, {"sha256": "xyz"}, {"sha256": "A" * 64},
                    {"installed_path": 3}):
            with self.subTest(bad=bad):
                self.assertEqual(self.problem({"skills": {"a": self.record(**bad)}}),
                                 "managed-provenance-invalid")
        self.assertIsNone(self.problem({"skills": {"a": self.record()},
                                        "providers": {"codex": {"b": self.record()}}}))
        self.assertIsNone(self.problem({"skills": {"stranger": {"managed": False}}}))

    def test_hash_label_and_dir_sha256(self):
        self.assertEqual(m.hash_label("abc"), "sha256:abc")
        self.assertEqual(m.hash_label(""), "sha256:<missing>")
        self.assertEqual(m.dir_sha256(self.root), "")
        write(self.root / "SKILL.md", SKILL)
        self.assertEqual(m.dir_sha256(self.root), hashlib.sha256(SKILL).hexdigest())


class SyncCase(Base):
    """``sync_skillset`` on a hand-made plan: the library and the selection rules are the caller's."""

    def setUp(self):
        super().setUp()
        self.lib = self.root / "lib"
        self.target = self.root / "project"
        self.target.mkdir()
        for name in ("alpha", "beta"):
            write(self.lib / "php" / name / "SKILL.md", SKILL.replace(b"demo", name.encode()))
            write(self.lib / "php" / name / "refs" / "r.md")

    def entry(self, name):
        skill_dir = self.lib / "php" / name
        return {"name": name, "bucket": "php", "skill_dir": skill_dir,
                "path": f"php/{name}/SKILL.md", "sha256": m.dir_sha256(skill_dir),
                "content_sha256": "c-" + name}

    def plan(self, wanted, *, skills_path=".claude/skills", conflicts=()):
        """What a planner returns for ``wanted`` against the lock and the files of the project."""
        lock = m.load_lock(self.target)
        locked = lock.get("skills", {})
        entries = [self.entry(n) for n in wanted]
        dest_root = self.target / skills_path
        add, update, keep = [], [], []
        for e in entries:
            record = locked.get(e["name"])
            if e["name"] in conflicts:
                continue
            if record is None:
                add.append(e["name"])
            elif record["sha256"] != e["sha256"]:
                update.append(e["name"])
            else:
                keep.append(e["name"])
        remove = [n for n, r in locked.items() if r.get("managed") and n not in wanted]
        return {"add": add, "update": update, "keep": keep, "remove": remove,
                "conflicts": list(conflicts), "conflicts_likely_ours": [],
                "managed_drift": [], "relocated": {}, "skills_path": skills_path,
                "entries": entries, "dest_root": dest_root, "provenance_invalid": None,
                "drift_hashes": {}}

    def sync(self, wanted, *, cfg=None, conflicts=(), skills_path=".claude/skills", **kwargs):
        plan = self.plan(wanted, skills_path=skills_path, conflicts=conflicts)
        result, _ = quiet(m.sync_skillset, None, self.target, cfg or {}, plan=plan, **kwargs)
        return result

    def test_install_writes_copies_lock_and_manifest(self):
        plan = self.sync(["alpha", "beta"])
        self.assertEqual(plan["installed"], ["alpha", "beta"])
        self.assertEqual(plan["skip_copy"], [])
        for name in ("alpha", "beta"):
            self.assertTrue((self.target / ".claude/skills" / name / "refs" / "r.md").is_file())
        lock = json.loads((self.target / m.LOCK_FILE).read_text())
        self.assertEqual(lock["version"], m.LOCK_VERSION)
        self.assertEqual(lock["sources"], {m.SOURCE: {"ref": "registry", "mode": "vendor"}})
        record = lock["skills"]["alpha"]
        self.assertEqual((record["source"], record["managed"], record["bucket"]),
                         (m.SOURCE, True, "php"))
        self.assertEqual(record["sha256"], m.dir_sha256(self.target / ".claude/skills/alpha"))
        self.assertEqual(record["content_sha256"], "c-alpha")
        self.assertEqual(record["installed_path"], ".claude/skills/alpha")
        self.assertEqual(list(lock["skills"]), ["alpha", "beta"])
        manifest = json.loads((self.target / ".claude/skills" / m.MANIFEST).read_text())
        self.assertEqual([i["flat_name"] for i in manifest["skills"]], ["alpha", "beta"])
        self.assertEqual(manifest["skills"][0]["source_path"], "php/alpha")
        self.assertEqual(manifest["layout"], "flat")
        self.assertIsNone(m.lock_problem(self.target))

    def test_a_repeat_run_changes_nothing(self):
        self.sync(["alpha"])
        lock = (self.target / m.LOCK_FILE).read_bytes()
        manifest = (self.target / ".claude/skills" / m.MANIFEST).read_bytes()
        plan = self.sync(["alpha"])
        self.assertEqual((plan["installed"], plan["keep"]), ([], ["alpha"]))
        self.assertEqual((self.target / m.LOCK_FILE).read_bytes(), lock)
        self.assertEqual((self.target / ".claude/skills" / m.MANIFEST).read_bytes(), manifest)

    def test_update_follows_a_changed_source(self):
        self.sync(["alpha"])
        write(self.lib / "php" / "alpha" / "SKILL.md", SKILL + b"more\n")
        plan = self.sync(["alpha"])
        self.assertEqual((plan["update"], plan["installed"]), (["alpha"], ["alpha"]))
        self.assertTrue((self.target / ".claude/skills/alpha/SKILL.md").read_bytes().endswith(b"more\n"))

    def test_a_retired_managed_skill_is_removed_and_a_foreign_one_is_kept(self):
        self.sync(["alpha", "beta"])
        write(self.target / ".claude/skills/stranger/SKILL.md", "mine\n")
        plan = self.sync(["alpha"])
        self.assertEqual(plan["remove"], ["beta"])
        self.assertFalse((self.target / ".claude/skills/beta").exists())
        self.assertTrue((self.target / ".claude/skills/stranger/SKILL.md").is_file())
        self.assertEqual(list(json.loads((self.target / m.LOCK_FILE).read_text())["skills"]), ["alpha"])

    def test_a_conflict_is_skipped_without_force_and_replaced_with_force(self):
        write(self.target / ".claude/skills/alpha/SKILL.md", "someone else's\n")
        plan = self.sync(["alpha"], conflicts=["alpha"])
        self.assertEqual(plan["installed"], [])
        self.assertEqual((self.target / ".claude/skills/alpha/SKILL.md").read_text(), "someone else's\n")
        self.assertNotIn("alpha", json.loads((self.target / m.LOCK_FILE).read_text())["skills"])
        plan = self.sync(["alpha"], conflicts=["alpha"], force=True)
        self.assertEqual(plan["installed"], ["alpha"])
        self.assertIn(b"name: alpha", (self.target / ".claude/skills/alpha/SKILL.md").read_bytes())

    def test_dry_run_prints_and_writes_nothing(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            m.sync_skillset(None, self.target, {}, dry_run=True, plan=self.plan(["alpha"]))
        self.assertIn("[dry-run] add php/alpha", out.getvalue())
        self.assertEqual(list(self.target.iterdir()), [])

    def test_gitignore_lists_managed_skills_and_goes_away_with_the_option(self):
        write(self.target / ".claude/skills/local/SKILL.md", "mine\n")
        self.sync(["alpha"], cfg={"gitignore_managed": True})
        ignore = self.target / ".claude/skills/.gitignore"
        text = ignore.read_text()
        self.assertTrue(text.startswith(m.GITIGNORE_HEADER))
        self.assertIn("/alpha/\n", text)
        self.assertIn("skiller sync   (from [skiller.sync] + skills-lock.json)", text)
        self.assertNotIn("local", text)
        self.sync(["alpha"], cfg={})
        self.assertFalse(ignore.exists())
        ignore.write_text("# user file\n")
        self.sync(["alpha"], cfg={})
        self.assertEqual(ignore.read_text(), "# user file\n")

    def test_a_skipped_copy_is_not_recorded_as_installed(self):
        with mock.patch.object(m, "safe_copy_skill", return_value=False) as copy:
            plan = self.sync(["alpha", "beta"])
        self.assertEqual(copy.call_count, 2)
        self.assertEqual((plan["installed"], plan["skip_copy"]), ([], ["alpha", "beta"]))
        self.assertEqual(json.loads((self.target / m.LOCK_FILE).read_text())["skills"], {})

    def test_an_invalid_lock_stops_the_sync(self):
        plan = self.plan(["alpha"])
        plan["provenance_invalid"] = "invalid-json"
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            m.sync_skillset(None, self.target, {}, plan=plan)
        self.assertIn("SPUB_OWNERSHIP_CONFLICT", err.getvalue())
        self.assertFalse((self.target / ".claude").exists())

    def test_managed_drift_needs_repair(self):
        plan = self.plan(["alpha"])
        plan["managed_drift"] = ["alpha"]
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            m.sync_skillset(None, self.target, {}, plan=plan)
        self.assertIn("managed-drift: alpha", err.getvalue())

    def test_the_second_provider_gets_its_own_lock_map(self):
        self.sync(["alpha"])
        plan = self.plan(["alpha"], skills_path=".agents/skills")
        plan["keep"], plan["add"] = [], ["alpha"]
        quiet(m.sync_skillset, None, self.target, {}, provider="codex", plan=plan)
        lock = json.loads((self.target / m.LOCK_FILE).read_text())
        self.assertEqual(list(lock["skills"]), ["alpha"])
        self.assertEqual(lock["providers"]["codex"]["alpha"]["installed_path"], ".agents/skills/alpha")
        self.assertTrue((self.target / ".agents/skills/alpha/SKILL.md").is_file())

    def test_without_a_plan_the_planner_plans(self):
        planner = mock.Mock(return_value=self.plan(["alpha"]))
        quiet(m.sync_skillset, "env", self.target, {"k": 1}, include_core=True, provider="claude-code",
              planner=planner)
        planner.assert_called_once_with("env", self.target, {"k": 1}, include_core=True,
                                        provider="claude-code")
        self.assertTrue((self.target / ".claude/skills/alpha/SKILL.md").is_file())

    def test_without_a_plan_and_a_planner_it_is_an_error(self):
        with self.assertRaises(ValueError):
            m.sync_skillset(None, self.target, {})


class ReportCountsCase(unittest.TestCase):
    PLAN = {"add": ["a", "b"], "update": ["c"], "conflicts": ["d", "e"],
            "installed": ["a", "c", "d"], "skip_copy": ["b"]}

    def test_dry_run_reports_the_plan(self):
        self.assertEqual(m.sync_report_counts(self.PLAN, True, False), (2, 1, 0, 0))
        self.assertEqual(m.sync_report_counts(self.PLAN, True, True), (2, 1, 2, 0))

    def test_a_real_run_reports_the_facts(self):
        self.assertEqual(m.sync_report_counts(self.PLAN, False, False), (1, 1, 0, 1))
        self.assertEqual(m.sync_report_counts(self.PLAN, False, True), (1, 1, 1, 1))


class RemovePathCase(Base):
    def test_removes_files_directories_and_symlinks_without_following(self):
        outside = self.root / "outside"
        write(outside / "keep.txt")
        (self.root / "link").symlink_to(outside, target_is_directory=True)
        write(self.root / "dir" / "f.txt")
        write(self.root / "file.txt")
        for name in ("link", "dir", "file.txt"):
            m.remove_path(self.root / name)
            self.assertFalse((self.root / name).is_symlink() or (self.root / name).exists())
        self.assertTrue((outside / "keep.txt").is_file())
        m.remove_path(self.root / "absent")  # nothing to remove
