"""Structural checks of the desktop shell configuration (no Rust toolchain needed).

The allowlist below is the permission set of knowledge/p6-design#desktop-shell; a permission added to
capabilities/default.json without a decision here fails the test.
"""
import json
import re
import unittest
from pathlib import Path

TAURI = Path(__file__).resolve().parents[1] / "desktop" / "src-tauri"

PERMISSION_ALLOWLIST = {
    "core:app:default",
    "core:event:default",
    "core:window:default",
    "allow-api-request",
    "allow-api-subscribe",
    "allow-api-unsubscribe",
    "allow-sidecar-status",
    "allow-sidecar-restart",
    "allow-sidecar-log",
    "shell:allow-spawn",
    "updater:default",
    "dialog:allow-open",
    "deep-link:default",
}
COMMANDS = ["api_request", "api_subscribe", "api_unsubscribe", "sidecar_status", "sidecar_restart", "sidecar_log"]


def load(rel: str) -> dict:
    return json.loads((TAURI / rel).read_text(encoding="utf-8"))


def identifier(entry) -> str:
    return entry if isinstance(entry, str) else entry["identifier"]


class TauriConf(unittest.TestCase):
    def setUp(self):
        self.conf = load("tauri.conf.json")
        self.csp = self.conf["app"]["security"]["csp"]

    def test_csp_has_no_eval_inline_script_or_remote(self):
        self.assertNotIn("unsafe-eval", self.csp)
        directives = {p.split()[0]: p.split()[1:] for p in self.csp.split(";") if p.strip()}
        self.assertNotIn("'unsafe-inline'", directives.get("script-src", []))
        self.assertIn("default-src", directives)
        remote = re.findall(r"https?://[^\s;]+", self.csp)
        self.assertEqual([r for r in remote if r != "http://ipc.localhost"], [])

    def test_csp_is_the_designed_one(self):
        self.assertEqual(
            self.csp,
            "default-src 'self'; script-src 'self'; style-src 'self'; connect-src ipc: http://ipc.localhost; "
            "img-src 'self' data:",
        )

    def test_windows_have_no_remote_url(self):
        windows = self.conf["app"]["windows"]
        self.assertTrue(windows)
        for window in windows:
            url = window.get("url", "index.html")
            self.assertNotRegex(url, r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
            self.assertFalse(url.startswith("//"))
        self.assertIn("main", [w["label"] for w in windows])

    def test_global_tauri_and_frontend(self):
        self.assertIs(self.conf["app"]["withGlobalTauri"], True)
        self.assertEqual(self.conf["build"]["frontendDist"], "../../frontend/dist")
        self.assertNotIn("devUrl", self.conf["build"])

    def test_sidecar_and_deep_link(self):
        self.assertEqual(self.conf["bundle"]["externalBin"], ["binaries/gui-backend"])
        self.assertEqual(self.conf["plugins"]["deep-link"]["desktop"]["schemes"], ["skm-gui"])
        self.assertEqual(self.conf["app"]["security"]["capabilities"], ["default"])


class Capabilities(unittest.TestCase):
    def setUp(self):
        self.cap = load("capabilities/default.json")
        self.perms = self.cap["permissions"]

    def test_permission_set_equals_allowlist(self):
        ids = [identifier(p) for p in self.perms]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), PERMISSION_ALLOWLIST)

    def test_forbidden_permissions(self):
        for ident in map(identifier, self.perms):
            self.assertFalse(ident.startswith(("fs:", "http:", "process:")), ident)
            self.assertNotEqual(ident, "shell:allow-execute")
            self.assertNotIn("shell:allow-open", ident)
        self.assertNotIn("shell:default", map(identifier, self.perms))

    def test_shell_scope_is_one_sidecar(self):
        shell = [p for p in self.perms if not isinstance(p, str)]
        self.assertEqual(len(shell), 1)
        self.assertEqual(shell[0]["identifier"], "shell:allow-spawn")
        self.assertEqual(shell[0]["allow"], [{"name": "binaries/gui-backend", "sidecar": True}])
        for key in shell[0]:
            self.assertIn(key, ("identifier", "allow"))

    def test_main_window_only_and_local(self):
        self.assertEqual(self.cap["windows"], ["main"])
        self.assertNotIn("remote", self.cap)
        self.assertNotIn("webviews", self.cap)

    def test_commands_match_build_and_main(self):
        build = (TAURI / "app" / "build.rs").read_text(encoding="utf-8")
        main = (TAURI / "app" / "src" / "main.rs").read_text(encoding="utf-8")
        allowed = {p[len("allow-"):].replace("-", "_") for p in map(identifier, self.perms) if p.startswith("allow-")}
        self.assertEqual(allowed, set(COMMANDS))
        for command in COMMANDS:
            self.assertIn(f'"{command}"', build)
            self.assertIn(f"commands::{command}", main)


class AdapterSurface(unittest.TestCase):
    """The adapter commands take no URL, host or header and return no secret (static reading of the Rust source)."""

    def setUp(self):
        self.commands = (TAURI / "app" / "src" / "commands.rs").read_text(encoding="utf-8")
        self.sidecar = (TAURI / "app" / "src" / "sidecar.rs").read_text(encoding="utf-8")

    def command_signatures(self):
        return re.findall(r"#\[tauri::command\]\s*pub (?:async )?fn (\w+)\((.*?)\)\s*(?:->|\{)", self.commands, re.S)

    def test_six_commands(self):
        self.assertEqual([name for name, _ in self.command_signatures()], COMMANDS)

    def test_no_command_takes_url_host_or_headers(self):
        for name, args in self.command_signatures():
            for forbidden in ("url", "host", "header", "origin", "scheme", "authorization", "secret"):
                self.assertNotRegex(args.lower(), rf"\b{forbidden}\w*\s*:", f"{name}: {forbidden}")

    def test_secret_is_not_returned_or_serialized(self):
        self.assertNotRegex(self.sidecar, r"pub secret")
        self.assertIn("fn secret(&self)", self.sidecar)
        self.assertIn("pub(crate) fn secret", self.sidecar)
        status = re.search(r"pub struct StatusView \{(.*?)\}", self.sidecar, re.S).group(1)
        self.assertNotIn("secret", status)
        self.assertIn("[redacted]", self.sidecar)
        self.assertNotRegex(self.commands, r"secret\(\)[^;]*\)\s*;?\s*Ok\(")

    def test_adapter_validates_before_sending(self):
        self.assertLess(self.commands.index("adapter::validate"), self.commands.index(".send().await"))


if __name__ == "__main__":
    unittest.main()
