"""P4.2 source-direction validator tests for the canonical template boundary."""

from __future__ import annotations

import subprocess
import shutil
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CHECKER = PACKAGE_ROOT / "scripts" / "check-translations.sh"


class TranslationDirectionTest(unittest.TestCase):
    def test_strict_check_accepts_canonical_english_template(self) -> None:
        result = subprocess.run(["bash", str(CHECKER), "--strict"], cwd=PACKAGE_ROOT,
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("EN canonical template", result.stdout)

    def test_checker_refuses_provider_controls_and_source_language_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skiller"
            (root / "scripts").mkdir(parents=True)
            generated = root / "generate-skill" / "generate-skill" / "snippets"
            generated.mkdir(parents=True)
            shutil.copy2(CHECKER, root / "scripts" / "check-translations.sh")
            original = (PACKAGE_ROOT / "SKILL_TEMPLATE.md").read_text(encoding="utf-8")
            (root / "SKILL_TEMPLATE.md").write_text(
                original.replace("provenance: local|upstream", "provenance: local|upstream\nadapters: [codex]")
                .replace("# Skill purpose", "# Назначение skill"), encoding="utf-8")
            (generated / "SKILL_TEMPLATE.md").write_text(original, encoding="utf-8")
            result = subprocess.run(["bash", str(root / "scripts" / "check-translations.sh"), "--strict"],
                                    cwd=root, capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("AUTHORING_SOURCE_NOT_ENGLISH", result.stderr)
        self.assertIn("SKILL_EVIDENCE_PROVIDER_TUNING_SHARED", result.stderr)


if __name__ == "__main__":
    unittest.main()
