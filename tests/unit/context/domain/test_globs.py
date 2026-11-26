"""Glob segment boundaries and inert dependency manifest extraction."""

import pytest

from skm.modules.context.domain.deps import project_deps
from skm.modules.context.domain.globs import glob_regex, path_matches


@pytest.mark.parametrize(
    ("path", "pattern", "matches"),
    [
        ("src/a.py", "src/*.py", True),
        ("src/a/b.py", "src/*.py", False),
        ("a.py", "**/*.py", True),
        ("src/a/b.py", "**/*.py", True),
        ("src/a.py", "src/**/a.py", True),
        ("src/x/a.py", "src/**/a.py", True),
        ("src/a.py", "*.py", True),
        ("src/a.py", "src/?.py", True),
        ("src/ab.py", "src/?.py", False),
        ("src/a.py", "src/[ab].py", True),
        ("src/c.py", "src/[!ab].py", True),
        ("src/a.py", "src/[!ab].py", False),
        ("src//.py", "src/[!ab].py", False),
        ("a+b.py", "a+b.py", True),
        ("axb.py", "a+b.py", False),
        ("foo[", "foo[", True),
    ],
)
def test_glob_semantics(path, pattern, matches):
    assert path_matches(path, pattern) is matches
    assert glob_regex(pattern).startswith("^")


def test_dependency_facts_include_pep508_extras_build_poetry_and_ecosystems():
    facts = project_deps(
        {
            "repo/pyproject.toml": """[project]
dependencies = ["HTTP_X[http2]>=1; python_version > '3'", "foo.bar @ https://example.com/foo"]
[project.optional-dependencies]
test = ["pytest>=8"]
[build-system]
requires = ["poetry-core>=2"]
[tool.poetry.dependencies]
python = "^3.12"
requests = "*"
[tool.poetry.group.dev.dependencies]
ruff = "*"
""",
            "package.json": (
                '{"dependencies":{"@org/name":"*"},"devDependencies":{"vitest":"*"},'
                '"peerDependencies":{"react":"*"}}'
            ),
            "composer.json": (
                '{"require":{"php":"^8", "vendor/package":"*", "ext-json":"*"},'
                '"require-dev":{"phpunit/phpunit":"*"}}'
            ),
        }
    )
    assert facts == frozenset(
        {
            "pip:http-x",
            "pip:foo-bar",
            "pip:pytest",
            "pip:poetry-core",
            "pip:requests",
            "pip:ruff",
            "npm:@org/name",
            "npm:vitest",
            "npm:react",
            "composer:vendor/package",
            "composer:phpunit/phpunit",
        }
    )


@pytest.mark.parametrize(
    "text", ["not a manifest", "[]", "null", '{"dependencies": ["bad"]}', '{"dependencies": 42}']
)
def test_malformed_manifests_are_no_dependency_evidence(text):
    assert project_deps({"package.json": text}) == frozenset()
    assert project_deps({"pyproject.toml": text}) == frozenset()
