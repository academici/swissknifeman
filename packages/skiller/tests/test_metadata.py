"""Skill metadata (E27): license, compatibility and allowed_tools in skills.json, `skiller describe`,
and the library-wide metadata gate that validate.sh runs through scripts/test.sh."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from aicore.content.skill import describe_skill, read_frontmatter
from skiller.describe import cmd_describe
from skiller.registry import build_registry
import tests.fixtures as fx

PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def metadata_errors(skill_dir):
    """Violations of the metadata rules for one skill directory (empty when valid)."""
    skill_md = skill_dir / "SKILL.md"
    try:
        descriptor = describe_skill(skill_dir, skill_id=skill_dir.name)
    except ValueError as exc:
        return [str(exc)]
    errors = []
    if (skill_dir / "upstream.json").is_file() and not descriptor.license:
        errors.append(f"{skill_md}: upstream skill has no license (frontmatter or upstream.json)")
    fm = read_frontmatter(skill_md)
    if "license" in fm and not (isinstance(fm["license"], str) and fm["license"].strip()):
        errors.append(f"{skill_md}: license must be a nonempty string")
    allowed = fm.get("allowed-tools", fm.get("allowed_tools"))
    if isinstance(allowed, list):
        errors.append(f"{skill_md}: allowed-tools must be a string, not a list")
    return errors


def run_describe(env, *argv):
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            cmd_describe(env, list(argv))
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class LibraryMetadataGate(unittest.TestCase):
    def test_every_library_skill_is_described_and_valid(self):
        problems = []
        for skill_md in sorted(PACKAGE_ROOT.glob("skills/**/SKILL.md")):
            problems.extend(metadata_errors(skill_md.parent))
        self.assertEqual(problems, [])

    def test_violating_fixture_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "bad"
            fx.write_skill(skill, "bad")
            fx.write_upstream(skill)
            errors = metadata_errors(skill)
            self.assertTrue(any("no license" in e for e in errors), errors)
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            (skill / "SKILL.md").write_text(
                text.replace("description: desc", "description: desc\ncompatibility: " + "x" * 501),
                encoding="utf-8")
            self.assertTrue(any("compatibility" in e for e in metadata_errors(skill)))


class RegistryMetadata(unittest.TestCase):
    def test_license_chain_and_optional_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = fx.make_registry(Path(tmp))
            pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
            pkg["license"] = "Apache-2.0"
            (root / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
            skill = root / "skills" / "quality" / "test-writer"
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            (skill / "SKILL.md").write_text(
                text.replace("---\n\n", "compatibility: needs git\nallowed-tools: Bash Read\n---\n\n", 1),
                encoding="utf-8")
            entries = {e["name"]: e for e in build_registry(env)[0]["skills"]}
            self.assertEqual(entries["code-style"]["license"], "Apache-2.0")
            self.assertNotIn("compatibility", entries["code-style"])
            self.assertEqual(entries["test-writer"]["compatibility"], "needs git")
            self.assertEqual(entries["test-writer"]["allowed_tools"], "Bash Read")
            keys = list(entries["test-writer"])
            self.assertLess(keys.index("content_sha256"), keys.index("license"))

    def test_describe_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = fx.make_registry(Path(tmp))
            from skiller.registry import cmd_registry
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_registry(env, [])
            code, out, _ = run_describe(env, "code-style", "--json")
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["name"], "code-style")
            code, out, _ = run_describe(env, "code-style")
            self.assertIn("license:", out)
            code, _, err = run_describe(env, "no-such-skill-xyz")
            self.assertEqual(code, 1)
            self.assertIn("unknown skill: no-such-skill-xyz", err)


if __name__ == "__main__":
    unittest.main()
