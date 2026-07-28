"""Тесты валидатора реестра ролей ревью (harness.reviewroles) — изоляция в tmpdir.

Позитив: синтетический реестр+пак+канон проходит все восемь проверок чисто. Пять
негативных фикстур — по одной на класс отказа, названный Implementation Rules
P9.2: отсутствующая проекция · заголовок вне канона · роль вне реестра · измерение
вне словаря · неизменённый `review_version`."""
import json
import tempfile
import unittest
from pathlib import Path

from harness import reviewroles as rr

_CARRIER_TEXT = (
    "---\nname: demo-reviewer\n---\n\n"
    "## Критерии\n\n- пример критерия\n\n"
    "## Гейты вердикта\n\n- пример гейта\n\n"
    "## Проектные оверрайды\n\nпример\n\n"
    "## Выход\n\nпример\n"
)

_REVIEW_ROLE = {
    "pack_id": "demo-pack",
    "role_id": "reviewer",
    "projection": "demo-pack/agents/reviewer.md",
    "overrides": "demo-pack/rules/reviewer-overrides.md",
    "required_sections": ["criteria", "verdict_gates", "project_overrides", "output"],
    "sections": {
        "criteria": "## Критерии",
        "verdict_gates": "## Гейты вердикта",
        "project_overrides": "## Проектные оверрайды",
        "output": "## Выход",
    },
    "dimensions": ["over-engineering", "generated-assets"],
}


class ReviewRolesTestCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.root = Path(self._tmpdir.name)

        self.agent_packs_dir = self.root / "configs" / "claude-code" / "agent-packs"
        pack = self.agent_packs_dir / "demo-pack"
        (pack / "agents").mkdir(parents=True)
        (pack / "rules").mkdir(parents=True)
        (pack / "agents" / "reviewer.md").write_text(_CARRIER_TEXT, encoding="utf-8")
        (pack / "rules" / "reviewer-overrides.md").write_text("# оверрайды\n", encoding="utf-8")

        self.roles_json = self.root / "roles.json"
        self.roles_json.write_text(json.dumps({
            "catalog_version": "1.0.0",
            "roles": [{
                "pack_id": "demo-pack", "role_id": "reviewer",
                "content": _CARRIER_TEXT, "skills": ["demo-skill"],
            }],
        }), encoding="utf-8")

        self.skills_json = self.root / "skills.json"
        self.skills_json.write_text(json.dumps({"skills": [{"name": "demo-skill"}]}), encoding="utf-8")

        self._orig_package_root = rr._PACKAGE_ROOT
        self._orig_roles_json = rr._ROLES_JSON
        self._orig_skills_json = rr._SKILLS_JSON
        rr._PACKAGE_ROOT = self.root
        rr._ROLES_JSON = self.roles_json
        rr._SKILLS_JSON = self.skills_json
        self.addCleanup(self._restore_globals)

    def _restore_globals(self):
        rr._PACKAGE_ROOT = self._orig_package_root
        rr._ROLES_JSON = self._orig_roles_json
        rr._SKILLS_JSON = self._orig_skills_json

    def _registry(self, role_overrides=None, review_version="1.0.0"):
        role = dict(_REVIEW_ROLE)
        if role_overrides:
            role.update(role_overrides)
        return {
            "review_version": review_version,
            "pack_root": "claude-code/agent-packs",
            "roles": [role],
        }

    def _run(self, data):
        path = self.root / "review-roles.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        fingerprint = rr._composition_fingerprint(data)
        orig = dict(rr._VERSION_FINGERPRINTS)
        rr._VERSION_FINGERPRINTS = {data["review_version"]: fingerprint}
        try:
            return rr.run_checks(path)
        finally:
            rr._VERSION_FINGERPRINTS = orig

    def test_positive_registry_is_clean(self):
        violations, code = self._run(self._registry())
        self.assertEqual(violations, [])
        self.assertEqual(code, 0)

    def test_negative_missing_projection(self):
        violations, code = self._run(self._registry(
            {"projection": "demo-pack/agents/does-not-exist.md"}))
        self.assertEqual(code, 1)
        self.assertTrue(any(v.check == "carrier-paths" for v in violations))

    def test_negative_heading_not_in_canon(self):
        violations, code = self._run(self._registry({"sections": {
            "criteria": "## Критерии", "verdict_gates": "## Гейты вердикта",
            "project_overrides": "## Проектные оверрайды", "output": "## Заведомо не существует",
        }}))
        self.assertEqual(code, 1)
        self.assertTrue(any(v.check == "sections-present" for v in violations))

    def test_negative_role_outside_registry(self):
        # Второй пак несёт agents/reviewer.md на диске, но НЕ упомянут в реестре.
        pack2 = self.agent_packs_dir / "second-pack" / "agents"
        pack2.mkdir(parents=True)
        (pack2 / "reviewer.md").write_text(_CARRIER_TEXT, encoding="utf-8")
        violations, code = self._run(self._registry())
        self.assertEqual(code, 1)
        self.assertTrue(any(v.check == "default-deny" and "second-pack" in v.message
                            for v in violations))

    def test_negative_canon_role_outside_registry(self):
        # roles.json несёт reviewer-роль третьего пака, которого нет в review-roles.json.
        self.roles_json.write_text(json.dumps({
            "catalog_version": "1.0.0",
            "roles": [
                {"pack_id": "demo-pack", "role_id": "reviewer",
                 "content": _CARRIER_TEXT, "skills": ["demo-skill"]},
                {"pack_id": "third-pack", "role_id": "reviewer",
                 "content": _CARRIER_TEXT, "skills": []},
            ],
        }), encoding="utf-8")
        violations, code = self._run(self._registry())
        self.assertEqual(code, 1)
        self.assertTrue(any(v.check == "default-deny" and "third-pack" in v.message
                            for v in violations))

    def test_negative_dimension_outside_dictionary(self):
        violations, code = self._run(self._registry(
            {"dimensions": ["over-engineering", "made-up-dimension"]}))
        self.assertEqual(code, 1)
        self.assertTrue(any(v.check == "dimensions" for v in violations))

    def test_negative_review_version_unchanged(self):
        data = self._registry()
        path = self.root / "review-roles.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        # Отпечаток НЕ зарегистрирован для текущего состава — версия "не сдвинута".
        orig = dict(rr._VERSION_FINGERPRINTS)
        rr._VERSION_FINGERPRINTS = {"1.0.0": "0" * 64}
        try:
            violations, code = rr.run_checks(path)
        finally:
            rr._VERSION_FINGERPRINTS = orig
        self.assertEqual(code, 1)
        self.assertTrue(any(v.check == "version-bump" for v in violations))

    def test_missing_registry_file_gives_exit_2(self):
        violations, code = rr.run_checks(self.root / "nope.json")
        self.assertEqual(code, 2)
        self.assertTrue(violations)

    def test_missing_skills_json_gives_one_diagnostic_violation(self):
        # Standalone-раскладка пакета (skiller-сосед отсутствует) — ОДНА диагностичная
        # находка, не N ложных «skill не найден» (P11.8, реконсиляция аудита P9, находка 7).
        rr._SKILLS_JSON = self.root / "does-not-exist" / "skills.json"
        violations, code = self._run(self._registry())
        self.assertEqual(code, 1)
        skills_violations = [v for v in violations if v.check == "skills"]
        self.assertEqual(len(skills_violations), 1)
        self.assertIn("индекс скиллов недоступен", skills_violations[0].message)


if __name__ == "__main__":
    unittest.main()
