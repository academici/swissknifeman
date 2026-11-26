"""Rule identity stays precise even when shortlist tokens match."""

import pytest

from skm.modules.learning.domain.tokens import jaccard, norm, tokens


def test_exact_norm_preserves_inner_whitespace_and_case() -> None:
    assert norm(" \r\nCafe\u0301\r\n  TLS\ragain\n") == "Café\n  TLS\nagain"


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Не отключать TLS", "Отключать TLS"),  # noqa: RUF001 - intentional Cyrillic test data
        ("Stop then delete", "Delete then stop"),
        ("push after approval", "approval after push"),
        ("Run pytest", "run pytest"),
        ("set  value", "set value"),
        ("Все", "Всё"),  # noqa: RUF001 - intentional Cyrillic test data
    ],
)
def test_exact_identity_preserves_wording(a: str, b: str) -> None:
    assert norm(a) != norm(b)


def test_shortlist_keeps_short_tokens_and_unicode_letters() -> None:
    assert tokens("Не no Tls") == {"не", "no", "tls"}  # noqa: RUF001 - intentional Cyrillic test data
    assert jaccard("Проверь TLS", "проверь tls!") == 1
    assert jaccard("stop → delete", "delete → stop") == 1
    assert jaccard("Все", "Всё") == 0  # noqa: RUF001 - intentional Cyrillic test data
    assert jaccard("?", "!") == 0
