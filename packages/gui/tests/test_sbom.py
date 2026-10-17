"""scripts/sbom.py: CycloneDX structure, determinism and one component per lock entry."""
import base64
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MODULE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = MODULE_ROOT / "scripts" / "sbom.py"
spec = importlib.util.spec_from_file_location("gui_sbom", SCRIPT)
sbom = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sbom)

SHA512 = "sha512-" + base64.b64encode(bytes(range(64))).decode()
LOCK = ("# comment\n"
        "starlette==1.2.3 --hash=sha256:" + "a" * 64 + "\n"
        "Anyio_Core==4.0.0 --hash=sha256:" + "b" * 64 + "\n")
NPM = {"name": "gui-frontend", "lockfileVersion": 3, "packages": {
    "": {"name": "gui-frontend", "version": "0.1.0"},
    "node_modules/react": {"version": "19.0.0", "integrity": SHA512},
    "node_modules/@xterm/xterm": {"version": "6.0.0", "integrity": SHA512},
    "node_modules/a/node_modules/react": {"version": "18.0.0", "integrity": SHA512, "dev": True},
}}
WORKSPACE = 'members = ["core", "app"]\n'
CORE = '[package]\nname = "c"\n[dependencies]\nserde = { version = "1", features = ["derive"] } # x\nserde_json = "1"\n'
APP = ('[dependencies]\nc = { path = "../core" }\ntauri = "2"\n[build-dependencies]\ntauri-build = "2"\n'
       '[[bin]]\nname = "x"\n')


def make_root(tmp, cargo_lock=None):
    root = Path(tmp)
    (root / "frontend").mkdir()
    (root / "desktop" / "src-tauri" / "core").mkdir(parents=True)
    (root / "desktop" / "src-tauri" / "app").mkdir()
    (root / "requirements.lock").write_text(LOCK)
    (root / "unit.json").write_text('{"version": "0.1.0"}')
    (root / "frontend" / "package-lock.json").write_text(json.dumps(NPM))
    (root / "desktop" / "src-tauri" / "Cargo.toml").write_text("[workspace]\n" + WORKSPACE)
    (root / "desktop" / "src-tauri" / "core" / "Cargo.toml").write_text(CORE)
    (root / "desktop" / "src-tauri" / "app" / "Cargo.toml").write_text(APP)
    if cargo_lock:
        (root / "desktop" / "src-tauri" / "Cargo.lock").write_text(cargo_lock)
    return root


class TestSbom(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = make_root(self.tmp)

    def test_structure(self):
        document = sbom.build(self.root)
        self.assertEqual("CycloneDX", document["bomFormat"])
        self.assertEqual("1.5", document["specVersion"])
        self.assertTrue(document["serialNumber"].startswith("urn:uuid:"))
        self.assertEqual("1970-01-01T00:00:00Z", document["metadata"]["timestamp"])
        by_purl = {component.get("purl"): component for component in document["components"]}
        self.assertEqual("a" * 64, by_purl["pkg:pypi/starlette@1.2.3"]["hashes"][0]["content"])
        self.assertIn("pkg:pypi/anyio-core@4.0.0", by_purl)
        xterm = by_purl["pkg:npm/%40xterm/xterm@6.0.0"]
        self.assertEqual({"alg": "SHA-512", "content": bytes(range(64)).hex()}, xterm["hashes"][0])
        refs = [component["bom-ref"] for component in document["components"]]
        self.assertEqual(sorted(refs), refs)
        self.assertEqual(len(refs), len(set(refs)))

    def test_count_equals_lock_entries(self):
        lock_entries = len([line for line in LOCK.splitlines() if line and not line.startswith("#")])
        npm_entries = len(NPM["packages"]) - 1
        cargo_entries = 4  # serde, serde_json, tauri, tauri-build; the path dependency is a member
        self.assertEqual(lock_entries + npm_entries + cargo_entries, len(sbom.build(self.root)["components"]))

    def test_cargo_without_lock_is_marked_unlocked(self):
        crates = [c for c in sbom.build(self.root)["components"] if c["bom-ref"].startswith("cargo:")]
        self.assertEqual({"serde", "serde_json", "tauri", "tauri-build"}, {c["name"] for c in crates})
        for crate in crates:
            self.assertEqual([{"name": "skm:locked", "value": "false"}], crate["properties"])

    def test_cargo_lock_wins(self):
        lock = ('[[package]]\nname = "skm-gui-core"\nversion = "0.1.0"\n\n[[package]]\nname = "serde"\n'
                'version = "1.0.1"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\n'
                'checksum = "' + "c" * 64 + '"\n')
        root = make_root(tempfile.mkdtemp(), cargo_lock=lock)
        self.addCleanup(shutil.rmtree, str(root), True)
        crates = [c for c in sbom.build(root)["components"] if c["bom-ref"].startswith("cargo:")]
        self.assertEqual(1, len(crates))
        self.assertEqual("1.0.1", crates[0]["version"])
        self.assertEqual("c" * 64, crates[0]["hashes"][0]["content"])

    def test_sidecar_digest_is_a_component(self):
        folder = self.root / "sidecar" / "dist" / "gui-backend-x86_64-unknown-linux-gnu"
        folder.mkdir(parents=True)
        (folder / "gui-backend.digest").write_text(json.dumps({"tree": "d" * 64}))
        names = [c["name"] for c in sbom.build(self.root)["components"]]
        self.assertIn("gui-backend-x86_64-unknown-linux-gnu", names)

    def test_source_date_epoch(self):
        with mock.patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "86400"}):
            self.assertEqual("1970-01-02T00:00:00Z", sbom.build(self.root)["metadata"]["timestamp"])

    def test_missing_lock_is_an_error(self):
        (self.root / "requirements.lock").unlink()
        with self.assertRaises(sbom.SbomError):
            sbom.build(self.root)

    def test_two_runs_are_byte_equal(self):
        first, second = Path(self.tmp) / "a.json", Path(self.tmp) / "b.json"
        for target in (first, second):
            done = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), "--out", str(target)],
                                  capture_output=True, text=True, timeout=60)
            self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_out_dev_null(self):
        done = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), "--out", os.devnull],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("component", done.stderr)

    def test_real_module_counts_match_its_locks(self):
        try:
            lock_text = (MODULE_ROOT / "requirements.lock").read_text()
            npm = json.loads((MODULE_ROOT / "frontend" / "package-lock.json").read_text())
        except OSError as error:
            self.skipTest(f"lock files are not readable here: {error}")
        pins = len([line for line in lock_text.replace("\\\n", " ").splitlines()
                    if line.split("#", 1)[0].strip()])
        components = sbom.build(MODULE_ROOT)["components"]
        counted = {kind: len([c for c in components if c["bom-ref"].startswith(kind + ":")])
                   for kind in ("pypi", "npm")}
        self.assertEqual(pins, counted["pypi"])
        self.assertEqual(len(npm["packages"]) - 1, counted["npm"])
        self.assertEqual(sbom.render(sbom.build(MODULE_ROOT)), sbom.render(sbom.build(MODULE_ROOT)))


if __name__ == "__main__":
    unittest.main()
