import multiprocessing
import os
import tempfile
import unittest
from pathlib import Path
import sys
from unittest import mock

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task import plan_projection


def _projection_writer(path, expected, barrier, queue):
    barrier.wait()
    try:
        queue.put(("ok", plan_projection.write_or_check(path, expected, check=False)))
    except Exception as exc:  # pragma: no cover - child diagnostic
        queue.put(("error", repr(exc)))


class PlanProjectionTest(unittest.TestCase):
    def test_write_and_check_reject_symlink_without_touching_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            external = root / "external.md"
            external.write_text("outside\n", encoding="utf-8")
            link = root / "view.md"
            link.symlink_to(external)
            for check in (False, True):
                with self.subTest(check=check), self.assertRaises(plan_projection.ProjectionError):
                    plan_projection.write_or_check(link, "outside\n", check=check)
            self.assertEqual(external.read_text(encoding="utf-8"), "outside\n")

    def test_publish_syncs_file_before_replace_and_directory_after(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "view.md"
            events = []
            real_fsync, real_replace = os.fsync, os.replace

            def fsync(fd):
                events.append("dir-fsync" if os.path.isdir(f"/proc/self/fd/{fd}") else "file-fsync")
                return real_fsync(fd)

            def replace(*args, **kwargs):
                events.append("replace")
                return real_replace(*args, **kwargs)

            with mock.patch.object(plan_projection.os, "fsync", side_effect=fsync), \
                    mock.patch.object(plan_projection.os, "replace", side_effect=replace):
                self.assertTrue(plan_projection.write_or_check(path, "expected\n", check=False))
            self.assertLess(events.index("file-fsync"), events.index("replace"))
            self.assertLess(events.index("replace"), events.index("dir-fsync"))

    def test_concurrent_publishers_serialize_complete_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "view.md"
            context = multiprocessing.get_context("fork")
            barrier, queue = context.Barrier(2), context.Queue()
            processes = [context.Process(
                target=_projection_writer, args=(path, "expected\n", barrier, queue))
                for _ in range(2)]
            for process in processes:
                process.start()
            results = [queue.get(timeout=5) for _ in processes]
            for process in processes:
                process.join(timeout=5)
                self.assertEqual(process.exitcode, 0)
            self.assertTrue(all(result[0] == "ok" for result in results), results)
            self.assertEqual(path.read_text(encoding="utf-8"), "expected\n")

    def test_inputs_hash_is_order_independent_and_content_sensitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, second = root / "a.md", root / "b.md"
            first.write_text("a", encoding="utf-8")
            second.write_text("b", encoding="utf-8")
            one = plan_projection.inputs_sha256((first, second), root=root)
            self.assertEqual(one, plan_projection.inputs_sha256((second, first), root=root))
            second.write_text("changed", encoding="utf-8")
            self.assertNotEqual(one, plan_projection.inputs_sha256((first, second), root=root))

    def test_check_compares_regenerated_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "view.md"
            plan_projection.write_or_check(path, "expected\n", check=False)
            self.assertFalse(plan_projection.write_or_check(path, "expected\n", check=True))
            path.write_text("manual edit\n", encoding="utf-8")
            with self.assertRaises(plan_projection.ProjectionError):
                plan_projection.write_or_check(path, "expected\n", check=True)
