"""Release scripts of the desktop shell: check-release-config.py, make-update-json.py, smoke.sh (no toolchain needed)."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DESKTOP = Path(__file__).resolve().parents[1] / "desktop"
SCRIPTS = DESKTOP / "scripts"
CONF = DESKTOP / "src-tauri" / "tauri.conf.json"
PLACEHOLDER_KEY = "OWNER_PUBKEY_REQUIRED"


def run(*args, **kwargs):
    return subprocess.run(list(args), capture_output=True, text=True, timeout=60, **kwargs)


class CheckReleaseConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conf = json.loads(CONF.read_text(encoding="utf-8"))

    def check(self, conf, *flags):
        path = Path(self.tmp.name) / "tauri.conf.json"
        path.write_text(json.dumps(conf), encoding="utf-8")
        return run(sys.executable, str(SCRIPTS / "check-release-config.py"), "--conf", str(path), *flags)

    def test_repository_conf_has_the_designed_structure_and_placeholders(self):
        bundle = self.conf["bundle"]
        self.assertEqual(bundle["targets"], ["appimage", "deb", "app"])
        self.assertIs(bundle["createUpdaterArtifacts"], True)
        updater = self.conf["plugins"]["updater"]
        self.assertEqual(updater["pubkey"], PLACEHOLDER_KEY)
        self.assertEqual(updater["endpoints"], ["https://updates.invalid/skm-gui/{{target}}/{{arch}}/{{current_version}}"])

    def test_structure_mode_accepts_the_repository_conf(self):
        result = run(sys.executable, str(SCRIPTS / "check-release-config.py"))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_release_mode_rejects_both_placeholders(self):
        result = run(sys.executable, str(SCRIPTS / "check-release-config.py"), "--release")
        self.assertEqual(result.returncode, 1)
        self.assertIn(PLACEHOLDER_KEY, result.stderr)
        self.assertIn(".invalid", result.stderr)

    def test_release_mode_rejects_each_placeholder_alone(self):
        conf = copy.deepcopy(self.conf)
        conf["plugins"]["updater"]["pubkey"] = "dW50cnVzdGVkIGNvbW1lbnQ6IGZha2U="
        result = self.check(conf, "--release")
        self.assertEqual(result.returncode, 1)
        self.assertIn(".invalid", result.stderr)
        self.assertNotIn(PLACEHOLDER_KEY, result.stderr)
        conf["plugins"]["updater"]["pubkey"] = PLACEHOLDER_KEY
        conf["plugins"]["updater"]["endpoints"] = ["https://updates.example.org/{{target}}"]
        result = self.check(conf, "--release")
        self.assertEqual(result.returncode, 1)
        self.assertIn(PLACEHOLDER_KEY, result.stderr)

    def test_release_mode_accepts_real_values(self):
        conf = copy.deepcopy(self.conf)
        conf["plugins"]["updater"]["pubkey"] = "dW50cnVzdGVkIGNvbW1lbnQ6IGZha2U="
        conf["plugins"]["updater"]["endpoints"] = ["https://updates.example.org/skm-gui/{{target}}/{{arch}}/{{current_version}}"]
        self.assertEqual(self.check(conf, "--release").returncode, 0)

    def test_structure_problems_fail_without_the_flag(self):
        for mutate in (
            lambda c: c["bundle"].update(createUpdaterArtifacts=False),
            lambda c: c["bundle"].update(targets=["deb"]),
            lambda c: c["bundle"].pop("externalBin"),
            lambda c: c["bundle"].pop("resources"),
            lambda c: c["plugins"].pop("updater"),
            lambda c: c["plugins"]["updater"].update(pubkey=""),
            lambda c: c["plugins"]["updater"].update(endpoints=["http://updates.example.org/x"]),
        ):
            conf = copy.deepcopy(self.conf)
            mutate(conf)
            self.assertEqual(self.check(conf).returncode, 1)

    def test_unreadable_conf_is_a_usage_error(self):
        result = run(sys.executable, str(SCRIPTS / "check-release-config.py"), "--conf", str(Path(self.tmp.name) / "none.json"))
        self.assertEqual(result.returncode, 2)


class MakeUpdateJson(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.artifact = self.dir / "SKM_GUI.AppImage.tar.gz"
        self.artifact.write_bytes(b"fake artifact")
        self.sig = self.dir / "SKM_GUI.AppImage.tar.gz.sig"
        self.sig.write_text("ZmFrZSBzaWduYXR1cmU=\n", encoding="utf-8")

    def make(self, **overrides):
        args = {
            "--version": "1.2.3", "--platform": "linux-x86_64", "--artifact": str(self.artifact), "--sig": str(self.sig),
            "--url": "https://updates.example.org/SKM_GUI.AppImage.tar.gz", "--pub-date": "2026-10-17T12:00:00Z",
        }
        args.update(overrides)
        argv = [item for pair in args.items() if pair[1] is not None for item in pair]
        return run(sys.executable, str(SCRIPTS / "make-update-json.py"), *argv)

    def test_deterministic_sorted_output(self):
        first, second = self.make(), self.make()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        document = json.loads(first.stdout)
        self.assertEqual(document, {
            "version": "1.2.3", "notes": "", "pub_date": "2026-10-17T12:00:00Z",
            "platforms": {"linux-x86_64": {"signature": "ZmFrZSBzaWduYXR1cmU=", "url": "https://updates.example.org/SKM_GUI.AppImage.tar.gz"}},
        })
        self.assertEqual(first.stdout, json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    def test_default_pub_date_is_utc_without_milliseconds(self):
        result = self.make(**{"--pub-date": None})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(json.loads(result.stdout)["pub_date"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_writes_out_file_and_notes(self):
        out = self.dir / "latest.json"
        result = self.make(**{"--out": str(out), "--notes": "first"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["notes"], "first")

    def test_refusals(self):
        empty = self.dir / "empty.sig"
        empty.write_text("  \n", encoding="utf-8")
        cases = {
            "empty signature": {"--sig": str(empty)},
            "not semver": {"--version": "1.2"},
            "v prefix": {"--version": "v1.2.3"},
            "http url": {"--url": "http://updates.example.org/x"},
            "no host": {"--url": "https:///x"},
            "missing artifact": {"--artifact": str(self.dir / "none.tar.gz")},
            "missing sig": {"--sig": str(self.dir / "none.sig")},
            "bad platform": {"--platform": "plan9"},
            "bad pub date": {"--pub-date": "2026-10-17T12:00:00.123Z"},
        }
        for name, override in cases.items():
            result = self.make(**override)
            self.assertEqual(result.returncode, 1, name)
            self.assertEqual(result.stdout, "", name)
            self.assertIn("make-update-json:", result.stderr, name)


class Smoke(unittest.TestCase):
    """Without a built sidecar (and the toolchain) smoke.sh refuses with 3 or, with the flag, reports SKIPPED."""

    def smoke(self, *flags):
        return run("bash", str(SCRIPTS / "smoke.sh"), "--sidecar", "/nonexistent/gui-backend", *flags)

    def test_missing_toolchain_without_flag_exits_3(self):
        result = self.smoke()
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("GUI_TOOLCHAIN_MISSING", result.stderr)

    def test_allow_missing_skips_with_exit_0(self):
        result = self.smoke("--allow-missing")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SKIPPED: GUI_TOOLCHAIN (", result.stdout)

    def test_unknown_argument_is_refused(self):
        self.assertEqual(run("bash", str(SCRIPTS / "smoke.sh"), "--bogus").returncode, 2)


class NoSecretsInRepository(unittest.TestCase):
    def test_scripts_and_conf_hold_no_private_key_or_its_path(self):
        for path in [*SCRIPTS.iterdir(), CONF]:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("BEGIN PRIVATE KEY", text, path.name)
            self.assertNotIn("TAURI_SIGNING_PRIVATE_KEY", text, path.name)
            self.assertNotRegex(text, r"\.key\b", path.name)

    def test_main_registers_the_updater_plugin(self):
        main = (DESKTOP / "src-tauri" / "app" / "src" / "main.rs").read_text(encoding="utf-8")
        self.assertIn("tauri_plugin_updater::Builder::new().build()", main)
        cargo = (DESKTOP / "src-tauri" / "app" / "Cargo.toml").read_text(encoding="utf-8")
        self.assertIn("tauri-plugin-updater", cargo)


if __name__ == "__main__":
    unittest.main()
