"""Canonical, resilient project-type detection for the monorepo.

The ordered markers select a value from ``PROJECT_TYPES`` and degrade safely when
manifests are malformed. stdlib-only.
"""
import json
import re
from pathlib import Path

# Ordered from specific to general; IDs match skiller profile names.
PROJECT_TYPES = (
    "obsidian-vault",
    "laravel-project",
    "php-package",
    "dart-flutter",
    "blender",
    "python-backend",
    "node-frontend",
    "node-package",
    "standalone",
)

# Code-graph language by project type.
LANGUAGE_BY_TYPE = {
    "laravel-project": "php",
    "php-package": "php",
    "dart-flutter": "dart",
    "blender": "python",
    "python-backend": "python",
    "node-frontend": "typescript",
    "node-package": "typescript",
}

# Default ``docs`` visibility: public for distributable packages, private for products.
DEFAULT_DOCS_VISIBILITY = "private"
DOCS_VISIBILITY_BY_TYPE = {
    "php-package": "public",
    "node-package": "public",
    "dart-flutter": "public",
    "laravel-project": "private",
    "node-frontend": "private",
    "python-backend": "private",
    "blender": "private",
    "obsidian-vault": "private",
    "standalone": "private",
}


def docs_visibility_for(ptype):
    """Return default ``docs`` visibility for a project type."""
    return DOCS_VISIBILITY_BY_TYPE.get(ptype, DEFAULT_DOCS_VISIBILITY)


# A package.json project is a frontend only with a UI framework or build marker.
_FRONTEND_DEP_HINTS = (
    "vue", "nuxt", "react", "svelte", "@angular/core",
    "@inertiajs/vue3", "@inertiajs/react", "vite",
)
_FRONTEND_CONFIG_FILES = (
    "vite.config.ts", "vite.config.js", "vue.config.js",
    "nuxt.config.ts", "nuxt.config.js", "svelte.config.js",
)


def _load_json(path):
    """Read JSON safely; failures return ``{}``."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_BPY_RE = re.compile(r'^\s*(?:import\s+bpy|from\s+bpy\b)', re.M)


def _is_blender(path):
    """Detect a Blender project from manifest, blend files, or top-level bpy imports."""
    if (path / "blender_manifest.toml").is_file():
        return True
    try:
        if any(path.glob("*.blend")):
            return True
        for py in list(path.glob("*.py"))[:20]:
            try:
                if _BPY_RE.search(py.read_text(encoding="utf-8", errors="ignore")[:2000]):
                    return True
            except OSError:
                continue
    except OSError:
        return False
    return False


def _is_node_frontend(path):
    """Distinguish a package.json frontend from a generic node package."""
    if any((path / name).is_file() for name in _FRONTEND_CONFIG_FILES):
        return True
    pkg = _load_json(path / "package.json")
    deps = {}
    for key in ("dependencies", "devDependencies"):
        section = pkg.get(key)
        if isinstance(section, dict):
            deps.update(section)
    return any(hint in deps for hint in _FRONTEND_DEP_HINTS)


def detect_project_type(path):
    """Detect a project type from ordered markers, defaulting to ``standalone``."""
    p = Path(path)
    if (p / ".obsidian").is_dir():
        return "obsidian-vault"
    composer = (p / "composer.json").is_file()
    if composer and (p / "artisan").is_file():
        return "laravel-project"
    if composer:
        return "php-package"
    if (p / "pubspec.yaml").is_file():
        return "dart-flutter"
    # Blender precedes Python because addons can include Python project markers.
    if _is_blender(p):
        return "blender"
    # Python precedes Node because package.json can be build tooling only.
    if ((p / "pyproject.toml").is_file() or (p / "requirements.txt").is_file()
            or (p / "setup.py").is_file()):
        return "python-backend"
    if (p / "package.json").is_file():
        return "node-frontend" if _is_node_frontend(p) else "node-package"
    return "standalone"
