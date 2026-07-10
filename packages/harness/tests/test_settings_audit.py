"""Ядро settings-doctor: слои настроек CC и эффективная конфигурация (P1.1).

Реальные tmpdir-деревья `.claude/settings*.json` — никаких моков ФС и никаких
готовых `values`-словарей, подсунутых напрямую (анти-самообман: ядро обязано САМО
прочитать слои)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness.common import Env
from harness.settings_audit import build_context, effective_config, load_layers, run_checks


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

    # (а) скаляр из local перекрывает user
    def test_scalar_local_overrides_user(self):
        _write(self.home / ".claude" / "settings.json",
               {"permissions": {"defaultMode": "default"}})
        _write(self.target / ".claude" / "settings.local.json",
               {"permissions": {"defaultMode": "bypassPermissions"}})
        layers = load_layers(self.env, self.target)
        values, provenance = effective_config(layers)
        self.assertEqual(values["permissions"]["defaultMode"], "bypassPermissions")
        self.assertEqual(provenance["permissions"]["defaultMode"], "local")

    # (б) permissions.allow из user+project+local — union с дедупом
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

    # (в) битый settings.local.json не ломает merge остальных слоёв, даёт Layer.error
    def test_broken_local_layer_reported_not_fatal(self):
        _write(self.home / ".claude" / "settings.json",
               {"permissions": {"allow": ["Bash(ls *)"]}})
        local = self.target / ".claude" / "settings.local.json"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text("{не json", encoding="utf-8")
        layers = load_layers(self.env, self.target)
        local_layer = next(l for l in layers if l.name == "local")
        self.assertIsNone(local_layer.data)
        self.assertIsNotNone(local_layer.error)
        # остальные слои по-прежнему сливаются
        values, _provenance = effective_config(layers)
        self.assertEqual(values["permissions"]["allow"], ["Bash(ls *)"])

    # (г) env — пер-ключевой override
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

    # (д) hooks мержатся по событию с дедупом
    def test_hooks_merge_by_event_with_dedup(self):
        _write(self.home / ".claude" / "settings.json", {"hooks": {"PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "a.sh"}]}]}})
        _write(self.target / ".claude" / "settings.json", {"hooks": {"PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "a.sh"}]},
            {"matcher": "Read", "hooks": [{"type": "command", "command": "b.sh"}]}]}})
        layers = load_layers(self.env, self.target)
        values, _provenance = effective_config(layers)
        entries = values["hooks"]["PreToolUse"]
        self.assertEqual(len(entries), 2)  # дубль (Bash, a.sh) не размножился
        pairs = {(e["matcher"], e["command"]) for e in entries}
        self.assertEqual(pairs, {("Bash", "a.sh"), ("Read", "b.sh")})

    # (е) провенанс правила указывает верный слой
    def test_provenance_points_to_correct_layer(self):
        _write(self.target / ".claude" / "settings.json",
               {"permissions": {"deny": ["Bash(sudo *)"]}})
        layers = load_layers(self.env, self.target)
        _values, provenance = effective_config(layers)
        rules = dict(provenance["permissions"]["deny"])
        self.assertEqual(rules["Bash(sudo *)"], "project")

    # --- дополнительно: отсутствующие слои — норма, без ошибок ---------------
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
    """Проверки 1-3,5,9 (P1.2) — прогон через `run_checks()`, реальное дерево
    `.claude/` в tmpdir (анти-самообман: не конструировать Finding руками)."""

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

    # №1 — битый JSON слоя → ровно одна находка error id=1
    def test_check1_broken_layer_json_single_error_finding(self):
        local = self.target / ".claude" / "settings.local.json"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text("{не json", encoding="utf-8")
        findings = self._run()
        errs = _findings_by_id(findings, 1)
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].level, "error")

    # №2 — permissions.autoApprove → warn id=2 (эталон D6)
    def test_check2_autoapprove_is_noncanonical_warn(self):
        _write(self.target / ".claude" / "settings.json",
               {"permissions": {"autoApprove": True}})
        findings = self._run()
        warns = _findings_by_id(findings, 2)
        self.assertTrue(any(w.level == "warn" for w in warns))
        self.assertTrue(any("autoApprove" in w.title for w in warns))

    # №3 — defaultMode в user и в local → warn id=3 с обоими слоями в detail
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

    # №5 — хук с несуществующим command → error id=5
    def test_check5_hook_command_missing_is_error(self):
        _write(self.target / ".claude" / "settings.json", {"hooks": {"PreToolUse": [
            {"matcher": "Bash",
             "hooks": [{"type": "command", "command": "does-not-exist.sh"}]}]}})
        findings = self._run()
        errs = [f for f in _findings_by_id(findings, 5) if f.level == "error"]
        self.assertEqual(len(errs), 1)

    # №5 — хук с событием TotallyUnknownEvent → info id=5 (снапшот неполный, [UNVERIFIED])
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

    # №9 — env.ANTHROPIC_API_KEY плейнтекстом → error id=9
    def test_check9_plaintext_secret_in_env_is_error(self):
        _write(self.target / ".claude" / "settings.local.json",
               {"env": {"ANTHROPIC_API_KEY": "sk-ant-01234567890"}})
        findings = self._run()
        errs = [f for f in _findings_by_id(findings, 9) if f.level == "error"
                and "ANTHROPIC_API_KEY" in f.title]
        self.assertEqual(len(errs), 1)

    # №9 — анти-ложняк: плейсхолдер ${BAR} не считается секретом
    def test_check9_placeholder_value_no_false_positive(self):
        _write(self.target / ".claude" / "settings.local.json",
               {"env": {"FOO_API_KEY": "${BAR}"}})
        findings = self._run()
        secret_findings = [f for f in _findings_by_id(findings, 9)
                            if "FOO_API_KEY" in f.title]
        self.assertEqual(secret_findings, [])


class SettingsAuditPolicyProfileCase(unittest.TestCase):
    """Проверки №4/№11 (P1.3) — policy-профили и сверка «ожидание vs факт».
    Реальные `.claude/settings*.json` + `.swissknife.json` в tmpdir, прогон через
    `run_checks()` (анти-самообман: не подсовывать готовый `values`-словарь)."""

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

    # профиль объявлен и совпадает → 0 находок №4 и №11
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

    # ask непуст при max-permissive → error id=11 с именами правил и слоёв-источников
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

    # deny урезан (нет Bash(sudo *)) → error id=4
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

    # deny расширен лишним правилом → 0 находок №4 (contains-семантика ⊇)
    def test_deny_extended_with_extra_rule_ok(self):
        self._declare("max-permissive")
        _write(self.target / ".claude" / "settings.json", {"permissions": {
            "defaultMode": "bypassPermissions",
            "ask": [],
            "deny": ["Read(~/.ssh/**)", "Read(~/.aws/**)", "Read(**/*.pem)",
                     "Bash(sudo *)", "Read(**/secret.txt)"],
        }})
        self.assertEqual(_findings_by_id(self._run(), 4), [])

    # неизвестное имя профиля → error id=4
    def test_unknown_profile_name_is_error(self):
        self._declare("does-not-exist")
        errs = [f for f in _findings_by_id(self._run(), 4) if f.level == "error"]
        self.assertEqual(len(errs), 1)
        self.assertIn("does-not-exist", errs[0].title)

    # декларации нет → ровно один info и ноль error за пару №4/№11
    def test_no_declaration_single_info_zero_error(self):
        findings = self._run()
        pair = [f for f in findings if f.id in (4, 11)]
        infos = [f for f in pair if f.level == "info"]
        errs = [f for f in pair if f.level == "error"]
        self.assertEqual(len(infos), 1)
        self.assertEqual(errs, [])


class SettingsDoctorCliCase(unittest.TestCase):
    """CLI `harness doctor --settings` (P1.4): --json как единственный вывод,
    exit-code 0/1/2 на реальных tmpdir-конфигурациях, регресс безфлагового doctor.
    Анти-подгонка: конфликты строятся в tmpdir, `run_checks` не мокается."""

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

    # --json: валидный JSON и НИЧЕГО кроме него (контракт fleet-скана P1.6)
    def test_json_is_single_valid_document(self):
        local = self.target / ".claude" / "settings.local.json"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text("{битый", encoding="utf-8")  # → error id=1
        exc, out = self._run_cli(self._argv("--json"))
        stripped = out.strip()
        # ровно один JSON-документ: одна строка, парсится, ничего лишнего рядом
        self.assertNotIn("\n", stripped)
        data = json.loads(stripped)  # не должно бросить
        self.assertEqual(data["target"], str(self.target))
        self.assertIn("counts", data)
        self.assertEqual(data["exit"], 2)
        self.assertTrue(any(f["id"] == 1 and f["level"] == "error"
                            for f in data["findings"]))
        self.assertIsInstance(exc, SystemExit)
        self.assertEqual(exc.code, 2)

    # exit 0 — чистая конфигурация (только info о необъявленном профиле)
    def test_exit_zero_on_clean(self):
        exc, _out = self._run_cli(self._argv())
        self.assertIsInstance(exc, SystemExit)
        self.assertEqual(exc.code, 0)

    # exit 1 — есть warn, нет error (неканонический ключ permissions.autoApprove)
    def test_exit_one_on_warn_only(self):
        _write(self.target / ".claude" / "settings.json",
               {"permissions": {"autoApprove": True}})
        exc, _out = self._run_cli(self._argv())
        self.assertIsInstance(exc, SystemExit)
        self.assertEqual(exc.code, 1)

    # exit 2 — есть error (битый JSON слоя)
    def test_exit_two_on_error(self):
        local = self.target / ".claude" / "settings.local.json"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text("{битый", encoding="utf-8")
        exc, out = self._run_cli(self._argv())
        self.assertIsInstance(exc, SystemExit)
        self.assertEqual(exc.code, 2)
        self.assertIn("[error]", out)  # человекочитаемый отчёт, не JSON

    # регресс: harness doctor БЕЗ флага печатает прежний вывод и не sys.exit'ает
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


if __name__ == "__main__":
    unittest.main()
