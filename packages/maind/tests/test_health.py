"""Tests health.py: communication report, providers health-doc/health-hook, CLI."""
import copy
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from maind import health
from maind.common import Env
from maind.config import load_config
from maind.projects import write_registry
from tests.fixtures import FakeMemoryServer, capture, make_repo, write_maind_config

_TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
_SESSION_START_HOOK = _TEMPLATES / "health" / "session-start-hook.sh"
_MEMORY_DIGEST_HOOK = _TEMPLATES / "health" / "memory-digest-hook.sh"


def _setup(tmp, *, with_mcp=False, memory_url=None, hook_maind=False):
    root, env = make_repo(tmp)
    shutil.copytree(_TEMPLATES, root / "templates")  # templates health available in env.root
    proj = Path(tmp) / "flexcrm"
    proj.mkdir(parents=True, exist_ok=True)
    if with_mcp:
        (proj / ".mcp.json").write_text(json.dumps({"mcpServers": {
            "agentmemory": {"command": "x"}, "maind": {"command": "y"}}}), encoding="utf-8")
        (proj / ".mcp.json.example").write_text("{}", encoding="utf-8")  # hygiene: not FAIL
    if hook_maind:                            # memory hook in daemon mode
        (proj / ".claude").mkdir(parents=True, exist_ok=True)
        (proj / ".claude" / "memory.env.ini").write_text("MODE=maind\n", encoding="utf-8")
    projects = [{"id": "flexcrm", "name": "FlexCRM", "type": "php-package",
                 "status": "active", "enabled": True, "local_path": str(proj),
                 "memory_scope": "project:flexcrm"}]
    cfg_over = {"graph": {"adapter": "federation"}, "projects": projects}
    if memory_url:
        cfg_over["memory"] = {"url": memory_url}
    write_maind_config(root, **cfg_over)
    config, _ = load_config(env)
    return env, config, config["projects"][0], proj


def _linked_worktree_env(tmp):
    """Primary machine-local config plus an isolated linked checkout."""
    primary = Path(tmp) / "primary"
    (primary / "core").mkdir(parents=True)
    (primary / "packages" / "maind").mkdir(parents=True)
    (primary / "core" / ".keep").write_text("\n", encoding="utf-8")
    (primary / "packages" / "maind" / ".keep").write_text("\n", encoding="utf-8")
    subprocess.run(["git", "init", str(primary)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(primary), "config", "user.email", "test@example.invalid"],
                   check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(primary), "config", "user.name", "Test"],
                   check=True, capture_output=True, text=True)
    (primary / "README").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(primary), "add", "."], check=True,
                   capture_output=True, text=True)
    subprocess.run(["git", "-C", str(primary), "commit", "-m", "fixture"], check=True,
                   capture_output=True, text=True)
    linked = Path(tmp) / "linked"
    subprocess.run(["git", "-C", str(primary), "worktree", "add", "--detach", str(linked)],
                   check=True, capture_output=True, text=True)
    home = Path(tmp) / "home"
    home.mkdir()
    env = Env(linked / "packages" / "maind", home=home)
    write_maind_config(primary, projects=[{
        "id": "swissknifeman", "name": "Swissknifeman", "type": "node-package",
        "status": "active", "enabled": True, "local_path": str(primary),
        "memory_scope": "project:swissknifeman",
    }])
    return primary, linked, env


class TestReport(unittest.TestCase):
    def test_linked_worktree_health_reads_primary_config_without_write_leakage(self):
        with tempfile.TemporaryDirectory() as tmp:
            primary, linked, env = _linked_worktree_env(tmp)
            config, source = load_config(env)
            self.assertEqual(source, "linked-worktree-config")
            self.assertFalse((linked / "config.json").exists())
            cwd0 = os.getcwd()
            try:
                os.chdir(linked)
                _, output = capture(health.cmd_health, env, ["--cwd", "--json"])
            finally:
                os.chdir(cwd0)
            self.assertEqual(json.loads(output)["id"], "swissknifeman")
            primary_before = (primary / "config.json").read_bytes()
            write_registry(env, config)
            self.assertEqual((primary / "config.json").read_bytes(), primary_before)
            self.assertTrue((linked / "config.json").is_file())

    def test_linked_worktree_does_not_match_different_repo_or_unknown_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            _primary, linked, env = _linked_worktree_env(tmp)
            config, _ = load_config(env)
            other = Path(tmp) / "other"
            other.mkdir()
            subprocess.run(["git", "init", str(other)], check=True, capture_output=True, text=True)
            from maind import projects
            self.assertIsNone(projects.match_cwd(env, config, cwd=other))
            with self.assertRaises(SystemExit):
                health._target(env, config, {"project": "unknown"})

    def test_standalone_when_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, _ = _setup(tmp)
            rep = health.health_report(env, config, proj, memory_reachable=False)
            self.assertEqual(rep["status"], "standalone")
            self.assertFalse(rep["maind_mcp"])
            self.assertTrue(any("start --only memory" in h for h in rep["hints"]))

    def test_connected_with_mcp_and_daemon(self):
        # Completely healthy project: MCP + demon + MODE=maind + native off + digest-injection + round-trip.
        with tempfile.TemporaryDirectory() as tmp, FakeMemoryServer() as url:
            env, config, proj, _ = _setup(tmp, with_mcp=True, memory_url=url, hook_maind=True)
            health.apply_memory_hook(env, config, proj, "auto", dry=False)  # native off + digest hook
            rep = health.health_report(env, config, proj, memory_reachable=True, deep=True)
            self.assertEqual(rep["status"], "connected")
            self.assertTrue(rep["maind_mcp"])
            self.assertEqual(rep["hook_memory_mode"], "maind")
            self.assertTrue(rep["native_memory_off"] and rep["digest_hook"])
            self.assertTrue(rep["memory_roundtrip"])      # write→recall→forget passed
            self.assertEqual(rep["hints"], [])

    def test_roundtrip_fails_when_split(self):
        # There is a daemon, but the hook is not in mode maind → hint about the mode (catches the split).
        with tempfile.TemporaryDirectory() as tmp, FakeMemoryServer() as url:
            env, config, proj, _ = _setup(tmp, with_mcp=True, memory_url=url, hook_maind=False)
            rep = health.health_report(env, config, proj, memory_reachable=True, deep=True)
            self.assertTrue(rep["memory_roundtrip"])       # the daemon itself responds
            self.assertNotEqual(rep["hook_memory_mode"], "maind")
            self.assertTrue(any("--memory manual" in h for h in rep["hints"]))

    def test_roundtrip_reports_unauthorized_not_generic_failure(self):
        # 401 on the protected endpoint differs from «not available»/«split» (findings §2) —
        # memory_roundtrip must return a detailed reason, not a general one RuntimeError-text.
        with tempfile.TemporaryDirectory() as tmp, FakeMemoryServer(secret="right-token") as url:
            env, config, proj, _ = _setup(tmp, with_mcp=True, memory_url=url, hook_maind=True)
            secret_path = env.root / "memory.secret"
            secret_path.write_text("wrong-token", encoding="utf-8")
            config["memory"]["secret_file"] = "memory.secret"
            roundtrip = health.memory_roundtrip(env, config, proj, memory_reachable=True)
            self.assertFalse(roundtrip["ok"])
            self.assertIn("unauthorized", roundtrip["detail"])

    def test_roundtrip_succeeds_with_correct_secret(self):
        with tempfile.TemporaryDirectory() as tmp, FakeMemoryServer(secret="right-token") as url:
            env, config, proj, _ = _setup(tmp, with_mcp=True, memory_url=url, hook_maind=True)
            secret_path = env.root / "memory.secret"
            secret_path.write_text("right-token", encoding="utf-8")
            config["memory"]["secret_file"] = "memory.secret"
            roundtrip = health.memory_roundtrip(env, config, proj, memory_reachable=True)
            self.assertTrue(roundtrip["ok"])

    def test_mcp_hygiene_missing_example_hinted(self):
        # .mcp.json yes, .example no → hint repair via maind sync --only mcp.
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            (pdir / ".mcp.json").write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
            rep = health.health_report(env, config, proj, memory_reachable=False)
            self.assertEqual(len(rep["mcp_hygiene"]), 1)
            self.assertIn("missing-example", rep["mcp_hygiene"][0]["problems"])
            self.assertTrue(any("sync --only mcp" in h and ".example" in h for h in rep["hints"]))
            # border: tooltip names a condition under which there is nothing to repair (P2.4, D91-D93).
            self.assertTrue(any("unmanaged-target" in h for h in rep["hints"]))


class TestHealthDoc(unittest.TestCase):
    def test_install_then_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            r1 = health.apply_health_doc(env, config, proj, "auto", dry=False)
            self.assertEqual(r1["state"], "absent")
            self.assertTrue(r1["changed"])
            claude = (pdir / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn("temporary project context", claude)
            self.assertIn("project:flexcrm", claude)
            r2 = health.apply_health_doc(env, config, proj, "auto", dry=False)
            self.assertEqual(r2["state"], "fresh")
            self.assertFalse(r2["changed"])

    def test_install_mode_skips_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            health.apply_health_doc(env, config, proj, "auto", dry=False)
            # fake drift
            claude = pdir / "CLAUDE.md"
            claude.write_text(claude.read_text().replace("temporary project context", "OLD"),
                              encoding="utf-8")
            r = health.apply_health_doc(env, config, proj, "install", dry=False)
            self.assertEqual(r["state"], "stale")
            self.assertFalse(r["changed"])  # install does NOT update outdated
            r2 = health.apply_health_doc(env, config, proj, "update", dry=False)
            self.assertTrue(r2["changed"])  # update — updates
            self.assertIn("temporary project context", claude.read_text())

    def test_preserves_foreign_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            (pdir / "CLAUDE.md").write_text("# FlexCRM\n\nMy documentation.\n", encoding="utf-8")
            health.apply_health_doc(env, config, proj, "auto", dry=False)
            txt = (pdir / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn("My documentation", txt)
            self.assertIn("temporary project context", txt)


class TestHealthHook(unittest.TestCase):
    def test_creates_script_and_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            r = health.apply_health_hook(env, config, proj, "auto", dry=False)
            self.assertTrue(r["changed"])
            self.assertTrue((pdir / ".claude" / "maind-health.sh").is_file())
            settings = json.loads((pdir / ".claude" / "settings.json").read_text())
            ss = settings["hooks"]["SessionStart"]
            cmds = [h["command"] for g in ss for h in g["hooks"]]
            self.assertTrue(any("maind-health" in c for c in cmds))

    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, _ = _setup(tmp)
            health.apply_health_hook(env, config, proj, "auto", dry=False)
            r2 = health.apply_health_hook(env, config, proj, "auto", dry=False)
            self.assertEqual(r2["state"], "fresh")
            self.assertFalse(r2["changed"])


class TestMemoryHook(unittest.TestCase):
    def test_apply_wires_digest_hook_and_disables_native(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            r = health.apply_memory_hook(env, config, proj, "auto", dry=False)
            self.assertTrue(r["changed"])
            self.assertTrue((pdir / ".claude" / "maind-memory.sh").is_file())
            settings = json.loads((pdir / ".claude" / "settings.json").read_text())
            self.assertIs(settings["autoMemoryEnabled"], False)   # native disabled
            cmds = [h["command"] for g in settings["hooks"]["SessionStart"] for h in g["hooks"]]
            self.assertTrue(any("maind-memory" in c for c in cmds))

    def test_apply_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, _ = _setup(tmp)
            health.apply_memory_hook(env, config, proj, "auto", dry=False)
            r2 = health.apply_memory_hook(env, config, proj, "auto", dry=False)
            self.assertEqual(r2["state"], "fresh")
            self.assertFalse(r2["changed"])

    def test_revert_restores_native(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            health.apply_memory_hook(env, config, proj, "auto", dry=False)
            health.revert_memory_hook(env, config, proj, dry=False)
            settings = json.loads((pdir / ".claude" / "settings.json").read_text())
            self.assertNotIn("autoMemoryEnabled", settings)       # native returned
            cmds = [h["command"] for g in settings.get("hooks", {}).get("SessionStart", [])
                    for h in g["hooks"]]
            self.assertFalse(any("maind-memory" in c for c in cmds))


class TestHookPortability(unittest.TestCase):
    """The generated hook scripts do NOT contain a machine-specific path to maind:
    launcher resolves in runtime (env MAIND_BIN → PATH). Ab-path leakage protection."""

    def _assert_portable(self, script_path, env):
        txt = script_path.read_text(encoding="utf-8")
        self.assertNotIn(str(env.root), txt)        # no baked abs-paths of the package maind
        self.assertNotIn("/bin/maind", txt)
        self.assertNotIn("{{MAIND_BIN}}", txt)      # placeholder did not leak
        self.assertIn("MAIND_BIN", txt)             # env-override
        self.assertIn("command -v maind", txt)      # PATH-fallback

    def test_memory_hook_portable(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            health.apply_memory_hook(env, config, proj, "auto", dry=False)
            self._assert_portable(pdir / ".claude" / "maind-memory.sh", env)

    def test_health_hook_portable(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            health.apply_health_hook(env, config, proj, "auto", dry=False)
            self._assert_portable(pdir / ".claude" / "maind-health.sh", env)


class TestSessionStartHookTemplate(unittest.TestCase):
    """P1.2: session-start-hook.sh — quiet when OK (--strict rc=0 → exit 0, nothing in stdout),
    prints status only when health unwell."""

    def _fake_maind(self, tmp, *, rc, stdout=""):
        """Stub script `maind`, responding to `health --cwd --strict` given rc/stdout."""
        fake = Path(tmp) / "maind"
        fake.write_text(
            "#!/usr/bin/env bash\n"
            f'printf %s "{stdout}"\n'
            f"exit {rc}\n",
            encoding="utf-8",
        )
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        return fake

    def _run_hook(self, maind_bin):
        env = dict(os.environ)
        env["MAIND_BIN"] = str(maind_bin)
        return subprocess.run(
            ["bash", str(_SESSION_START_HOOK)],
            env=env, capture_output=True, text=True, timeout=10,
        )

    def test_static_content_has_strict_and_rc_gate(self):
        # Technical specification requirement P1.2: template contains --strict and rc-gate `exit 0`.
        txt = _SESSION_START_HOOK.read_text(encoding="utf-8")
        self.assertIn("--strict", txt)
        self.assertIn('"$rc" -eq 0 ] && exit 0', txt)

    def test_quiet_when_healthy(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = self._fake_maind(tmp, rc=0, stdout="status: connected")
            r = self._run_hook(fake)
            self.assertEqual(r.returncode, 0)
            self.assertEqual(r.stdout, "")            # quiet when OK — does not write anything in the context

    def test_prints_status_when_unhealthy(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = self._fake_maind(tmp, rc=1, stdout="status: standalone")
            r = self._run_hook(fake)
            self.assertEqual(r.returncode, 0)          # safety hook: the hook itself does not crash
            self.assertIn("status: standalone", r.stdout)

    def test_missing_maind_is_quiet_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ)
            env["MAIND_BIN"] = str(Path(tmp) / "does-not-exist")
            # PATH without maind (but with bash/coreutils, so that the hook itself can run)
            env["PATH"] = os.path.dirname(shutil.which("bash"))
            r = subprocess.run(["bash", str(_SESSION_START_HOOK)], env=env,
                                capture_output=True, text=True, timeout=10)
            self.assertEqual(r.returncode, 0)
            self.assertEqual(r.stdout, "")


class TestMemoryDigestHookTemplate(unittest.TestCase):
    """P1.2: memory-digest-hook.sh — header bump comment (byte-change → stale for
    `maind sync`), the call itself remains argless (config-driven, single source of truth P1.1)."""

    def test_header_bumped_for_sync_staleness(self):
        txt = _MEMORY_DIGEST_HOOK.read_text(encoding="utf-8")
        self.assertIn("P1.2", txt)                      # header bump marker
        self.assertIn('"$MAIND" memory digest', txt)     # call remains argless


class TestCLI(unittest.TestCase):
    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, _, _ = _setup(tmp, with_mcp=True)
            _, out = capture(health.cmd_health, env, ["--project", "flexcrm", "--json"])
            rep = json.loads(out)
            self.assertEqual(rep["id"], "flexcrm")
            self.assertIn("status", rep)

    def test_strict_rejects_required_provider_trust_failure_in_human_and_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, _config, _, _ = _setup(tmp)
            report = {
                "id": "flexcrm", "scope": "project:flexcrm", "namespaces": [],
                "status": "connected", "memory_daemon": True,
                "hook_memory_mode": "maind", "native_memory_off": True,
                "digest_hook": True, "memory_roundtrip": True,
                "agentmemory_mcp": True, "maind_mcp": True, "code_mcp": True,
                "mcp_hygiene": [], "path": None, "hints": [],
                "provider_trust": [{"provider_id": "claude-code", "green": False,
                                    "diagnostics": ["HARNESS_TRUST_REQUIRED"]}],
            }
            with patch.object(health, "health_report", return_value=report):
                for output in ([], ["--json"]):
                    with self.subTest(output=output):
                        with self.assertRaises(SystemExit) as error:
                            health.cmd_health(env, ["--project", "flexcrm", "--strict", *output])
                        self.assertEqual(error.exception.code, 1)

    def test_strict_accepts_satisfied_provider_trust_in_human_and_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, _config, _, _ = _setup(tmp)
            report = {
                "id": "flexcrm", "scope": "project:flexcrm", "namespaces": [],
                "status": "connected", "memory_daemon": True,
                "hook_memory_mode": "maind", "native_memory_off": True,
                "digest_hook": True, "memory_roundtrip": True,
                "agentmemory_mcp": True, "maind_mcp": True, "code_mcp": True,
                "mcp_hygiene": [], "path": None, "hints": [],
                "provider_trust": [{"provider_id": "claude-code", "green": True,
                                    "diagnostics": []}],
            }
            with patch.object(health, "health_report", return_value=report):
                for output in ([], ["--json"]):
                    with self.subTest(output=output):
                        _, text = capture(health.cmd_health, env,
                                          ["--project", "flexcrm", "--strict", *output])
                        if output:
                            self.assertTrue(json.loads(text)["provider_trust"][0]["green"])
                        else:
                            self.assertIn("[ok  ] provider:claude-code trust", text)


class TestActPrimitive(unittest.TestCase):
    """_act(mode, state): what state of the artifact is repaired in what mode."""

    def test_fresh_never_acts(self):
        for mode in ("install", "update", "auto"):
            self.assertFalse(health._act(mode, "fresh"))

    def test_install_only_absent(self):
        self.assertTrue(health._act("install", "absent"))
        self.assertFalse(health._act("install", "stale"))

    def test_update_only_stale(self):
        self.assertTrue(health._act("update", "stale"))
        self.assertFalse(health._act("update", "absent"))

    def test_auto_acts_on_absent_and_stale(self):
        self.assertTrue(health._act("auto", "absent"))
        self.assertTrue(health._act("auto", "stale"))


class TestFileState(unittest.TestCase):
    """_file_state(path, content): absent (no file) / fresh (matches) / stale (drift)."""

    def test_absent_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(health._file_state(Path(tmp) / "nope.sh", "x"), "absent")

    def test_fresh_when_content_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.sh"
            p.write_text("echo hi\n", encoding="utf-8")
            self.assertEqual(health._file_state(p, "echo hi\n"), "fresh")

    def test_stale_when_content_drifts(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.sh"
            p.write_text("echo old\n", encoding="utf-8")
            self.assertEqual(health._file_state(p, "echo new\n"), "stale")


class TestMergeSessionHook(unittest.TestCase):
    """_merge_session_hook: idempotent insertion/update hook by marker into the event."""

    def test_inserts_into_empty(self):
        settings, changed = health._merge_session_hook({}, "bash x maind-health")
        self.assertTrue(changed)
        cmds = [h["command"] for g in settings["hooks"]["SessionStart"] for h in g["hooks"]]
        self.assertIn("bash x maind-health", cmds)

    def test_idempotent_same_command(self):
        s, _ = health._merge_session_hook({}, "bash x maind-health")
        _, changed = health._merge_session_hook(s, "bash x maind-health")
        self.assertFalse(changed)
        groups = s["hooks"]["SessionStart"]
        cmds = [h["command"] for g in groups for h in g["hooks"]]
        self.assertEqual(cmds.count("bash x maind-health"), 1)   # without duplicates

    def test_updates_command_same_marker(self):
        s, _ = health._merge_session_hook({}, "bash OLD maind-health")
        _, changed = health._merge_session_hook(s, "bash NEW maind-health")
        self.assertTrue(changed)
        cmds = [h["command"] for g in s["hooks"]["SessionStart"] for h in g["hooks"]]
        self.assertEqual(cmds, ["bash NEW maind-health"])        # updated in place

    def test_custom_event_and_marker(self):
        s, changed = health._merge_session_hook({}, "bash y maind-memory",
                                                event="SessionEnd", marker="maind-memory")
        self.assertTrue(changed)
        self.assertIn("SessionEnd", s["hooks"])

    def test_caller_copy_isolates_original(self):
        # _merge_session_hook mutates the input (because the providers call him to copy.deepcopy):
        # trial merge on the copy should not touch the original (fix contract json→deepcopy).
        original = {"hooks": {"SessionStart": []}}
        health._merge_session_hook(copy.deepcopy(original), "bash x maind-health")
        self.assertEqual(original, {"hooks": {"SessionStart": []}})


if __name__ == "__main__":
    unittest.main()


class TestRetiredFeatureHook(unittest.TestCase):
    def test_sync_retirement_is_dry_run_safe_idempotent_and_preserves_foreign_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, project, root = _setup(tmp)
            script = root / ".claude/maind-feature-log.sh"
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text("legacy\n")
            settings = script.parent / "settings.json"
            original = {"hooks": {"SessionEnd": [{"hooks": [
                {"type": "command", "command": f"bash {script}"},
                {"type": "command", "command": "bash foreign.sh"}]}]}}
            settings.write_text(json.dumps(original))
            from maind.provision import sync
            preview = sync._feature_log_hook_run(env, config, [project], "auto", True)
            self.assertEqual(preview[0]["status"], "dry")
            self.assertFalse(preview[0]["changed"])
            self.assertTrue(script.exists())
            self.assertEqual(json.loads(settings.read_text()), original)
            applied = sync._feature_log_hook_run(env, config, [project], "auto", False)
            self.assertTrue(applied[0]["changed"])
            self.assertFalse(script.exists())
            remaining = json.loads(settings.read_text())["hooks"]["SessionEnd"][0]["hooks"]
            self.assertEqual(remaining, [{"type": "command", "command": "bash foreign.sh"}])
            self.assertFalse(sync._feature_log_hook_run(env, config, [project], "auto", False)[0]["changed"])
