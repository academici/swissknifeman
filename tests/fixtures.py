"""Хелперы для тестов: фейковый реестр и фейковые проекты во временных каталогах.

Тесты гоняют CLI против синтетического реестра (несколько бакетов, профили,
buckets.json) — не против настоящих 125 скиллов, чтобы не ломаться при каждой
правке контента. Это покрывает логику connect/vendor/registry/selection,
а не конкретный набор скиллов."""
import json
from pathlib import Path

from swissknifeman.common import Env


def write_skill(skill_dir, name, *, version="0.1.0", description="desc",
                requires=None, body="Body.\n"):
    """Создать каталог скилла с SKILL.md (frontmatter + тело)."""
    skill_dir.mkdir(parents=True, exist_ok=True)
    fm = ["---", f"name: {name}", f"version: {version}",
          f"description: {description}"]
    if requires:
        fm.append(f"requires: [{', '.join(requires)}]")
    fm.append("---")
    (skill_dir / "SKILL.md").write_text("\n".join(fm) + "\n\n" + body,
                                        encoding="utf-8")


def make_registry(tmp_path):
    """Собрать минимальный, но валидный реестр в tmp_path.

    Бакеты:
      php/      laravel-conventions (requires: code-style)
                code-style
      quality/  test-writer
      devops/   docker
    Профиль laravel-project -> [php, quality]; standalone -> ["*"] include_meta.
    Возвращает (root: Path, Env).
    """
    root = tmp_path / "registry"
    skills = root / "skills"

    write_skill(skills / "php" / "laravel-conventions", "laravel-conventions",
                requires=["code-style"], description="Laravel conventions")
    write_skill(skills / "php" / "code-style", "code-style",
                description="PHP code style")
    write_skill(skills / "quality" / "test-writer", "test-writer",
                description="Test writer")
    write_skill(skills / "devops" / "docker", "docker", description="Docker")

    # generate-skill meta-skill (для include_meta профилей)
    write_skill(root / "generate-skill" / "generate-skill", "generate-skill",
                description="Meta-skill")

    # profiles
    profiles = root / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    (profiles / "laravel-project.json").write_text(json.dumps({
        "name": "laravel-project", "description": "Laravel",
        "buckets": ["php", "quality"], "include_meta": False}) + "\n")
    (profiles / "php-package.json").write_text(json.dumps({
        "name": "php-package", "description": "PHP pkg",
        "buckets": ["php", "devops"], "include_meta": False}) + "\n")
    (profiles / "obsidian-vault.json").write_text(json.dumps({
        "name": "obsidian-vault", "description": "Vault",
        "buckets": ["quality"], "include_meta": False}) + "\n")
    (profiles / "standalone.json").write_text(json.dumps({
        "name": "standalone", "description": "All",
        "buckets": ["*"], "include_meta": True}) + "\n")

    # buckets.json (1:1 с каталогами бакетов)
    (root / "buckets.json").write_text(json.dumps({
        "php": {"description": "PHP", "category": "engineering", "tags": ["php"]},
        "quality": {"description": "Quality", "category": "engineering",
                    "tags": ["test"]},
        "devops": {"description": "DevOps", "category": "infrastructure",
                   "tags": ["docker"]},
    }) + "\n")

    # marketplace.json placeholder (launcher проверяет наличие; тесты зовут main напрямую)
    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (root / ".claude-plugin" / "marketplace.json").write_text("{}\n")

    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = Env(root, home=home)
    return root, env


def make_laravel_project(tmp_path, *, boost=False):
    """Фейковый Laravel-проект: artisan + composer.json (+ boost.json).
    autodetect должен распознать его как laravel-project."""
    proj = tmp_path / "myapp"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "artisan").write_text("#!/usr/bin/env php\n<?php\n")
    (proj / "composer.json").write_text(json.dumps(
        {"name": "acme/app", "require": {"laravel/framework": "^11.0"}}) + "\n")
    if boost:
        (proj / "boost.json").write_text(json.dumps({"skills": []}) + "\n")
    return proj
