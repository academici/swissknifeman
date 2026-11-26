"""Unit tests for ``SKILL.md`` frontmatter and prompt block variable extraction (extensions §4.2, §4.8)."""

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.extensions.domain.prompt_block import (
    extract_variables,
    validate_prompt_block_variables,
)
from skm.modules.extensions.domain.skill import parse_skill_frontmatter


def test_parse_skill_frontmatter_without_fence() -> None:
    text = "# Plain Skill\nBody text here."
    fm, body = parse_skill_frontmatter(text)
    assert fm == {}
    assert body == text


def test_parse_skill_frontmatter_valid_with_bom_and_quotes() -> None:
    text = (
        "\ufeff---\nname: \"code-review\"\ndescription: 'Reviews code changes carefully'\n---\n# Body\nLine 2"
    )
    fm, body = parse_skill_frontmatter(text, key="code-review")
    assert fm == {"name": "code-review", "description": "Reviews code changes carefully"}
    assert body == "# Body\nLine 2"


def test_parse_skill_frontmatter_unterminated_raises() -> None:
    text = "---\nname: code-review\ndescription: Missing closing fence\n# Body"
    with pytest.raises(ValidationFailed) as exc_info:
        parse_skill_frontmatter(text)
    assert exc_info.value.code is ErrorCode.SCHEMA_INVALID
    assert exc_info.value.details["reason"] == "front_matter_unterminated"


def test_parse_skill_frontmatter_disallowed_key_raises() -> None:
    text = "---\nname: code-review\ndescription: Valid\nauthor: someone\n---\n# Body"
    with pytest.raises(ValidationFailed) as exc_info:
        parse_skill_frontmatter(text)
    assert exc_info.value.code is ErrorCode.SCHEMA_INVALID
    assert exc_info.value.details["reason"] == "frontmatter_key_not_allowed"
    assert exc_info.value.details["key"] == "author"


@pytest.mark.parametrize(
    "bad_frontmatter",
    [
        "---\nname: only-name\n---\nBody",
        "---\ndescription: only-desc\n---\nBody",
        "---\nname: code-review\ndescription: |\n  multiline\n---\nBody",
        "---\nname: code-review\ndescription: >\n  folded\n---\nBody",
        "---\nname: [list]\ndescription: ok\n---\nBody",
        "---\nname: {k: v}\ndescription: ok\n---\nBody",
        "---\n- list-item\n---\nBody",
        "---\n  indented: value\n---\nBody",
        "---\nname: dup\nname: dup2\ndescription: ok\n---\nBody",
        "---\nname: code-review\ndescription: " + ("x" * 1025) + "\n---\nBody",
    ],
)
def test_parse_skill_frontmatter_invalid_syntax_or_limits(bad_frontmatter: str) -> None:
    with pytest.raises(ValidationFailed) as exc_info:
        parse_skill_frontmatter(bad_frontmatter)
    assert exc_info.value.code is ErrorCode.SCHEMA_INVALID
    assert exc_info.value.details["reason"] == "frontmatter_invalid"


def test_parse_skill_frontmatter_key_mismatch() -> None:
    text = "---\nname: wrong-key\ndescription: Valid desc\n---\n# Body"
    with pytest.raises(ValidationFailed) as exc_info:
        parse_skill_frontmatter(text, key="expected-key")
    assert exc_info.value.code is ErrorCode.SCHEMA_INVALID
    assert exc_info.value.details["reason"] == "key_mismatch"


def test_extract_variables_and_escaped_braces() -> None:
    body = 'Use {{ task.id }} and {{role.name}}, literal {{"{{"}} not_a_var }} stays literal.'
    extracted = extract_variables(body)
    assert extracted == frozenset({"task.id", "role.name"})


def test_extract_variables_rejects_unknown_namespace() -> None:
    with pytest.raises(ValidationFailed) as exc_info:
        extract_variables("Hello {{ secret.token }}")
    assert exc_info.value.code is ErrorCode.SCHEMA_INVALID
    assert exc_info.value.details["reason"] == "unknown_variable_namespace"
    assert exc_info.value.details["variable"] == "secret.token"


def test_validate_prompt_block_variables_checks_declared_list() -> None:
    manifest = {"block_type": "role", "variables": ["task.id", "role.name"]}
    assert validate_prompt_block_variables(manifest, "Task {{ task.id }}") == frozenset({"task.id"})

    with pytest.raises(ValidationFailed) as exc_info:
        validate_prompt_block_variables(manifest, "Task {{ task.id }} and {{ run.id }}", key="executor/role")
    assert exc_info.value.code is ErrorCode.SCHEMA_INVALID
    assert exc_info.value.details["reason"] == "undeclared_variable"
    assert exc_info.value.details["variable"] == "run.id"

    with pytest.raises(ValidationFailed) as empty_exc:
        validate_prompt_block_variables({}, "Task {{ task.id }}", key="shared/note")
    assert empty_exc.value.code is ErrorCode.SCHEMA_INVALID
    assert empty_exc.value.details["reason"] == "undeclared_variable"
    assert empty_exc.value.details["variable"] == "task.id"
