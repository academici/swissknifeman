"""Stubs (instruction overlays): the layers and slots resolve deterministically, an empty published file masks nothing,
the modes replace, append and disable act on one slot, unsafe files are refused before anything reads them, and
publishing never overwrites a file."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from aicore import stubs  # noqa: E402

T = "orch.role.reviewer"


class StubCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.env = {"SKM_HOME": str(root / "skm")}
        self.project = root / "project"
        self.machine_root = root / "skm" / "config" / "stubs"
        self.project_root = self.project / ".swissknifeman" / "stubs"

    def write(self, layer: str, slot: str, text: str) -> Path:
        path = (self.machine_root if layer == "machine" else self.project_root) / slot
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
        return path

    def text(self, target: str = T, **kwargs) -> str:
        return stubs.resolve([target], self.project, env=self.env, **kwargs)[target]["text"]


class ResolveTests(StubCase):
    def test_nothing_published_gives_nothing(self):
        self.assertEqual(self.text(), "")
        self.assertEqual(stubs.snapshot([T], self.project, env=self.env)["targets"], {})

    def test_slots_join_from_the_general_to_the_specific(self):
        self.write("machine", "_all.md", "every role\n")
        self.write("machine", "orch/roles/reviewer.md", "reviewer only\n")
        self.write("project", "orch/_all.md", "orch roles of this project\n")
        self.assertEqual(self.text(), "every role\n\norch roles of this project\n\nreviewer only\n")
        self.assertEqual(self.text("orch.role.executor"), "every role\n\norch roles of this project\n")

    def test_an_empty_published_project_file_inherits(self):
        self.write("machine", "orch/roles/reviewer.md", "machine rule\n")
        self.write("project", "orch/roles/reviewer.md", stubs.template(T, "orch/roles/reviewer.md"))
        found = stubs.resolve([T], self.project, env=self.env)[T]
        self.assertEqual(found["text"], "machine rule\n")
        self.assertEqual([part["reason"] for part in found["parts"]], ["inherited"])
        self.assertEqual([row["reason"] for row in found["skipped"]], ["empty"])

    def test_replace_append_and_disable_act_on_their_slot_only(self):
        self.write("machine", "_all.md", "global\n")
        self.write("machine", "orch/roles/_all.md", "roles\n")
        self.write("machine", "orch/roles/reviewer.md", "machine reviewer\n")
        self.write("project", "orch/roles/reviewer.md", "project reviewer\n")  # replace by default
        self.write("project", "orch/roles/_all.md", "<!-- skm-stub:v1 target=orch.roles._all mode=append -->\nmore\n")
        self.write("project", "_all.md", "<!-- skm-stub:v1 target=_all mode=disable -->\n")
        self.assertEqual(self.text(), "roles\n\nmore\n\nproject reviewer\n")

    def test_comments_crlf_and_bom_are_normalised_and_text_stays_literal(self):
        self.write("project", "orch/roles/reviewer.md", b"\xef\xbb\xbf<!-- note -->\r\nUse ${TOKEN} literally\r\n")
        self.assertEqual(self.text(), "Use ${TOKEN} literally\n")

    def test_the_project_layer_can_be_left_out(self):
        self.write("project", "orch/roles/reviewer.md", "project rule\n")
        self.write("machine", "orch/roles/reviewer.md", "machine rule\n")
        self.assertEqual(self.text(layers=("machine",)), "machine rule\n")

    def test_the_snapshot_digest_follows_the_effective_text(self):
        self.write("project", "orch/roles/reviewer.md", "one\n")
        first = stubs.snapshot([T], self.project, env=self.env)
        self.assertEqual(first["digest"], stubs.snapshot([T], self.project, env=self.env)["digest"])
        self.write("project", "orch/roles/reviewer.md", "<!-- changed comment -->\none\n")
        self.assertNotEqual(stubs.snapshot([T], self.project, env=self.env)["targets"][T]["parts"][0]["path"], "")
        self.write("project", "orch/roles/reviewer.md", "two\n")
        self.assertNotEqual(first["digest"], stubs.snapshot([T], self.project, env=self.env)["digest"])


class WorkspaceProjectTests(StubCase):
    def setUp(self):
        super().setUp()
        marker = self.project / ".swissknifeman" / "project.json"
        marker.parent.mkdir(parents=True)
        marker.write_text('{"workspace": "ws", "project_id": "alpha", "plans_store": "workspace"}')
        self.local = Path(self.tmp.name) / "skm" / "workspaces" / "ws" / "projects" / "alpha" / "local"
        self.local.parent.mkdir(parents=True)

    def test_the_project_stubs_live_in_the_local_folder_of_the_workspace_project(self):
        self.assertEqual(stubs.roots(self.project, env=self.env)["project"], self.local / "stubs")
        self.write("machine", "_all.md", "machine\n")
        self.write("project", "_all.md", "from the checkout\n")
        (self.local / "stubs").mkdir(parents=True)
        (self.local / "stubs" / "_all.md").write_text("from the workspace\n", encoding="utf-8")
        self.assertEqual(self.text(layers=("project",)), "from the workspace\n")

    def test_without_the_workspace_project_the_stubs_stay_in_the_checkout(self):
        self.local.parent.rmdir()
        self.assertEqual(stubs.roots(self.project, env=self.env)["project"], self.project_root)


class VariantTests(StubCase):
    def resolve(self, *variants, **kwargs):
        return stubs.resolve([T], self.project, env=self.env, variants={T: variants}, **kwargs)[T]

    def test_variant_parts_keep_the_base_target_and_text(self):
        self.write("machine", "_all.md", "common\n")
        self.write("machine", "orch/roles/reviewer@codex.md",
                   "<!-- skm-stub:v1 target=orch.role.reviewer@codex -->\ncodex rule\n")
        found = self.resolve("codex", "codex")
        self.assertEqual(found["text"], "common\n")
        self.assertNotIn("variant", found["parts"][0])
        self.assertNotIn("body", found["parts"][0])
        self.assertEqual(found["parts"][1]["variant"], "codex")
        self.assertEqual(found["parts"][1]["body"], "codex rule\n")
        self.assertEqual(len(found["parts"]), 2)
        snap = stubs.snapshot([T], self.project, env=self.env, variants={T: ["codex"]})
        self.assertEqual(snap["targets"], {T: {key: found[key] for key in ("text", "parts")}})
        self.assertNotEqual(snap["digest"], stubs.snapshot([T], self.project, env=self.env)["digest"])

    def test_the_size_limit_counts_the_common_parts_and_the_largest_variant_one_route_takes(self):
        kb = 1024
        self.write("machine", "orch/roles/reviewer.md", "c" * (20 * kb))
        self.write("machine", "orch/roles/reviewer@codex.md", "x" * (25 * kb))
        self.write("machine", "orch/roles/reviewer@claude-code.md", "y" * (25 * kb))
        self.write("machine", "orch/roles/reviewer@claude-code--opus.md", "z" * (10 * kb))
        found = self.resolve("codex", "claude-code", "claude-code--opus")  # 80 KB in all, at most 55 KB for one route
        self.assertEqual(found["text"].strip(), "c" * (20 * kb))
        self.write("project", "orch/roles/reviewer.md",
                   f"<!-- skm-stub:v1 target={T} mode=append -->\n" + "a" * (30 * kb))  # 50 KB common + 25 KB codex
        with self.assertRaises(stubs.StubError) as caught:
            self.resolve("codex", "claude-code")
        self.assertEqual(caught.exception.code, "STUB_TOO_LARGE")

    def test_variant_modes_are_independent_of_the_base_and_other_variants(self):
        self.write("machine", "orch/roles/reviewer.md", "base\n")
        slot = "orch/roles/reviewer@codex.md"
        self.write("machine", slot, "machine\n")
        self.write("machine", "orch/roles/reviewer@codex--gpt-6-sol.md", "family\n")
        for mode, body, expected in (("replace", "project", ["project\n", "family\n"]),
                                     ("append", "project", ["machine\n", "project\n", "family\n"]),
                                     ("disable", "", ["family\n"]),
                                     ("replace", "", ["machine\n", "family\n"])):
            with self.subTest(mode=mode, body=body):
                self.write("project", slot, f"<!-- skm-stub:v1 target={T}@codex mode={mode} -->\n{body}")
                found = self.resolve("codex", "codex--gpt-6-sol")
                self.assertEqual(found["text"], "base\n")
                self.assertEqual([part["body"] for part in found["parts"] if "variant" in part], expected)
        self.assertEqual([part.get("body") for part in self.resolve("codex", layers=("machine",))["parts"]],
                         [None, "machine\n"])

    def test_invalid_variants_and_variant_targets_are_refused(self):
        for variant in ("", "Codex", "../codex", "codex/foo", "codex--", "codex--gpt--sol", "codex--../sol"):
            with self.subTest(variant=variant), self.assertRaises(stubs.StubError) as caught:
                self.resolve(variant)
            self.assertEqual(caught.exception.code, "STUB_TARGET_UNKNOWN")
            self.assertIn("reviewer@", caught.exception.message)
        with self.assertRaises(stubs.StubError):
            stubs.slots(T + "@codex")  # the base target grammar stays unchanged
        slot = "orch/roles/reviewer@codex--gpt-6.1-sol.md"
        self.assertEqual(stubs.slot_target(T, slot), T + "@codex--gpt-6.1-sol")
        self.write("project", slot, f"<!-- skm-stub:v1 target={T}@claude-code -->\nwrong\n")
        with self.assertRaises(stubs.StubError) as caught:
            self.resolve("codex--gpt-6.1-sol")
        self.assertEqual(caught.exception.code, "STUB_TARGET_MISMATCH")

    def test_variant_reads_refuse_symlinks_and_unsafe_text(self):
        slot = "orch/roles/reviewer@codex.md"
        path = self.write("project", slot, "safe\n")
        path.unlink()
        path.symlink_to("/etc/hostname")
        with self.assertRaises(stubs.StubError) as caught:
            self.resolve("codex")
        self.assertEqual(caught.exception.code, "STUB_SYMLINK_FORBIDDEN")
        path.unlink()
        self.write("project", slot, "token=abcdef123456\n")
        with self.assertRaises(stubs.StubError) as caught:
            self.resolve("codex")
        self.assertEqual(caught.exception.code, "STUB_SECRET")


class RefusalTests(StubCase):
    def refused(self, code: str) -> None:
        with self.assertRaises(stubs.StubError) as caught:
            stubs.resolve([T], self.project, env=self.env)
        self.assertEqual(caught.exception.code, code)

    def test_a_symlinked_file_or_folder_is_refused(self):
        secret = Path(self.tmp.name) / "secret.txt"
        secret.write_text("key\n", encoding="utf-8")
        (self.project_root / "orch" / "roles").mkdir(parents=True)
        (self.project_root / "orch" / "roles" / "reviewer.md").symlink_to(secret)
        self.refused("STUB_SYMLINK_FORBIDDEN")

    def test_a_symlinked_slot_folder_is_refused(self):
        elsewhere = Path(self.tmp.name) / "elsewhere"
        (elsewhere / "roles").mkdir(parents=True)
        self.project_root.mkdir(parents=True)
        (self.project_root / "orch").symlink_to(elsewhere)
        self.refused("STUB_SYMLINK_FORBIDDEN")

    def test_a_folder_in_place_of_a_file_is_refused(self):
        (self.project_root / "orch" / "roles" / "reviewer.md").mkdir(parents=True)
        self.refused("STUB_NOT_REGULAR")

    def test_bad_text_and_headers_are_refused(self):
        for text, code in ((b"\xff\xfe bad", "STUB_INVALID_UTF8"), ("x" * (stubs.MAX_BYTES + 1), "STUB_TOO_LARGE"),
                           ("<!-- skm-stub:v2 -->\n", "STUB_METADATA_INVALID"),
                           ("<!-- skm-stub:v1 colour=red -->\n", "STUB_METADATA_INVALID"),
                           ("<!-- skm-stub:v1 mode=merge -->\n", "STUB_MODE_INVALID"),
                           ("<!-- skm-stub:v1 mode=disable -->\ntext\n", "STUB_MODE_INVALID"),
                           ("<!-- skm-stub:v1 target=orch.role.executor -->\n", "STUB_TARGET_MISMATCH")):
            with self.subTest(code=code, text=str(text)[:30]):
                self.write("project", "orch/roles/reviewer.md", text)
                self.refused(code)

    def test_a_world_writable_file_and_a_secret_are_refused(self):
        path = self.write("project", "orch/roles/reviewer.md", "fine text\n")
        os.chmod(path, 0o666)
        self.refused("STUB_PERMISSIONS")
        os.chmod(path, 0o644)
        self.write("project", "orch/roles/reviewer.md", "use token=abcdef123456 for the API\n")
        self.refused("STUB_SECRET")

    def test_an_unknown_target_shape_is_refused(self):
        with self.assertRaises(stubs.StubError) as caught:
            stubs.slots("reviewer")
        self.assertEqual(caught.exception.code, "STUB_TARGET_UNKNOWN")


class PublishTests(StubCase):
    def test_publish_creates_the_missing_files_once_and_never_overwrites(self):
        rows = stubs.publish([T, "orch.role.executor"], self.project_root)
        self.assertEqual([row["slot"] for row in rows],
                         ["_all.md", "orch/_all.md", "orch/roles/_all.md", "orch/roles/reviewer.md", "orch/roles/executor.md"])
        self.assertEqual({row["status"] for row in rows}, {"created"})
        edited = self.project_root / "orch" / "roles" / "reviewer.md"
        edited.write_text("mine\n", encoding="utf-8")
        again = stubs.publish([T, "orch.role.executor"], self.project_root)
        self.assertEqual({row["status"] for row in again}, {"unchanged"})
        self.assertEqual(edited.read_text(encoding="utf-8"), "mine\n")
        self.assertEqual(self.text(), "mine\n")  # the other published files are empty: they inherit nothing

    def test_dry_run_writes_nothing_and_a_symlink_is_refused(self):
        self.assertEqual({row["status"] for row in stubs.publish([T], self.project_root, dry_run=True)}, {"created"})
        self.assertFalse(self.project_root.exists())
        (self.project_root / "orch" / "roles").mkdir(parents=True)
        os.symlink("/etc/passwd", self.project_root / "orch" / "roles" / "reviewer.md")
        rows = {row["slot"]: row["status"] for row in stubs.publish([T], self.project_root)}
        self.assertEqual(rows["orch/roles/reviewer.md"], "refused")


if __name__ == "__main__":
    unittest.main()
