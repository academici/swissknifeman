"""Test helpers: fake registry and fake projects in temporary directories.

Tests are running CLI vs. synthetic registry (several buckets, profiles,
buckets.json) — don't mind real 125 skills, so as not to break down at each
content editing. This covers logic connect/vendor/registry/selection,
and not a specific set of skills."""
import json

from skiller.common import Env


def write_skill(skill_dir, name, *, version="0.1.0", description="desc",
                requires=None, body="Body.\n"):
    """Create a skill directory with SKILL.md (frontmatter + body)."""
    skill_dir.mkdir(parents=True, exist_ok=True)
    fm = ["---", f"name: {name}", f"version: {version}",
          f"description: {description}"]
    if requires:
        fm.append(f"requires: [{', '.join(requires)}]")
    fm.append("---")
    (skill_dir / "SKILL.md").write_text("\n".join(fm) + "\n\n" + body,
                                        encoding="utf-8")


def write_upstream(skill_dir, *, source="github", url="https://example/SKILL.md",
                   sha256="deadbeef", fetched_at="2026-01-01",
                   strategy="notify", path="SKILL.md", review_pending=None,
                   body_path=None, extra_files=None):
    """Put upstream.json next to SKILL.md (marks the skill as external).

    strategy/path/review_pending — for fork-skills (path points to the mirror,
    e.g. references/source.md, and not on SKILL.md). body_path (P7.3 thin-navigator) —
    additive field, names files[]-recording with real upstream body (see
    schema/upstream.schema.json); extra_files — add. files[]-records (dict-s) on top
    main, e.g. to hold at the same time SKILL.md AND references/full.md."""
    import json as _json
    data = {
        "schema_version": 1,
        "source": source,
        "strategy": strategy,
        "files": [{"path": path, "url": url, "sha256": sha256,
                   "fetched_at": fetched_at}, *(extra_files or [])],
    }
    if review_pending is not None:
        data["review_pending"] = review_pending
    if body_path is not None:
        data["body_path"] = body_path
    (skill_dir / "upstream.json").write_text(_json.dumps(data) + "\n", encoding="utf-8")


def make_registry(tmp_path):
    """Build a minimal but valid registry in tmp_path.

    Buckets:
      php/      laravel-conventions (requires: code-style)
                code-style
      quality/  test-writer
      devops/   docker
    Profile laravel-project -> [php, quality]; standalone -> ["*"] include_meta.
    Returns (root: Path, Env).
    """
    root = tmp_path / "registry"
    skills = root / "skills"
    # P3 publication reads the sole package-version source before rendering.
    (root / "package.json").parent.mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text(
        json.dumps({"name": "@fixture/registry", "version": "0.1.0"}) + "\n",
        encoding="utf-8")

    write_skill(skills / "php" / "laravel-conventions", "laravel-conventions",
                requires=["code-style"], description="Laravel conventions")
    write_skill(skills / "php" / "code-style", "code-style",
                description="PHP code style")
    write_skill(skills / "quality" / "test-writer", "test-writer",
                description="Test writer")
    write_skill(skills / "devops" / "docker", "docker", description="Docker")

    # generate-skill meta-skill (for include_meta profiles)
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

    # buckets.json (1:1 with bucket catalogs)
    (root / "buckets.json").write_text(json.dumps({
        "php": {"description": "PHP", "category": "engineering", "tags": ["php"]},
        "quality": {"description": "Quality", "category": "engineering",
                    "tags": ["test"]},
        "devops": {"description": "DevOps", "category": "infrastructure",
                   "tags": ["docker"]},
    }) + "\n")

    # marketplace.json placeholder (launcher checks for presence; tests are calling main directly)
    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (root / ".claude-plugin" / "marketplace.json").write_text("{}\n")

    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = Env(root, home=home)
    return root, env


def make_laravel_project(tmp_path, *, boost=False):
    """Fake Laravel-project: artisan + composer.json (+ boost.json).
    autodetect should recognize it as laravel-project."""
    proj = tmp_path / "myapp"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "artisan").write_text("#!/usr/bin/env php\n<?php\n")
    (proj / "composer.json").write_text(json.dumps(
        {"name": "acme/app", "require": {"laravel/framework": "^11.0"}}) + "\n")
    if boost:
        (proj / "boost.json").write_text(json.dumps({"skills": []}) + "\n")
    return proj


def make_standalone_project(tmp_path):
    """Directory without stack markers - autodetect → standalone (type not recognized)."""
    proj = tmp_path / "blank"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "README.md").write_text("# blank\n")
    return proj
