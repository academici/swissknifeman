"""Sources feed the real resolver; ignored authority and provenance stay observable."""

import json
from dataclasses import dataclass
from pathlib import Path
from runpy import run_path
from typing import Literal
from uuid import UUID

import pytest

from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.platform.config.keys import Chain, Level
from skm.platform.config.layers import Contribution, Layer, LayerRef
from skm.platform.config.resolver import resolve
from skm.platform.config.scopes import ScopeChain, ScopeRef
from skm.platform.config.sources.cli_overrides import InvocationOverrides, cli_layers, invocation_layers
from skm.platform.config.sources.defaults import defaults_layer
from skm.platform.config.sources.document import DocEntry, parse_document, render_document
from skm.platform.config.sources.env import env_layers
from skm.platform.config.sources.packs import PackFragment, pack_layers

h = run_path(str(Path(__file__).with_name("test_resolver.py")))


@pytest.fixture
def registry(tmp_path):
    leaf = h["leaf"]
    properties = dict(h["DEMO"])
    properties.update(
        {
            "map": leaf(
                {
                    "type": "object",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}, "count": {"type": "integer"}},
                        "required": ["name"],
                    },
                },
                default={},
                merge="deep_merge",
                override=True,
            ),
            "tags": leaf({"type": "array", "items": {"type": "string"}}, default=["base"], override=True),
            "blocked": leaf({"type": "integer"}, default=4, pack=False),
        }
    )
    return h["build_registry"](tmp_path, properties)


def effective(registry, layers=(), *, chain=Chain.WORK):
    scope = ScopeRef(Level.INSTANCE, UUID(int=1))
    ordered = list(layers)
    if not any(layer.ref.level is Level.INSTANCE for layer in ordered):
        at = next((i for i, layer in enumerate(ordered) if layer.ref.level is Level.INVOCATION), len(ordered))
        ordered.insert(at, Layer(LayerRef(Level.INSTANCE, scope.scope_id), {}))
    return resolve(
        registry,
        ScopeChain(chain, (scope,)),
        [defaults_layer(registry, chain), *ordered],
        generation=1,
        pack_generation=1,
    )


def test_defaults_use_chain_and_do_not_invent_absent_values(registry):
    assert "demo.note" not in defaults_layer(registry, Chain.WORK).contributions
    assert "demo.host_only" not in defaults_layer(registry, Chain.WORK).contributions
    assert set(defaults_layer(registry, Chain.HOST).contributions) == {"demo.host_only"}
    assert effective(registry).get("demo.size") == 1


def test_invocation_priority_and_each_set_keeps_provenance(registry, tmp_path):
    first, second = tmp_path / "first.toml", tmp_path / "second.json"
    first.write_text("[demo]\nsize=3\n", encoding="utf-8")
    second.write_text('{"demo": {"size": 4}}', encoding="utf-8")
    layers = invocation_layers(
        registry,
        {"SKM__DEMO__SIZE": "2"},
        InvocationOverrides((first, second), ("demo.size=5", "demo.size=6")),
    )
    result = effective(registry, layers)
    assert result.get("demo.size") == 6
    history = result.resolution("demo.size").trace
    assert [c.contribution.value for c in history] == [1, 2, 3, 4, 5, 6]
    assert [layer.ref.source for layer in layers] == [
        "env",
        f"config-file:{first}",
        f"config-file:{second}",
        "cli",
        "cli",
    ]


def test_unknown_env_warns_once_per_process_variable(registry):
    diagnostics = []
    environ = {"SKM__NONEXISTENT__P0205_A": "do not publish me", "SKM_DATABASE_URL": "ignored"}
    assert env_layers(registry, environ, warn=diagnostics.append) == ()
    assert env_layers(registry, environ, warn=diagnostics.append) == ()
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "CONFIG_UNKNOWN_KEY"
    assert "do not publish me" not in repr(diagnostics)


@pytest.mark.parametrize("source", ["env", "set", "file"])
def test_protected_values_are_ignored_and_visible(registry, tmp_path, source):
    path = tmp_path / "protected.toml"
    path.write_text("[demo]\nrounds=99\n", encoding="utf-8")
    env = {"SKM__DEMO__ROUNDS": "99"} if source == "env" else {}
    overrides = InvocationOverrides(
        (path,) if source == "file" else (), ("demo.rounds=99",) if source == "set" else ()
    )
    result = effective(registry, invocation_layers(registry, env, overrides))
    assert result.get("demo.rounds") == 2
    assert result.resolution("demo.rounds").trace[-1].reason == "override_not_allowed"
    assert any(d.code == "CONFIG_OVERRIDE_NOT_ALLOWED" for d in result.diagnostics)


def test_set_append_order_and_invalid_append_cannot_change_scalar(registry):
    layers = cli_layers(
        registry,
        InvocationOverrides(
            sets=(
                "demo.tags=a",
                "demo.tags+=b, c",
                "demo.size+=7",
            )
        ),
    )
    result = effective(registry, layers)
    assert result.get("demo.tags") == ["a", "b", "c"]
    assert result.get("demo.size") == 1
    assert result.resolution("demo.size").trace[-1].reason == "op_not_allowed"


@pytest.mark.parametrize("assignment", ["bad", "=value", "demo.unknown=1"])
def test_bad_cli_input_fails_without_applying(registry, assignment):
    with pytest.raises(ValidationFailed):
        cli_layers(registry, InvocationOverrides(sets=(assignment,)))


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("[unknown]\nvalue=1", "CONFIG_UNKNOWN_KEY"),
        ('lock=["demo.size"]\n[demo]\nsize=2', "CONFIG_INVALID"),
        ('unset=["demo.size"]\n[demo]\nsize=2', "CONFIG_INVALID"),
        ("[demo\n", "CONFIG_INVALID"),
    ],
)
def test_config_files_fail_closed(registry, tmp_path, text, code):
    path = tmp_path / "bad.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValidationFailed) as caught:
        cli_layers(registry, InvocationOverrides((path,)))
    assert caught.value.code == code


def test_missing_file_and_text_errors_are_structured(registry, tmp_path):
    with pytest.raises(ValidationFailed):
        cli_layers(registry, InvocationOverrides((tmp_path / "missing.toml",)))
    with pytest.raises(ValidationFailed) as caught:
        invocation_layers(registry, {"SKM__DEMO__SIZE": "nope"})
    assert caught.value.details["reason"] == "text_value"


def test_unset_and_deep_map_markers_reach_resolver(registry, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('unset=["demo.size"]\n[demo.map]\na={"$unset"=true}\nb={name="new"}', encoding="utf-8")
    stored = LayerRef(Level.INSTANCE, UUID(int=1))
    layers = [
        Layer(
            stored,
            {
                "demo.size": Contribution(stored, "set", 8),
                "demo.map": Contribution(stored, "set", {"a": {"name": "old"}}),
            },
        ),
        *cli_layers(registry, InvocationOverrides((path,))),
    ]
    result = effective(registry, layers)
    assert result.get("demo.size") == 1
    assert result.get("demo.map") == {"b": {"name": "new"}}


def test_pack_order_invalid_values_and_authority_gates(registry):
    diagnostics = []
    fragments = [
        PackFragment("z", 1, {"demo.size": 3}),
        PackFragment("a", 1, {"demo.size": 2}),
        PackFragment(
            "early",
            -1,
            {
                "demo.size": 99,
                "demo.blocked": 0,
                "unknown.key": 1,
                "demo.host_only": 9,
                "demo.map": {"a": {"count": 1}},
            },
        ),
    ]
    layers = pack_layers(fragments, registry, Chain.WORK, warn=diagnostics.append)
    assert [layer.ref.pack_id for layer in layers] == ["early", "a", "z"]
    assert "demo.size" not in layers[0].contributions
    assert "demo.host_only" not in layers[0].contributions
    assert "demo.map" in layers[0].contributions  # required name may be inherited
    assert {d.code for d in diagnostics} == {
        "CONFIG_INVALID",
        "CONFIG_PACK_NOT_ALLOWED",
        "CONFIG_UNKNOWN_KEY",
    }
    assert effective(registry, layers).get("demo.size") == 3


def test_pack_unset_cannot_reset_monotonic_authority(registry):
    diagnostics = []
    fragments = [PackFragment("p", 0, {}, frozenset({"demo.rounds", "demo.size"}))]
    layers = pack_layers(fragments, registry, Chain.WORK, warn=diagnostics.append)
    assert "demo.rounds" not in layers[0].contributions
    assert layers[0].contributions["demo.size"].op == "unset"
    assert diagnostics[0].code == "CONFIG_INVALID"


def test_pack_partial_maps_validate_values_and_preserve_tombstones(registry):
    diagnostics = []
    layers = pack_layers(
        [
            PackFragment("valid", 0, {"demo.map": {"a": {"$unset": True}, "b": {"count": 1}}}),
            PackFragment("invalid", 1, {"demo.map": {"b": {"count": "invalid"}}}),
        ],
        registry,
        Chain.WORK,
        warn=diagnostics.append,
    )
    assert layers[0].contributions["demo.map"].value == {"a": {"$unset": True}, "b": {"count": 1}}
    assert "demo.map" not in layers[1].contributions
    assert diagnostics[0].code == "CONFIG_INVALID"


def test_invalid_invocation_value_fails_on_resolver_read(registry):
    result = effective(registry, cli_layers(registry, InvocationOverrides(sets=("demo.size=99",))))
    with pytest.raises(ValidationFailed, match="CONFIG_INVALID"):
        result.get("demo.size")


def test_invocation_cannot_widen_monotonic_authority(registry):
    ref = LayerRef(Level.INSTANCE, UUID(int=1))
    result = effective(
        registry,
        [
            Layer(ref, {"demo.access": Contribution(ref, "set", "confined")}),
            *cli_layers(registry, InvocationOverrides(sets=("demo.access=open",))),
        ],
    )
    assert result.get("demo.access") == "confined"


@pytest.fixture(scope="module")
def owner_registry():
    inputs = run_path(str(Path(__file__).with_name("test_registry_all_sections.py")))
    return inputs["real_registry"]()


def test_real_import_example_round_trips_through_owner_registry(owner_registry):
    registry = owner_registry
    path = Path(__file__).resolve().parents[4] / "tests/fixtures/corpus/examples/config/project-import.toml"
    parsed = parse_document(path.read_text(encoding="utf-8"), "toml", registry)
    assert not parsed.problems
    profiles = parsed.entries["execution.workflow.profile_by_work_kind"].value
    assert isinstance(profiles, dict)
    assert profiles["research"] == {"$unset": True}
    for fmt in ("toml", "json"):
        rendered = render_document(parsed.entries, registry, fmt=fmt)
        assert parse_document(rendered, fmt, registry) == parsed


@pytest.mark.parametrize(
    "text",
    ["ascii", "a\x7fb", "face-\U0001f600", "\x00\b\x0b\f\x1f", '"\\\t\n\r'],
    ids=["ascii", "del", "non-bmp", "controls", "escapes"],
)
@pytest.mark.parametrize("fmt", ["toml", "json"])
def test_unicode_strings_and_map_keys_round_trip(owner_registry, text, fmt):
    @dataclass
    class Entry:
        key: str
        op: Literal["set", "unset", "append"]
        value: JsonValue
        locked: bool

    servers: JsonValue = {
        "sample": {
            "type": "stdio",
            "command": "runner" + text,
            "args": [text],
            "env_refs": {text: "secret://env/TOKEN"},
        }
    }
    command = [text, "second"]
    assert not owner_registry.value_issues("integrations.mcp.servers", servers)
    assert not owner_registry.value_issues("execution.generation.command", command)
    rows = [
        Entry("integrations.mcp.servers", "set", servers, True),
        Entry("execution.generation.command", "append", command, True),
    ]
    expected = {entry.key: DocEntry(entry.op, entry.value) for entry in rows}
    rendered = render_document(rows, owner_registry, fmt=fmt)
    parsed = parse_document(rendered, fmt, owner_registry)
    assert not parsed.problems
    assert dict(parsed.entries) == expected
    assert parsed.locks == frozenset(expected)
    assert render_document(rows, owner_registry, fmt=fmt) == rendered
    assert render_document(reversed(rows), owner_registry, fmt=fmt) == rendered


@pytest.mark.parametrize("fmt", ["toml", "json"])
def test_document_round_trip_is_deterministic(registry, fmt):
    document = parse_document(
        {
            "unset": ["demo.note"],
            "lock": ["demo.size"],
            "append": {"demo.tags": ["z"]},
            "demo": {
                "size": 3,
                "ratio": 1.25,
                "map": {"strange.key": {"$unset": True}, "b": {"name": "two\nlines", "count": 2}},
            },
        },
        "json",
        registry,
    )
    assert not document.problems

    @dataclass
    class Entry:
        key: str
        op: str
        value: JsonValue
        locked: bool

    rows = [
        Entry(key, entry.op, entry.value, key in document.locks) for key, entry in document.entries.items()
    ]
    rendered = render_document(rows, registry, fmt=fmt)
    assert rendered == render_document(reversed(rows), registry, fmt=fmt)
    parsed = parse_document(rendered, fmt, registry)
    assert parsed == document
    assert rendered == render_document(rows, registry, fmt=fmt)


@pytest.mark.parametrize(
    "data",
    [
        {"schema": "v2"},
        {"unset": "demo.size"},
        {"append": []},
        {"unset": ["demo.size"], "demo": {"size": 2}},
        {"append": {"demo.tags": []}, "demo": {"tags": []}},
        {"lock": ["demo.size"]},
        {"lock": ["unknown.key"]},
        {"demo.size": 1, "demo": {"size": 2}},
    ],
)
def test_document_problems_prevent_ambiguous_or_unknown_writes(registry, data):
    document = parse_document(data, "json", registry)
    assert document.problems
    assert not any("value" in problem.message for problem in document.problems)


def test_json_rejects_duplicate_keys_and_non_json_values(registry):
    for text in ('{"demo.size":1,"demo.size":2}', '{"demo.ratio":NaN}', "[]"):
        assert parse_document(text, "json", registry).problems
    assert parse_document({"demo": {"note": object()}}, "json", registry).problems


# Wider than the default int-to-text limit (4300 digits): the test never converts between them by int()/str().
WIDE_TEXT = "7" * 5001
WIDE = 7 * (10**5001 - 1) // 9


@pytest.mark.parametrize(
    ("token", "number"),
    [
        (WIDE_TEXT, WIDE),
        ("-" + WIDE_TEXT, -WIDE),
        ("1" + "0" * 5000, 10**5000),
        ("1" * 65536, (10**65536 - 1) // 9),  # exactly 64 KiB of canonical JSON
        ("-" + "9" * 65535, -(10**65535 - 1)),
    ],
    ids=["wide", "negative", "power", "limit", "negative-limit"],
)
def test_json_integers_of_any_width_within_a_value_are_read(registry, token, number):
    text = '{"demo": {"size": ' + token + ', "ratio": 1.5, "map": {"a": {"name": "n", "count": 1e2}}}}'
    document = parse_document(text, "json", registry)
    assert not document.problems
    size = document.entries["demo.size"].value
    assert type(size) is int
    assert size == number
    ratio = document.entries["demo.ratio"].value
    assert type(ratio) is float
    assert ratio == 1.5
    # a nested exponent number stays a float (written back as 100.0, not 100)
    assert json.dumps(document.entries["demo.map"].value) == '{"a": {"name": "n", "count": 100.0}}'


def test_json_wide_integer_reaches_the_schema_check_as_an_issue(registry):
    document = parse_document('{"demo": {"size": ' + WIDE_TEXT + "}}", "json", registry)
    issues = registry.value_issues("demo.size", document.entries["demo.size"].value)
    assert [issue.code for issue in issues] == ["maximum"]
    assert WIDE_TEXT[:100] not in issues[0].message


@pytest.mark.parametrize(
    "text",
    [
        '{"demo": {"size": ' + "1" * 65537 + "}}",  # longer than a stored value may be
        '{"demo": {"size": -' + "1" * 65536 + "}}",
        '{"demo": {"size": ' + "1" * 5001 + "x}}",
        '{"demo": {"size": 0' + "1" * 5001 + "}}",
        '{"demo": {"size": -}}',
        '{"demo": {"size": ' + "1" * 5001 + ', "size": 1}}',
        '{"demo": {"ratio": 1e999}}',
    ],
    ids=["over-limit", "negative-over-limit", "garbage", "leading-zero", "bare-sign", "duplicate", "inf"],
)
def test_malformed_or_oversized_json_numbers_are_a_syntax_problem(registry, text):
    document = parse_document(text, "json", registry)
    problems = [(p.code, p.key, p.reason) for p in document.problems]
    assert problems == [("CONFIG_INVALID", "", "document_syntax")]
    assert not document.entries
    assert all("1111" not in problem.message for problem in document.problems)


def test_empty_known_section_is_a_valid_empty_document(registry):
    assert not parse_document("[demo]\n", "toml", registry).problems
    assert parse_document("[unknown]\n", "toml", registry).problems


def test_invalid_marker_and_pack_map_field_cannot_hide_schema_error(registry):
    diagnostics = []
    layers = pack_layers(
        [
            PackFragment("p", 0, {"demo.map": {"a": {"count": {"$unset": 1}}}}),
        ],
        registry,
        Chain.WORK,
        warn=diagnostics.append,
    )
    assert "demo.map" not in layers[0].contributions
    assert diagnostics[0].code == "CONFIG_INVALID"


def test_json_null_round_trips_and_toml_reports_its_limit(registry):
    entries = {"demo.label": DocEntry("set", None)}
    rendered = render_document(entries, registry, fmt="json")
    assert parse_document(json.dumps(rendered), "json", registry).entries == entries
    with pytest.raises(ValidationFailed) as caught:
        render_document(entries, registry, fmt="toml")
    assert caught.value.details["reason"] == "toml_null"
