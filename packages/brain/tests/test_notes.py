"""Notes: names, text and the write model I1-I7 (idempotence by event id, no overwrite, one writer at a time)."""
import datetime
import errno
import json
import multiprocessing
import os
import shutil
import unittest
from unittest import mock

from aicore.ext import build_event, read_events
from aicore.state import state_dir

from brain import catalog, errors, events, notes, settings
from brain.errors import BrainError
from tests.support import FIXTURE, TempCase, load_event

NOW = datetime.datetime(2026, 10, 9, 10, 2, 15, tzinfo=datetime.timezone.utc)
FULL_NOTE = """---
type: plan-closed
plan: 2026.01.15-DEMO-PLAN
short_id: PLAN3
status: done
closed: "2026-10-09T09:59:41Z"
project: Demo
repository: swissknifeman
event_id: 0f1e2d3c4b5a69788796a5b4c3d2e1f0
event_source: "urn:swissknifeman:module:planner"
tags: [plan, closed]
---

# Ecosystem split

> Split the monolith into independent modules.

| Phase | Title | Status |
| --- | --- | --- |
| P6 | Extensions and events | done |
| P7 | brain: module base | done_with_deviations |
| P8 | Pipes \\| cells | skipped |

Counts: items 12, done 9, done with deviations 2, skipped 1.

Closed 2026-10-09T09:59:41Z.
"""
MINIMAL_NOTE = """---
type: plan-closed
plan: 2026.01.15-DEMO-PLAN
status: done
closed: "2026-10-09T09:15:30.250Z"
event_id: a1b2c3d4e5f60718293a4b5c6d7e8f90
event_source: "urn:swissknifeman:module:planner"
tags: [plan, closed]
---

# Ecosystem split

Closed 2026-10-09T09:15:30.250Z.
"""
FULL_NAME = "2026-10-09 2026.01.15-DEMO-PLAN closed 0f1e2d3c.md"


def plan_of(name):
    plan, reason = events.parse_plan_closed(load_event(name))
    assert reason is None
    return plan


def numbered_event(index):
    return build_event("planner.plan.closed", {"plan_id": f"demo-conc-{index}", "title": f"Plan {index}"},
                       source="planner", subject=f"plan-{index}", id=f"{index:032x}").to_json()


def _worker(root, env, home, docs):
    config = settings.load(None, env=env, home=home)
    for doc in docs:
        notes.handle(doc, project_root=None, settings=config, env=env, home=home, now=NOW)


class NotesCase(TempCase):
    def setUp(self):
        super().setUp()
        self.configure()

    def configure(self, extra="", vault=None):
        self.machine_config(f'[brain]\nvault_path = "{vault or self.vault}"\n' + extra)

    def handle(self, doc, *, project=False, root=None, **kwargs):
        target = root if root is not None else (self.project if project else None)
        config = settings.load(target, env=self.env, home=self.home)
        return notes.handle(doc, project_root=target, settings=config, env=self.env, home=self.home, now=NOW, **kwargs)

    @property
    def state(self):
        return state_dir("brain", env=self.env, home=self.home)

    @property
    def ledger(self):
        return self.state / "notes.jsonl"

    def ledger_lines(self):
        return self.ledger.read_text(encoding="utf-8").splitlines() if self.ledger.exists() else []

    def written(self, vault=None):
        base = vault or self.vault
        return sorted(p for p in base.rglob("*.md") if p.name != "Demo.md")

    def assertNoTemporaryFiles(self):
        self.assertEqual([], [p for p in self.vault.rglob("*") if ".tmp-" in p.name])


class TestPureParts(NotesCase):
    def test_render_exact(self):
        self.assertEqual(FULL_NOTE, notes.render(plan_of("valid-full"), "Demo"))
        self.assertEqual(MINIMAL_NOTE, notes.render(plan_of("valid-minimal"), None))

    def test_render_is_readable_by_frontmatter(self):
        from brain import frontmatter
        fields = frontmatter.parse(notes.render(plan_of("valid-full"), "Demo"))
        self.assertEqual("0f1e2d3c4b5a69788796a5b4c3d2e1f0", fields["event_id"])
        self.assertEqual(["plan", "closed"], fields["tags"])
        self.assertEqual("2026-10-09T09:59:41Z", fields["closed"])

    def test_render_keeps_one_line_titles_and_quoted_goals(self):
        doc = load_event("valid-full")
        doc["data"].update(title="Two\nlines  here", goal="First\n\nThird", phases=[], counts={})
        plan, _ = events.parse_plan_closed(doc)
        text = notes.render(plan, "Demo")
        self.assertIn("\n# Two lines here\n", text)
        self.assertIn("\n> First\n>\n> Third\n", text)
        self.assertNotIn("| Phase", text)
        self.assertNotIn("Counts:", text)

    def test_name_is_date_plan_and_event(self):
        self.assertEqual(FULL_NAME, notes.note_name(plan_of("valid-full")))

    def test_name_date_is_the_utc_date_of_the_closing_time(self):
        doc = load_event("valid-additive")
        doc["data"]["closed_at"] = "2026-10-10T01:30:00+02:00"
        plan, _ = events.parse_plan_closed(doc)
        self.assertTrue(notes.note_name(plan).startswith("2026-10-09 "))
        doc["data"]["closed_at"] = "2026-10-09T23:30:00-03:00"
        plan, _ = events.parse_plan_closed(doc)
        self.assertTrue(notes.note_name(plan).startswith("2026-10-10 "))

    def test_name_without_closed_at_uses_the_event_time(self):
        self.assertTrue(notes.note_name(plan_of("valid-minimal")).startswith("2026-10-09 "))
        self.assertTrue(notes.note_name(plan_of("valid-minimal")).endswith(" closed a1b2c3d4.md"))

    def test_plan_id_is_cleaned_for_a_file_name(self):
        for dirty in ("a/b\\c\x01d", "../../etc/passwd", "...hidden", "..", "\x01", "x" * 300):
            doc = load_event("valid-full")
            doc["data"]["plan_id"] = dirty
            plan, _ = events.parse_plan_closed(doc)
            name = notes.note_name(plan)
            with self.subTest(plan_id=dirty):
                self.assertNotIn("/", name)
                self.assertNotIn("\\", name)
                self.assertFalse(any(ord(ch) < 32 for ch in name))
                self.assertFalse(name.startswith("."))
                self.assertLess(len(name), 160)

    def test_path_is_a_pure_function(self):
        config = settings.load(self.project, env=self.env, home=self.home)
        plan = plan_of("valid-full")
        project = catalog.VaultProject("Demo", self.vault / "05-Projects" / "03-Packages" / "Demo", "control-note")
        before = sorted(self.root.rglob("*"))
        self.assertEqual(self.vault / "Ecosystem" / "Plans" / FULL_NAME, notes.note_path(config, self.vault, None, plan))
        self.assertEqual(project.folder / "Ecosystem" / "Plans" / FULL_NAME,
                         notes.note_path(config, self.vault, project, plan))
        self.assertEqual(before, sorted(self.root.rglob("*")))


class TestHandle(NotesCase):
    def test_writes_the_note_in_the_project_folder(self):
        self.claim_project(self.project)
        result = self.handle(load_event("valid-full"), project=True)
        relative = f"05-Projects/03-Packages/Demo/Ecosystem/Plans/{FULL_NAME}"
        self.assertEqual({"status": "ok", "note": relative}, result.to_dict())
        self.assertEqual(FULL_NOTE, (self.vault / relative).read_text(encoding="utf-8"))
        record = json.loads(self.ledger_lines()[0])
        self.assertEqual((("0f1e2d3c4b5a69788796a5b4c3d2e1f0", relative, str(self.vault))),
                         (record["event_id"], record["note"], record["vault"]))
        self.assertEqual([self.vault / relative], self.written())
        self.assertNoTemporaryFiles()

    def test_project_not_in_the_vault_uses_the_fallback_folder(self):
        result = self.handle(load_event("valid-minimal"), project=True)
        self.assertTrue(result.note.startswith("Ecosystem/Plans/2026-10-09 "))
        self.assertIn("project: demo\n", (self.vault / result.note).read_text(encoding="utf-8"))

    def test_no_project_uses_the_fallback_folder_without_a_project_field(self):
        result = self.handle(load_event("valid-minimal"))
        self.assertEqual(MINIMAL_NOTE, (self.vault / result.note).read_text(encoding="utf-8"))

    def test_configured_folders(self):
        self.claim_project(self.project)
        self.project_config('[brain.notes]\nfolder = "Plans/Closed"\n')
        self.configure('[brain.notes]\nfallback_folder = "Inbox/Plans"\n')
        self.assertTrue(self.handle(load_event("valid-minimal"), project=True).note.startswith(
            "05-Projects/03-Packages/Demo/Plans/Closed/"))
        self.assertTrue(self.handle(load_event("valid-additive")).note.startswith("Inbox/Plans/"))

    def test_catalog_folder_outside_the_vault_falls_back_with_a_warning(self):
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        (self.vault / ".projects.json").write_text(json.dumps(
            {"projects": [{"repo": str(self.project), "vault_path": str(elsewhere), "name": "Out"}]}), encoding="utf-8")
        result = self.handle(load_event("valid-minimal"), project=True)
        self.assertTrue(result.note.startswith("Ecosystem/Plans/"))
        self.assertTrue(any(errors.CATALOG_INVALID in w for w in result.warnings), result.warnings)
        self.assertEqual([], list(elsewhere.iterdir()))

    def test_dry_run_writes_nothing(self):
        result = self.handle(load_event("valid-full"), dry_run=True)
        self.assertEqual({"status": "skipped", "reason": "DRY_RUN", "note": f"Ecosystem/Plans/{FULL_NAME}"},
                         result.to_dict())
        self.assertEqual([], self.written())
        self.assertFalse(self.state.exists())

    def test_skips(self):
        self.assertEqual({"status": "skipped", "reason": "EVENT_TYPE_IGNORED"},
                         self.handle(load_event("other-type")).to_dict())
        self.configure('[brain.notes]\nenabled = false\n')
        self.assertEqual({"status": "skipped", "reason": "NOTES_DISABLED"},
                         self.handle(load_event("valid-minimal")).to_dict())
        self.assertEqual([], self.written())

    def test_disabled_notes_skip_even_invalid_events(self):
        self.configure('[brain.notes]\nenabled = false\n')
        self.assertEqual("NOTES_DISABLED", self.handle(load_event("invalid-no-plan-id")).reason)

    def test_no_vault_is_skipped_not_failed(self):
        self.machine_config("")
        self.assertEqual({"status": "skipped", "reason": "VAULT_NOT_CONFIGURED"},
                         self.handle(load_event("valid-minimal")).to_dict())
        self.assertFalse(self.state.exists())

    def test_missing_vault_directory_is_temporary(self):
        self.configure(vault=self.root / "gone")
        with self.assertRaises(BrainError) as caught:
            self.handle(load_event("valid-minimal"))
        self.assertEqual((errors.VAULT_UNAVAILABLE, 75), (caught.exception.code, errors.exit_status(caught.exception.code)))

    @unittest.skipIf(os.geteuid() == 0, "root ignores directory permissions")
    def test_vault_without_write_access_is_temporary(self):
        self.vault.chmod(0o555)
        self.addCleanup(self.vault.chmod, 0o755)
        with self.assertRaises(BrainError) as caught:
            self.handle(load_event("valid-minimal"))
        self.assertEqual(errors.VAULT_UNAVAILABLE, caught.exception.code)

    def test_invalid_data_is_refused_before_the_vault_is_touched(self):
        with self.assertRaises(BrainError) as caught:
            self.handle(load_event("invalid-no-plan-id"))
        self.assertEqual((errors.EVENT_DATA_INVALID, 65), (caught.exception.code, errors.exit_status(caught.exception.code)))
        self.assertEqual([], self.written())


    def test_a_symlinked_vault_with_a_catalog_entry_writes_and_records_the_note(self):
        link = self.root / "vault-link"
        link.symlink_to(self.vault, target_is_directory=True)
        self.configure(vault=link)
        (self.vault / ".projects.json").write_text(json.dumps(
            {"projects": [{"repo": str(self.project), "vault_path": "05-Projects/03-Packages/Demo"}]}),
            encoding="utf-8")
        result = self.handle(load_event("valid-full"), project=True)
        relative = f"05-Projects/03-Packages/Demo/Ecosystem/Plans/{FULL_NAME}"
        self.assertEqual({"status": "ok", "note": relative}, result.to_dict())
        self.assertEqual("DUPLICATE_EVENT", self.handle(load_event("valid-full"), project=True).reason)
        self.assertEqual(1, len(self.ledger_lines()))


class TestIdempotence(NotesCase):
    def test_repeat_gives_one_file_and_duplicate_event(self):
        first = self.handle(load_event("valid-full"))
        second = self.handle(load_event("valid-full"))
        self.assertEqual("ok", first.status)
        self.assertEqual({"status": "skipped", "reason": "DUPLICATE_EVENT", "note": first.note}, second.to_dict())
        self.assertEqual(1, len(self.written()))
        self.assertEqual(1, len(self.ledger_lines()))
        self.assertNoTemporaryFiles()

    def test_lost_ledger_does_not_duplicate_and_is_restored(self):
        first = self.handle(load_event("valid-full"))
        self.ledger.unlink()
        second = self.handle(load_event("valid-full"))
        self.assertEqual(("skipped", "DUPLICATE_EVENT", first.note), (second.status, second.reason, second.note))
        self.assertEqual(1, len(self.written()))
        self.assertEqual(first.note, json.loads(self.ledger_lines()[0])["note"])

    def test_a_note_that_was_written_without_its_ledger_line_is_repaired(self):
        """A crash between the link and the ledger write: the retry finds the note by its event id."""
        with mock.patch.object(notes, "_append_ledger", side_effect=OSError(errno.EIO, "disk")):
            with self.assertRaises(BrainError) as caught:
                self.handle(load_event("valid-full"))
        self.assertEqual(errors.NOTE_IO, caught.exception.code)
        self.assertEqual(1, len(self.written()))
        self.assertEqual([], self.ledger_lines())
        again = self.handle(load_event("valid-full"))
        self.assertEqual("DUPLICATE_EVENT", again.reason)
        self.assertEqual(1, len(self.written()))
        self.assertEqual(1, len(self.ledger_lines()))

    def test_a_note_moved_by_a_person_is_not_created_again(self):
        first = self.handle(load_event("valid-full"))
        moved = self.vault / "Archive" / "closed.md"
        moved.parent.mkdir()
        (self.vault / first.note).rename(moved)
        again = self.handle(load_event("valid-full"))
        self.assertEqual(("skipped", "DUPLICATE_EVENT"), (again.status, again.reason))
        self.assertEqual([moved], self.written())

    def test_the_same_event_in_another_vault_is_a_new_note(self):
        self.handle(load_event("valid-full"))
        other = self.root / "other-vault"
        shutil.copytree(FIXTURE, other)
        self.configure(vault=other)
        self.assertEqual("ok", self.handle(load_event("valid-full")).status)
        self.assertEqual(1, len(self.written(other)))
        self.assertEqual(2, len(self.ledger_lines()))

    def test_a_person_file_with_the_same_name_is_never_replaced(self):
        config = settings.load(None, env=self.env, home=self.home)
        path = notes.note_path(config, self.vault, None, plan_of("valid-full"))
        path.parent.mkdir(parents=True)
        path.write_text("My own notes.\n", encoding="utf-8")
        os.utime(path, (1_000_000_000, 1_000_000_000))
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        result = self.handle(load_event("valid-full"))
        self.assertEqual(f"Ecosystem/Plans/{path.stem} (2).md", result.note)
        self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))
        self.assertEqual(FULL_NOTE.replace("project: Demo\n", "").replace("(2)", ""),
                         (self.vault / result.note).read_text(encoding="utf-8"))
        # the repeat finds the suffixed note by the ledger; with the ledger gone, by its event id
        self.assertEqual("DUPLICATE_EVENT", self.handle(load_event("valid-full")).reason)
        self.ledger.unlink()
        again = self.handle(load_event("valid-full"))
        self.assertEqual(("DUPLICATE_EVENT", result.note), (again.reason, again.note))
        self.assertEqual(2, len(list(path.parent.iterdir())))

    def test_the_suffix_skips_taken_names(self):
        config = settings.load(None, env=self.env, home=self.home)
        path = notes.note_path(config, self.vault, None, plan_of("valid-full"))
        path.parent.mkdir(parents=True)
        path.write_text("one\n", encoding="utf-8")
        path.with_name(f"{path.stem} (2).md").write_text("two\n", encoding="utf-8")
        self.assertEqual(f"Ecosystem/Plans/{path.stem} (3).md", self.handle(load_event("valid-full")).note)

    def test_no_hard_links_falls_back_to_an_exclusive_create(self):
        with mock.patch("brain.notes.os.link", side_effect=OSError(errno.EPERM, "not permitted")):
            result = self.handle(load_event("valid-full"))
        self.assertEqual(FULL_NOTE.replace("project: Demo\n", ""), (self.vault / result.note).read_text(encoding="utf-8"))
        self.assertNoTemporaryFiles()
        self.assertEqual("DUPLICATE_EVENT", self.handle(load_event("valid-full")).reason)

    def test_other_link_errors_are_temporary_failures(self):
        with mock.patch("brain.notes.os.link", side_effect=OSError(errno.EIO, "disk")):
            with self.assertRaises(BrainError) as caught:
                self.handle(load_event("valid-full"))
        self.assertEqual(errors.NOTE_IO, caught.exception.code)
        self.assertEqual([], self.written())
        self.assertNoTemporaryFiles()
        self.assertEqual("ok", self.handle(load_event("valid-full")).status)  # the retry succeeds

    def test_a_file_at_the_old_temporary_name_is_never_removed(self):
        folder = self.vault / "Ecosystem" / "Plans"
        folder.mkdir(parents=True)
        foreign = folder / f"{FULL_NAME}.tmp-{os.getpid()}"
        foreign.write_text("USER-VAULT-FILE do not delete", encoding="utf-8")
        self.assertEqual("ok", self.handle(load_event("valid-full")).status)
        self.assertEqual("USER-VAULT-FILE do not delete", foreign.read_text(encoding="utf-8"))
        self.assertEqual([self.vault / "Ecosystem" / "Plans" / FULL_NAME], self.written())

    def test_the_fallback_write_completes_after_short_writes(self):
        real_write = os.write

        def short_write(fd, data):
            return real_write(fd, bytes(data)[:100])

        with mock.patch("brain.notes.os.link", side_effect=OSError(errno.EPERM, "not permitted")), \
                mock.patch("brain.notes.os.write", side_effect=short_write):
            result = self.handle(load_event("valid-full"))
        self.assertEqual(FULL_NOTE.replace("project: Demo\n", ""), (self.vault / result.note).read_text(encoding="utf-8"))
        self.assertEqual("DUPLICATE_EVENT", self.handle(load_event("valid-full")).reason)

    def test_a_failed_fallback_write_leaves_no_file_and_the_retry_keeps_the_name(self):
        real_write = os.write
        calls = []

        def failing_write(fd, data):
            calls.append(fd)
            if len(calls) >= 2:  # the first call fills the temporary file, the second is the in-place write
                raise OSError(errno.ENOSPC, "no space left on device")
            return real_write(fd, data)

        with mock.patch("brain.notes.os.link", side_effect=OSError(errno.EPERM, "not permitted")), \
                mock.patch("brain.notes.os.write", side_effect=failing_write):
            with self.assertRaises(BrainError) as caught:
                self.handle(load_event("valid-full"))
        self.assertEqual(errors.NOTE_IO, caught.exception.code)
        self.assertEqual([], self.written())
        self.assertNoTemporaryFiles()
        self.assertEqual(f"Ecosystem/Plans/{FULL_NAME}", self.handle(load_event("valid-full")).note)


    def test_a_failed_fallback_write_never_removes_a_file_put_at_the_name_meanwhile(self):
        real_write = os.write
        calls = []
        target = self.vault / "Ecosystem" / "Plans" / FULL_NAME

        def swapping_write(fd, data):
            calls.append(fd)
            if len(calls) >= 2:
                target.rename(target.with_name(FULL_NAME + ".ours"))
                target.write_text("USER-REPLACEMENT do not delete", encoding="utf-8")
                raise OSError(errno.ENOSPC, "no space left on device")
            return real_write(fd, data)

        with mock.patch("brain.notes.os.link", side_effect=OSError(errno.EPERM, "not permitted")), \
                mock.patch("brain.notes.os.write", side_effect=swapping_write):
            with self.assertRaises(BrainError):
                self.handle(load_event("valid-full"))
        self.assertEqual("USER-REPLACEMENT do not delete", target.read_text(encoding="utf-8"))

    def test_a_note_that_links_outside_the_vault_is_recorded_once_under_its_name_in_the_vault(self):
        folder = self.vault / "Ecosystem" / "Plans"
        folder.mkdir(parents=True)
        (folder / FULL_NAME).write_text("a file of the user\n", encoding="utf-8")
        outside = self.root / "outside.md"
        outside.write_text("---\nevent_id: 0f1e2d3c4b5a69788796a5b4c3d2e1f0\n---\nbody\n", encoding="utf-8")
        (folder / FULL_NAME.replace(".md", " (2).md")).symlink_to(outside)
        for _ in range(2):
            result = self.handle(load_event("valid-full"))
            self.assertEqual(("skipped", "DUPLICATE_EVENT"), (result.status, result.reason))
        lines = self.ledger_lines()
        self.assertEqual(1, len(lines))
        self.assertEqual("Ecosystem/Plans/" + FULL_NAME.replace(".md", " (2).md"), json.loads(lines[0])["note"])


class TestLedger(NotesCase):
    def test_a_broken_line_is_skipped_with_a_warning(self):
        self.handle(load_event("valid-full"))
        with open(self.ledger, "a", encoding="utf-8") as handle:
            handle.write("not json\n")
        result = self.handle(load_event("valid-additive"))
        self.assertEqual("ok", result.status)
        self.assertTrue(any("line 2" in w for w in result.warnings), result.warnings)
        self.assertEqual("DUPLICATE_EVENT", self.handle(load_event("valid-full")).reason)

    def test_a_torn_last_line_does_not_swallow_the_next_record(self):
        self.state.mkdir(parents=True)
        self.ledger.write_bytes(b'{"event_id": "x')
        self.assertEqual("ok", self.handle(load_event("valid-full")).status)
        lines = self.ledger_lines()
        self.assertEqual(2, len(lines))
        self.assertEqual("0f1e2d3c4b5a69788796a5b4c3d2e1f0", json.loads(lines[1])["event_id"])

    def test_the_ledger_and_lock_are_private(self):
        self.handle(load_event("valid-full"))
        self.assertEqual(0o600, self.ledger.stat().st_mode & 0o777)
        self.assertEqual(0o600, (self.state / "notes.lock").stat().st_mode & 0o777)

    def test_writing_needs_the_lock(self):
        with notes._ledger_lock(self.state) as lock:
            self.assertTrue(lock.held)
        self.assertFalse(lock.held)
        with self.assertRaises(RuntimeError):
            notes._write_once(lock, self.vault / "x.md", "x", "e", vault=self.vault, now=NOW)
        with self.assertRaises(RuntimeError):
            notes._append_ledger(lock, {"event_id": "e"})
        with self.assertRaises(RuntimeError):
            notes._create_new(lock, self.vault / "y.md", "y")
        self.assertFalse((self.vault / "x.md").exists() or (self.vault / "y.md").exists())

    def test_a_busy_lock_is_a_temporary_failure_after_the_deadline(self):
        with notes._ledger_lock(self.state):
            started = datetime.datetime.now()
            with self.assertRaises(BrainError) as caught:
                self.handle(load_event("valid-full"), lock_deadline_s=0.2)
        self.assertLess((datetime.datetime.now() - started).total_seconds(), 5)
        self.assertEqual((errors.LEDGER_LOCKED, 75), (caught.exception.code, errors.exit_status(caught.exception.code)))
        self.assertEqual([], self.written())
        self.assertEqual("ok", self.handle(load_event("valid-full")).status)  # free again: the delivery retries

    @unittest.skipIf(os.geteuid() == 0, "root ignores directory permissions")
    def test_an_unwritable_notes_folder_is_a_temporary_failure_and_leaves_no_trace(self):
        first = self.handle(load_event("valid-minimal"))
        folder = (self.vault / first.note).parent
        folder.chmod(0o555)
        self.addCleanup(folder.chmod, 0o755)
        with self.assertRaises(BrainError) as caught:
            self.handle(load_event("valid-full"))
        self.assertEqual((errors.NOTE_IO, 75), (caught.exception.code, errors.exit_status(caught.exception.code)))
        self.assertEqual(1, len(self.ledger_lines()))
        folder.chmod(0o755)
        self.assertEqual("ok", self.handle(load_event("valid-full")).status)
        self.assertEqual(2, len(self.written()))
        self.assertNoTemporaryFiles()


class TestConcurrency(NotesCase):
    def test_two_processes_with_repeats_write_each_note_once(self):
        docs = [numbered_event(index) for index in range(20)]
        context = multiprocessing.get_context("fork")
        workers = [context.Process(target=_worker, args=(str(self.root), self.env, self.home, docs))
                   for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(60)
        self.assertEqual([0, 0], [worker.exitcode for worker in workers])
        self.assertEqual(20, len(self.written()))
        lines = [json.loads(line) for line in self.ledger_lines()]
        self.assertEqual(20, len(lines))
        self.assertEqual(20, len({line["event_id"] for line in lines}))
        self.assertEqual(sorted(line["note"] for line in lines),
                         sorted(p.relative_to(self.vault).as_posix() for p in self.written()))
        self.assertNoTemporaryFiles()

    def test_notes_do_not_change_when_nothing_is_written(self):
        first = self.handle(load_event("valid-full"))
        path = self.vault / first.note
        os.utime(path, (1_000_000_000, 1_000_000_000))
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        for _ in range(3):
            self.handle(load_event("valid-full"))
        self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))


class TestAnnouncement(NotesCase):
    def created_events(self):
        found, problems = read_events(self.project, types=["brain.note.created"], env=self.env, home=self.home)
        self.assertEqual([], problems)
        return found

    def test_a_new_note_emits_brain_note_created_with_causation(self):
        result = self.handle(load_event("valid-full"), root=self.project)
        (event,) = self.created_events()
        self.assertEqual("urn:swissknifeman:module:brain", event.source)
        self.assertEqual("2026.01.15-DEMO-PLAN", event.subject)
        self.assertEqual("0f1e2d3c4b5a69788796a5b4c3d2e1f0", event.causationid)
        self.assertEqual({"note": result.note, "plan_id": "2026.01.15-DEMO-PLAN",
                          "event_id": "0f1e2d3c4b5a69788796a5b4c3d2e1f0"}, event.data)

    def test_nothing_is_emitted_for_a_repeat_a_skip_or_a_dry_run(self):
        self.handle(load_event("valid-full"), root=self.project)
        self.handle(load_event("valid-full"), root=self.project)
        self.handle(load_event("other-type"), root=self.project)
        self.handle(load_event("valid-minimal"), root=self.project, dry_run=True)
        self.assertEqual(1, len(self.created_events()))

    def test_a_failing_emit_does_not_change_the_answer(self):
        with mock.patch.object(notes, "_emit", side_effect=RuntimeError("journal gone")):
            result = self.handle(load_event("valid-full"), root=self.project)
        self.assertEqual("ok", result.status)
        self.assertTrue(any("brain.note.created was not emitted" in w for w in result.warnings), result.warnings)
        self.assertEqual(1, len(self.written()))


if __name__ == "__main__":
    unittest.main()
