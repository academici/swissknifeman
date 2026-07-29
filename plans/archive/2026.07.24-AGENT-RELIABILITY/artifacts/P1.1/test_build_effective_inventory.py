#!/usr/bin/env python3
"""Focused tests for the P1.1 effective-inventory owner (stdlib unittest only).

Structure follows the item's Code Guidance:

* every acceptance dimension of the class-A map is proven **independently** by
  mutating one valid fixture;
* collision behaviour is driven by fixture marketplaces, so counts are derived,
  never asserted as literals inside the tool;
* the currently measured shape of the real repository is a regression case;
* the observed capture is proven to record `unknown` — never green, never a
  silent narrowing — when its declared command is absent or unparseable.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_effective_inventory as tool  # noqa: E402

REPO = Path(__file__).resolve().parents[4]


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def skill(identity: str, body: str = "body\n") -> str:
    return f"---\nname: {identity}\nversion: 0.1.0\n---\n\n{body}"


def fixture_repo(base: Path, *, units: dict[str, list[str]] | None = None,
                 codex_roots: list[str] | None = None,
                 claude_roots: list[str] | None = None,
                 class_a: bool = False) -> Path:
    """Build a synthetic repository with explicit units and root projections."""
    units = units or {}
    identities = list(tool.CLASS_A_IDENTITIES) if class_a else []
    for unit, members in units.items():
        for member in members:
            write(base / "packages/skiller/skills" / unit / member / "SKILL.md", skill(member))
    for identity in (codex_roots or []) + identities:
        write(base / ".agents/skills" / identity / "SKILL.md", skill(identity))
    for identity in (claude_roots or []) + identities:
        write(base / ".claude/skills" / identity / "SKILL.md", skill(identity))
    plugins = [{"name": unit, "source": f"./packages/skiller/skills/{unit}"}
               for unit in sorted(units)]
    write(base / ".agents/plugins/marketplace.json",
          json.dumps({"name": "swissknifeman", "plugins": plugins}))
    write(base / ".claude-plugin/marketplace.json",
          json.dumps({"name": "swissknifeman", "plugins": plugins}))
    # Minimal capability/routing carriers: the tool reads them explicitly and must
    # never fall back to the real repository while running against a fixture.
    write(base / "configs/provider-capabilities.json", json.dumps({
        "catalog_version": "1.0.0",
        "capabilities": [{"id": "skills.repository",
                          "support": {"codex": {"level": "native"},
                                      "claude-code": {"level": "native"}}}]}))
    write(base / "packages/task/configs/command-routing.json", json.dumps({
        "contract_version": "1.0.0", "catalog_version": "1.0.0",
        "plugin_version": "0.3.0", "commands": [], "mappings": {}}))
    return base


class BootstrapMapAcceptanceTest(unittest.TestCase):
    """D38: exact set equality, dimension by dimension, from one valid fixture."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repo = fixture_repo(Path(self.directory.name), class_a=True)
        self.valid = tool.build_bootstrap_map(self.repo)
        self.path = self.repo / "map.json"
        tool.write_json(self.path, self.valid)

    def check(self, payload) -> list[str]:
        tool.write_json(self.path, payload)
        return tool.check_bootstrap_map(self.repo, self.path)

    def mutate(self, mutator) -> list[str]:
        payload = copy.deepcopy(self.valid)
        mutator(payload)
        return self.check(payload)

    def test_valid_fixture_passes(self):
        self.assertEqual(tool.check_bootstrap_map(self.repo, self.path), [])
        self.assertEqual(len(self.valid["records"]), 13)

    def test_extra_top_level_key_fails(self):
        self.assertTrue(self.mutate(lambda p: p.update({"extra": 1})))

    def test_missing_top_level_key_fails(self):
        self.assertTrue(self.mutate(lambda p: p.pop("schema_version")))

    def test_wrong_schema_version_fails(self):
        failures = self.mutate(lambda p: p.update({"schema_version": "other/v9"}))
        self.assertTrue(any("schema_version" in item for item in failures))

    def test_extra_record_key_fails(self):
        failures = self.mutate(lambda p: p["records"][0].update({"note": "x"}))
        self.assertTrue(any("record keys" in item for item in failures))

    def test_missing_record_key_fails(self):
        failures = self.mutate(lambda p: p["records"][0].pop("generator"))
        self.assertTrue(any("record keys" in item for item in failures))

    def test_twelve_identities_fails(self):
        failures = self.mutate(lambda p: p["records"].pop(0))
        self.assertTrue(any("identity set mismatch" in item for item in failures))

    def test_fourteen_identities_fails(self):
        def add(payload):
            extra = copy.deepcopy(payload["records"][0])
            extra["identity"] = "zz-extra"
            payload["records"].append(extra)
        failures = self.mutate(add)
        self.assertTrue(any("identity set mismatch" in item for item in failures))

    def test_wrong_identity_fails(self):
        failures = self.mutate(lambda p: p["records"][0].update({"identity": "not-a-member"}))
        self.assertTrue(any("identity set mismatch" in item for item in failures))

    def test_unsorted_records_fail(self):
        failures = self.mutate(lambda p: p["records"].reverse())
        self.assertTrue(any("sorted by identity" in item for item in failures))

    def test_duplicate_identity_fails(self):
        def duplicate(payload):
            payload["records"].insert(1, copy.deepcopy(payload["records"][0]))
        failures = self.mutate(duplicate)
        self.assertTrue(any("duplicate identity" in item for item in failures))

    def test_wrong_canonical_formula_fails(self):
        failures = self.mutate(
            lambda p: p["records"][0]["canonical"].update({"ru": "packages/skiller/skills/general/x/SKILL.ru.md"}))
        self.assertTrue(any("canonical bilingual formula" in item for item in failures))

    def test_missing_projection_fails(self):
        failures = self.mutate(lambda p: p["records"][0]["projections"].pop("codex"))
        self.assertTrue(any("projection formula" in item for item in failures))
        self.assertTrue(any("formula-derived paths" in item for item in failures))

    def test_duplicate_projection_target_fails(self):
        def collide(payload):
            payload["records"][1]["projections"] = dict(payload["records"][0]["projections"])
        failures = self.mutate(collide)
        self.assertTrue(any("projection formula" in item for item in failures))

    def test_extra_projection_provider_fails(self):
        failures = self.mutate(
            lambda p: p["records"][0]["projections"].update({"cursor": ".cursor/skills/x/SKILL.md"}))
        self.assertTrue(any("projection formula" in item for item in failures))

    def test_wrong_content_version_literal_fails(self):
        failures = self.mutate(lambda p: p["records"][0].update({"canonical_content_version": "0.2.0"}))
        self.assertTrue(any("canonical_content_version" in item for item in failures))

    def test_wrong_unit_literal_fails(self):
        failures = self.mutate(lambda p: p["records"][0].update({"publication_unit": "general@0.1.0"}))
        self.assertTrue(any("publication_unit" in item for item in failures))

    def test_wrong_generator_literal_fails(self):
        failures = self.mutate(lambda p: p["records"][0].update({"generator": "skillset.py"}))
        self.assertTrue(any("generator" in item for item in failures))

    def test_wrong_lock_literal_fails(self):
        failures = self.mutate(lambda p: p["records"][0].update({"lock_path": "packages/skiller/lock.json"}))
        self.assertTrue(any("lock_path" in item for item in failures))

    def test_missing_seed_file_fails(self):
        identity = self.valid["records"][0]["identity"]
        (self.repo / ".agents/skills" / identity / "SKILL.md").unlink()
        failures = tool.check_bootstrap_map(self.repo, self.path)
        self.assertTrue(any("seed codex file is missing" in item for item in failures))

    def test_hash_drifted_seed_fails(self):
        identity = self.valid["records"][0]["identity"]
        write(self.repo / ".claude/skills" / identity / "SKILL.md", skill(identity, "drifted\n"))
        failures = tool.check_bootstrap_map(self.repo, self.path)
        self.assertTrue(any("seed claude hash drifted" in item for item in failures))

    def test_missing_resolution_fails(self):
        failures = self.mutate(lambda p: p["records"][0].pop("resolution"))
        self.assertTrue(any("record keys" in item for item in failures))

    def test_invalid_resolution_fails(self):
        failures = self.mutate(lambda p: p["records"][0]["resolution"].update({"reason": "  "}))
        self.assertTrue(any("resolution.reason" in item for item in failures))

    def test_resolution_must_agree_with_actual_seed_bytes(self):
        """Byte equality is a measurement, never a claim the record may contradict."""
        failures = self.mutate(lambda p: p["records"][0]["resolution"].update({"seeds_differ": True}))
        self.assertTrue(any("seeds_differ disagrees" in item for item in failures))

    def test_unknown_selected_seed_fails(self):
        failures = self.mutate(lambda p: p["records"][0]["resolution"].update({"selected_seed": "cursor"}))
        self.assertTrue(any("selected_seed" in item for item in failures))


class CollisionDetectionTest(unittest.TestCase):
    """Fixture-driven: the tool derives counts, it never carries them."""

    def state(self, base: Path, provider: str = "codex"):
        return tool.provider_state(base, provider)

    def test_root_and_unit_carrier_is_root_vs_unit(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = fixture_repo(Path(directory), units={"architect": ["architecture"]},
                                codex_roots=["architecture"])
            view = tool.collision_view(self.state(repo), None)
            self.assertEqual(view["colliding_identities"], 1)
            self.assertEqual(view["class_counts"], {"root-vs-unit": 1})
            self.assertEqual(view["collisions"]["architecture"]["carriers"],
                             ["root:architecture", "unit:architect"])

    def test_two_units_are_unit_vs_unit(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = fixture_repo(Path(directory),
                                units={"core": ["query-craft"], "research": ["query-craft"]})
            view = tool.collision_view(self.state(repo), None)
            self.assertEqual(view["class_counts"], {"unit-vs-unit": 1})

    def test_triple_carrier_reports_both_classes(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = fixture_repo(Path(directory),
                                units={"core": ["query-craft"], "research": ["query-craft"]},
                                codex_roots=["query-craft"])
            view = tool.collision_view(self.state(repo), None)
            self.assertEqual(view["collisions"]["query-craft"]["classes"],
                             ["root-vs-unit", "unit-vs-unit"])

    def test_unique_root_carrier_is_not_a_collision(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = fixture_repo(Path(directory), units={"general": ["something"]},
                                codex_roots=["orphan-bootstrap"])
            view = tool.collision_view(self.state(repo), None)
            self.assertEqual(view["colliding_identities"], 0)
            self.assertEqual(view["unique_root_carriers"], ["orphan-bootstrap"])

    def test_enabled_set_narrows_only_the_diagnostic_view(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = fixture_repo(Path(directory),
                                units={"core": ["query-craft"], "research": ["query-craft"]},
                                codex_roots=["query-craft"])
            state = self.state(repo)
            worst = tool.collision_view(state, None)
            enabled = tool.collision_view(state, ("core",))
            self.assertEqual(worst["collisions"]["query-craft"]["classes"],
                             ["root-vs-unit", "unit-vs-unit"])
            self.assertEqual(enabled["collisions"]["query-craft"]["classes"], ["root-vs-unit"])

    def test_display_prefix_is_not_identity(self):
        """`core:anti-drift` and `anti-drift` are different frontmatter names."""
        with tempfile.TemporaryDirectory() as directory:
            repo = fixture_repo(Path(directory), units={"core": ["anti-drift"]})
            write(repo / ".agents/skills/anti-drift/SKILL.md", skill("core:anti-drift"))
            view = tool.collision_view(self.state(repo), None)
            self.assertEqual(view["colliding_identities"], 0)

    def test_undeclared_root_file_is_measured(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = fixture_repo(Path(directory), units={}, codex_roots=["x"])
            write(repo / ".agents/skills/x/agents/openai.yaml", "name: x\n")
            state = self.state(repo)
            self.assertEqual(state["root_projection_extra_files"],
                             [".agents/skills/x/agents/openai.yaml"])

    def test_duplicate_marketplace_entry_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = fixture_repo(Path(directory), units={"core": ["a"]})
            payload = json.loads((repo / ".agents/plugins/marketplace.json").read_text())
            payload["plugins"].append(dict(payload["plugins"][0]))
            write(repo / ".agents/plugins/marketplace.json", json.dumps(payload))
            with self.assertRaises(tool.InventoryError):
                self.state(repo)

    def test_marketplace_skills_list_wins_over_source_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = fixture_repo(Path(directory), units={"general": ["a", "b"]})
            payload = json.loads((repo / ".agents/plugins/marketplace.json").read_text())
            payload["plugins"].append({
                "name": "core", "source": "./",
                "skills": ["./packages/skiller/skills/general/a"]})
            write(repo / ".agents/plugins/marketplace.json", json.dumps(payload))
            state = self.state(repo)
            core = next(unit for unit in state["units"] if unit["name"] == "core")
            self.assertEqual(core["skills_resolution"], "marketplace-skills")
            self.assertEqual(sorted(core["identities"]), ["a"])


class RealRepositoryRegressionTest(unittest.TestCase):
    """The currently measured shape (findings/12) must not drift unnoticed."""

    @classmethod
    def setUpClass(cls):
        cls.codex = tool.provider_state(REPO, "codex")
        cls.claude = tool.provider_state(REPO, "claude-code")

    def test_codex_worst_case_is_twenty(self):
        view = tool.collision_view(self.codex, None)
        self.assertEqual(view["colliding_identities"], 20)

    def test_codex_enabled_conditioned_shape(self):
        view = tool.collision_view(self.codex, tool.DECLARED_ENABLED["codex"])
        self.assertEqual(view["colliding_identities"], 16)
        self.assertEqual(view["class_counts"]["root-vs-unit"], 16)
        self.assertEqual(view["class_counts"]["unit-vs-unit"], 1)

    def test_fourteen_unique_root_carriers(self):
        view = tool.collision_view(self.codex, tool.DECLARED_ENABLED["codex"])
        self.assertEqual(len(view["unique_root_carriers"]), 14)
        self.assertIn(tool.CLASS_B_IDENTITY, view["unique_root_carriers"])
        for identity in tool.CLASS_A_IDENTITIES:
            self.assertIn(identity, view["unique_root_carriers"])

    def test_claude_side_is_nine_mutual_exclusion_pairs(self):
        view = tool.collision_view(self.claude, None)
        self.assertEqual(view["class_counts"], {"unit-vs-unit": 9})

    def test_every_measured_collision_has_an_owner(self):
        failures = tool.check_collision_owners(
            REPO, Path(__file__).with_name("remediation-map.json"))
        self.assertEqual(failures, [])

    def test_committed_bootstrap_map_passes_acceptance(self):
        failures = tool.check_bootstrap_map(
            REPO, Path(__file__).with_name("repository-bootstrap-map.json"))
        self.assertEqual(failures, [])

    def test_new_root_carrier_without_owner_is_a_hard_failure(self):
        """A carrier appearing without an owner item fails the gate, not warns."""
        payload = json.loads(
            Path(__file__).with_name("remediation-map.json").read_text(encoding="utf-8"))
        payload["collisions"] = [item for item in payload["collisions"]
                                 if item["identity"] != "architecture"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "map.json"
            tool.write_json(path, payload)
            failures = tool.check_collision_owners(REPO, path)
        self.assertTrue(any("measured collision without an owner record" in item
                            and "architecture" in item for item in failures))

    def test_owner_without_measured_collision_is_reported(self):
        payload = json.loads(
            Path(__file__).with_name("remediation-map.json").read_text(encoding="utf-8"))
        payload["collisions"].append({"provider": "codex", "identity": "invented",
                                      "carriers": [], "classes": [], "owners": []})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "map.json"
            tool.write_json(path, payload)
            failures = tool.check_collision_owners(REPO, path)
        self.assertTrue(any("owner record without a measured collision" in item
                            for item in failures))

    def test_version_ledger_drift_is_a_failure(self):
        payload = json.loads(
            Path(__file__).with_name("remediation-map.json").read_text(encoding="utf-8"))
        payload["version_ledger"][0]["to"] = "9.9.9"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "map.json"
            tool.write_json(path, payload)
            failures = tool.check_collision_owners(REPO, path)
        self.assertTrue(any("version ledger drifted" in item for item in failures))

    def test_owner_path_set_drift_is_a_failure(self):
        payload = json.loads(
            Path(__file__).with_name("remediation-map.json").read_text(encoding="utf-8"))
        payload["owners"]["P1.2"]["paths"].append("packages/maind/")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "map.json"
            tool.write_json(path, payload)
            failures = tool.check_collision_owners(REPO, path)
        self.assertTrue(any("owner path set drifted" in item for item in failures))


class ObservedCaptureTest(unittest.TestCase):
    """`unknown` is the only honest answer when the declared command cannot be read."""

    def capture(self, repo: Path, runner) -> dict:
        return tool.capture_observed(repo, repo / "observed.json", home=str(Path.home()),
                                     runner=runner)

    def test_absent_command_records_unknown_not_green(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = fixture_repo(Path(directory), units={"core": ["a"]}, codex_roots=["b"])

            def runner(*_args, **_kwargs):
                raise FileNotFoundError("codex")

            payload = self.capture(repo, runner)
            self.assertEqual(payload["providers"]["codex"]["state"], "unknown")
            self.assertIn("unavailable", payload["providers"]["codex"]["reason"])
            self.assertEqual(payload["providers"]["codex"]["units"], [])
            self.assertIsNone(tool.observed_enabled(payload, "codex"))

    def test_unparseable_output_records_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = fixture_repo(Path(directory), units={"core": ["a"]})

            def runner(*_args, **_kwargs):
                return subprocess.CompletedProcess([], 0, stdout="not json", stderr="")

            payload = self.capture(repo, runner)
            self.assertEqual(payload["providers"]["codex"]["state"], "unknown")
            self.assertIn("unparseable", payload["providers"]["codex"]["reason"])

    def test_failed_command_records_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = fixture_repo(Path(directory), units={"core": ["a"]})

            def runner(*_args, **_kwargs):
                return subprocess.CompletedProcess([], 3, stdout="", stderr="boom")

            payload = self.capture(repo, runner)
            self.assertEqual(payload["providers"]["codex"]["state"], "unknown")
            self.assertEqual(payload["commands"][1]["exit_code"], 3)

    def test_claude_provider_has_no_declared_command_and_stays_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = fixture_repo(Path(directory), units={"core": ["a"]}, claude_roots=["b"])

            def runner(*_args, **_kwargs):
                return subprocess.CompletedProcess([], 0, stdout='{"installed": []}', stderr="")

            payload = self.capture(repo, runner)
            self.assertEqual(payload["providers"]["claude-code"]["state"], "unknown")
            claude_command = next(item for item in payload["commands"]
                                  if item["provider"] == "claude-code")
            self.assertEqual(claude_command["argv"], [])
            self.assertEqual(claude_command["status"], "no-declared-command")

    def test_successful_capture_records_literal_argv_and_enabled_units(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = fixture_repo(Path(directory), units={"core": ["a"]}, codex_roots=["b"])
            output = json.dumps({"installed": [
                {"name": "core", "marketplaceName": "swissknifeman", "version": "0.4.0",
                 "enabled": True},
                {"name": "pdf", "marketplaceName": "openai-primary-runtime",
                 "version": "1", "enabled": True}]})

            def runner(*_args, **_kwargs):
                return subprocess.CompletedProcess([], 0, stdout=output, stderr="")

            payload = self.capture(repo, runner)
            record = payload["providers"]["codex"]
            self.assertEqual(record["state"], "read")
            self.assertEqual(tool.observed_enabled(payload, "codex"), ("core",))
            self.assertEqual(record["other_marketplace_units"], 1)
            self.assertEqual(record["units"][0]["identities"], ["a"])
            self.assertEqual(record["root_projections"],
                             [{"path": ".agents/skills/b/SKILL.md", "identity": "b"}])
            command = next(item for item in payload["commands"] if item["provider"] == "codex")
            self.assertEqual(command["argv"], ["codex", "plugin", "list", "--json"])

    def test_unchanged_recapture_reuses_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = fixture_repo(Path(directory), units={"core": ["a"]})

            def runner(*_args, **_kwargs):
                return subprocess.CompletedProcess(
                    [], 0, stdout='{"installed": []}', stderr="")

            first = self.capture(repo, runner)
            before = (repo / "observed.json").read_bytes()
            second = self.capture(repo, runner)
            self.assertEqual((repo / "observed.json").read_bytes(), before)
            self.assertEqual(first["captured_at"], second["captured_at"])

    def test_capture_cannot_remove_a_repo_derived_collision(self):
        """Corroboration only: an empty enabled set never clears the worst case."""
        with tempfile.TemporaryDirectory() as directory:
            repo = fixture_repo(Path(directory), units={"architect": ["architecture"]},
                                codex_roots=["architecture"])

            def runner(*_args, **_kwargs):
                return subprocess.CompletedProcess([], 0, stdout='{"installed": []}', stderr="")

            payload = self.capture(repo, runner)
            inventory = tool.build_inventory(
                repo, payload, REPO / "plans/2026.07.24-AGENT-RELIABILITY/artifacts"
                                      "/source-evidence/runtime/effective-runtime-inventory.json")
            worst = inventory["providers"]["codex"]["collisions"]["repo_derived_worst_case"]
            self.assertTrue(worst["authoritative"])
            self.assertEqual(worst["colliding_identities"], 1)
            self.assertEqual(inventory["providers"]["codex"]["observed"]["enabled_units"], [])


class HookSourceTest(unittest.TestCase):
    """Hook identities are owned like any other carrier — repo-derived, never scanned."""

    def test_absent_registration_is_stated_not_assumed(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = fixture_repo(Path(directory))
            state = tool.hook_state(repo, "codex", home=str(Path.home()))
        self.assertEqual(state["registration_state"], "absent")
        self.assertEqual(state["registrations"], [])

    def test_repo_local_and_outside_repo_handlers_are_classified(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = fixture_repo(Path(directory))
            write(repo / ".codex/hooks.json", json.dumps({"hooks": {"SessionStart": [
                {"hooks": [{"type": "command",
                            "command": 'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/lifecycle.py"'}],
                 "matcher": "startup"},
                {"hooks": [{"type": "command", "command": "bash ~/.claude/hooks/memory.sh"}]},
            ]}}))
            state = tool.hook_state(repo, "codex", home=str(Path.home()))
        localities = [item["handler_locality"] for item in state["registrations"]]
        self.assertEqual(sorted(localities), ["outside-repo", "repo-local"])
        outside = next(item for item in state["registrations"]
                       if item["handler_locality"] == "outside-repo")
        self.assertEqual(outside["content_state"], "unknown")

    def test_absolute_repo_path_is_repo_local_not_a_home_path(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = fixture_repo(Path(directory))
            write(repo / ".codex/hooks.json", json.dumps({"hooks": {"SessionStart": [
                {"hooks": [{"type": "command", "command": f"bash {repo}/.claude/memory.sh"}]}]}}))
            state = tool.hook_state(repo, "codex", home=str(repo.parent))
        self.assertEqual(state["registrations"][0]["handler_locality"], "repo-local")
        self.assertIn("$HOME", state["registrations"][0]["command"])

    def test_lock_owner_marks_a_managed_registration(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = fixture_repo(Path(directory))
            write(repo / ".codex/hooks.json", json.dumps({"hooks": {"SessionStart": []}}))
            write(repo / tool.PROVIDER_ARTIFACT_LOCK, json.dumps({"records": [
                {"provider_id": "codex", "target_path": ".codex/hooks.json",
                 "adapter_id": "maind.d104.bootstrap-transfer",
                 "artifact_id": "harness.codex.lifecycle.hooks", "rendered_hash": "sha256:x"}]}))
            state = tool.hook_state(repo, "codex", home=str(Path.home()))
        self.assertIn(".codex/hooks.json", state["managed_artifacts"])
        self.assertEqual(state["unmanaged_registration_targets"], [])

    def test_registration_without_lock_owner_is_reported_unmanaged(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = fixture_repo(Path(directory))
            write(repo / ".codex/hooks.json", json.dumps({"hooks": {"SessionStart": []}}))
            state = tool.hook_state(repo, "codex", home=str(Path.home()))
        self.assertEqual(state["unmanaged_registration_targets"], [".codex/hooks.json"])

    def test_real_repository_hook_ownership(self):
        codex = tool.hook_state(REPO, "codex", home=str(Path.home()))
        claude = tool.hook_state(REPO, "claude-code", home=str(Path.home()))
        # P0.4 restored the composed Codex lifecycle under one adapter owner…
        self.assertEqual(sorted(codex["managed_artifacts"]),
                         [".codex/hooks.json", ".codex/hooks/lifecycle.py"])
        self.assertEqual(codex["unmanaged_registration_targets"], [])
        # …while the Claude registration still points at global handlers, which is the
        # "effective hook set spans global and project sources" fact of findings/04.
        self.assertEqual(claude["unmanaged_registration_targets"], [".claude/settings.json"])
        self.assertTrue(any(item["handler_locality"] == "outside-repo"
                            for item in claude["registrations"]))
        for record in codex["registrations"] + claude["registrations"]:
            self.assertNotIn(str(Path.home()), record["command"])


class CapabilityAndReferenceTest(unittest.TestCase):
    def test_carrier_literal_without_capability_is_a_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            write(repo / "packages/task/commands/design.md",
                  "---\nmodel: opus\n---\nUse AskUserQuestion when blocked.\n")
            commands = {"task-design": {"command_id": "task:design",
                                        "required": ["skills.repository"], "routing": {}}}
            gaps = tool.carrier_literal_gaps(repo, commands, {"skills.repository": {}})
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["expected_capability"], "command.interactive-user-input")
        self.assertEqual(gaps[0]["gap_class"], "capability-absent-from-catalog")

    def test_catalogued_but_undeclared_literal_is_a_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            write(repo / "packages/task/commands/plan-exec.md", "---\n---\nWorkflow({scriptPath})\n")
            commands = {"task-plan-exec": {"command_id": "task:plan-exec",
                                           "required": ["skills.repository"], "routing": {}}}
            gaps = tool.carrier_literal_gaps(
                repo, commands, {"command.workflow-carrier": {"codex": "adapted"}})
        self.assertEqual(gaps[0]["gap_class"], "capability-not-declared-by-carrier")

    def test_declared_literal_is_not_a_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            write(repo / "packages/task/commands/research.md", "---\n---\nUse WebSearch.\n")
            commands = {"task-research": {"command_id": "task:research",
                                          "required": ["command.external-research"],
                                          "routing": {}}}
            gaps = tool.carrier_literal_gaps(
                repo, commands, {"command.external-research": {"codex": "adapted"}})
        self.assertEqual(gaps, [])

    def test_missing_runtime_reference_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            write(path, "---\nname: x\nsnippets: [a.md]\n---\nSee snippets/b.md too.\n")
            record = tool.runtime_references(path)
        self.assertFalse(record["complete"])
        self.assertEqual(record["missing"], ["snippets/a.md", "snippets/b.md"])

    def test_resolved_runtime_reference_is_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            write(path, "---\nname: x\nsnippets: [a.md]\n---\nbody\n")
            write(Path(directory) / "snippets/a.md", "ok\n")
            record = tool.runtime_references(path)
        self.assertTrue(record["complete"])

    def test_real_repository_capability_gaps_are_named_not_hidden(self):
        support = tool.capability_support(REPO)
        gaps = tool.carrier_literal_gaps(REPO, tool.command_capabilities(REPO), support)
        self.assertNotIn("command.interactive-user-input", support)
        self.assertTrue(any(item["command_id"] == "task:design"
                            and item["gap_class"] == "capability-absent-from-catalog"
                            for item in gaps))


if __name__ == "__main__":
    unittest.main(verbosity=2)
