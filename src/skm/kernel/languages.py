"""Canonical ecosystem and source-language vocabulary (kernel).

Domain, host and adapter code share one table so a new ecosystem cannot drift between
fence tags, steering scopes, graph answers and manifest language labels. The module is
stdlib-only: domain imports kernel, and must not reach platform for this data.

The closed set is the nine configured ecosystem ids plus the manifest aliases readers
emit. An unknown ecosystem id has no language; callers that label a graph use
:func:`language_for_ecosystem` and skip the miss.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

__all__ = [
    "CODE_SUFFIXES",
    "DEBT_FREE_GLOBS",
    "ECOSYSTEMS",
    "EXTENSION_LANGUAGES",
    "FENCE_TAGS",
    "LANGUAGE_EXTENSIONS",
    "RESEARCH_SECRET_NAMES",
    "RESEARCH_SKIPPED_DIRS",
    "RUNNER_DIAGNOSTICS",
    "RUNNER_NAMES",
    "RUNNER_WITH_ARGS",
    "RUNNER_WRAPPER",
    "language_for_ecosystem",
    "language_for_path",
]

# Ecosystem id → language label written onto a project graph.
# The first nine keys are ``ecosystems.ids``. ``pypi`` / ``npm`` / ``composer`` are the
# ids manifest readers emit for the python, node and php families.
ECOSYSTEMS: Final[MappingProxyType[str, str]] = MappingProxyType(
    {
        "python": "python",
        "node": "javascript",
        "php": "php",
        "cargo": "rust",
        "go": "go",
        "ruby": "ruby",
        "brew": "brew",
        "dart": "dart",
        "jvm": "java",
        "pypi": "python",
        "npm": "javascript",
        "composer": "php",
    }
)

# Extension → language. Fence tags that differ (``.tsx`` / ``.jsx``) live in ``FENCE_TAGS``.
# Markdown is a steering scope, not a code language, so it is absent here.
_LANGUAGE_BY_EXTENSION: Final[tuple[tuple[str, str], ...]] = (
    (".py", "python"),
    (".pyi", "python"),
    (".ts", "typescript"),
    (".tsx", "typescript"),
    (".js", "javascript"),
    (".jsx", "javascript"),
    (".mjs", "javascript"),
    (".cjs", "javascript"),
    (".go", "go"),
    (".rs", "rust"),
    (".php", "php"),
    (".sql", "sql"),
    (".java", "java"),
    (".kt", "kotlin"),
    (".rb", "ruby"),
    (".cs", "c#"),
    (".c", "c"),
    (".cpp", "c++"),
    (".cc", "c++"),
    (".dart", "dart"),
    (".toml", "toml"),
    (".yaml", "yaml"),
    (".yml", "yaml"),
    (".json", "json"),
    (".sh", "bash"),
    (".diff", "diff"),
    (".patch", "diff"),
)

EXTENSION_LANGUAGES: Final[MappingProxyType[str, str]] = MappingProxyType(dict(_LANGUAGE_BY_EXTENSION))

# Longest suffix wins so ``.patch`` is not claimed by a shorter neighbour.
_EXTENSIONS_LONGEST_FIRST: Final[tuple[str, ...]] = tuple(sorted(EXTENSION_LANGUAGES, key=len, reverse=True))

FENCE_TAGS: Final[MappingProxyType[str, str]] = MappingProxyType(
    {**EXTENSION_LANGUAGES, ".tsx": "tsx", ".jsx": "jsx"}
)


def _extensions_for(language: str) -> tuple[str, ...]:
    return tuple(ext for ext, name in _LANGUAGE_BY_EXTENSION if name == language)


LANGUAGE_EXTENSIONS: Final[MappingProxyType[str, tuple[str, ...]]] = MappingProxyType(
    {
        "python": _extensions_for("python"),
        "typescript": _extensions_for("typescript"),
        "javascript": _extensions_for("javascript"),
        "go": _extensions_for("go"),
        "rust": _extensions_for("rust"),
        "php": _extensions_for("php"),
        "sql": _extensions_for("sql"),
        "markdown": (".md",),
        "toml": _extensions_for("toml"),
        "yaml": _extensions_for("yaml"),
        "java": _extensions_for("java"),
        "kotlin": _extensions_for("kotlin"),
        "ruby": _extensions_for("ruby"),
        "c#": _extensions_for("c#"),
        "c": _extensions_for("c"),
        "c++": _extensions_for("c++"),
        "dart": _extensions_for("dart"),
        "json": _extensions_for("json"),
        "bash": _extensions_for("bash"),
        "diff": _extensions_for("diff"),
    }
)

# Historical code suffixes used by the revision writer when it has no resolved settings.
CODE_SUFFIXES: Final[tuple[str, ...]] = (".py", ".ts", ".tsx", ".js", ".go", ".rs", ".sql")

# Paths that do not create review debt. This is the historical review set: a source
# file such as ``src/payments.test.ts`` stays in debt unless a finding covers it.
DEBT_FREE_GLOBS: Final[tuple[str, ...]] = (
    "tests/**",
    "**/tests/**",
    "**/test_*.py",
    "**/*_test.py",
    "docs/**",
    "**/docs/**",
    "**/*.md",
)

# Directory names a confined research walk never descends into.
# ``vendor`` and ``target`` stay visible: PHP and Rust/Java sources live there.
RESEARCH_SKIPPED_DIRS: Final[frozenset[str]] = frozenset(
    {
        ".git",
        ".skm",
        ".codex",
        ".ssh",
        ".aws",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".cache",
        "dist",
        "build",
    }
)

# Basenames that mark a file as a credential store for a known ecosystem.
RESEARCH_SECRET_NAMES: Final[tuple[str, ...]] = (
    ".npmrc",
    ".pypirc",
    ".netrc",
    ".cargo/credentials",
    ".cargo/credentials.toml",
)

# Check runners recognized in shell command position (learning).
RUNNER_NAMES: Final[tuple[str, ...]] = (
    "pytest",
    "phpunit",
    "pest",
    "jest",
    "vitest",
    "unittest",
    "ruff",
    "flake8",
    "pylint",
    "mypy",
    "eslint",
    "phpstan",
    "psalm",
    "pint",
    "black",
    "isort",
    "tsc",
    "prettier",
    "composer",
    "py_compile",
    "validate.sh",
    "test.sh",
)

RUNNER_WITH_ARGS: Final[tuple[str, ...]] = (
    "npm test",
    "npm run test",
    "npm run lint",
    "npm lint",
    "yarn test",
    "yarn run test",
    "yarn run lint",
    "yarn lint",
    "pnpm test",
    "pnpm run test",
    "pnpm run lint",
    "pnpm lint",
    "go test",
    "cargo test",
    "sail test",
    "php artisan test",
    "dart test",
    "flutter test",
)

RUNNER_DIAGNOSTICS: Final[frozenset[str]] = frozenset({"grep", "rg", "ag", "find", "ls", "cat", "which"})

# Wrappers stripped before the real executable is classified.
RUNNER_WRAPPER: Final[tuple[str, ...]] = (
    "uv run",
    "python -m",
    "python3 -m",
    "xargs",
    "env",
    "sh",
    "bash",
    "command",
)


def language_for_ecosystem(ecosystem: str) -> str | None:
    """Language label for a manifest ecosystem, or ``None`` when the id is unknown.

    Unknown ids never raise. Callers that record languages on a graph omit the miss.
    """
    return ECOSYSTEMS.get(ecosystem)


def language_for_path(path: str) -> str | None:
    """Language of ``path`` by its extension, or ``None`` for prose and unknown suffixes."""
    lowered = path.lower()
    for ext in _EXTENSIONS_LONGEST_FIRST:
        if lowered.endswith(ext):
            return EXTENSION_LANGUAGES[ext]
    return None
