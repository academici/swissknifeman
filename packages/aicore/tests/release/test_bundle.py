"""aicore release bundle: the files of a release, byte-identical runs, sha256sum and the compat schema."""
import io
import json
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

from aicore import cli
from aicore.release import bundle
from aicore.util import schema

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas" / "compat-manifest" / "v1"


def write(root, relative, value):
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")


def git(root, *args):
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
                   cwd=root, check=True, capture_output=True)


def unit(unit_id, kind="capability", requires=(), contracts=()):
    return {"$schema": "urn:swissknifeman:aicore:unit:v1", "id": unit_id, "title": unit_id, "kind": kind,
            "version": "0.2.0", "stability": "alpha", "destination": "hub",
            "requires": [{"unit": name, "range": "^0.1"} for name in requires],
            "provides": {"contracts": [{"id": f"urn:test:{unit_id}:{name}", "path": f"schemas/{name}/v1",
                                        "version": "v1", "stability": "alpha"} for name in contracts]}}


def make_hub(root):
    """Two modules with schemas, a bridge, a plugin and the files of the attestation, committed."""
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    write(root, "CHANGELOG.md", "# Changelog\n\n## [1.2.0] - 2026-01-02\n- entry\n")
    write(root, ".agents/plugins/marketplace.json", {"plugins": []})
    write(root, ".claude-plugin/marketplace.json", {"plugins": [{"name": "plug", "source": "vendor/plug"}]})
    write(root, "vendor/plug/.claude-plugin/plugin.json", {"version": "1.2.0", "commands": "./commands"})
    write(root, "vendor/plug/commands/go.md", "go\n")
    write(root, "configs/release-units.json", {
        "schema_version": "release-unit-policy/v1", "default_plugin_version_owner": "umbrella",
        "plugins": {"plug": {"version_owner": "umbrella", "required_providers": ["claude-code"]}}})
    write(root, "packages/found/unit.json", unit("found", "foundation", contracts=("alpha",)))
    write(root, "packages/found/schemas/alpha/v1/alpha.schema.json",
          {"$id": "urn:test:found:alpha:v1", "type": "object"})
    write(root, "packages/found/schemas/alpha/v1/examples/valid/one.json", {})
    write(root, "packages/mod/unit.json", unit("mod", requires=("found",), contracts=("beta",)))
    write(root, "packages/mod/schemas/beta/v1/beta.schema.json", {"$id": "urn:test:mod:beta:v1", "type": "object"})
    write(root, "bridges/mod-found/unit.json", unit("mod-found", "bridge", requires=("found", "mod")))
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixture")


class BundleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name).resolve()
        self.hub = self.tmp / "hub"
        make_hub(self.hub)

    def run_bundle(self, name, tag="v1.2.0", out_dir=None):
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(["release", "bundle", "--root", str(self.hub), "--tag", tag,
                         "--out", str(out_dir or self.tmp / name)], out=out, err=err)
        return code, out.getvalue(), err.getvalue()

    def test_the_bundle_holds_the_four_files_and_nothing_else(self):
        code, stdout, err = self.run_bundle("a")
        self.assertEqual((0, ""), (code, err))
        names = sorted(path.name for path in (self.tmp / "a").iterdir())
        self.assertEqual(["SHA256SUMS", "compat.json", "release-attestation.json", "schemas-v1.2.0.tar.gz"], names)
        self.assertEqual(names, sorted(line[len("wrote "):] for line in stdout.splitlines()))
        self.assertEqual(["a", "hub"], sorted(path.name for path in self.tmp.iterdir()))

    def test_two_runs_are_byte_identical(self):
        self.assertEqual(0, self.run_bundle("a")[0])
        self.assertEqual(0, self.run_bundle("b")[0])
        for path in sorted((self.tmp / "a").iterdir()):
            self.assertEqual(path.read_bytes(), (self.tmp / "b" / path.name).read_bytes(), path.name)

    def test_sha256sum_accepts_the_bundle(self):
        self.run_bundle("a")
        if shutil.which("sha256sum") is None:
            self.skipTest("sha256sum is not installed")
        result = subprocess.run(["sha256sum", "-c", "--quiet", "SHA256SUMS"], cwd=self.tmp / "a",
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        lines = (self.tmp / "a" / "SHA256SUMS").read_text().splitlines()
        self.assertEqual(["compat.json", "release-attestation.json", "schemas-v1.2.0.tar.gz"],
                         [line.split("  ")[1] for line in lines])

    def test_compat_manifest_follows_the_schema_and_the_unit_files(self):
        self.run_bundle("a", tag="rc-1")
        doc = json.loads((self.tmp / "a" / "compat.json").read_text())
        registry, kind = schema.load_contract(SCHEMA_DIR)
        self.assertEqual([], schema.validate(doc, kind, registry))
        self.assertEqual({"version": "1.2.0", "tag": "rc-1"}, doc["umbrella"])
        self.assertEqual(["found", "mod"], [item["id"] for item in doc["units"]])
        self.assertEqual(["mod-found"], [item["id"] for item in doc["bridges"]])
        mod = doc["units"][1]
        self.assertEqual([{"unit": "found", "range": "^0.1"}], mod["requires"])
        self.assertEqual("packages/mod/schemas/beta/v1", mod["contracts"][0]["path"])

    def test_schema_package_has_an_index_and_normalised_members(self):
        self.run_bundle("a")
        with tarfile.open(self.tmp / "a" / "schemas-v1.2.0.tar.gz") as tar:
            members = tar.getmembers()
            names = [member.name for member in members]
            self.assertEqual("index.json", names[0])
            self.assertEqual(sorted(names[1:]), names[1:])
            self.assertIn("packages/found/schemas/alpha/v1/examples/valid/one.json", names)
            for member in members:
                self.assertEqual((0, 0, 0, "", ""), (member.mtime, member.uid, member.gid, member.uname, member.gname))
            index = json.loads(tar.extractfile("index.json").read())["schemas"]
        self.assertEqual(["urn:test:found:alpha:v1", "urn:test:mod:beta:v1"], [item["id"] for item in index])
        self.assertEqual({"id", "version", "path", "sha256"}, set(index[0]))
        self.assertEqual("v1", index[0]["version"])

    def test_attestation_is_taken_at_head_and_the_tag_is_only_a_label(self):
        code, _out, err = self.run_bundle("a", tag="v0.0.0-label")
        self.assertEqual((0, ""), (code, err))
        doc = json.loads((self.tmp / "a" / "release-attestation.json").read_text())
        self.assertEqual("release-attestation/v1", doc["schema_version"])
        self.assertEqual("v1.2.0", doc["umbrella"]["tag"])
        self.assertTrue((self.tmp / "a" / "schemas-v0.0.0-label.tar.gz").is_file())

    def test_a_non_empty_out_is_refused_and_left_alone(self):
        target = self.tmp / "full"
        target.mkdir()
        (target / "keep.txt").write_text("keep")
        code, _out, err = self.run_bundle("full")
        self.assertEqual(2, code)
        self.assertIn("OUT_NOT_EMPTY", err)
        self.assertEqual(["keep.txt"], [path.name for path in target.iterdir()])

    def test_an_empty_out_is_accepted_and_a_bad_tag_writes_nothing(self):
        (self.tmp / "empty").mkdir()
        self.assertEqual(0, self.run_bundle("empty")[0])
        code, _out, err = self.run_bundle("bad", tag="../x")
        self.assertEqual(2, code)
        self.assertIn("TAG_INVALID", err)
        self.assertFalse((self.tmp / "bad").exists())

    def test_a_root_that_is_not_a_repository_fails_without_output(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(["release", "bundle", "--root", str(plain), "--tag", "v1", "--out", str(self.tmp / "o")],
                        out=out, err=err)
        self.assertEqual(1, code)
        self.assertFalse((self.tmp / "o").exists())

    def test_usage_errors_exit_2(self):
        self.assertEqual(2, cli.main(["release", "bundle"], err=io.StringIO()))
        self.assertEqual(2, cli.main(["release"], err=io.StringIO()))


if __name__ == "__main__":
    unittest.main()
