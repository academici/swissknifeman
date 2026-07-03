"""P7.3 (thin-navigator): scripts/validate.sh body_path-гейты — изолированно, без
задевания настоящего packages/skiller.

scripts/validate.sh — bash-обёртка вокруг python-heredoc'а (та же причина, что у
test_update_upstreams.py: не lib/skiller-модуль, честно тестируется только реальным
запуском). REPO_ROOT резолвится от расположения скрипта, поэтому копируем
validate.sh рядом с МИНИМАЛЬНЫМ синтетическим skills/. Такой корень намеренно НЕ
содержит buckets.json/skills.json/marketplace.json и т.п. — секции validate.sh,
которым они нужны, при их отсутствии мягко копят ERROR (не падают исключением), а
python-heredoc почти сразу делает sys.exit(1) из-за непустого errors[] — bash-секции
11+ (registry --check, полный test.sh, budget --check-core) до реального
packages/skiller НЕ достаются вовсе (и потому не могут рекурсивно перезапустить
этот же тест-сьют). Проверяем не общий exit-код (он ожидаемо ненулевой из-за
недостающего окружения реестра), а КОНКРЕТНЫЕ строки про body_path в stdout."""
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
VALIDATE_SCRIPT = PKG_ROOT / "scripts" / "validate.sh"


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ValidateBodyPathCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "registry"
        self.skill_dir = self.root / "skills" / "external" / "thin-monolith"
        self.skill_dir.mkdir(parents=True)
        (self.skill_dir / "SKILL.md").write_text(
            "---\nname: thin-monolith\n"
            "description: Navigator only, body lives in references/full.md.\n"
            "---\n\nSee references/full.md for the full content.\n",
            encoding="utf-8")
        refs = self.skill_dir / "references"
        refs.mkdir()
        self.body_text = "Full upstream body.\n"
        (refs / "full.md").write_text(self.body_text, encoding="utf-8")
        scripts_dir = self.root / "scripts"
        scripts_dir.mkdir()
        shutil.copy2(VALIDATE_SCRIPT, scripts_dir / "validate.sh")

    def tearDown(self):
        self._tmp.cleanup()

    def _write_upstream(self, **overrides):
        data = {
            "schema_version": 1, "source": "file", "strategy": "notify",
            "body_path": "references/full.md",
            "files": [{"path": "references/full.md", "url": "file:///unused",
                      "sha256": _sha256(self.body_text), "fetched_at": "2026-07-01"}],
        }
        data.update(overrides)
        (self.skill_dir / "upstream.json").write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def _run(self):
        return subprocess.run(
            ["bash", str(self.root / "scripts" / "validate.sh")],
            capture_output=True, text=True, timeout=60)

    def test_valid_body_path_no_related_errors(self):
        self._write_upstream()
        result = self._run()
        out = result.stdout
        self.assertNotIn("Traceback", out + result.stderr)
        self.assertNotIn("body_path", out,
                         "well-formed body_path must not raise any body_path error")

    def test_body_path_not_tracked_in_files(self):
        self._write_upstream(body_path="references/missing.md")
        result = self._run()
        self.assertIn(
            "body_path 'references/missing.md' is not tracked in files[]",
            result.stdout)

    def test_body_path_escaping_skill_dir(self):
        self._write_upstream(body_path="../../etc/passwd")
        result = self._run()
        self.assertIn("body_path escapes skill dir", result.stdout)

    def test_replace_strategy_with_skill_md_still_tracked_is_rejected(self):
        # Иначе update-upstreams.sh --apply тихо перезаписал бы навигатор.
        self._write_upstream(strategy="replace", files=[
            {"path": "references/full.md", "url": "file:///unused",
             "sha256": _sha256(self.body_text), "fetched_at": "2026-07-01"},
            {"path": "SKILL.md", "url": "file:///unused2",
             "sha256": "deadbeef", "fetched_at": "2026-07-01"},
        ])
        result = self._run()
        self.assertIn(
            "body_path set (thin-navigator) but files[] also tracks SKILL.md "
            "under strategy=replace", result.stdout)


if __name__ == "__main__":
    unittest.main()
