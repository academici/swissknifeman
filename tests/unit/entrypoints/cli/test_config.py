"""Settings CLI through explicit test composition; no production authority fallback."""

import json
import tomllib
from collections.abc import Generator
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from fakes.app import FakeScopeChain
from fakes.authorizer import FakeAuthorizer
from skm.adapters.memory.config_store import increment_config_generation, write_config_entry
from skm.application_bus.ports import AuthzDecision
from skm.bootstrap.composition import App, CompositionOverrides, build_app
from skm.entrypoints.cli.commands import GROUPS
from skm.entrypoints.cli.commands import config as config_command
from skm.entrypoints.cli.commands.config import GROUP
from skm.entrypoints.cli.main import Backend, app_backend, main
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, ValidationFailed
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.settings.public import GetSchema, GetSchemaView
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.config.keys import KeySpec
from skm.platform.config.secrets import SecretResolver
from skm.platform.config.store import StoredContribution
from skm.platform.logging import setup
from skm.platform.system_clock import SystemClock

ROOT = Path(__file__).resolve().parents[4]
ROUNDS = "execution.review.max_rounds"
PROFILE = "execution.workflow.profile"
SCOPES = {level.value: ScopeId(UUID(int=index)) for index, level in enumerate(ScopeKind, 1)}
ACTOR = Actor(PrincipalId(UUID(int=100)), PrincipalKind.HUMAN, "fixture CLI owner")


class StateProbe:
    """Pseudo port: ``uow.repo(StateProbe)`` is the working copy of that unit of work."""


@dataclass
class Cli:
    app: App
    authorizer: FakeAuthorizer

    def run(self, *args: str, json_mode: bool = True, state_dir: Path | None = None) -> tuple[int, str, str]:
        out, err = StringIO(), StringIO()

        def backend(options: object, environ: object) -> Backend:
            attached = app_backend(self.app, ACTOR)
            # A test owns one App across invocations; main still closes each attached backend.
            return Backend(attached.client, state_dir=state_dir, instance_id=self.app.instance_id)

        code = main(
            [*(["--json", "--quiet"] if json_mode else []), *args],
            environ={},
            stdout=out,
            stderr=err,
            backend=backend,
        )
        return code, out.getvalue(), err.getvalue()

    def result(self, *args: str) -> Any:
        code, out, err = self.run("config", *args)
        assert (code, err) == (0, ""), (out, err)
        envelope = json.loads(out)
        assert set(envelope) == {"schema", "ok", "command", "request_id", "result", "diagnostics"}
        assert envelope["schema"] == "urn:skm:cli:envelope:v1"
        assert envelope["request_id"].startswith("cli-")
        assert envelope["ok"] is True
        return envelope["result"]


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Cli]:
    monkeypatch.setattr(setup._state, "settings", setup._state.settings)
    authorizer = FakeAuthorizer()
    app = build_app(
        load_bootstrap(None, {"SKM_DATABASE_URL": "postgresql://unused"}, tmp_path),
        surface=Surface.CLI,
        environ={},
        invocation={},
        overrides=CompositionOverrides(
            authorizer=authorizer,
            scopes=FakeScopeChain(),
            instance_id=SCOPES["instance"],
            repositories={StateProbe: lambda state: state},
        ),
    )
    parents = {
        "workspace": "instance",
        "project": "workspace",
        "plan": "project",
        "run": "plan",
        "host": "instance",
    }
    with app.uow_factory(RequestMeta("req_" + "0" * 26, Surface.CLI, None, SystemClock().now())) as uow:
        registry = uow.repo(ScopeRegistry)
        for level in ScopeKind:
            parent = parents.get(level.value)
            registry.create(
                SCOPES[level.value],
                level,
                parent=SCOPES[parent] if parent else None,
                workspace_id=WorkspaceId(SCOPES["workspace"])
                if level not in {ScopeKind.INSTANCE, ScopeKind.HOST}
                else None,
            )
        uow.commit()
    yield Cli(app, authorizer)
    app.close()


def test_discovered_group_and_all_help_need_no_backend() -> None:
    assert GROUP in GROUPS
    for verb in (
        "schema",
        "get",
        "explain",
        "set",
        "unset",
        "remove",
        "lock",
        "unlock",
        "import",
        "export",
        "entries",
        "history",
        "doctor",
    ):

        def refused(options: object, environ: object) -> Backend:
            raise AssertionError("help must not compose a backend")

        assert main(["config", verb, "--help"], stdout=StringIO(), backend=refused) == 0


@pytest.mark.parametrize("verb", ["get", "doctor"])
def test_production_still_fails_closed(tmp_path: Path, verb: str) -> None:
    """Without the production authority owners no backend exists, so doctor cannot report a clean state."""
    out = StringIO()
    args = ["get", ROUNDS] if verb == "get" else ["doctor"]
    assert (
        main(
            ["--json", "config", *args],
            environ={"HOME": str(tmp_path)},
            stdout=out,
            stderr=StringIO(),
        )
        == 6
    )
    assert json.loads(out.getvalue())["error"]["code"] == "BOOTSTRAP_MISSING"


def _store(cli: Cli, scope: str, key: str, value: object) -> None:
    """A stored entry written under the facade, as a stale or invalid key left by an older release."""
    with cli.app.uow_factory(RequestMeta("req_" + "1" * 26, Surface.CLI, None, SystemClock().now())) as uow:
        state = uow.repo(StateProbe)
        entry = StoredContribution(uuid4(), key, "set", value, False, 1)  # type: ignore[arg-type]
        write_config_entry(state, SCOPES[scope], entry)  # type: ignore[arg-type]
        increment_config_generation(state)  # type: ignore[arg-type]
        uow.commit()


def test_doctor_reports_all_scopes_and_never_a_clean_unknown(cli: Cli) -> None:
    result = cli.result("doctor")
    checks = {check["id"]: check for check in result["checks"]}
    assert checks["config.registry"]["status"] == "ok"
    # No process snapshot was captured: restart-pending is unknown (warn), not healthy.
    restart = checks["config.restart_pending"]
    assert restart["status"] == "warn"
    assert json.loads(restart["details"]["detail"])["state"] == "unknown"
    code, out, err = cli.run("config", "doctor")
    assert (code, err) == (0, "")
    assert json.loads(out)["command"] == "platform.doctor"


def test_doctor_exits_6_on_a_failed_check_without_disclosing_values(cli: Cli) -> None:
    secret = "sk-live-0123456789abcdef"  # fixture value that must never be printed
    _store(cli, "project", "x.stale_key", secret)
    _store(cli, "instance", "integrations.conflict_suffix", secret)  # breaks the key's pattern
    code, out, err = cli.run("config", "doctor")
    assert (code, err) == (6, "")
    statuses = {check["id"]: check["status"] for check in json.loads(out)["result"]["checks"]}
    assert statuses["config.CONFIG_INVALID"] == "fail"
    assert statuses["config.CONFIG_UNKNOWN_KEY"] == "warn"
    assert secret not in out
    code, out, err = cli.run("config", "doctor", json_mode=False)
    assert code == 6
    assert "fail  config.CONFIG_INVALID" in out
    assert "warn  config.CONFIG_UNKNOWN_KEY" in out
    assert "warn  config.restart_pending" in out
    assert secret not in out + err
    assert "fail" in out.splitlines()[-1]


def test_doctor_only_selects_exact_ids_and_refuses_unknown_ones(cli: Cli) -> None:
    result = cli.result("doctor", "--only", "config.registry", "--only", "config.restart_pending")
    assert {check["id"] for check in result["checks"]} == {"config.registry", "config.restart_pending"}
    code, out, err = cli.run("config", "doctor", "--only", "no.such.check")
    assert (code, err) == (1, "")  # a refused request, not a failed check
    assert json.loads(out)["error"]["code"] == "SCHEMA_INVALID"


def test_doctor_covers_every_scope_and_takes_no_scope_selector(cli: Cli) -> None:
    code, out, err = cli.run("config", "doctor", "--scope", str(SCOPES["project"]))
    assert code == 2
    assert out == ""
    assert "--scope" in err
    code, out, err = cli.run("--scope", str(SCOPES["project"]), "config", "doctor")
    assert code != 0
    assert json.loads(out)["error"]["code"] == "SCHEMA_INVALID"


def test_write_get_explain_version_conflict_and_history(cli: Cli) -> None:
    entry = cli.result("set", ROUNDS, "4", "--expected-version", "0", "--reason", "deeper review")["entry"]
    assert entry["value"] == 4
    assert cli.result("get", ROUNDS)["value"] == 4
    report = cli.result("explain", ROUNDS, PROFILE, "--detail", "value")
    assert {k["key"] for k in report["keys"]} == {ROUNDS, PROFILE}
    assert all(k["contributions"] == [] for k in report["keys"])
    code, out, err = cli.run("config", "set", ROUNDS, "3", "--expect-version", "0")
    assert (code, err) == (6, "")
    assert json.loads(out)["error"]["code"] == "VERSION_CONFLICT"
    history = cli.result("history", ROUNDS)
    assert len(history["items"]) == 1
    assert history["items"][0]["reason"] == "deeper review"


def test_explain_no_all_hides_keys_that_only_have_a_default(cli: Cli) -> None:
    cli.result("set", ROUNDS, "4")
    every = {k["key"] for k in cli.result("explain", ROUNDS, PROFILE)["keys"]}
    assert every == {ROUNDS, PROFILE}
    assert {k["key"] for k in cli.result("explain", ROUNDS, PROFILE, "--no-all")["keys"]} == {ROUNDS}
    # The last of --all/--no-all wins.
    assert {k["key"] for k in cli.result("explain", ROUNDS, PROFILE, "--no-all", "--all")["keys"]} == every


def test_unselected_optional_members_are_omitted_not_sent_as_null(cli: Cli) -> None:
    """``keys``, ``section``, ``key``, ``after`` and ``key_prefix`` are optional but not nullable."""
    cli.result("set", ROUNDS, "4")  # expected_row_version and locked are nullable: an unset one stays null
    assert any(k["key"] == ROUNDS for k in cli.result("explain")["keys"])
    assert cli.result("schema")["sections"]
    assert [h["key"] for h in cli.result("history")["items"]] == [ROUNDS]
    assert [e["key"] for e in cli.result("entries")["items"]] == [ROUNDS]
    assert cli.result("entries", "--prefix", "execution.review")["items"]


def test_unset_resets_and_remove_reveals_inheritance(cli: Cli) -> None:
    project = f"project:{SCOPES['project']}"
    cli.result("set", PROFILE, "quick-fix")
    cli.result("set", PROFILE, "reviewed-development", "--scope", project)
    cli.result("unset", PROFILE, "--scope", project)
    assert cli.result("entries", "--scope", project)["items"][0]["op"] == "unset"
    cli.result("remove", PROFILE, "--scope", project)
    assert cli.result("get", PROFILE, "--scope", project)["value"] == "quick-fix"
    assert cli.result("entries", "--scope", project)["items"] == []


def test_locks_narrowing_and_scope_rules_stay_with_facade(cli: Cli) -> None:
    cli.result("set", ROUNDS, "4", "--lock")
    project = f"project:{SCOPES['project']}"
    code, out, _ = cli.run("config", "set", ROUNDS, "2", "--scope", project)
    assert code == 6
    assert json.loads(out)["error"]["code"] == "CONFIG_LOCKED"
    cli.result("unlock", ROUNDS)
    code, out, _ = cli.run("config", "set", ROUNDS, "5", "--scope", project)
    assert code == 1
    assert json.loads(out)["error"]["code"] == "CONFIG_NARROWING_VIOLATION"
    cli.result("lock", ROUNDS)
    code, out, _ = cli.run("config", "set", "worker.capacity", "4", "--scope", project)
    assert code == 1
    assert json.loads(out)["error"]["code"] == "CONFIG_SCOPE_NOT_ALLOWED"


@pytest.mark.parametrize(
    ("key", "text", "value"),
    [
        (ROUNDS, "+4", 4),
        ("execution.autopilot.enabled", "off", False),
        ("execution.consilium.members", "codex,claude_code", ["codex", "claude_code"]),
        ("execution.integration.branch", "true", "true"),
    ],
)
def test_text_values_follow_owner_types(cli: Cli, key: str, text: str, value: Any) -> None:
    assert cli.result("set", key, text)["entry"]["value"] == value


@pytest.mark.parametrize("value", ["true", "1.5", "NaN", '["4"]'])
def test_bad_typed_text_never_writes(cli: Cli, value: str) -> None:
    code, out, _ = cli.run("config", "set", ROUNDS, value)
    assert code == 1
    assert json.loads(out)["error"]["code"] == "CONFIG_INVALID"
    assert cli.result("entries")["items"] == []


@pytest.mark.parametrize("value", ["0", "11", "-1"])
def test_out_of_range_values_are_refused_by_the_key_schema(cli: Cli, value: str) -> None:
    # set reads only the owning section's schema; the facade still validates against the full key schema.
    code, out, _ = cli.run("config", "set", ROUNDS, value)
    assert code == 1
    assert json.loads(out)["error"]["code"] == "CONFIG_INVALID"
    assert cli.result("entries")["items"] == []


@pytest.mark.parametrize("key", ["execution.typo", "nosuch.section.key", "execution", "execution.review"])
def test_set_of_an_unknown_key_or_a_bare_section_is_unknown(cli: Cli, key: str) -> None:
    code, out, _ = cli.run("config", "set", key, "1")
    assert code == 1
    error = json.loads(out)["error"]
    assert (error["code"], error["details"]) == ("CONFIG_UNKNOWN_KEY", {"key": key})
    assert cli.result("entries")["items"] == []


def test_set_with_too_many_key_segments_checks_permission_once(cli: Cli) -> None:
    key = "execution" + ".typo" * 64
    code, out, _ = cli.run("config", "set", key, "1")
    assert code == 1
    assert json.loads(out)["error"]["code"] == "CONFIG_UNKNOWN_KEY"
    assert len([call for call in cli.authorizer.calls if call.permission == "config.read"]) == 1


class _SectionClient:
    """Answers get_schema per section like the facade: an unknown section is CONFIG_UNKNOWN_KEY."""

    def __init__(self, sections: dict[str, JsonObject]) -> None:
        self.sections = sections
        self.asked: list[str] = []

    def ask(self, query: GetSchema) -> GetSchemaView:
        section = query.section
        assert section is not None, "set must never ask for the whole catalog"
        self.asked.append(section)
        if section not in self.sections:
            raise ValidationFailed(
                ErrorCode.CONFIG_UNKNOWN_KEY,
                f"unknown settings section {section!r}",
                details={"section": section},
            )
        return GetSchemaView.from_json(
            {"registry_digest": "sha256:" + "0" * 64, "sections": [self.sections[section]]}
        )


def _fake_section(template: JsonObject, section_id: str, *keys: str) -> JsonObject:
    key_template = cast("list[JsonObject]", template["keys"])[0]
    return {
        **template,
        "id": section_id,
        "keys": [{**key_template, "key": key, "section": section_id} for key in keys],
    }


def _resolve(cli: Cli, sections: dict[str, JsonObject], key: str) -> tuple[KeySpec, list[str]]:
    client = _SectionClient(sections)
    spec = config_command._key_spec(cast("Any", SimpleNamespace(client=client)), key, {"level": "instance"})
    return spec, client.asked


def test_a_dotted_plugin_section_owns_its_keys_beside_its_parent_section(cli: Cli) -> None:
    template = cli.result("schema", "execution")["sections"][0]
    sections = {
        "plugins": _fake_section(template, "plugins", "plugins.enabled"),
        "plugins.acme": _fake_section(template, "plugins.acme", "plugins.acme.depth"),
    }
    spec, asked = _resolve(cli, sections, "plugins.acme.depth")
    assert (spec.key, spec.section) == ("plugins.acme.depth", "plugins.acme")
    assert asked == ["plugins", "plugins.acme"]
    assert _resolve(cli, sections, "plugins.enabled")[0].section == "plugins"
    with pytest.raises(ValidationFailed) as unknown:
        _resolve(cli, sections, "plugins.acme.width")
    assert unknown.value.code is ErrorCode.CONFIG_UNKNOWN_KEY


def test_a_key_claimed_by_two_sections_is_an_error_not_a_pick(cli: Cli) -> None:
    template = cli.result("schema", "execution")["sections"][0]
    sections = {
        "plugins": _fake_section(template, "plugins", "plugins.acme.depth"),
        "plugins.acme": _fake_section(template, "plugins.acme", "plugins.acme.depth"),
    }
    with pytest.raises(InternalError) as caught:
        _resolve(cli, sections, "plugins.acme.depth")
    assert caught.value.details == {"key": "plugins.acme.depth", "sections": ["plugins", "plugins.acme"]}


def test_global_and_local_scope_saved_context_and_host_chain(cli: Cli, tmp_path: Path) -> None:
    cli.result("set", ROUNDS, "4")
    project = f"project:{SCOPES['project']}"
    cli.result("set", ROUNDS, "3", "--scope", project)
    code, out, _ = cli.run("--scope", project, "config", "get", ROUNDS)
    assert code == 0
    assert json.loads(out)["result"]["value"] == 3
    (tmp_path / "cli-context.json").write_text(
        json.dumps(
            {
                "schema": "urn:skm:cli:context:v1",
                "instance_id": str(cli.app.instance_id),
                "project_id": str(SCOPES["project"]),
            }
        )
    )
    code, out, _ = cli.run("config", "get", ROUNDS, state_dir=tmp_path)
    assert code == 0
    assert json.loads(out)["result"]["value"] == 3
    cli.result("set", "logging.level", "debug", "--scope", f"host:{SCOPES['host']}")
    assert cli.result("get", "logging.level", "--scope", f"host:{SCOPES['host']}")["value"] == "debug"
    code, out, _ = cli.run("config", "get", ROUNDS, "--scope", "project:skm")
    assert code == 6
    assert json.loads(out)["error"]["code"] == "CAPABILITY_UNAVAILABLE"


def test_import_dry_run_apply_replace_export_and_digest(cli: Cli, tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[execution.review]\nmax_rounds = 4\n")
    dry = cli.result("import", str(path), "--dry-run")
    assert dry["dry_run"]
    assert not dry["applied"]
    assert cli.result("entries")["items"] == []
    assert cli.result("import", str(path), "--expect-digest", dry["entries_digest_before"])["applied"]
    exported = cli.result("export", "--format", "json")
    json_path = tmp_path / "config.json"
    json_path.write_text(json.dumps(exported["document"]))
    assert cli.result("import", str(json_path))["changes"][0]["change"] == "unchanged"
    code, out, _ = cli.run("config", "export", json_mode=False)
    assert code == 0
    assert tomllib.loads(out)["execution"]["review.max_rounds"] == 4
    path.write_text('[execution.workflow]\nprofile = "quick-fix"\n')
    assert cli.result("import", str(path), "--replace")["applied"]
    assert [e["key"] for e in cli.result("entries")["items"]] == [PROFILE]
    code, out, _ = cli.run("config", "import", str(path), "--expect-digest", dry["entries_digest_before"])
    assert code == 6
    assert json.loads(out)["error"]["code"] == "VERSION_CONFLICT"


def test_bad_imports_and_dry_run_problems_are_explicit(cli: Cli, tmp_path: Path) -> None:
    for name, text in (
        ("config.yaml", "x"),
        ("config.json", "[]"),
        ("config.json", "{"),
        ("config.toml", "x" * (1024 * 1024 + 1)),
    ):
        path = tmp_path / name
        path.write_text(text)
        code, out, _ = cli.run("config", "import", str(path))
        assert code == 1
        assert json.loads(out)["error"]["code"] == "CONFIG_INVALID"
    path = tmp_path / "unknown.toml"
    path.write_text("[execution]\nunknown = true\n")
    code, out, _ = cli.run("config", "import", str(path), "--dry-run")
    assert code == 1
    assert json.loads(out)["result"]["problems"]
    assert cli.result("entries")["items"] == []


def test_schema_filter_and_entries_pagination(cli: Cli) -> None:
    schema = cli.result("schema", "execution", "--key", ROUNDS)
    assert [k["key"] for s in schema["sections"] for k in s["keys"]] == [ROUNDS]
    code, out, _ = cli.run("config", "schema", "--key", "execution.typo")
    assert code == 1
    assert json.loads(out)["error"]["code"] == "CONFIG_UNKNOWN_KEY"
    cli.result("set", ROUNDS, "4")
    cli.result("set", PROFILE, "quick-fix")
    first = cli.result("entries", "--prefix", "execution.", "--limit", "1")
    second = cli.result("entries", "--after", first["next"], "--limit", "1")
    assert first["items"][0]["key"] != second["items"][0]["key"]


def test_permissions_and_confirmation_cannot_be_bypassed(cli: Cli) -> None:
    cli.authorizer.allowed = {"config.read"}
    code, out, _ = cli.run("config", "set", ROUNDS, "4", "--yes")
    assert code == 5
    assert json.loads(out)["error"]["code"] == "FORBIDDEN"
    cli.authorizer.allow_all()
    code, out, _ = cli.run("config", "set", "execution.kill_switch", "true")
    assert code == 6
    assert json.loads(out)["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert cli.result("set", "execution.kill_switch", "true", "--yes")["entry"]["value"] is True


def test_human_raw_export_and_json_keep_the_safe_output_boundary(cli: Cli) -> None:
    text = "branch\x1b[31m\nforged\u202eQ7"
    cli.result("set", "context.rules.extra", json.dumps([text]))
    for args in (
        ("get", "context.rules.extra"),
        ("get", "context.rules.extra", "--raw"),
        ("explain", "context.rules.extra"),
        ("export",),
        ("entries",),
        ("history",),
    ):
        code, out, err = cli.run("--as-token", "Q7", "config", *args, json_mode=False)
        assert code == 0, err
        assert "\x1b" not in out + err
        assert "\u202e" not in out + err
        assert "Q7" not in out + err
        assert "\nforged" not in out
        code, out, err = cli.run("--as-token", "Q7", "config", *args)
        assert code == 0, err
        assert json.loads(out)["ok"] is True
        assert len(out.splitlines()) == 1
        assert "Q7" not in out + err


@pytest.mark.parametrize(
    "char", ["\u0080", "\u0085", "\u009b", "\x7f", "\x1b", "\n", chr(0x202E), chr(0x2028)]
)
def test_plain_exports_and_raw_get_stay_valid_documents(cli: Cli, tmp_path: Path, char: str) -> None:
    value = [f"A{char}B"]
    cli.result("set", "context.rules.extra", json.dumps(value))
    history = cli.result("history")["items"]
    code, out, err = cli.run("config", "get", "context.rules.extra", "--raw", json_mode=False)
    assert (code, err) == (0, "")
    assert json.loads(out) == value
    for fmt in ("json", "toml"):
        code, out, err = cli.run("config", "export", "--format", fmt, json_mode=False)
        assert (code, err) == (0, "")
        assert f"A{char}B" not in out
        assert "\\x" not in out
        if fmt == "json":
            assert json.loads(out)["context"]["rules"]["extra"] == value
        else:
            assert tomllib.loads(out)["context"]["rules.extra"] == value
        path = tmp_path / f"export.{fmt}"
        path.write_text(out, encoding="utf-8")
        assert [c["change"] for c in cli.result("import", str(path))["changes"]] == ["unchanged"]
    envelope = cli.result("export", "--format", "json")["document"]
    path = tmp_path / "envelope.json"
    path.write_text(json.dumps(envelope), encoding="utf-8")
    assert [c["change"] for c in cli.result("import", str(path))["changes"]] == ["unchanged"]
    assert cli.result("history")["items"] == history


@pytest.mark.parametrize(
    "text",
    [
        '{"execution":{"review":{"max_rounds":NaN}}}',
        '{"execution":{"review":{"max_rounds":Infinity}}}',
        '{"execution":{"review":{"max_rounds":-Infinity}}}',
        '{"execution":{"review":{"max_rounds":1e999}}}',
        # Deep enough that parsing or the request DTO copy cannot recurse through it.
        *('{"execution":' + "[" * depth + "0" + "]" * depth + "}" for depth in (2000, 990)),
    ],
)
@pytest.mark.parametrize("dry_run", [False, True])
def test_non_json_numbers_and_deep_documents_are_invalid_not_internal(
    cli: Cli, tmp_path: Path, text: str, dry_run: bool
) -> None:
    path = tmp_path / "config.json"
    path.write_text(text)
    for json_mode in (True, False):
        code, out, err = cli.run(
            "config", "import", str(path), *(["--dry-run"] if dry_run else []), json_mode=json_mode
        )
        assert code == 1
        assert "INTERNAL_ERROR" not in out + err
        if json_mode:
            assert json.loads(out)["error"]["code"] == "CONFIG_INVALID"
        else:
            assert "CONFIG_INVALID" in err
    assert cli.result("entries")["items"] == []
    assert cli.result("history")["items"] == []


@pytest.mark.parametrize("depth", [63, 64, 65, 100, 300])
def test_no_cli_nesting_limit_the_facade_judges_deep_input(cli: Cli, tmp_path: Path, depth: int) -> None:
    # No owner contract bounds nesting: the facade, not the CLI, decides on the value and the document.
    key = "context.rules.extra"
    code, out, err = cli.run("config", "set", key, "[" * depth + "]" * depth)
    assert code == 1, err
    error = json.loads(out)["error"]
    assert error["code"] == "CONFIG_INVALID"
    assert error["details"]["key"] == key
    assert error["details"]["issues"]  # the key's value schema, never a CLI depth refusal
    assert "too_deep" not in out
    path = tmp_path / "config.json"
    path.write_text('{"context":{"rules":{"extra":' + "[" * depth + "]" * depth + "}}}")
    code, out, _ = cli.run("config", "import", str(path), "--dry-run")
    assert code == 1
    assert [p["key"] for p in json.loads(out)["result"]["problems"]] == [key]
    code, out, _ = cli.run("config", "import", str(path))
    assert code == 1
    assert json.loads(out)["error"]["code"] == "CONFIG_INVALID"
    assert "too_deep" not in out
    assert cli.result("entries")["items"] == []


@pytest.mark.parametrize("depth", [490, 600])
@pytest.mark.parametrize("leaf", ["", "0.5"])
def test_deep_input_past_the_bus_request_digest_fails_without_writing(
    cli: Cli, tmp_path: Path, depth: int, leaf: str
) -> None:
    # Both digest forms must report recursion as validation, without imposing a CLI nesting limit.
    value = "[" * depth + leaf + "]" * depth
    path = tmp_path / "config.json"
    path.write_text('{"context":{"rules":{"extra":' + value + "}}}")
    for args in (
        ("set", "context.rules.extra", value),
        ("import", str(path)),
        ("import", str(path), "--dry-run"),
    ):
        for json_mode in (True, False):
            code, out, err = cli.run("config", *args, json_mode=json_mode)
            assert code == 1
            reported = err.splitlines()[-1] if err else ""
            assert "INTERNAL_ERROR" not in out + err
            if json_mode:
                assert json.loads(out)["error"]["code"] in {"CONFIG_INVALID", "SCHEMA_INVALID"}
            else:
                assert reported.startswith(("error: CONFIG_INVALID", "error: SCHEMA_INVALID"))
            assert "Traceback" not in out + err
            assert "[[[[" not in out + err
    assert cli.result("entries")["items"] == []
    assert cli.result("history")["items"] == []


def test_set_reads_key_metadata_with_config_read_in_the_target_scope(cli: Cli) -> None:
    project = f"project:{SCOPES['project']}"
    decide, readable = cli.authorizer.authorize, {SCOPES["project"]}

    def authorize(uow: Any, actor: Any, permission: str, chain: Any) -> AuthzDecision:
        decision = decide(uow, actor, permission, chain)
        if permission == "config.read" and chain[-1].id not in readable:
            return AuthzDecision(allowed=False, reason_code="ROLE_LACKS_PERMISSION")
        return decision

    cli.authorizer.authorize = authorize
    assert cli.result("set", ROUNDS, "1", "--scope", project)["entry"]["value"] == 1
    reads = [call.scope_id for call in cli.authorizer.calls if call.permission == "config.read"]
    assert reads  # one read per candidate section; the instance right is never needed for a project write
    assert set(reads) == {SCOPES["project"]}
    # Without a scope the request still reads at instance, where this principal has no right.
    for args in (("set", ROUNDS, "2"), ("schema",), ("schema", "execution", "--key", ROUNDS)):
        code, out, _ = cli.run("config", *args)
        assert code == 5
        error = json.loads(out)["error"]
        assert (error["code"], error["details"]["permission"]) == ("FORBIDDEN", "config.read")
        assert "max_rounds" not in json.dumps(error["details"])
    # Refused before any metadata: an unknown key is FORBIDDEN, not CONFIG_UNKNOWN_KEY.
    readable.clear()
    for key in (ROUNDS, "execution.typo"):
        code, out, _ = cli.run("config", "set", key, "3", "--scope", project, "--yes")
        assert code == 5
        assert json.loads(out)["error"]["code"] == "FORBIDDEN"
    readable.update((SCOPES["project"], SCOPES["instance"]))
    assert [(e["key"], e["value"]) for e in cli.result("entries", "--scope", project)["items"]] == [
        (ROUNDS, 1)
    ]
    assert cli.result("entries")["items"] == []


def test_human_entries_and_history_are_tables_with_cursor(cli: Cli) -> None:
    cli.result("set", ROUNDS, "4", "--reason", "deeper review")
    cli.result("set", ROUNDS, "3")
    code, out, err = cli.run("config", "history", ROUNDS, json_mode=False)
    assert (code, err) == (0, "")
    lines = out.splitlines()
    assert lines[0].split() == ["at", "actor", "op", "key", "old", "→", "new", "reason"]
    assert "{" not in out
    assert lines[1].split()[2:] == ["updated", ROUNDS, "4", "→", "3"]
    assert lines[2].split()[2:] == ["created", ROUNDS, "—", "→", "4", "deeper", "review"]
    cli.result("set", PROFILE, "quick-fix")
    code, out, err = cli.run("config", "entries", "--limit", "1", json_mode=False)
    assert (code, err) == (0, "")
    lines = out.splitlines()
    assert lines[0].split() == ["key", "op", "value", "locked", "version", "updated", "reason"]
    assert lines[1].split()[:4] == [ROUNDS, "set", "3", "2"]
    cursor = cli.result("entries", "--limit", "1")["next"]
    assert lines[2] == f"next: {cursor} (use --after)"
    code, out, _ = cli.run("config", "entries", "--after", cursor, json_mode=False)
    assert code == 0
    assert out.splitlines()[1].split()[:4] == [PROFILE, "set", '"quick-fix"', "1"]
    assert len(out.splitlines()) == 2


def test_local_json_flag_and_raw_values(cli: Cli) -> None:
    code, out, _ = cli.run("config", "get", ROUNDS, "--json", json_mode=False)
    assert code == 0
    assert json.loads(out)["command"] == "settings.get_value"
    assert cli.run("config", "get", ROUNDS, "--raw", json_mode=False) == (0, "2\n", "")


@pytest.mark.parametrize("credential", ["key", "value", "scope", "instance", "default", "2"])
def test_credentials_matching_report_fields_do_not_break_human_explain(cli: Cli, credential: str) -> None:
    code, out, err = cli.run("--as-token", credential, "config", "explain", ROUNDS, json_mode=False)
    assert code == 0, err
    assert credential not in out
    assert "INTERNAL_ERROR" not in err


@pytest.mark.parametrize(
    "credential", ["locked_above", "above", "locked", "ignored", "winner", "reason", "level", "Q7"]
)
def test_credentials_matching_ignored_locked_contributions_keep_explain_layout(
    cli: Cli, credential: str
) -> None:
    project = f"project:{SCOPES['project']}"
    cli.result("set", ROUNDS, "1", "--scope", project)
    cli.result("set", ROUNDS, "2", "--lock")
    for json_mode in (False, True):
        code, out, err = cli.run(
            "--as-token", credential, "config", "explain", ROUNDS, "--scope", project, json_mode=json_mode
        )
        assert code == 0, err
        assert credential not in out + err
        assert "INTERNAL_ERROR" not in out + err
        if json_mode:
            contributions = json.loads(out)["result"]["keys"][0]["contributions"]
            assert len(contributions) > 1
        elif credential == "Q7":
            assert "ignored: locked above (instance)" in out


def test_secret_reference_round_trip_never_resolves_a_secret(
    cli: Cli, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def refused(*args: object, **kwargs: object) -> object:
        raise AssertionError("configuration CLI must never resolve secrets")

    monkeypatch.setattr(SecretResolver, "resolve", refused)
    key = "integrations.mcp.servers"
    value = {"fixture": {"command": "fixture", "env_refs": {"FIXTURE_KEY": "secret://env/FIXTURE_SECRET"}}}
    cli.result("set", key, json.dumps(value), "--yes")
    assert cli.result("get", key)["value"] == value
    report = cli.result("explain", key, "--show-secrets-refs")
    assert report["keys"][0]["value"] == value
    assert cli.result("export", "--format", "json")["document"]["integrations"]["mcp"]["servers"] == value
    for args in (("get", key), ("explain", key, "--show-secrets-refs"), ("entries",), ("history",)):
        code, out, _ = cli.run("config", *args, json_mode=False)
        assert code == 0
        assert "secret://env/FIXTURE_SECRET" in out
    for fmt in ("json", "toml"):
        code, out, _ = cli.run("config", "export", "--format", fmt, json_mode=False)
        assert code == 0
        assert "secret://env/FIXTURE_SECRET" in out
        path = tmp_path / f"export.{fmt}"
        path.write_text(out, encoding="utf-8")
        assert [c["change"] for c in cli.result("import", str(path))["changes"]] == ["unchanged"]
    bad = {"fixture": {"command": "fixture", "env_refs": {"FIXTURE_KEY": "plaintext"}}}
    code, out, _ = cli.run("config", "set", key, json.dumps(bad), "--yes")
    assert code == 1
    assert json.loads(out)["error"]["code"] == "CONFIG_INVALID"


def test_append_mode_uses_facade_and_confirmation_is_not_assumed(cli: Cli) -> None:
    key = "execution.generation.command"
    cli.result("set", key, '["python3"]', "--yes")
    result = cli.result("set", key, '["tools/gen.py"]', "--append", "--yes")
    assert result["entry"]["op"] == "append"
    assert "tools/gen.py" in result["effective"]["value"]
