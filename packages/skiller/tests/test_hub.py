"""Тесты генератора хаба (`lib/skiller/hub.py`, лаунчер `scripts/generate-hub.sh`).

До P2.5 генератор жил в heredoc'е bash-скрипта и тестов не имел вовсе. Здесь
проверяется контракт формы блока (D20): краткая форма каналу с нативным листингом,
полная — каналу без него, флаг возврата, сверка перед сокращением, идемпотентность,
сохранность содержимого ВНЕ маркеров и freshness-штамп.
"""
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from skiller import hub
from skiller.common import Env

INDEX_TITLE = "## Установленные скиллы"
RESIDUAL_TITLE = "## Скиллы вне нативного листинга"


def _skill_md(name, description):
    return f"---\nname: {name}\nversion: 0.1.0\ndescription: {description}\n---\n\nBody.\n"


def make_monorepo(tmp):
    """Мини-монорепо: <mono>/core, <mono>/packages/skiller (реестр из 3 скиллов),
    <mono>/.claude-plugin/marketplace.json с курируемым и бакетным плагином."""
    mono = Path(tmp) / "mono"
    (mono / "core").mkdir(parents=True)
    root = mono / "packages" / "skiller"
    skills = root / "skills"
    entries = [("php", "code-style", "PHP code style"),
               ("php", "laravel-conventions", "Laravel conventions"),
               ("quality", "test-writer", "Test writer")]
    for bucket, name, desc in entries:
        d = skills / bucket / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(_skill_md(name, desc), encoding="utf-8")
    (root / "skills.json").write_text(json.dumps({"skills": [
        {"name": name, "bucket": bucket, "path": f"skills/{bucket}/{name}/SKILL.md",
         "version": "0.1.0", "description": desc}
        for bucket, name, desc in entries]}), encoding="utf-8")
    (root / "buckets.json").write_text(json.dumps({
        "php": {"description": "PHP"}, "quality": {"description": "Quality"}}),
        encoding="utf-8")
    (mono / ".claude-plugin").mkdir()
    (mono / ".claude-plugin" / "marketplace.json").write_text(json.dumps({
        "name": "swissknifeman", "plugins": [
            {"name": "php", "source": "./packages/skiller/skills/php"},
            {"name": "quality", "source": "./packages/skiller/skills/quality"},
            {"name": "curated", "source": "./",
             "skills": ["./packages/skiller/skills/php/code-style"]},
        ]}), encoding="utf-8")
    home = mono / "home"
    home.mkdir()
    hub._REGISTRY_CACHE.pop(str(root), None)
    return Env(root, "generate-hub", home=home)


def make_project(tmp, *, plugins=("php", "quality"), claude_md=None, boost=False,
                 config=None):
    proj = Path(tmp) / "project"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude" / "settings.local.json").write_text(json.dumps(
        {"enabledPlugins": {f"{p}@swissknifeman": True for p in plugins}}),
        encoding="utf-8")
    if claude_md is not None:
        (proj / "CLAUDE.md").write_text(claude_md, encoding="utf-8")
    if boost:
        (proj / "boost.json").write_text("{}\n", encoding="utf-8")
    if config is not None:
        (proj / ".swissknife.json").write_text(json.dumps(config), encoding="utf-8")
    return proj


def run_hub(env, proj, **kw):
    buf = io.StringIO()
    with redirect_stdout(buf):
        result = hub.run(env, proj, **kw)
    result["stdout"] = buf.getvalue()
    return result


class HubFormTests(unittest.TestCase):
    """Форма блока определяется каналом-целью, а не проектом (D20)."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = make_monorepo(self.tmp.name)

    def test_claude_md_gets_short_form(self):
        proj = make_project(self.tmp.name, config={"buckets": ["php", "quality"]})
        result = run_hub(self.env, proj)
        text = (proj / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertEqual(result["forms"]["CLAUDE.md"], hub.FORM_SHORT)
        self.assertNotIn(INDEX_TITLE, text)
        self.assertNotIn("- **code-style**", text)
        self.assertIn("НАТИВНЫМ листингом", text)
        self.assertIn("--full-index", text)  # указатель на полную форму

    def test_root_files_get_full_form_in_same_run(self):
        """Один прогон, две цели: CLAUDE.md краткая, AGENTS.md полная."""
        proj = make_project(self.tmp.name, config={"buckets": ["php", "quality"]})
        result = run_hub(self.env, proj, root_files=["AGENTS.md"])
        self.assertEqual(result["forms"]["AGENTS.md"], hub.FORM_FULL)
        agents_md = (proj / "AGENTS.md").read_text(encoding="utf-8")
        claude_md = (proj / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn(INDEX_TITLE, agents_md)
        self.assertIn("- **code-style** — PHP code style", agents_md)
        self.assertNotIn(INDEX_TITLE, claude_md)

    def test_full_index_flag_returns_index_to_claude_md(self):
        proj = make_project(self.tmp.name, config={"buckets": ["php", "quality"]})
        result = run_hub(self.env, proj, full_index=True)
        self.assertEqual(result["forms"]["CLAUDE.md"], hub.FORM_FULL)
        text = (proj / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn(INDEX_TITLE, text)
        self.assertIn("- **test-writer** — Test writer", text)

    def test_boost_target_is_claude_channel(self):
        """Boost вставляет фрагмент в CLAUDE.md — резидентность та же, форма краткая."""
        proj = make_project(self.tmp.name, boost=True,
                            config={"buckets": ["php", "quality"]})
        result = run_hub(self.env, proj)
        out = proj / ".ai" / "guidelines" / "swissknifeman-hub.md"
        self.assertTrue(out.is_file())
        self.assertEqual(list(result["forms"].values()), [hub.FORM_SHORT])
        self.assertNotIn(INDEX_TITLE, out.read_text(encoding="utf-8"))

    def test_stamp_present_in_both_forms(self):
        """freshness-штамп сверяет skiller doctor — он обязан быть в обеих формах."""
        proj = make_project(self.tmp.name, config={"buckets": ["php", "quality"]})
        run_hub(self.env, proj, root_files=["AGENTS.md"])
        for name in ("CLAUDE.md", "AGENTS.md"):
            text = (proj / name).read_text(encoding="utf-8")
            self.assertIn("<!-- swissknifeman:registry sha=", text)
            self.assertIn("skills=3 -->", text)


class HubNativeCheckTests(unittest.TestCase):
    """Сверка перед сокращением: без подтверждения скилл остаётся перечисленным."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = make_monorepo(self.tmp.name)

    def test_unconfirmed_skill_stays_listed(self):
        """Бакет quality не включён плагином, но приехал манифестом вендоринга в
        .ai/skills — нативным листингом Claude Code он не покрыт, значит остаётся."""
        proj = make_project(self.tmp.name, plugins=["php"],
                            config={"buckets": ["php", "quality"]})
        manifest_dir = proj / ".ai" / "skills"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / ".swissknifeman-manifest.json").write_text(json.dumps(
            {"skills": [{"source_path": "skills/quality/test-writer"}]}),
            encoding="utf-8")
        result = run_hub(self.env, proj)
        self.assertEqual(result["check"]["unconfirmed"], ["test-writer"])
        text = (proj / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn(RESIDUAL_TITLE, text)
        self.assertIn("- **test-writer**", text)
        self.assertNotIn("- **code-style**", text)  # подтверждён — ушёл из блока

    def test_confirmed_set_is_intersection_with_measurer(self):
        """Скилл, которого нет в наборе измерителя, не сокращается, даже если
        доставлен плагином (конъюнкция двух источников)."""
        proj = make_project(self.tmp.name, plugins=["php", "quality"],
                            config={"buckets": ["php"]})
        result = run_hub(self.env, proj)
        self.assertNotIn("test-writer", result["check"]["confirmed"])
        self.assertIn("test-writer", result["check"]["unconfirmed"])
        self.assertIn("code-style", result["check"]["confirmed"])

    def test_no_delivery_channel_is_an_error(self):
        proj = Path(self.tmp.name) / "bare"
        (proj / ".claude").mkdir(parents=True)
        with self.assertRaises(SystemExit):
            run_hub(self.env, proj)


class HubWriteTests(unittest.TestCase):
    """Запись: только между маркерами, идемпотентно, файл создаётся при отсутствии."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = make_monorepo(self.tmp.name)

    def test_content_outside_markers_is_preserved(self):
        head = "# Проект\n\nАвторский текст.\n\n"
        tail = "\n## Ниже блока\n\nЕщё авторский текст.\n"
        existing = (head + hub.HUB_START + "\nстарый блок\n" + hub.HUB_END + tail)
        proj = make_project(self.tmp.name, claude_md=existing,
                            config={"buckets": ["php", "quality"]})
        run_hub(self.env, proj)
        text = (proj / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith(head))
        self.assertTrue(text.endswith(tail))
        self.assertNotIn("старый блок", text)

    def test_repeat_run_is_idempotent(self):
        proj = make_project(self.tmp.name, claude_md="# Проект\n\nТекст.\n",
                            config={"buckets": ["php", "quality"]})
        run_hub(self.env, proj, root_files=["AGENTS.md"])
        first = {n: (proj / n).read_text(encoding="utf-8")
                 for n in ("CLAUDE.md", "AGENTS.md")}
        run_hub(self.env, proj, root_files=["AGENTS.md"])
        second = {n: (proj / n).read_text(encoding="utf-8")
                  for n in ("CLAUDE.md", "AGENTS.md")}
        self.assertEqual(first, second)

    def test_missing_claude_md_is_created(self):
        proj = make_project(self.tmp.name, config={"buckets": ["php", "quality"]})
        self.assertFalse((proj / "CLAUDE.md").exists())
        run_hub(self.env, proj)
        text = (proj / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith(hub.HUB_START))
        self.assertIn(hub.HUB_END, text)

    def test_dry_run_writes_nothing(self):
        proj = make_project(self.tmp.name, config={"buckets": ["php", "quality"]})
        result = run_hub(self.env, proj, dry_run=True)
        self.assertFalse((proj / "CLAUDE.md").exists())
        self.assertIn("[dry-run]", result["stdout"])


if __name__ == "__main__":
    unittest.main()
