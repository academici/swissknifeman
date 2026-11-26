"""Donor token/masking cases plus the new registry and JSON-only boundary."""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, override
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.generated._codec import SecretRef
from skm.platform.logging.redaction import DEFAULT_PATTERNS, MASK, Redactor

TOKENS = (
    "sk-" + "a1B2c3D4e5F6g7H8i9J0k1L2",
    "ghp_" + "A" * 36,
    "github_pat_" + "B1" * 20,
    "xoxb-1234567890-abcdefghij",
    "xoxa-1234567890-abcdefghij",
    "xoxp-1234567890-abcdefghij",
    "AKIAABCDEFGHIJKLMNOP",
    "Bearer abcdefghijklmnopqrstuvwxyz012345",
)

REFERENCES = (
    "secret://env/FIXTURE_SECRET",
    "secret://env/_" + "A" * 127,
    "secret://file/~/.config/skm/fixture-secret",
    "secret://file/relative-path",
    "secret://file/" + "a" * 1024,
    "secret://file/a,b;c(d)[e]{f}\"g'h\\i",
    "secret://keyring/fixture-service/fixture.name@host",
    "secret://keyring/" + "s" * 128 + "/" + "n" * 128,
)


@pytest.mark.parametrize("ref", REFERENCES)
def test_secret_reference_metadata_round_trips_in_text_and_documents(ref: str) -> None:
    assert str(SecretRef.parse(ref)) == ref
    redactor = Redactor()
    assert redactor.text(ref) == ref
    document = {ref: [ref], "value": ref}
    assert redactor.document(document) == document
    assert json.loads(json.dumps(redactor.document(document))) == document


@pytest.mark.parametrize(
    "template",
    ["{}", '"{}"', "'{}'", "({})", "[{}]", "{{{}}}", "ref={}", "using {} here", '{{"ref": "{}"}}'],
)
@pytest.mark.parametrize("ref", [REFERENCES[0], REFERENCES[2], REFERENCES[6]])
def test_reference_delimiters_preserve_only_reference_metadata(template: str, ref: str) -> None:
    text = template.format(ref)
    assert Redactor().text(text) == text


@pytest.mark.parametrize(
    "value",
    [
        "secret://env/lowercase",
        "secret://env/FIXTURE_SECRET/extra",
        "secret://env/FIXTURE_SECRET?password=abcdefgh12345",
        "secret://env/FIXTURE_SECRET%20suffix",
        "secret://env/" + "A" * 129,
        "secret://env/FIXTURE_SECRET\n",
        "secret://file/a\nb",
        "secret://file/" + "a" * 1024 + ",extra",
        "secret://keyring/service",
        "secret://keyring/service/name/extra",
        "secret://keyring/service/" + "n" * 129,
        "secret://unknown/FIXTURE_SECRET",
        "SECRET://env/FIXTURE_SECRET",
        "secret ://env/FIXTURE_SECRET",
        r"secret:\/\/env/FIXTURE_SECRET",
        r"secret://env/FIXTURE_SECRET\u0020suffix",
    ],
)
def test_malformed_or_disguised_references_do_not_bypass_named_masking(value: str) -> None:
    with pytest.raises(ValidationFailed) as caught:
        SecretRef.parse(value)
    assert caught.value.code == ErrorCode.CONFIG_INVALID
    redacted = Redactor().text(value)
    assert MASK in redacted
    assert redacted != value
    assert Redactor().document({"value": value}) == {"value": redacted}


@pytest.mark.parametrize(
    "value",
    [
        "prefixsecret://env/FIXTURE_SECRET",
        "https://secret://env/FIXTURE_SECRET",
        "secret://env/FIXTURE_SECRET)suffix",
        '"secret://env/FIXTURE_SECRET',
        r'\"secret://env/FIXTURE_SECRET"',
        r'"secret://env/FIXTURE_SECRET\"suffix"',
    ],
)
def test_reference_prefixes_and_escaping_do_not_create_an_exemption(value: str) -> None:
    assert MASK in Redactor().text(value)


@pytest.mark.parametrize("ref", [REFERENCES[0], REFERENCES[2], REFERENCES[6]])
@pytest.mark.parametrize("name", ["token", "password", "secret", "api_key"])
@pytest.mark.parametrize("separator", ["=", ": ", '="'])
def test_named_assignments_still_mask_reference_shaped_values(ref: str, name: str, separator: str) -> None:
    value = name + separator + ref
    assert Redactor().text(value) == name + separator + MASK


@pytest.mark.parametrize("name", ["token", "password", "secret", "api_key"])
def test_named_assignments_inside_file_references_are_still_masked(name: str) -> None:
    value = f"secret://file/{name}=fixture-credential-123"
    assert str(SecretRef.parse(value)) == value
    assert Redactor().text(value) == f"secret://file/{name}={MASK}"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ('token:"fixture-credential-123"', f'token:"{MASK}"'),
        ('"password":"fixture-credential-123"', f'"password":"{MASK}"'),
        ("secret='fixture-credential-123'", f"secret='{MASK}'"),
        ("a;api_key=fixture-credential-123,control", f"a;api_key={MASK},control"),
        (REFERENCES[0], "secret:" + MASK),
    ],
)
def test_file_reference_delimiters_cannot_hide_nested_assignments(path: str, expected: str) -> None:
    value = "secret://file/" + path
    assert str(SecretRef.parse(value)) == value
    assert Redactor().text(value) == "secret://file/" + expected
    assert Redactor().document({"value": value}) == {"value": "secret://file/" + expected}


@pytest.mark.parametrize("token", TOKENS)
def test_issuer_patterns_inside_file_references_are_still_masked(token: str) -> None:
    value = "secret://file/" + token
    assert token not in Redactor().text(value)
    assert MASK in Redactor().text(value)


@pytest.mark.parametrize("value", ["secret://env/" + TOKENS[6], "secret://keyring/fixture/" + TOKENS[1]])
def test_issuer_patterns_in_other_valid_reference_segments_are_still_masked(value: str) -> None:
    assert str(SecretRef.parse(value)) == value
    assert Redactor().text(value).endswith("/" + MASK)


@pytest.mark.parametrize(
    ("ref", "secret"),
    [
        (REFERENCES[0], REFERENCES[0]),
        (REFERENCES[0], "FIXTURE_SECRET"),
        (REFERENCES[0], "secret://"),
        (REFERENCES[0], "env/FIXTURE"),
        (REFERENCES[2], "fixture-secret"),
        (REFERENCES[6], "fixture-service"),
    ],
)
def test_registered_values_take_priority_over_reference_metadata(ref: str, secret: str) -> None:
    redactor = Redactor()
    redactor.register_secret(secret)
    result = redactor.text(ref)
    assert secret not in result
    assert MASK in result
    assert redactor.document({ref: [ref]}) == {result: [result]}


def test_overlapping_registered_values_and_adjacent_assignments_remain_masked() -> None:
    redactor = Redactor()
    ref = REFERENCES[0]
    for secret in (ref, "FIXTURE_SECRET", "env/FIXTURE"):
        redactor.register_secret(secret)
    value = f'{ref}; password="fixture-password-123", {REFERENCES[6]}'
    assert redactor.text(value) == f'{MASK}; password="{MASK}", {REFERENCES[6]}'


def test_pattern_masking_cannot_turn_a_malformed_reference_into_exempt_metadata() -> None:
    value = "secret://file/ghp_" + "A" * 1100 + "/fixture-secret"
    with pytest.raises(ValidationFailed):
        SecretRef.parse(value)
    assert Redactor().text(value) == "secret:" + MASK


def test_registry_masking_cannot_turn_a_malformed_reference_into_exempt_metadata() -> None:
    secret = "fixture\ncredential"
    value = "secret://file/" + secret
    redactor = Redactor()
    redactor.register_secret(secret)
    with pytest.raises(ValidationFailed):
        SecretRef.parse(value)
    assert redactor.text(value) == "secret:" + MASK


def test_registered_assignment_name_does_not_hide_its_value_from_the_named_detector() -> None:
    redactor = Redactor()
    redactor.register_secret("password")
    assert redactor.text("password=fixture-credential-123") == f"{MASK}={MASK}"


@pytest.mark.parametrize(
    ("secret", "value", "hidden", "expected"),
    [
        ("password=fixture", "password=fixture-credential-123", "credential", MASK),
        ("my-token", "my-token=abcdefghijk", "abcdefghijk", f"{MASK}={MASK}"),
        ("x-api_ke", "x-api_key: abcdefghijk", "abcdefghijk", f"{MASK}y: {MASK}"),
        ("Bearer a", f"Authorization: {TOKENS[7]}", "nopqrstuvwxyz", f"Authorization: {MASK}"),
        ("x secret", "x secret://env/lower_invalid_value", "lower_invalid", f"{MASK}:{MASK}"),
        ("secret://fil", "secret://file/a\nb", "file/a", f"{MASK}\nb"),
    ],
)
def test_a_registered_value_cannot_erase_another_detection(
    secret: str, value: str, hidden: str, expected: str
) -> None:
    redactor = Redactor()
    redactor.register_secret(secret)
    tail = f" ref {REFERENCES[0]}"
    assert redactor.text(value) == expected
    assert hidden not in expected
    assert redactor.text(value + tail) == expected + tail
    assert redactor.document({value: [value + tail], "n": 1}) == {expected: [expected + tail], "n": 1}


def test_overlapping_registered_segments_are_all_masked_before_reference_display() -> None:
    redactor = Redactor()
    for secret in ("abcdefghijk", "ijklmnopqr"):
        redactor.register_secret(secret)
    assert redactor.text("secret://file/abcdefghijklmnopqr/control") == f"secret://file/{MASK}/control"


# A mask inserted for one registered value must not complete another one (a review finding).
PRIMARY = "P" * 40
ASSEMBLED = [
    pytest.param(MASK[3:] + "SECONDARY_0123456789", PRIMARY + "SECONDARY_0123456789", id="mask-and-suffix"),
    pytest.param("SECONDARY_0123456789" + MASK[:4], "SECONDARY_0123456789" + PRIMARY, id="prefix-and-mask"),
    pytest.param(
        "LEFT_FIXTURE" + MASK + "RIGHT_FIXTURE", "LEFT_FIXTURE" + PRIMARY + "RIGHT_FIXTURE", id="both-sides"
    ),
]


@pytest.mark.parametrize("order", [1, -1], ids=["primary-first", "secondary-first"])
@pytest.mark.parametrize(("secondary", "value"), ASSEMBLED)
def test_a_mask_cannot_assemble_another_registered_value(secondary: str, value: str, order: int) -> None:
    redactor = Redactor()
    for secret in (PRIMARY, secondary)[::order]:
        redactor.register_secret(secret)
    assert redactor.text(value) == MASK
    direct = f"{value} {secondary}"
    assert redactor.text(direct) == f"{MASK} {MASK}"
    document = redactor.document({value: [value, {"nested": direct}]})
    assert document == {MASK: [MASK, {"nested": f"{MASK} {MASK}"}]}
    assert secondary not in json.dumps(document, ensure_ascii=False)


@pytest.mark.parametrize(("secondary", "value"), ASSEMBLED)
def test_assembled_values_are_masked_beside_valid_reference_metadata(secondary: str, value: str) -> None:
    redactor = Redactor()
    for secret in (PRIMARY, secondary):
        redactor.register_secret(secret)
    text = f"ref {REFERENCES[0]} {value} ({REFERENCES[6]})"
    expected = f"ref {REFERENCES[0]} {MASK} ({REFERENCES[6]})"
    assert redactor.text(text) == expected
    assert redactor.document({"ref": text, REFERENCES[2]: value}) == {"ref": expected, REFERENCES[2]: MASK}


def test_text_beside_a_mask_survives_when_it_completes_no_registered_value() -> None:
    redactor = Redactor()
    for secret in (PRIMARY, MASK[3:] + "SECONDARY_0123456789"):
        redactor.register_secret(secret)
    assert redactor.text(PRIMARY + "SECONDARY_012345678") == MASK + "SECONDARY_012345678"
    assert redactor.text("SECONDARY_0123456789" + PRIMARY) == "SECONDARY_0123456789" + MASK


def test_masking_an_assembled_value_repeats_until_nothing_is_assembled() -> None:
    redactor = Redactor()
    for secret in (PRIMARY, MASK[3:] + "SECONDARY_0123456789", MASK[3:] + "_TAIL_FIXTURE"):
        redactor.register_secret(secret)
    assert redactor.text(PRIMARY + "SECONDARY_0123456789_TAIL_FIXTURE") == MASK


def test_touching_registered_values_share_one_mask_so_masks_cannot_pair_up() -> None:
    redactor = Redactor(patterns=())
    for secret in ("AAAAAAAA", "BBBBBBBB", MASK[1:] + MASK[:-1]):
        redactor.register_secret(secret)
    assert redactor.text("AAAAAAAABBBBBBBB") == MASK
    assert redactor.text("AAAAAAAA BBBBBBBB") == f"{MASK} {MASK}"


@pytest.mark.parametrize("name", ["token", "password", "secret", "api_key"])
def test_json_assignment_values_are_masked_even_when_they_are_references(name: str) -> None:
    value = json.dumps({name: REFERENCES[0]})
    assert json.loads(Redactor().text(value)) == {name: MASK}


def test_custom_patterns_can_mask_references_without_disabling_default_protections() -> None:
    ref = REFERENCES[0]
    redactor = Redactor(patterns=(*DEFAULT_PATTERNS, re.compile(re.escape(ref))))
    assert redactor.text(ref) == MASK
    assert Redactor(patterns=()).text(ref) == ref


@pytest.mark.parametrize("token", TOKENS)
def test_donor_issuer_patterns(token: str) -> None:
    assert Redactor().text(f"failed with {token} at the end") == f"failed with {MASK} at the end"


@pytest.mark.parametrize(
    "token",
    [
        "skm_abcdefg2_" + "Zz0-_" * 8 + "abc",
        "gho_" + "C" * 36,
        "ghu_" + "D" * 36,
        "ghs_" + "E" * 36,
        "ghr_" + "F" * 36,
    ],
)
def test_product_api_tokens_and_github_token_family_are_masked(token: str) -> None:
    # A worker's own credential echoed into a transcript must not reach logs or artifacts.
    assert Redactor().text(f"env SKM_TOKEN={token}\nnext") == f"env SKM_TOKEN={MASK}\nnext"
    assert Redactor().text(f"curl -H x:{token} y") == f"curl -H x:{MASK} y"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("api_key=abcdefgh12345 and x", f"api_key={MASK} and x"),
        ('"password": "hunter2hunter2"', f'"password": "{MASK}"'),
        ("TOKEN: s3cr3t-value-1", f"TOKEN: {MASK}"),
        ("api-key='abcdefghijk'", f"api-key='{MASK}'"),
    ],
)
def test_donor_named_values_keep_the_name(value: str, expected: str) -> None:
    assert Redactor().text(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "tokens 120/30 used",
        "the token budget is spent",
        "sk-short",
        "password: none",
        "risk score 40 reached 30",
        "AKIA is a prefix",
        "Bearer of bad news",
    ],
)
def test_ordinary_text_is_not_treated_as_a_secret(value: str) -> None:
    assert Redactor().text(value) == value


def test_known_values_are_longest_first_and_patterns_can_be_disabled() -> None:
    redactor = Redactor(patterns=())
    for secret in ("value-12", "value-1234", "", "short"):
        redactor.register_secret(secret)
    assert redactor.text("value-12 value-1234 short") == f"{MASK} {MASK} short"
    assert redactor.text(TOKENS[0]) == TOKENS[0]
    assert Redactor(patterns=[re.compile("custom-credential")]).text("custom-credential") == MASK
    assert len(DEFAULT_PATTERNS) == 2


def test_nested_document_keys_strings_and_numeric_scalars_are_copied() -> None:
    redactor = Redactor()
    redactor.register_secret("known-secret-1")
    redactor.register_secret("34567890")
    doc = {"a": [f"x {TOKENS[1]}", 3, None, True], f"k-{TOKENS[0]}": {"b": "known-secret-1"}, "n": 1234567890}
    assert redactor.document(doc) == {
        "a": [f"x {MASK}", 3, None, True],
        f"k-{MASK}": {"b": MASK},
        "n": MASK,
    }
    assert TOKENS[1] in str(doc)


def test_reveal_callback_registration_does_not_need_a_secret_wrapper() -> None:
    redactor = Redactor()
    on_reveal = redactor.register_secret
    on_reveal("revealed-value-123")
    assert redactor.text("use revealed-value-123 here") == f"use {MASK} here"


def test_never_reveal_or_stringify_non_json_objects() -> None:
    class SecretValue:
        def reveal(self) -> str:
            pytest.fail("logging must not resolve secrets")

        @override
        def __str__(self) -> str:
            raise AssertionError("logging must not stringify objects")

    value: Any = SecretValue()
    with pytest.raises(TypeError, match="revealed secret must be a string"):
        Redactor().register_secret(value)
    with pytest.raises(TypeError, match="only JSON"):
        Redactor().document({"secret": value})


def test_thread_safe_registration() -> None:
    redactor = Redactor(patterns=())
    secrets = [f"opaque-value-{i:03}" for i in range(32)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(redactor.register_secret, secrets))
    assert redactor.text(" ".join(secrets)) == " ".join([MASK] * len(secrets))


@pytest.mark.parametrize(
    "secret",
    [
        "019A0254-FC00-7000-8000-000000000001",
        "019A0254-fC00-7000-8000-000000000001",
        "019a0254-fc00-7000-8000-000000000001",
    ],
)
def test_registered_uuid_masks_original_and_canonical_forms(secret: str) -> None:
    canonical = str(UUID(secret))
    other = "019a0254-fc00-7000-8000-000000000002"
    redactor = Redactor(patterns=())
    redactor.register_secret(secret)
    assert redactor.text(f"{secret} {canonical} {other}") == f"{MASK} {MASK} {other}"
    assert redactor.document({secret: [canonical, secret], "other": other}) == {
        MASK: [MASK, MASK],
        "other": other,
    }


def test_non_uuid_secrets_and_request_ids_keep_exact_case_matching() -> None:
    redactor = Redactor(patterns=())
    secret = "Opaque-SeCrEt-123"
    request = "req_" + "A" * 26
    redactor.register_secret(secret)
    redactor.register_secret(request)
    assert redactor.text(f"{secret} {secret.lower()} {request} {request.lower()}") == (
        f"{MASK} {secret.lower()} {MASK} {request.lower()}"
    )
