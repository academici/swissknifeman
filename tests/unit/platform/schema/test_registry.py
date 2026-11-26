"""SchemaRegistry: offline URN resolution, load-time rejection with JSON pointers, validation (§3.3)."""

import json
import socket
import sys
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, NoReturn, cast

import pytest
from referencing.exceptions import Unresolvable

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, ValidationFailed
from skm.platform.schema.findings import SchemaLoadError, SchemaLoadProblem
from skm.platform.schema.locator import default_schema_root
from skm.platform.schema.registry import MAX_REPORTED_ISSUES, SchemaRegistry
from skm.platform.schema.validator import scope

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "schemas"
DIALECT = "https://json-schema.org/draft/2020-12/schema"
ORDER = "urn:skm:shop:command:place-order:v1"
CREATE_PROJECT = "urn:skm:workspace:command:create-project:v1"
UUID = "0191e2a4-7c3f-7b21-8a54-3f6d2c1b9e07"


def schema(urn: str, **body: Any) -> dict[str, Any]:
    return {"$schema": DIALECT, "$id": urn, **body}


def write_tree(root: Path, files: dict[str, Any]) -> Path:
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    return root


def load_failure(root: Path, files: dict[str, Any]) -> SchemaLoadError:
    write_tree(root, files)
    with pytest.raises(SchemaLoadError) as raised:
        SchemaRegistry.load(root)
    return raised.value


def found(
    problems: tuple[SchemaLoadProblem, ...], path: str, pointer: str, code: str | None, text: str | None
) -> bool:
    return any(
        p.path == path
        and p.issue.pointer == pointer
        and (code is None or p.issue.code == code)
        and (text is None or text in p.issue.message)
        for p in problems
    )


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("the schema registry must not touch the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture(scope="module")
def shop() -> SchemaRegistry:
    return SchemaRegistry.load(FIXTURES / "valid")


@pytest.fixture(scope="module")
def default() -> SchemaRegistry:
    return SchemaRegistry.load_default()


# --- the fixture tree


def test_fixture_tree_loads_schemas_and_skips_data_directories(shop: SchemaRegistry) -> None:
    assert shop.urns() == {
        "urn:skm:shop:defs:v1",
        ORDER,
        "urn:skm:shop:tree:v1",
        "urn:skm:shop:node-a:v1",
        "urn:skm:shop:node-b:v1",
    }


def test_only_the_root_tooling_lock_is_excluded_from_schema_discovery(tmp_path: Path) -> None:
    urn = "urn:skm:shop:sample:v1"
    write_tree(tmp_path, {"shop/sample.v1.json": schema(urn, type="string")})
    # The lock is tooling data, so even malformed content must not reach schema parsing.
    (tmp_path / "schema-lock.json").write_text("not a schema", encoding="utf-8")
    assert SchemaRegistry.load(tmp_path).urns() == {urn}
    for name in ("shop/schema-lock.json", "other-lock.json"):
        path = tmp_path / name
        path.write_text("{}", encoding="utf-8")
        with pytest.raises(SchemaLoadError) as raised:
            SchemaRegistry.load(tmp_path)
        assert found(raised.value.problems, name, "", "file-name", None)
        path.unlink()


def test_get_returns_the_document_read_only_and_unknown_urn_is_internal(shop: SchemaRegistry) -> None:
    document = shop.get(ORDER)
    assert document["$id"] == ORDER
    with pytest.raises(TypeError):
        cast("Any", document)["$id"] = "changed"
    with pytest.raises(InternalError) as raised:
        shop.get("urn:skm:shop:nope:v1")
    assert raised.value.code is ErrorCode.INTERNAL_ERROR
    assert raised.value.details == {"urn": "urn:skm:shop:nope:v1"}


def test_validator_is_cached_per_registry(shop: SchemaRegistry) -> None:
    assert shop.validator(ORDER) is shop.validator(ORDER)
    assert shop.validator(ORDER) is not SchemaRegistry.load(FIXTURES / "valid").validator(ORDER)


def order(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"order_id": UUID, "sku": "ABC-0001", "quantity": 3}
    return {**base, **changes}


def test_valid_dto_has_no_issues(shop: SchemaRegistry) -> None:
    dto = order(placed_at="2026-10-25T14:03:11Z", contact="a@b.co", channel="web")
    assert shop.validate(ORDER, dto) == ()
    shop.require_valid(ORDER, dto)
    assert shop.validate(ORDER, order(channel={"partner": "acme"})) == ()


@pytest.mark.parametrize(
    ("dto", "pointer", "code"),
    [
        ({"sku": "ABC-0001", "quantity": 3}, "", "required"),
        (order(sku="abc-1"), "/sku", "pattern"),
        (order(order_id="nope"), "/order_id", "format"),
        (order(quantity=0), "/quantity", "minimum"),
        (order(quantity="3"), "/quantity", "type"),
        (order(placed_at="2026-10-25"), "/placed_at", "format"),
        (order(contact="no-at-sign"), "/contact", "format"),
        (order(extra=1), "", "additionalProperties"),
        (order(channel="mail"), "/channel", "oneOf"),
    ],
)
def test_invalid_dto_reports_pointer_and_code(
    shop: SchemaRegistry, dto: dict[str, Any], pointer: str, code: str
) -> None:
    assert (pointer, code) in [(i.pointer, i.code) for i in shop.validate(ORDER, dto)]


def test_references_across_documents_and_into_defs_are_resolved(shop: SchemaRegistry) -> None:
    # sku/order_id live in urn:skm:shop:defs:v1, quantity in the schema's own $defs
    pointers = {i.pointer for i in shop.validate(ORDER, order(sku="x", order_id="y", quantity=1000))}
    assert pointers == {"/sku", "/order_id", "/quantity"}


def test_self_recursive_schema_validates_deep_instances(shop: SchemaRegistry) -> None:
    tree = {"name": "root", "children": [{"name": "a"}, {"name": "b", "children": [{"name": "c"}]}]}
    assert shop.validate("urn:skm:shop:tree:v1", tree) == ()
    broken = {"name": "root", "children": [{"name": "a"}, {"name": "b", "children": [{"name": ""}]}]}
    pointers = [(i.pointer, i.code) for i in shop.validate("urn:skm:shop:tree:v1", broken)]
    assert pointers == [("/children/1/children/0/name", "minLength")]


def test_mutually_recursive_schemas_across_documents(shop: SchemaRegistry) -> None:
    chain = {"kind": "a", "next": {"kind": "b", "next": {"kind": "a"}}}
    assert shop.validate("urn:skm:shop:node-a:v1", chain) == ()
    wrong = {"kind": "a", "next": {"kind": "b", "next": {"kind": "b"}}}
    assert [(i.pointer, i.code) for i in shop.validate("urn:skm:shop:node-a:v1", wrong)] == [
        ("/next/next/kind", "const")
    ]


def test_require_valid_raises_schema_invalid_with_bounded_issues(tmp_path: Path) -> None:
    root = write_tree(
        tmp_path,
        {"shop/list.v1.json": schema("urn:skm:shop:list:v1", type="array", items={"type": "integer"})},
    )
    registry = SchemaRegistry.load(root)
    with pytest.raises(ValidationFailed) as raised:
        registry.require_valid("urn:skm:shop:list:v1", ["x"] * (MAX_REPORTED_ISSUES + 10))
    error = raised.value
    assert error.code is ErrorCode.SCHEMA_INVALID
    assert error.details["urn"] == "urn:skm:shop:list:v1"
    issues = error.details["issues"]
    assert isinstance(issues, list)
    assert len(issues) == MAX_REPORTED_ISSUES
    assert issues[0] == {
        "pointer": "/0",
        "schema_pointer": "/items/type",
        "code": "type",
        "message": "'x' is not of type 'integer'",
    }


def test_validating_an_unknown_urn_is_internal(shop: SchemaRegistry) -> None:
    with pytest.raises(InternalError):
        shop.validate("urn:skm:shop:nope:v1", {})


def test_progress_through_properties_is_not_a_cycle(tmp_path: Path) -> None:
    body = {"allOf": [{"properties": {"next": {"$ref": "#"}}}]}
    root = write_tree(tmp_path, {"shop/a.v1.json": schema("urn:skm:shop:a:v1", **body)})
    registry = SchemaRegistry.load(root)
    assert registry.validate("urn:skm:shop:a:v1", {"next": {"next": {}}}) == ()


# --- rejected trees

REF_X = {"properties": {"x": {"$ref": "urn:skm:shop:missing:v1"}}}
B = {"shop/b.v1.json": schema("urn:skm:shop:b:v1", **{"$defs": {"ok": {}}})}
FAILURES = {
    "unresolved-urn": (
        {"shop/a.v1.json": schema("urn:skm:shop:a:v1", **REF_X)},
        ("shop/a.v1.json", "/properties/x/$ref", "$ref", "urn:skm:shop:missing:v1"),
    ),
    "missing-pointer-in-other-document": (
        {
            **B,
            "shop/a.v1.json": schema(
                "urn:skm:shop:a:v1", properties={"x": {"$ref": "urn:skm:shop:b:v1#/$defs/nope"}}
            ),
        },
        ("shop/a.v1.json", "/properties/x/$ref", "$ref", "unresolved"),
    ),
    "missing-local-pointer": (
        {"shop/a.v1.json": schema("urn:skm:shop:a:v1", properties={"x": {"$ref": "#/$defs/nope"}})},
        ("shop/a.v1.json", "/properties/x/$ref", "$ref", "unresolved"),
    ),
    "network-reference": (
        {"shop/a.v1.json": schema("urn:skm:shop:a:v1", items={"$ref": "https://example.com/s.json"})},
        ("shop/a.v1.json", "/items/$ref", "$ref", "forbidden"),
    ),
    "file-reference": (
        {"shop/a.v1.json": schema("urn:skm:shop:a:v1", items={"$ref": "b.v1.json"}), **B},
        ("shop/a.v1.json", "/items/$ref", "$ref", "forbidden"),
    ),
    "metaschema-violation": (
        {"shop/a.v1.json": schema("urn:skm:shop:a:v1", properties={"a": {"type": "strnig"}})},
        ("shop/a.v1.json", "/properties/a/type", None, None),
    ),
    "unknown-format": (
        {"shop/a.v1.json": schema("urn:skm:shop:a:v1", properties={"h": {"format": "hostname"}})},
        ("shop/a.v1.json", "/properties/h/format", "format", "hostname"),
    ),
    "module-differs-from-directory": (
        {"shop/a.v1.json": schema("urn:skm:other:a:v1")},
        ("shop/a.v1.json", "/$id", "$id", "directory"),
    ),
    "file-outside-a-module-directory": (
        {"a.v1.json": schema("urn:skm:shop:a:v1")},
        ("a.v1.json", "/$id", "$id", "module directory"),
    ),
    "id-is-not-a-urn": (
        {"shop/a.v1.json": schema("https://example.com/a")},
        ("shop/a.v1.json", "/$id", "$id", "urn:skm"),
    ),
    "id-without-kind": (
        {"shop/a.v1.json": schema("urn:skm:shop:v1")},
        ("shop/a.v1.json", "/$id", "$id", "urn:skm"),
    ),
    "wrong-dialect": (
        {
            "shop/a.v1.json": schema("urn:skm:shop:a:v1")
            | {"$schema": "http://json-schema.org/draft-07/schema#"}
        },
        ("shop/a.v1.json", "/$schema", "$schema", "2020-12"),
    ),
    "missing-dialect": (
        {"shop/a.v1.json": {"$id": "urn:skm:shop:a:v1"}},
        ("shop/a.v1.json", "/$schema", "$schema", None),
    ),
    "broken-json": ({"shop/a.v1.json": "{not json"}, ("shop/a.v1.json", "", "json", None)),
    "duplicate-key": ({"shop/a.v1.json": '{"a": 1, "a": 2}'}, ("shop/a.v1.json", "", "json", "duplicate")),
    "non-finite-number": ({"shop/a.v1.json": '{"a": NaN}'}, ("shop/a.v1.json", "", "json", "NaN")),
    "not-an-object": ({"shop/a.v1.json": "[]"}, ("shop/a.v1.json", "", "type", None)),
    "file-name-without-version": (
        {"shop/a.json": schema("urn:skm:shop:a:v1")},
        ("shop/a.json", "", "file-name", None),
    ),
    "duplicate-urn": (
        {
            "shop/a.v1.json": schema("urn:skm:shop:a:v1"),
            "shop/nested/a.v1.json": schema("urn:skm:shop:a:v1"),
        },
        ("shop/nested/a.v1.json", "/$id", "duplicate-urn", "shop/a.v1.json"),
    ),
    "alias-cycle-between-documents": (
        {
            "shop/a.v1.json": schema("urn:skm:shop:a:v1", **{"$ref": "urn:skm:shop:b:v1"}),
            "shop/b.v1.json": schema("urn:skm:shop:b:v1", **{"$ref": "urn:skm:shop:a:v1"}),
        },
        ("shop/b.v1.json", "/$ref", "$ref", "circular"),
    ),
    "self-reference-without-progress": (
        {"shop/a.v1.json": schema("urn:skm:shop:a:v1", **{"$ref": "#"})},
        ("shop/a.v1.json", "/$ref", "$ref", "circular"),
    ),
    "cycle-through-all-of": (
        {"shop/a.v1.json": schema("urn:skm:shop:a:v1", allOf=[{"$ref": "#"}])},
        ("shop/a.v1.json", "/allOf/0/$ref", "$ref", "circular"),
    ),
    "branching-cycle": (
        {"shop/a.v1.json": schema("urn:skm:shop:a:v1", anyOf=[{"$ref": "#"}, {"$ref": "#"}])},
        ("shop/a.v1.json", "/anyOf/0/$ref", "$ref", "circular"),
    ),
    "branching-dynamic-cycle": (
        {"shop/a.v1.json": schema("urn:skm:shop:a:v1", anyOf=[{"$dynamicRef": "#"}, {"$dynamicRef": "#"}])},
        ("shop/a.v1.json", "/anyOf/0/$dynamicRef", "$dynamicRef", "circular"),
    ),
    "cycle-through-defs": (
        {
            "shop/a.v1.json": schema(
                "urn:skm:shop:a:v1", **{"$defs": {"x": {"$ref": "#/$defs/y"}, "y": {"$ref": "#/$defs/x"}}}
            )
        },
        ("shop/a.v1.json", "/$defs/y/$ref", "$ref", "#/$defs/x"),
    ),
}


@pytest.mark.parametrize("case", sorted(FAILURES))
def test_load_rejects_with_file_pointer_and_code(case: str, tmp_path: Path, no_network: None) -> None:
    files, (path, pointer, code, text) = FAILURES[case]
    error = load_failure(tmp_path, files)
    assert isinstance(error, ValueError)
    assert found(error.problems, path, pointer, code, text), error.problems
    assert f"{path}{pointer}" in str(error)


def test_load_reports_every_problem_not_just_the_first(tmp_path: Path) -> None:
    error = load_failure(
        tmp_path,
        {
            "shop/a.v1.json": schema("urn:skm:shop:a:v1", **REF_X),
            "shop/c.v1.json": schema("urn:skm:shop:c:v1", format="hostname"),
            "shop/d.v1.json": "{",
        },
    )
    assert [(p.path, p.issue.code) for p in error.problems] == [
        ("shop/a.v1.json", "$ref"),
        ("shop/c.v1.json", "format"),
        ("shop/d.v1.json", "json"),
    ]


def test_data_documents_are_not_treated_as_schemas(tmp_path: Path) -> None:
    files = {"shop/data/not-a-schema.json": "{ broken", "shop/a.v1.json": schema("urn:skm:shop:a:v1")}
    root = write_tree(tmp_path, files)
    assert SchemaRegistry.load(root).urns() == {"urn:skm:shop:a:v1"}


def test_every_schema_in_a_module_directory_is_found_at_any_depth(tmp_path: Path) -> None:
    deep = {"shop/x/y/z/deep.v2.json": schema("urn:skm:shop:deep:v2")}
    assert SchemaRegistry.load(write_tree(tmp_path, deep)).urns() == {"urn:skm:shop:deep:v2"}


# --- integer literals past the interpreter's int-to-text limit (sys.set_int_max_str_digits)

WIDE_DIGITS = "7" * 5000
WIDE = 7 * (10**5000 - 1) // 9  # the value of WIDE_DIGITS, built without int(str)
SHOWN = "7" * 79 + "…"
# the lowest accepted limit, the default, off
LIMITS = pytest.mark.parametrize("limit", [640, 4300, 0], ids=["lowest", "default", "off"])


@contextmanager
def int_text_limit(limit: int) -> Iterator[None]:
    before = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(limit)
    try:
        yield
    finally:
        sys.set_int_max_str_digits(before)


def wide_file(urn: str, body: str) -> str:
    """A schema file as text: ``json.dumps`` cannot write such an integer under a limit."""
    return f'{{"$schema": "{DIALECT}", "$id": "{urn}", {body}}}'


@LIMITS
def test_a_wide_integer_literal_in_a_schema_file_is_loaded_exactly(limit: int, tmp_path: Path) -> None:
    """``json.loads`` refused an integer token past the limit, so the whole file failed as ``json``."""
    urn = "urn:skm:shop:wide:v1"
    body = (
        f'"properties": {{"max": {{"maximum": {WIDE_DIGITS}}}, "low": {{"minimum": -{WIDE_DIGITS}}},'
        f' "one": {{"enum": [1, {WIDE_DIGITS}]}}, "step": {{"multipleOf": {WIDE_DIGITS}}}}},'
        f' "default": {{"max": {WIDE_DIGITS}}}'
    )
    root = write_tree(tmp_path, {"shop/wide.v1.json": wide_file(urn, body)})
    with int_text_limit(limit):
        registry = SchemaRegistry.load(root)
        assert sys.get_int_max_str_digits() == limit  # the interpreter setting is left as it was
        document = cast("dict[str, Any]", registry.get(urn))
        maximum = document["properties"]["max"]["maximum"]
        assert type(maximum) is int  # the stored literal is the plain exact integer
        assert maximum == WIDE
        assert document["properties"]["low"]["minimum"] == -WIDE
        assert document["properties"]["one"]["enum"] == [1, WIDE]
        assert document["default"] == {"max": WIDE}
        valid = {"max": WIDE, "low": -WIDE, "one": WIDE, "step": 2 * WIDE}
        assert registry.validate(urn, valid) == ()
        found_issues = registry.validate(urn, {"max": WIDE + 1, "low": -WIDE - 1, "one": 2, "step": WIDE + 1})
        assert [(issue.pointer, issue.code) for issue in found_issues] == [
            ("/low", "minimum"),
            ("/max", "maximum"),
            ("/one", "enum"),
            ("/step", "multipleOf"),
        ]
        assert found_issues[1].message == f"{SHOWN} is greater than the maximum of {SHOWN}"


@pytest.mark.parametrize("limit", [640, 4300], ids=["lowest", "default"])
def test_past_an_enabled_limit_integer_literals_are_read_up_to_a_bounded_width(
    limit: int, tmp_path: Path
) -> None:
    widest = "9" * 65536
    files = {
        "shop/edge.v1.json": wide_file("urn:skm:shop:edge:v1", f'"const": [{widest}, -{widest}, -0, 12]'),
        "shop/past.v1.json": wide_file("urn:skm:shop:past:v1", f'"const": -{widest}9'),
    }
    with int_text_limit(limit):
        error = load_failure(tmp_path, files)
        assert [(p.path, p.issue.pointer, p.issue.code) for p in error.problems] == [
            ("shop/past.v1.json", "", "json")
        ]
        message = error.problems[0].issue.message
        assert (
            f"65537 digits is wider than 65536 and than the interpreter's int-to-text limit of {limit}"
            in message
        )
        assert len(str(error)) < 300  # the refused token is not quoted
        (tmp_path / "shop/past.v1.json").unlink()
        registry = SchemaRegistry.load(tmp_path)
        assert sys.get_int_max_str_digits() == limit
    assert registry.get("urn:skm:shop:edge:v1")["const"] == [10**65536 - 1, 1 - 10**65536, 0, 12]


# past _INT_DIGITS_MAX: json.loads read these when the limit was off or wide enough, so they still are
PAST_DIGITS = 70000
PAST = 10**PAST_DIGITS - 1  # the value of "9" * PAST_DIGITS


@pytest.mark.parametrize("limit", [0, 100000], ids=["off", "wider"])
def test_an_integer_literal_past_the_bound_is_read_when_the_limit_admits_it(
    limit: int, tmp_path: Path
) -> None:
    urn = "urn:skm:shop:past:v1"
    widest = "9" * PAST_DIGITS
    body = f'"properties": {{"max": {{"maximum": {widest}}}, "one": {{"enum": [-{widest}, 1]}}}}'
    root = write_tree(tmp_path, {"shop/past.v1.json": wide_file(urn, body)})
    with int_text_limit(limit):
        registry = SchemaRegistry.load(root)
        assert sys.get_int_max_str_digits() == limit
        document = cast("dict[str, Any]", registry.get(urn))
        maximum = document["properties"]["max"]["maximum"]
        assert type(maximum) is int
        assert maximum == PAST
        assert document["properties"]["one"]["enum"] == [-PAST, 1]
        assert registry.validate(urn, {"max": PAST, "one": -PAST}) == ()
        found_issues = registry.validate(urn, {"max": PAST + 1, "one": 2})
        assert [(issue.pointer, issue.code) for issue in found_issues] == [
            ("/max", "maximum"),
            ("/one", "enum"),
        ]
        above, shown = "1" + "0" * 78 + "…", "9" * 79 + "…"  # PAST + 1 is 10**PAST_DIGITS
        assert found_issues[0].message == f"{above} is greater than the maximum of {shown}"


def test_an_integer_literal_past_a_wider_limit_is_refused_as_json_loads_refuses_it(tmp_path: Path) -> None:
    files = {"shop/past.v1.json": wide_file("urn:skm:shop:past:v1", f'"const": -{"9" * 100001}')}
    with int_text_limit(100000):
        error = load_failure(tmp_path, files)
    assert [(p.path, p.issue.pointer, p.issue.code) for p in error.problems] == [
        ("shop/past.v1.json", "", "json")
    ]
    message = error.problems[0].issue.message
    assert (
        "100001 digits is wider than 65536 and than the interpreter's int-to-text limit of 100000" in message
    )
    assert len(str(error)) < 300


@LIMITS
@pytest.mark.parametrize(
    ("body", "pointer", "code", "text"),
    [
        (f'"items": {WIDE_DIGITS}', "/items", "type", f"{SHOWN} is not of type 'object', 'boolean'"),
        (f'"properties": {{"a": {{"type": -{WIDE_DIGITS}}}}}', "/properties/a/type", None, "-" + "7" * 78),
        (f'"minLength": -{WIDE_DIGITS}', "/minLength", "minimum", "-" + "7" * 78 + "… is less than"),
    ],
    ids=["items", "type", "minLength"],
)
def test_a_wide_literal_that_breaks_the_metaschema_is_a_load_problem(
    limit: int, body: str, pointer: str, code: str | None, text: str, tmp_path: Path
) -> None:
    """The metaschema check quoted ``repr`` of the literal, which raised ValueError (or, with the limit
    off, put every digit into the message)."""
    with int_text_limit(limit):
        error = load_failure(tmp_path, {"shop/a.v1.json": wide_file("urn:skm:shop:a:v1", body)})
    assert found(error.problems, "shop/a.v1.json", pointer, code, text), error.problems
    assert len(str(error)) < 400


@LIMITS
def test_a_reference_to_a_non_schema_with_a_wide_literal_is_a_load_problem(
    limit: int, tmp_path: Path
) -> None:
    body = (
        f'"properties": {{"x": {{"$ref": "#/$defs/data/const"}}}},'
        f' "$defs": {{"data": {{"const": {{"type": {WIDE_DIGITS}}}}}}}'
    )
    with int_text_limit(limit):
        error = load_failure(tmp_path, {"shop/a.v1.json": wide_file("urn:skm:shop:a:v1", body)})
    expected = f"is not a schema: it points to an invalid schema: {SHOWN}"
    assert found(error.problems, "shop/a.v1.json", "/properties/x/$ref", "$ref", expected), error.problems
    assert len(str(error)) < 400


# --- the packaged schemas


def packaged_files() -> Iterator[Path]:
    root = Path(str(default_schema_root()))
    for path in sorted(root.rglob("*.json")):
        if path != root / "schema-lock.json" and "data" not in path.relative_to(root).parts[:-1]:
            yield path


def test_default_registry_loads_every_packaged_schema(default: SchemaRegistry) -> None:
    root = Path(str(default_schema_root()))
    expected = {json.loads(p.read_text(encoding="utf-8"))["$id"] for p in packaged_files()}
    assert default.urns() == expected
    assert len(expected) > 100
    for path in packaged_files():
        module = path.relative_to(root).parts[0]
        assert json.loads(path.read_text(encoding="utf-8"))["$id"].startswith(f"urn:skm:{module}:")


def test_golden_create_project_accepts_a_valid_dto(default: SchemaRegistry) -> None:
    dto = {"workspace_id": UUID, "slug": "my-project", "title": "My project", "description": "text"}
    assert default.validate(CREATE_PROJECT, dto) == ()
    assert default.validate(CREATE_PROJECT, {k: v for k, v in dto.items() if k != "description"}) == ()


@pytest.mark.parametrize(
    ("changes", "pointer", "code"),
    [
        ({"title": None}, "", "required"),
        ({"workspace_id": "nope"}, "/workspace_id", "format"),
        ({"workspace_id": 7}, "/workspace_id", "type"),
        ({"slug": "-bad-"}, "/slug", "pattern"),
        ({"slug": "A"}, "/slug", "pattern"),
        ({"title": ""}, "/title", "minLength"),
        ({"title": "t" * 201}, "/title", "maxLength"),
        ({"description": "d" * 4001}, "/description", "maxLength"),
        ({"stray": 1}, "", "additionalProperties"),
    ],
)
def test_golden_create_project_rejects_invalid_dtos(
    default: SchemaRegistry, changes: dict[str, Any], pointer: str, code: str
) -> None:
    dto: dict[str, Any] = {"workspace_id": UUID, "slug": "my-project", "title": "My project"}
    dto.update(changes)
    if dto.get("title") is None:
        del dto["title"]
    assert (pointer, code) in [(i.pointer, i.code) for i in default.validate(CREATE_PROJECT, dto)]


def test_data_documents_validate_against_the_schema_they_name(default: SchemaRegistry) -> None:
    path = Path(str(default_schema_root())) / "kernel" / "data" / "error-codes.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    assert default.validate(document["schema"], document) == ()
    document["version"] = 0
    found_issues = default.validate(document["schema"], document)
    assert [(i.pointer, i.code) for i in found_issues] == [("/version", "minimum")]


# --- offline, independent of the checkout and the working directory


def test_load_default_needs_neither_network_nor_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, no_network: None, default: SchemaRegistry
) -> None:
    monkeypatch.chdir(tmp_path)
    registry = SchemaRegistry.load_default()
    assert registry.urns() == default.urns()
    dto = {"workspace_id": UUID, "slug": "my-project", "title": "T"}
    assert registry.validate(CREATE_PROJECT, dto) == ()


def test_registry_loads_from_an_archive_without_any_checkout(
    tmp_path: Path, no_network: None, default: SchemaRegistry
) -> None:
    root = Path(str(default_schema_root()))
    archive = tmp_path / "schemas.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in sorted(root.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                bundle.write(path, path.relative_to(root).as_posix())
    with zipfile.ZipFile(archive) as bundle:
        registry = SchemaRegistry.load(zipfile.Path(bundle))
        assert registry.urns() == default.urns()
        dto = {"workspace_id": UUID, "slug": "my-project", "title": "T"}
        assert registry.validate(CREATE_PROJECT, dto) == ()
        assert [i.code for i in registry.validate(CREATE_PROJECT, {**dto, "slug": "A"})] == ["pattern"]


def test_a_network_reference_is_refused_at_load_without_a_connection(
    tmp_path: Path, no_network: None
) -> None:
    files = {"shop/a.v1.json": schema("urn:skm:shop:a:v1", items={"$ref": "http://example.com/other.json"})}
    error = load_failure(tmp_path, files)
    assert [(p.issue.pointer, p.issue.code) for p in error.problems] == [("/items/$ref", "$ref")]


# --- resolvers rooted at a free-standing schema


@pytest.mark.parametrize(
    "body",
    [
        {"type": 5},
        {"properties": {"secret": {"type": 5}}},
        {"$defs": {"secret": {"type": 5}}},
        {"allOf": []},
        {"pattern": "("},
        {"$schema": "http://json-schema.org/draft-07/schema#"},
    ],
)
def test_free_standing_schema_facade_rejects_malformed_schemas(
    default: SchemaRegistry, no_network: None, body: dict[str, Any]
) -> None:
    assert not default.is_valid_schema(body)


@pytest.mark.parametrize("dialect", [DIALECT, DIALECT + "#"])
def test_free_standing_schema_facade_accepts_supported_dialect_aliases(
    default: SchemaRegistry, no_network: None, dialect: str
) -> None:
    assert default.is_valid_schema({"$schema": dialect, "type": "string"})


@pytest.mark.parametrize("keyword", ["propertyNames", "contentSchema"])
@pytest.mark.parametrize("malformed", [False, True])
def test_free_standing_schema_facade_validates_deep_schema_nodes_without_recursion(
    default: SchemaRegistry, no_network: None, keyword: str, malformed: bool
) -> None:
    body: dict[str, Any] = {"type": 5} if malformed else {}
    for _ in range(500):
        body = {keyword: body}
    before = sys.getrecursionlimit()
    assert default.is_valid_schema(body) is not malformed
    assert sys.getrecursionlimit() == before


@pytest.mark.parametrize(
    "body",
    [
        {"properties": {"bad": None}},
        {"patternProperties": {"(": {}}},
        {"prefixItems": [5]},
        {"dependencies": {"bad": {"type": 5}}},
        {"dependencies": {"bad": ["duplicate", "duplicate"]}},
        {"contentSchema": {"items": []}},
        {"propertyNames": {"minLength": -1}},
    ],
)
def test_free_standing_schema_facade_keeps_projected_child_constraints(
    default: SchemaRegistry, no_network: None, body: dict[str, Any]
) -> None:
    assert not default.is_valid_schema(body)


def test_free_standing_schema_facade_preserves_schema_and_literal_positions(
    default: SchemaRegistry, no_network: None
) -> None:
    body: dict[str, Any] = {
        "$defs": {"public": False},
        "definitions": {"old": {"type": "string"}},
        "properties": {"name": True},
        "patternProperties": {"^key": {}},
        "dependentSchemas": {"name": False},
        "dependencies": {"old": ["name"], "name": {"type": "object"}},
        "allOf": [False],
        "anyOf": [True],
        "oneOf": [{}],
        "prefixItems": [False],
        "items": False,
        "contains": {},
        "additionalProperties": True,
        "unevaluatedProperties": False,
        "unevaluatedItems": True,
        "propertyNames": {},
        "contentSchema": False,
        "if": True,
        "then": {},
        "else": False,
        "not": {},
        # These objects are instance data, including unknown extension data, rather than schemas.
        "const": {"type": 5},
        "enum": [{"items": None}],
        "default": {"properties": 5},
        "examples": [{"not": None}],
        "extension": {"contentSchema": 5},
        "additionalItems": 5,  # no longer a schema keyword in Draft 2020-12
    }
    assert default.is_valid_schema(body)


def test_free_standing_schema_facade_bounds_cyclic_and_oversized_inputs(
    default: SchemaRegistry, no_network: None
) -> None:
    body: dict[str, Any] = {}
    body["propertyNames"] = body
    assert not default.is_valid_schema(body)
    body = {"extension": [None] * 100_001}
    assert not default.is_valid_schema(body)
    body = {"extension": [None] * 99_998}  # root + extension array + literals = 100,000 visits
    assert default.is_valid_schema(body)
    assert default.is_valid_schema({"type": "string"})


def test_free_standing_schema_facade_returns_false_for_recursive_format_checks(
    default: SchemaRegistry, no_network: None
) -> None:
    # The library's regex format checker uses Python's recursive regular expression parser.
    assert not default.is_valid_schema({"pattern": "(" * 1500 + "a" + ")" * 1500})


@LIMITS
def test_free_standing_schema_facade_preserves_wide_literals_offline(
    default: SchemaRegistry, no_network: None, limit: int
) -> None:
    body: dict[str, Any] = {
        "$id": "https://example.invalid/tree.json",
        "$dynamicAnchor": "node",
        "$defs": {"public": {"type": ["integer", "string"], "enum": [WIDE, "public"]}},
        "properties": {
            "number": {"maximum": WIDE, "minimum": -WIDE},
            "public": {"$ref": "#/$defs/public"},
            "next": {"$dynamicRef": "#node"},
        },
    }
    with int_text_limit(limit):
        assert default.is_valid_schema(body)
        assert not default.is_valid_schema({"minLength": -WIDE})
        assert sys.get_int_max_str_digits() == limit
    assert body["properties"]["number"]["maximum"] is WIDE
    assert "https://example.invalid/tree.json" not in default.urns()


def test_resolver_for_roots_local_references_and_reaches_registered_urns(default: SchemaRegistry) -> None:
    root: dict[str, Any] = {
        "$defs": {"local": {"type": "integer"}},
        "properties": {"x": {"$ref": "#/$defs/local"}},
    }
    resolver = default.resolver_for(root)
    assert resolver.lookup("#").contents == root
    assert resolver.lookup("#/$defs/local").contents == {"type": "integer"}
    defs = cast("dict[str, Any]", default.get("urn:skm:integrations:defs:v1"))
    hook = resolver.lookup("urn:skm:integrations:defs:v1#/$defs/hook_subscription")
    assert hook.contents == defs["$defs"]["hook_subscription"]
    # a relative reference reached through the target resolves inside the target, not the free-standing root
    assert hook.resolver.lookup("#/$defs/WebhookTarget").contents == defs["$defs"]["WebhookTarget"]
    with pytest.raises(Unresolvable):
        resolver.lookup("#/$defs/WebhookTarget")


def test_resolver_for_resolves_embedded_ids_and_read_only_documents(default: SchemaRegistry) -> None:
    leaf: dict[str, Any] = {"type": "string"}
    root: dict[str, Any] = {"$defs": {"inner": {"$id": "urn:skm:shop:inner:v1", "$defs": {"leaf": leaf}}}}
    inner = default.resolver_for(root).lookup("urn:skm:shop:inner:v1")
    assert inner.resolver.lookup("#/$defs/leaf").contents == leaf
    hooks = default.get("urn:skm:settings:hooks:v1")  # a MappingProxyType is accepted and left unchanged
    resolved = default.resolver_for(hooks).lookup("#/properties/subscriptions")
    assert resolved.contents == cast("dict[str, Any]", hooks)["properties"]["subscriptions"]
    assert "urn:skm:shop:inner:v1" not in default.urns()  # the root never enters the registry itself


def test_resolver_for_scopes_colliding_definitions_to_the_resource_entered(default: SchemaRegistry) -> None:
    inner_leaf: dict[str, Any] = {"x-skm-secret": True}
    inner: dict[str, Any] = {"$id": "urn:skm:shop:inner:v1", "$defs": {"leaf": inner_leaf}}
    root: dict[str, Any] = {"$defs": {"leaf": {"type": "string"}}, "properties": {"inner": inner}}
    resolver = default.resolver_for(root)
    assert resolver.lookup("#/$defs/leaf").contents == {"type": "string"}
    # entering the embedded resource in place, as validation does, rebases its fragment references
    assert scope(inner, resolver).lookup("#/$defs/leaf").contents == inner_leaf
    assert scope({"type": "object"}, resolver) is resolver  # a subschema without $id keeps the scope
    # a pointer through the embedded resource returns a resolver already inside it
    assert resolver.lookup("#/properties/inner").resolver.lookup("#/$defs/leaf").contents == inner_leaf


def test_resolver_for_follows_dynamic_anchors_through_the_lookup_scope(default: SchemaRegistry) -> None:
    root_item: dict[str, Any] = {"$dynamicAnchor": "item", "type": "string"}
    list_item: dict[str, Any] = {"$dynamicAnchor": "item"}
    root: dict[str, Any] = {
        "$id": "https://example.invalid/root.json",
        "$ref": "list.json",
        "$defs": {
            "item": root_item,
            "list": {"$id": "list.json", "items": {"$dynamicRef": "#item"}, "$defs": {"item": list_item}},
        },
    }
    resolver = default.resolver_for(root)
    assert resolver.lookup("list.json").resolver.lookup("#item").contents == root_item  # outermost wins
    assert resolver.lookup("list.json").contents["$defs"]["item"] == list_item
    # rooted at the list itself, nothing outer is in the dynamic scope: its own anchor applies
    alone = default.resolver_for(root["$defs"]["list"]).lookup("list.json")
    assert alone.resolver.lookup("#item").contents == list_item


@pytest.mark.parametrize(
    "ref",
    [
        "#/$defs/missing",
        "urn:skm:missing:schema:v1",
        "urn:skm:kernel:defs:v1#/$defs/missing",
        "http://example.com/other.json",
        "file:///etc/schema.json",
    ],
)
def test_resolver_for_fails_offline_on_unresolved_references(
    default: SchemaRegistry, no_network: None, ref: str
) -> None:
    with pytest.raises(Unresolvable):
        default.resolver_for({"$defs": {}}).lookup(ref)
