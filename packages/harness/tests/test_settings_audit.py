"""Internal documentation."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness.common import Env
from harness.settings_audit import (
    build_context, effective_config, load_layers, run_checks, run_cursor_checks,
    _load_vscode_layer,
)


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class SettingsAuditCoreCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.target = self.tmp / "proj"
        self.home.mkdir()
        self.target.mkdir()
        self.env = Env(self.tmp, "test", home=self.home)

    def tearDown(self):
        self._tmp.cleanup()


    def test_scalar_local_overrides_user(self):
        _write(self.home / ".claude" / "settings.json",
               {"permissions": {"defaultMode": "default"}})
        _write(self.target / ".claude" / "settings.local.json",
               {"permissions": {"defaultMode": "bypassPermissions"}})
        layers = load_layers(self.env, self.target)
        values, provenance = effective_config(layers)
        self.assertEqual(values["permissions"]["defaultMode"], "bypassPermissions")
        self.assertEqual(provenance["permissions"]["defaultMode"], "local")


    def test_permissions_allow_union_with_dedup(self):
        _write(self.home / ".claude" / "settings.json",
               {"permissions": {"allow": ["Bash(ls *)"]}})
        _write(self.target / ".claude" / "settings.json",
               {"permissions": {"allow": ["Bash(git status)", "Bash(ls *)"]}})
        _write(self.target / ".claude" / "settings.local.json",
               {"permissions": {"allow": ["Read(**)"]}})
        layers = load_layers(self.env, self.target)
        values, _provenance = effective_config(layers)
        self.assertEqual(
            values["permissions"]["allow"],
            ["Bash(ls *)", "Bash(git status)", "Read(**)"])


    def test_broken_local_layer_reported_not_fatal(self):
        _write(self.home / ".claude" / "settings.json",
               {"permissions": {"allow": ["Bash(ls *)"]}})
        local = self.target / ".claude" / "settings.local.json"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text("{not json", encoding="utf-8")
        layers = load_layers(self.env, self.target)
        local_layer = next(l for l in layers if l.name == "local")
        self.assertIsNone(local_layer.data)
        self.assertIsNotNone(local_layer.error)

        values, _provenance = effective_config(layers)
        self.assertEqual(values["permissions"]["allow"], ["Bash(ls *)"])


    def test_env_per_key_override(self):
        _write(self.home / ".claude" / "settings.json",
               {"env": {"FOO": "user-foo", "BAR": "user-bar"}})
        _write(self.target / ".claude" / "settings.local.json",
               {"env": {"FOO": "local-foo"}})
        layers = load_layers(self.env, self.target)
        values, provenance = effective_config(layers)
        self.assertEqual(values["env"], {"FOO": "local-foo", "BAR": "user-bar"})
        self.assertEqual(provenance["env"]["FOO"], "local")
        self.assertEqual(provenance["env"]["BAR"], "user")


    def test_hooks_merge_by_event_with_dedup(self):
        _write(self.home / ".claude" / "settings.json", {"hooks": {"PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "a.sh"}]}]}})
        _write(self.target / ".claude" / "settings.json", {"hooks": {"PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "a.sh"}]},
            {"matcher": "Read", "hooks": [{"type": "command", "command": "b.sh"}]}]}})
        layers = load_layers(self.env, self.target)
        values, _provenance = effective_config(layers)
        entries = values["hooks"]["PreToolUse"]
        self.assertEqual(len(entries), 2)
        pairs = {(e["matcher"], e["command"]) for e in entries}
        self.assertEqual(pairs, {("Bash", "a.sh"), ("Read", "b.sh")})


    def test_provenance_points_to_correct_layer(self):
        _write(self.target / ".claude" / "settings.json",
               {"permissions": {"deny": ["Bash(sudo *)"]}})
        layers = load_layers(self.env, self.target)
        _values, provenance = effective_config(layers)
        rules = dict(provenance["permissions"]["deny"])
        self.assertEqual(rules["Bash(sudo *)"], "project")


    def test_absent_layers_are_normal_no_errors(self):
        layers = load_layers(self.env, self.target)
        for layer in layers:
            if layer.name != "managed":
                self.assertIsNone(layer.data)
                self.assertIsNone(layer.error)
        values, provenance = effective_config(layers)
        self.assertEqual(values, {})
        self.assertEqual(provenance, {})


def _findings_by_id(findings, check_id):
    return [f for f in findings if f.id == check_id]


class SettingsAuditChecksCase(unittest.TestCase):
    """Internal documentation."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.target = self.tmp / "proj"
        self.home.mkdir()
        self.target.mkdir()
        self.env = Env(self.tmp, "test", home=self.home)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self):
        ctx = build_context(self.env, self.target)
        return run_checks(ctx)


    def test_check1_broken_layer_json_single_error_finding(self):
        local = self.target / ".claude" / "settings.local.json"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text("{not json", encoding="utf-8")
        findings = self._run()
        errs = _findings_by_id(findings, 1)
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].level, "error")


    def test_check2_autoapprove_is_noncanonical_warn(self):
        _write(self.target / ".claude" / "settings.json",
               {"permissions": {"autoApprove": True}})
        findings = self._run()
        warns = _findings_by_id(findings, 2)
        self.assertTrue(any(w.level == "warn" for w in warns))
        self.assertTrue(any("autoApprove" in w.title for w in warns))


    def test_check3_default_mode_conflict_across_layers(self):
        _write(self.home / ".claude" / "settings.json",
               {"permissions": {"defaultMode": "default"}})
        _write(self.target / ".claude" / "settings.local.json",
               {"permissions": {"defaultMode": "bypassPermissions"}})
        findings = self._run()
        warns = _findings_by_id(findings, 3)
        self.assertEqual(len(warns), 1)
        self.assertEqual(warns[0].level, "warn")
        self.assertIn("user", warns[0].detail)
        self.assertIn("local", warns[0].detail)


    def test_check5_hook_command_missing_is_error(self):
        _write(self.target / ".claude" / "settings.json", {"hooks": {"PreToolUse": [
            {"matcher": "Bash",
             "hooks": [{"type": "command", "command": "does-not-exist.sh"}]}]}})
        findings = self._run()
        errs = [f for f in _findings_by_id(findings, 5) if f.level == "error"]
        self.assertEqual(len(errs), 1)



    def test_check5_tilde_path_expanded_no_false_error(self):
        process_home = self.tmp / "process-home"
        process_home.mkdir()
        hooks_dir = self.home / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        script = hooks_dir / "log-bash-command.sh"
        script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        script.chmod(0o755)
        _write(self.target / ".claude" / "settings.json", {"hooks": {"PreToolUse": [
            {"matcher": "Bash",
             "hooks": [{"type": "command", "command": "~/.claude/hooks/log-bash-command.sh"}]}]}})
        with mock.patch.dict("os.environ", {"HOME": str(process_home)}):
            self.assertNotEqual(Path.home(), self.home)
            findings = self._run()
        errs = [f for f in _findings_by_id(findings, 5) if f.level == "error"]
        self.assertEqual(errs, [], "tilde must be expanded - false error is invalid")


    def test_check5_interpreter_prefix_checks_script_not_interpreter(self):
        script = self.target / "hook.sh"
        script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        script.chmod(0o755)
        _write(self.target / ".claude" / "settings.json", {"hooks": {"PreToolUse": [
            {"matcher": "Bash",
             "hooks": [{"type": "command", "command": f"bash {script}"}]}]}})
        findings = self._run()
        errs = [f for f in _findings_by_id(findings, 5) if f.level == "error"]
        self.assertEqual(errs, [], "`bash <script>` — the script is checked, not the interpreter")

    def test_check5_interpreter_prefix_does_not_require_script_executable(self):
        script = self.target / "hook.py"
        script.write_text("print('ok')\n", encoding="utf-8")
        _write(self.target / ".claude" / "settings.json", {"hooks": {"PreToolUse": [
            {"matcher": "Bash",
             "hooks": [{"type": "command", "command": f"python3 {script}"}]}]}})
        findings = self._run()
        errs = [f for f in _findings_by_id(findings, 5) if f.level == "error"]
        self.assertEqual(errs, [], "`python3 <script>` does not require X_OK for the script")


    def test_check5_unknown_hook_event_is_info_not_warn(self):
        script = self.target / "hook.sh"
        script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        script.chmod(0o755)
        _write(self.target / ".claude" / "settings.json", {"hooks": {"TotallyUnknownEvent": [
            {"matcher": "*", "hooks": [{"type": "command", "command": str(script)}]}]}})
        findings = self._run()
        by5 = _findings_by_id(findings, 5)
        self.assertTrue(any(f.level == "info" for f in by5))
        self.assertFalse(any(f.level in ("warn", "error") for f in by5))


    def test_check9_plaintext_secret_in_env_is_error(self):
        _write(self.target / ".claude" / "settings.local.json",
               {"env": {"ANTHROPIC_API_KEY": "sk-ant-01234567890"}})
        findings = self._run()
        errs = [f for f in _findings_by_id(findings, 9) if f.level == "error"
                and "ANTHROPIC_API_KEY" in f.title]
        self.assertEqual(len(errs), 1)


    def test_check9_placeholder_value_no_false_positive(self):
        _write(self.target / ".claude" / "settings.local.json",
               {"env": {"FOO_API_KEY": "${BAR}"}})
        findings = self._run()
        secret_findings = [f for f in _findings_by_id(findings, 9)
                            if "FOO_API_KEY" in f.title]
        self.assertEqual(secret_findings, [])


class CursorSettingsAuditChecksCase(unittest.TestCase):
    """Internal documentation."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.target = self.tmp / "proj"
        self.home.mkdir()
        self.target.mkdir()
        self.env = Env(self.tmp, "test", home=self.home)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self):
        return run_cursor_checks(build_context(self.env, self.target))

    def _write_compat_log_hook(self):
        _write(self.home / ".claude" / "settings.json", {"hooks": {"PreToolUse": [
            {"matcher": "Bash", "hooks": [
                {"type": "command", "command": "~/.claude/hooks/log-bash-command.sh"}
            ]}
        ]}})

    def test_check14_reports_overlap_between_cursor_native_and_claude_compat(self):
        self._write_compat_log_hook()
        _write(self.target / ".cursor" / "hooks.json", {
            "version": 1,
            "hooks": {
                "preToolUse": [
                    {"matcher": "Shell",
                     "command": ('python3 "${CURSOR_PROJECT_DIR:-.}/.cursor/hooks/lifecycle.py" '
                                 "--surface lifecycle.command-log")}
                ]
            },
        })
        warns = [f for f in _findings_by_id(self._run(), 14) if f.level == "warn"]
        self.assertEqual(len(warns), 1)
        self.assertIn("lifecycle.command-log", warns[0].title)

    def test_check14_invalid_cursor_hooks_is_error(self):
        hooks = self.target / ".cursor" / "hooks.json"
        hooks.parent.mkdir(parents=True, exist_ok=True)
        hooks.write_text("{broken", encoding="utf-8")
        errs = [f for f in _findings_by_id(self._run(), 14) if f.level == "error"]
        self.assertEqual(len(errs), 1)
        self.assertIn(".cursor/hooks.json", errs[0].title)

    def test_check15_detects_duplicate_identical_registration(self):
        _write(self.home / ".claude" / "settings.json", {"hooks": {"PreToolUse": [
            {"matcher": "Bash", "hooks": [
                {"type": "command", "command": "~/.claude/hooks/log-bash-command.sh"}
            ]},
            {"matcher": "Bash", "hooks": [
                {"type": "command", "command": "~/.claude/hooks/log-bash-command.sh"}
            ]},
            {"matcher": "Bash", "hooks": [
                {"type": "command", "command": "~/.claude/hooks/daemon-safety/block-daemon-ops.sh"},
                {"type": "command", "command": "~/.claude/hooks/log-bash-command.sh"},
            ]},
        ]}})
        warns = [f for f in _findings_by_id(self._run(), 15) if f.level == "warn"]
        self.assertTrue(any("x3" in warning.title for warning in warns))
        self.assertTrue(any("log-bash-command.sh" in warning.detail for warning in warns))

    def test_check16_reports_unmanaged_cursor_compat_binding(self):
        _write(self.target / ".claude" / "settings.json", {"hooks": {"PreToolUse": [
            {"matcher": "Bash", "hooks": [
                {"type": "command", "command": "~/.claude/hooks/daemon-safety/block-daemon-ops.sh"}
            ]}
        ]}})
        infos = [f for f in _findings_by_id(self._run(), 16) if f.level == "info"]
        self.assertEqual(len(infos), 1)
        self.assertIn("Include Third-Party Plugins, Skills, and Other Configs", infos[0].hint)


class SettingsAuditPolicyProfileCase(unittest.TestCase):
    """Internal documentation."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.target = self.tmp / "proj"
        self.home.mkdir()
        self.target.mkdir()
        self.env = Env(self.tmp, "test", home=self.home)

    def tearDown(self):
        self._tmp.cleanup()

    def _declare(self, name):
        _write(self.target / ".swissknife.json", {"policy_profile": name})

    def _run(self):
        return run_checks(build_context(self.env, self.target))


    def test_profile_matches_no_findings(self):
        self._declare("max-permissive")
        _write(self.target / ".claude" / "settings.json", {"permissions": {
            "defaultMode": "bypassPermissions",
            "ask": [],
            "deny": ["Read(~/.ssh/**)", "Read(~/.aws/**)",
                     "Read(**/*.pem)", "Bash(sudo *)"],
        }})
        findings = self._run()
        self.assertEqual(_findings_by_id(findings, 4), [])
        self.assertEqual(_findings_by_id(findings, 11), [])


    def test_ask_nonempty_under_max_permissive_is_error(self):
        self._declare("max-permissive")
        _write(self.target / ".claude" / "settings.json", {"permissions": {
            "defaultMode": "bypassPermissions",
            "ask": ["Bash(git push *)"],
            "deny": ["Read(~/.ssh/**)", "Read(~/.aws/**)",
                     "Read(**/*.pem)", "Bash(sudo *)"],
        }})
        errs = [f for f in _findings_by_id(self._run(), 11) if f.level == "error"]
        self.assertEqual(len(errs), 1)
        self.assertIn("Bash(git push *)", errs[0].detail)
        self.assertIn("project", errs[0].detail)


    def test_deny_stripped_missing_guardrail_is_error(self):
        self._declare("max-permissive")
        _write(self.target / ".claude" / "settings.json", {"permissions": {
            "defaultMode": "bypassPermissions",
            "ask": [],
            "deny": ["Read(~/.ssh/**)", "Read(~/.aws/**)", "Read(**/*.pem)"],
        }})
        errs = [f for f in _findings_by_id(self._run(), 4) if f.level == "error"]
        self.assertEqual(len(errs), 1)
        self.assertIn("Bash(sudo *)", errs[0].detail)


    def test_deny_extended_with_extra_rule_ok(self):
        self._declare("max-permissive")
        _write(self.target / ".claude" / "settings.json", {"permissions": {
            "defaultMode": "bypassPermissions",
            "ask": [],
            "deny": ["Read(~/.ssh/**)", "Read(~/.aws/**)", "Read(**/*.pem)",
                     "Bash(sudo *)", "Read(**/secret.txt)"],
        }})
        self.assertEqual(_findings_by_id(self._run(), 4), [])


    def test_unknown_profile_name_is_error(self):
        self._declare("does-not-exist")
        errs = [f for f in _findings_by_id(self._run(), 4) if f.level == "error"]
        self.assertEqual(len(errs), 1)
        self.assertIn("does-not-exist", errs[0].title)


    def test_no_declaration_single_info_zero_error(self):
        findings = self._run()
        pair = [f for f in findings if f.id in (4, 11)]
        infos = [f for f in pair if f.level == "info"]
        errs = [f for f in pair if f.level == "error"]
        self.assertEqual(len(infos), 1)
        self.assertEqual(errs, [])


class SettingsDoctorCliCase(unittest.TestCase):
    """Internal documentation."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.target = self.tmp / "proj"
        self.home.mkdir()
        self.target.mkdir()
        self.env = Env(self.tmp, "test", home=self.home)

    def tearDown(self):
        self._tmp.cleanup()

    def _run_cli(self, argv):
        import contextlib
        import io
        from harness.doctor import cmd_doctor
        buf = io.StringIO()
        exc = None
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                cmd_doctor(self.env, argv)
            except SystemExit as e:
                exc = e
        return exc, buf.getvalue()

    def _argv(self, *extra):
        return ["--settings", "--target", str(self.target), *extra]


    def test_json_is_single_valid_document(self):
        local = self.target / ".claude" / "settings.local.json"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text("{broken", encoding="utf-8")  # → error id=1
        exc, out = self._run_cli(self._argv("--json"))
        stripped = out.strip()

        self.assertNotIn("\n", stripped)
        data = json.loads(stripped)
        self.assertEqual(data["target"], str(self.target))
        self.assertIn("counts", data)
        self.assertEqual(data["exit"], 2)
        self.assertTrue(any(f["id"] == 1 and f["level"] == "error"
                            for f in data["findings"]))
        self.assertIsInstance(exc, SystemExit)
        self.assertEqual(exc.code, 2)


    def test_exit_zero_on_clean(self):
        exc, _out = self._run_cli(self._argv())
        self.assertIsInstance(exc, SystemExit)
        self.assertEqual(exc.code, 0)


    def test_exit_one_on_warn_only(self):
        _write(self.target / ".claude" / "settings.json",
               {"permissions": {"autoApprove": True}})
        exc, _out = self._run_cli(self._argv())
        self.assertIsInstance(exc, SystemExit)
        self.assertEqual(exc.code, 1)


    def test_exit_two_on_error(self):
        local = self.target / ".claude" / "settings.local.json"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text("{broken", encoding="utf-8")
        exc, out = self._run_cli(self._argv())
        self.assertIsInstance(exc, SystemExit)
        self.assertEqual(exc.code, 2)
        self.assertIn("[error]", out)


    def test_no_flag_keeps_env_doctor_output(self):
        import contextlib
        import io
        import tests.fixtures as fx
        from harness.doctor import cmd_doctor
        env = fx.real_env(self.tmp)
        buf = io.StringIO()
        exc = None
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                cmd_doctor(env, [])
            except SystemExit as e:
                exc = e
        self.assertIsNone(exc)
        self.assertIn("harness doctor:", buf.getvalue())
        self.assertNotIn("--settings (target", buf.getvalue())


class SettingsAuditSecondSliceChecksCase(unittest.TestCase):
    """Internal documentation."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.target = self.tmp / "proj"
        self.home.mkdir()
        self.target.mkdir()
        self.env = Env(self.tmp, "test", home=self.home)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self):
        return run_checks(build_context(self.env, self.target))


    def test_check6_dead_allow_rules_info_with_count(self):
        rules = [f"Bash(echo {i})" for i in range(200)]
        _write(self.home / ".claude" / "settings.json",
               {"permissions": {"allow": rules}})
        findings = _findings_by_id(self._run(), 6)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "info")
        self.assertIn("200", findings[0].title)


    def test_check6_below_threshold_no_finding(self):
        rules = [f"Bash(echo {i})" for i in range(10)]
        _write(self.home / ".claude" / "settings.json",
               {"permissions": {"allow": rules}})
        self.assertEqual(_findings_by_id(self._run(), 6), [])


    def test_check6_wildcard_rule_not_counted(self):
        rules = [f"Bash(echo {i} *)" for i in range(200)]
        _write(self.home / ".claude" / "settings.json",
               {"permissions": {"allow": rules}})
        self.assertEqual(_findings_by_id(self._run(), 6), [])


    def test_check7_pattern_in_allow_and_deny_is_warn(self):
        _write(self.target / ".claude" / "settings.json", {"permissions": {
            "allow": ["Bash(git status)"],
            "deny": ["Bash(git status)"],
        }})
        warns = [f for f in _findings_by_id(self._run(), 7) if f.level == "warn"]
        self.assertEqual(len(warns), 1)
        self.assertIn("Bash(git status)", warns[0].title)


    def test_check8_nonexistent_additional_directory_is_warn(self):
        _write(self.target / ".claude" / "settings.json", {"permissions": {
            "additionalDirectories": ["/does/not/exist/at/all"]}})
        warns = [f for f in _findings_by_id(self._run(), 8) if f.level == "warn"]
        self.assertEqual(len(warns), 1)
        self.assertIn("project", warns[0].title)


    def test_check8_existing_additional_directory_no_finding(self):
        real_dir = self.tmp / "real"
        real_dir.mkdir()
        _write(self.target / ".claude" / "settings.json", {"permissions": {
            "additionalDirectories": [str(real_dir)]}})
        self.assertEqual(_findings_by_id(self._run(), 8), [])


    def test_check10_bypass_without_skip_dialog_is_exactly_info(self):
        _write(self.target / ".claude" / "settings.json",
               {"permissions": {"defaultMode": "bypassPermissions"}})
        findings = _findings_by_id(self._run(), 10)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "info")


    def test_check10_bypass_with_skip_dialog_no_finding(self):
        _write(self.target / ".claude" / "settings.json", {
            "permissions": {
                "defaultMode": "bypassPermissions",
                "skipDangerousModePermissionPrompt": True,
            },
        })
        self.assertEqual(_findings_by_id(self._run(), 10), [])


    def test_check12_initial_mode_mismatch_is_warn(self):
        _write(self.target / ".claude" / "settings.json",
               {"permissions": {"defaultMode": "bypassPermissions"}})
        _write(self.target / ".vscode" / "settings.json",
               {"claudeCode.initialPermissionMode": "default"})
        warns = [f for f in _findings_by_id(self._run(), 12) if f.level == "warn"]
        self.assertEqual(len(warns), 1)


    def test_check12_initial_mode_matches_no_finding(self):
        _write(self.target / ".claude" / "settings.json",
               {"permissions": {"defaultMode": "bypassPermissions"}})
        _write(self.target / ".vscode" / "settings.json",
               {"claudeCode.initialPermissionMode": "bypassPermissions"})
        self.assertEqual(_findings_by_id(self._run(), 12), [])


    def test_check13_bypass_toggle_missing_is_warn(self):
        _write(self.target / ".claude" / "settings.json",
               {"permissions": {"defaultMode": "bypassPermissions"}})
        _write(self.target / ".vscode" / "settings.json",
               {"claudeCode.initialPermissionMode": "bypassPermissions"})
        warns = [f for f in _findings_by_id(self._run(), 13) if f.level == "warn"]
        self.assertEqual(len(warns), 1)


    def test_check13_bypass_toggle_present_no_finding(self):
        _write(self.target / ".claude" / "settings.json",
               {"permissions": {"defaultMode": "bypassPermissions"}})
        _write(self.target / ".vscode" / "settings.json", {
            "claudeCode.initialPermissionMode": "bypassPermissions",
            "claudeCode.allowDangerouslySkipPermissions": True,
        })
        self.assertEqual(_findings_by_id(self._run(), 13), [])


    def test_jsonc_comment_and_url_value_parse_correctly(self):
        text = (
            "{\n"
            "  // line comment\n"
            "  \"claudeCode.initialPermissionMode\": \"bypassPermissions\", // trailing\n"
            "  /* block\n     comment */\n"
            "  \"someUrl\": \"https://example.com/path//double-slash\",\n"
            "}\n"
        )
        (self.target / ".vscode").mkdir(parents=True, exist_ok=True)
        (self.target / ".vscode" / "settings.json").write_text(text, encoding="utf-8")
        layer = _load_vscode_layer("project", self.target / ".vscode" / "settings.json")
        self.assertIsNone(layer.error)
        self.assertEqual(layer.data["claudeCode.initialPermissionMode"], "bypassPermissions")
        self.assertEqual(layer.data["someUrl"], "https://example.com/path//double-slash")


    def test_broken_vscode_json_is_info_not_error(self):
        (self.target / ".vscode").mkdir(parents=True, exist_ok=True)
        (self.target / ".vscode" / "settings.json").write_text("{not json", encoding="utf-8")
        findings = self._run()
        by12 = _findings_by_id(findings, 12)
        self.assertTrue(any(f.level == "info" for f in by12))
        self.assertFalse(any(f.level in ("warn", "error") for f in by12))




    def test_broken_vscode_json_with_bypass_mode_check13_no_warn(self):
        _write(self.target / ".claude" / "settings.json",
               {"permissions": {"defaultMode": "bypassPermissions"}})
        (self.target / ".vscode").mkdir(parents=True, exist_ok=True)
        (self.target / ".vscode" / "settings.json").write_text("{not json", encoding="utf-8")
        findings = self._run()
        self.assertEqual(_findings_by_id(findings, 13), [])
        by12 = _findings_by_id(findings, 12)
        self.assertTrue(any(f.level == "info" for f in by12))


    def test_no_vscode_file_no_crash_no_vscode_findings(self):
        findings = self._run()
        self.assertEqual(_findings_by_id(findings, 12), [])
        self.assertEqual(_findings_by_id(findings, 13), [])



    def test_check13_bypass_without_any_vscode_no_finding(self):
        _write(self.target / ".claude" / "settings.json",
               {"permissions": {"defaultMode": "bypassPermissions"}})
        self.assertEqual(_findings_by_id(self._run(), 13), [])


    def test_load_vscode_layer_missing_file_is_normal(self):
        layer = _load_vscode_layer("user", self.target / "no-such-file.json")
        self.assertIsNone(layer.data)
        self.assertIsNone(layer.error)


    def test_load_vscode_layer_broken_json_sets_error_text(self):
        broken = self.target / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        layer = _load_vscode_layer("user", broken)
        self.assertIsNone(layer.data)
        self.assertIsNotNone(layer.error)


class SettingsAuditFourthCheckVscodeCase(unittest.TestCase):
    """Internal documentation."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.target = self.tmp / "proj"
        self.home.mkdir()
        self.target.mkdir()
        self.env = Env(self.tmp, "test", home=self.home)

    def tearDown(self):
        self._tmp.cleanup()

    def _declare(self, name):
        _write(self.target / ".swissknife.json", {"policy_profile": name})

    def _run(self):
        return run_checks(build_context(self.env, self.target))

    def _base_settings(self):
        _write(self.target / ".claude" / "settings.json", {"permissions": {
            "defaultMode": "bypassPermissions",
            "ask": [],
            "deny": ["Read(~/.ssh/**)", "Read(~/.aws/**)",
                     "Read(**/*.pem)", "Bash(sudo *)"],
        }})


    def test_vscode_matches_profile_no_findings(self):
        self._declare("max-permissive")
        self._base_settings()
        _write(self.target / ".vscode" / "settings.json", {
            "claudeCode.initialPermissionMode": "bypassPermissions",
            "claudeCode.allowDangerouslySkipPermissions": True,
        })
        self.assertEqual(_findings_by_id(self._run(), 4), [])


    def test_vscode_mismatches_profile_is_error(self):
        self._declare("max-permissive")
        self._base_settings()
        _write(self.target / ".vscode" / "settings.json", {
            "claudeCode.initialPermissionMode": "default",
        })
        errs = [f for f in _findings_by_id(self._run(), 4) if f.level == "error"]
        self.assertTrue(any("vscode" in f.title.lower()
                             or "VSCode" in f.title for f in errs))


    def test_no_vscode_at_all_check4_silent_on_vscode(self):
        self._declare("max-permissive")
        self._base_settings()
        errs = [f for f in _findings_by_id(self._run(), 4)
                if "VSCode" in f.title or "vscode" in f.title.lower()]
        self.assertEqual(errs, [])


if __name__ == "__main__":
    unittest.main()
