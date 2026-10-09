"""aicore.ext.overlays: slots of modules, files by layer, the marked block, limits, warnings and the CLI."""
import json
import unittest

from aicore.ext import overlays
from aicore.ext.errors import CODES, ExtError

from tests.ext.support import TempCase, run_cli

SLOT = "demo:plan"


class OverlayCase(TempCase):
    def setUp(self):
        super().setUp()
        self.env.pop("SKM_AICORE_EVENTS__DELIVERY")

    def machine(self, text):
        path = self.tmp / "skm" / "config" / "config.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("schema_version = 1\n" + text, encoding="utf-8")
        return path

    def project_file(self, text):
        path = self.project / ".swissknifeman" / "config.toml"
        path.write_text("schema_version = 1\n" + text, encoding="utf-8")
        return path

    def write(self, where, text, binary=False):
        where.parent.mkdir(parents=True, exist_ok=True)
        if binary:
            where.write_bytes(text)
        else:
            where.write_text(text, encoding="utf-8")
        return where

    def resolve(self, slot=SLOT, **kwargs):
        return overlays.resolve_overlays(slot, project=self.project, env=self.env, home=self.home, **kwargs)

    def cli(self, *argv):
        return run_cli("ext", "overlays", *argv, env=self.env, cwd=self.project)


class TestSlots(OverlayCase):
    def test_a_declared_slot_without_files_is_empty(self):
        found = self.resolve()
        self.assertEqual((found.slot, found.items, found.warnings), (SLOT, (), ()))
        self.assertEqual(overlays.render_overlays(found), "")

    def test_unknown_module_slot_and_shape(self):
        for slot in ("nomodule:plan", "demo:other", "demo", "Demo:plan", "demo:plan:x", ""):
            with self.subTest(slot):
                with self.assertRaises(ExtError) as caught:
                    self.resolve(slot)
                self.assertEqual(caught.exception.code, "OVERLAY_SLOT_UNKNOWN")
        self.assertIn("demo:plan", caught.exception.message)

    def test_no_modules_at_all(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        self.env["SKM_UNITS_PATH"] = str(empty)
        with self.assertRaises(ExtError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "OVERLAY_SLOT_UNKNOWN")
        self.assertIn("none", caught.exception.message)

    def test_a_slot_configured_but_not_declared_is_refused(self):
        self.machine('[aicore.overlays]\n"demo:typo" = ["/x.md"]\n')
        with self.assertRaises(ExtError) as caught:
            self.resolve("demo:typo")
        self.assertEqual(caught.exception.code, "OVERLAY_SLOT_UNKNOWN")

    def test_codes_are_registered(self):
        for code in ("OVERLAY_SLOT_UNKNOWN", "OVERLAY_TOO_LARGE", "OVERLAY_MISSING", "OVERLAY_INVALID"):
            self.assertIn(code, CODES)


class TestSources(OverlayCase):
    def test_machine_files_in_array_order(self):
        first = self.write(self.tmp / "a.md", "first\n")
        second = self.write(self.tmp / "b.md", "second")
        self.machine(f'[aicore.overlays]\n"{SLOT}" = [{json.dumps(str(second))}, {json.dumps(str(first))}]\n')
        found = self.resolve()
        self.assertEqual([(item.path, item.layer, item.text) for item in found.items],
                         [(second, "machine", "second"), (first, "machine", "first\n")])
        self.assertEqual(found.warnings, ())
        self.assertTrue(all(item.digest.startswith("sha256:") for item in found.items))
        self.assertNotEqual(found.items[0].digest, found.items[1].digest)

    def test_the_project_array_replaces_the_machine_array(self):
        machine_file = self.write(self.tmp / "machine.md", "machine\n")
        project_file = self.write(self.project / "rules" / "project.md", "project\n")
        self.machine(f'[aicore.overlays]\n"{SLOT}" = [{json.dumps(str(machine_file))}]\n')
        self.project_file(f'[aicore.overlays]\n"{SLOT}" = ["../rules/project.md"]\n')
        found = self.resolve()
        self.assertEqual([(item.path.name, item.layer) for item in found.items], [("project.md", "project")])
        self.assertEqual(found.items[0].path.resolve(), project_file.resolve())

    def test_append_from_the_project_keeps_the_machine_files_first(self):
        machine_file = self.write(self.tmp / "machine.md", "machine\n")
        self.write(self.project / ".swissknifeman" / "extra.md", "project\n")
        self.machine(f'[aicore.overlays]\n"{SLOT}" = [{json.dumps(str(machine_file))}]\n')
        self.project_file(f'[aicore]\n_append = {{"overlays.{SLOT}" = ["extra.md"]}}\n')
        found = self.resolve()
        self.assertEqual([(item.path.name, item.layer, item.text) for item in found.items],
                         [("machine.md", "machine", "machine\n"), ("extra.md", "project", "project\n")])

    def test_a_relative_path_is_taken_from_the_file_of_the_layer(self):
        self.write(self.tmp / "skm" / "config" / "rules" / "r.md", "relative\n")
        self.machine(f'[aicore.overlays]\n"{SLOT}" = ["rules/r.md"]\n')
        found = self.resolve()
        self.assertEqual([item.text for item in found.items], ["relative\n"])
        self.assertEqual(found.items[0].path, self.tmp / "skm" / "config" / "rules" / "r.md")

    def test_tilde_is_expanded(self):
        self.write(self.home / "rules" / "h.md", "home\n")
        self.machine(f'[aicore.overlays]\n"{SLOT}" = ["~/rules/h.md"]\n')
        self.assertEqual([item.text for item in self.resolve().items], ["home\n"])

    def test_the_invocation_file_overrides(self):
        low = self.write(self.tmp / "low.md", "low\n")
        high = self.write(self.tmp / "high.md", "high\n")
        self.machine(f'[aicore.overlays]\n"{SLOT}" = [{json.dumps(str(low))}]\n')
        extra = self.tmp / "invocation.toml"
        extra.write_text(f'schema_version = 1\n[aicore.overlays]\n"{SLOT}" = [{json.dumps(str(high))}]\n',
                         encoding="utf-8")
        found = self.resolve(config_file=extra)
        self.assertEqual([(item.text, item.layer) for item in found.items], [("high\n", "invocation")])

    def test_a_broken_configuration_is_config_invalid(self):
        self.machine(f'[aicore.overlays]\n"{SLOT}" = "not-a-list"\n')
        with self.assertRaises(ExtError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")


class TestWarnings(OverlayCase):
    def test_missing_file_is_a_warning_and_is_skipped(self):
        present = self.write(self.tmp / "present.md", "here\n")
        self.machine(f'[aicore.overlays]\n"{SLOT}" = ["~/gone.md", {json.dumps(str(present))}]\n')
        found = self.resolve()
        self.assertEqual([item.text for item in found.items], ["here\n"])
        self.assertEqual([(item["code"], item["path"]) for item in found.warnings], [("OVERLAY_MISSING", "~/gone.md")])

    def test_not_utf8_and_unreadable_are_invalid(self):
        bad = self.write(self.tmp / "bad.md", b"\xff\xfe text", binary=True)
        directory = self.tmp / "folder"
        directory.mkdir()
        self.machine(f'[aicore.overlays]\n"{SLOT}" = [{json.dumps(str(bad))}, {json.dumps(str(directory))}]\n')
        found = self.resolve()
        self.assertEqual(found.items, ())
        self.assertEqual([item["code"] for item in found.warnings], ["OVERLAY_INVALID", "OVERLAY_INVALID"])

    def test_the_project_cannot_pull_in_files_outside_itself(self):
        outside = self.write(self.tmp / "secret.md", "SENTINEL\n")
        inside = self.write(self.project / "docs" / "ok.md", "ok\n")
        escape = self.project / "docs" / "escape.md"
        escape.symlink_to(outside)
        self.project_file(f'[aicore.overlays]\n"{SLOT}" = [{json.dumps(str(outside))}, "../../../skm/x.md", '
                          f'"../docs/escape.md", "../docs/ok.md"]\n')
        found = self.resolve()
        self.assertEqual([(item.path.name, item.text) for item in found.items], [("ok.md", "ok\n")])
        self.assertEqual([item["code"] for item in found.warnings], ["OVERLAY_INVALID"] * 3)
        self.assertNotIn("SENTINEL", repr(found))

    def test_the_machine_may_name_any_file(self):
        outside = self.write(self.tmp / "anywhere.md", "ok\n")
        self.machine(f'[aicore.overlays]\n"{SLOT}" = [{json.dumps(str(outside))}]\n')
        self.assertEqual(len(self.resolve().items), 1)

    def test_without_a_project_the_project_layer_does_not_exist(self):
        outside = self.write(self.tmp / "m.md", "m\n")
        self.machine(f'[aicore.overlays]\n"{SLOT}" = [{json.dumps(str(outside))}]\n')
        found = overlays.resolve_overlays(SLOT, project=None, env=self.env, home=self.home)
        self.assertEqual([item.text for item in found.items], ["m\n"])


class TestLimit(OverlayCase):
    def files(self, *sizes):
        paths = [self.write(self.tmp / f"f{index}.md", "x" * size) for index, size in enumerate(sizes)]
        self.machine(f'[aicore.overlays]\n"{SLOT}" = [{", ".join(json.dumps(str(path)) for path in paths)}]\n')

    def test_exactly_the_limit_passes(self):
        self.files(16384, 16384)
        self.assertEqual(sum(item.size for item in self.resolve().items), overlays.MAX_BYTES)

    def test_one_byte_more_is_refused(self):
        self.files(16384, 16385)
        with self.assertRaises(ExtError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "OVERLAY_TOO_LARGE")

    def test_the_limit_counts_bytes_not_characters(self):
        self.write(self.tmp / "wide.md", "é" * 16385)  # 32770 bytes
        self.machine(f'[aicore.overlays]\n"{SLOT}" = [{json.dumps(str(self.tmp / "wide.md"))}]\n')
        with self.assertRaises(ExtError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "OVERLAY_TOO_LARGE")

    def test_a_huge_file_is_not_read_whole(self):
        self.files(5 * 1024 * 1024)
        with self.assertRaises(ExtError):
            self.resolve()


class TestRender(OverlayCase):
    def test_exact_block(self):
        self.write(self.home / "rules" / "a.md", "Always write tests first.\n")
        self.write(self.tmp / "b.md", "no newline at the end")
        self.machine(f'[aicore.overlays]\n"{SLOT}" = ["~/rules/a.md", {json.dumps(str(self.tmp / "b.md"))}]\n')
        text = overlays.render_overlays(self.resolve())
        self.assertEqual(text, "<!-- overlays: demo:plan -->\n"
                               "<!-- overlay: ~/rules/a.md (machine) -->\n"
                               "Always write tests first.\n"
                               f"<!-- overlay: {self.tmp}/b.md (machine) -->\n"
                               "no newline at the end\n"
                               "<!-- end overlays: demo:plan -->\n")

    def test_the_home_directory_is_never_printed(self):
        self.write(self.home / "rules" / "a.md", "text\n")
        self.machine(f'[aicore.overlays]\n"{SLOT}" = [{json.dumps(str(self.home / "rules" / "a.md"))}, '
                     f'{json.dumps(str(self.home / "rules" / "gone.md"))}]\n')
        found = self.resolve()
        printed = overlays.render_overlays(found) + json.dumps(overlays.describe_overlays(found))
        self.assertNotIn(str(self.home), printed)
        self.assertIn("~/rules/a.md", printed)

    def test_a_path_cannot_close_the_comment(self):
        odd = self.write(self.tmp / "a --> b.md", "text\n")
        self.machine(f'[aicore.overlays]\n"{SLOT}" = [{json.dumps(str(odd))}]\n')
        header = overlays.render_overlays(self.resolve()).splitlines()[1]
        self.assertEqual(header.count("-->"), 1)
        self.assertTrue(header.endswith("(machine) -->"))

    def test_describe(self):
        self.write(self.tmp / "a.md", "héllo\n")
        self.machine(f'[aicore.overlays]\n"{SLOT}" = [{json.dumps(str(self.tmp / "a.md"))}, "~/gone.md"]\n')
        found = self.resolve()
        document = overlays.describe_overlays(found)
        self.assertEqual(document["slot"], SLOT)
        self.assertEqual(document["overlays"], [{"path": f"{self.tmp}/a.md", "layer": "machine",
                                                 "digest": found.items[0].digest, "bytes": 7}])
        self.assertEqual([item["code"] for item in document["warnings"]], ["OVERLAY_MISSING"])


class TestCli(OverlayCase):
    def setUp(self):
        super().setUp()
        self.write(self.tmp / "rule.md", "Always write tests first.\n")
        self.machine(f'[aicore.overlays]\n"{SLOT}" = [{json.dumps(str(self.tmp / "rule.md"))}]\n')

    def test_prints_the_block(self):
        code, out, err = self.cli(SLOT)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Always write tests first.\n", out)
        self.assertTrue(out.startswith("<!-- overlays: demo:plan -->\n"))
        self.assertTrue(out.endswith("<!-- end overlays: demo:plan -->\n"))

    def test_unknown_slot_exits_1(self):
        code, out, err = self.cli("demo:nope")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("OVERLAY_SLOT_UNKNOWN", err)

    def test_warnings_go_to_stderr_and_strict_makes_them_fail(self):
        self.machine(f'[aicore.overlays]\n"{SLOT}" = [{json.dumps(str(self.tmp / "rule.md"))}, "~/gone.md"]\n')
        code, out, err = self.cli(SLOT)
        self.assertEqual(code, 0)
        self.assertIn("Always write tests first.", out)
        self.assertIn("OVERLAY_MISSING", err)
        self.assertNotIn("OVERLAY_MISSING", out)
        code, out, err = self.cli(SLOT, "--strict")
        self.assertEqual(code, 1)
        self.assertIn("Always write tests first.", out)

    def test_strict_without_warnings_is_fine(self):
        self.assertEqual(self.cli(SLOT, "--strict")[0], 0)

    def test_json(self):
        code, out, err = self.cli(SLOT, "--json")
        self.assertEqual((code, err), (0, ""))
        document = json.loads(out)
        self.assertEqual(document["slot"], SLOT)
        self.assertEqual([(item["layer"], item["bytes"]) for item in document["overlays"]], [("machine", 26)])
        self.assertEqual(document["warnings"], [])

    def test_too_large_exits_1(self):
        self.write(self.tmp / "big.md", "x" * 40000)
        self.machine(f'[aicore.overlays]\n"{SLOT}" = [{json.dumps(str(self.tmp / "big.md"))}]\n')
        code, _out, err = self.cli(SLOT)
        self.assertEqual(code, 1)
        self.assertIn("OVERLAY_TOO_LARGE", err)

    def test_an_empty_slot_prints_nothing(self):
        self.machine("")
        self.assertEqual(self.cli(SLOT), (0, "", ""))

    def test_the_group_lists_overlays(self):
        code, out, _err = run_cli("--help")
        self.assertIn("plugins, overlays, status", out)
        self.assertEqual(run_cli("ext", "--help", env=self.env)[0], 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
