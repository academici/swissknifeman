"""Cursor-specific profile conformance cases from freeze §3.6."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core import EffectiveProvider, ProviderId
from harness.cursor_render import (assert_rule_frontmatter, check_cursor_rules,
                                   plan_cursor_rules, render_cursor_cli_json,
                                   render_cursor_rules)
from harness.profiles import load_catalog, resolve_profile

PACKAGE = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]
CATALOG = PACKAGE / "configs/common/profile-catalog.json"
BINDINGS = PACKAGE / "configs/cursor/config/profile-bindings.json"
FRAGMENT = "packages/harness/configs/common/instructions/root/cursor.md"


def effective():
    return EffectiveProvider(ProviderId.CURSOR, True)


class CursorProviderConformanceTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(CATALOG)

    def test_trusted_full_access_positive_self_host(self):
        resolution = resolve_profile(
            self.catalog, provider_id=ProviderId.CURSOR, profile_id="trusted-full-access",
            target_scope="project", trusted=True, operation_id="self-host-apply",
            target_identity="repo:swissknifeman", origin="operation", effective_provider=effective())
        self.assertTrue(resolution.green)
        cli = render_cursor_cli_json(resolution, BINDINGS)
        self.assertIn(b'"Shell(**)"', cli)
        self.assertNotIn(b"approvalMode", cli)
        rules = render_cursor_rules(resolution)
        self.assertEqual(len(rules), 3)
        for path, content in rules.items():
            assert_rule_frontmatter(path, content)

    def test_inheritance_forbidden(self):
        resolution = resolve_profile(
            self.catalog, provider_id=ProviderId.CURSOR, profile_id="trusted-full-access",
            target_scope="project", trusted=True, operation_id="self-host-apply",
            target_identity="repo:swissknifeman", origin="fleet", effective_provider=effective())
        self.assertIn("HARNESS_FULL_ACCESS_INHERITANCE_FORBIDDEN",
                      {item.code for item in resolution.diagnostics})

    def test_wrong_operation_refused(self):
        resolution = resolve_profile(
            self.catalog, provider_id=ProviderId.CURSOR, profile_id="trusted-full-access",
            target_scope="project", trusted=True, operation_id="onboard",
            target_identity="repo:swissknifeman", origin="operation", effective_provider=effective())
        self.assertIn("HARNESS_FULL_ACCESS_EXPLICIT_REQUIRED",
                      {item.code for item in resolution.diagnostics})

    def test_non_repo_identity_refused(self):
        resolution = resolve_profile(
            self.catalog, provider_id=ProviderId.CURSOR, profile_id="trusted-full-access",
            target_scope="project", trusted=True, operation_id="self-host-apply",
            target_identity=None, origin="operation", effective_provider=effective())
        self.assertIn("HARNESS_FULL_ACCESS_EXPLICIT_REQUIRED",
                      {item.code for item in resolution.diagnostics})

    def test_untrusted_refused(self):
        resolution = resolve_profile(
            self.catalog, provider_id=ProviderId.CURSOR, profile_id="workspace-contained",
            target_scope="project", trusted=False, origin="operation", effective_provider=effective())
        self.assertIn("HARNESS_TRUST_REQUIRED", {item.code for item in resolution.diagnostics})

    def test_cli_json_refuses_project_mode_keys(self):
        import json
        poisoned = BINDINGS.parent / "poisoned-bindings.json"
        value = json.loads(BINDINGS.read_text(encoding="utf-8"))
        value["cursor"]["workspace-contained"]["approvalMode"] = "unrestricted"
        poisoned.write_text(json.dumps(value), encoding="utf-8")
        resolution = resolve_profile(
            self.catalog, provider_id=ProviderId.CURSOR, profile_id="workspace-contained",
            target_scope="project", trusted=True, origin="operation", effective_provider=effective())
        with self.assertRaisesRegex(ValueError, "HARNESS_CURSOR_CLI_PROJECT_MODE_REFUSED"):
            render_cursor_cli_json(resolution, poisoned)
        poisoned.unlink()

    def test_trusted_shapes_refused_for_non_self_host_target(self):
        resolution = resolve_profile(
            self.catalog, provider_id=ProviderId.CURSOR, profile_id="trusted-full-access",
            target_scope="project", trusted=True, operation_id="self-host-apply",
            target_identity="repo:other-project", origin="operation", effective_provider=effective())
        self.assertTrue(resolution.green)
        with self.assertRaisesRegex(ValueError, "HARNESS_CURSOR_TRUSTED_NON_SELF_HOST_REFUSED"):
            render_cursor_cli_json(resolution, BINDINGS)


class CursorRuleProjectionTests(unittest.TestCase):
    """P0.6: the committed rules are a projection of the instruction catalog, not a copy."""

    def test_committed_rules_match_the_catalog(self):
        self.assertEqual(check_cursor_rules(REPO), ())

    def test_every_rule_body_is_quoted_from_the_fragment(self):
        fragment = (REPO / FRAGMENT).read_text(encoding="utf-8")
        for path, content in plan_cursor_rules(REPO).items():
            assert_rule_frontmatter(path, content)
            body = content.decode("utf-8").split("---\n", 2)[2]
            prose = [line for line in body.splitlines()
                     if line and not line.startswith("<!--") and not line.startswith("## ")]
            self.assertTrue(prose, path)
            for line in prose:
                self.assertIn(line, fragment, f"{path}: body is not quoted from the catalog")

    def test_editing_the_catalog_moves_the_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            (root / Path(FRAGMENT).parent).mkdir(parents=True)
            source = REPO / FRAGMENT
            edited = source.read_text(encoding="utf-8").replace(
                "Name the intended workspace", "Name the CANARY workspace")
            (root / FRAGMENT).write_text(edited, encoding="utf-8")
            rendered = plan_cursor_rules(root)[".cursor/rules/swissknifeman-launch.mdc"]
            self.assertIn(b"Name the CANARY workspace", rendered)

    def test_check_reports_a_hand_edited_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            (root / Path(FRAGMENT).parent).mkdir(parents=True)
            shutil.copyfile(REPO / FRAGMENT, root / FRAGMENT)
            for path, content in plan_cursor_rules(root).items():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            self.assertEqual(check_cursor_rules(root), ())
            hand_edited = root / ".cursor/rules/swissknifeman-packages.mdc"
            hand_edited.write_bytes(hand_edited.read_bytes() + b"hand edit\n")
            self.assertEqual(check_cursor_rules(root),
                             (".cursor/rules/swissknifeman-packages.mdc",))


if __name__ == "__main__":
    unittest.main()
