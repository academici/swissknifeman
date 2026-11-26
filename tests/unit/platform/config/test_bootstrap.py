"""Bootstrap selection is an instance isolation boundary; pool checks consume a bound ProcessConfig."""

from dataclasses import replace
from pathlib import Path
from runpy import run_path
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ports_uow import Surface
from skm.platform.config.bootstrap import (
    apply_process_config,
    load_bootstrap,
    pool_capacity,
    validate_worker_host,
)
from skm.platform.config.effective import ProcessConfig
from skm.platform.config.keys import Chain, Level, Reload
from skm.platform.config.layers import Contribution, Layer, LayerRef
from skm.platform.config.resolver import resolve
from skm.platform.config.scopes import ScopeChain, ScopeRef
from skm.platform.config.secrets import SecretRef
from skm.platform.config.sources.defaults import defaults_layer

ROOT = Path(__file__).resolve().parents[4]
INSTANCE = UUID("0192f5c4-7a10-7c3e-9b1a-5d2f0e8a4c11")
HOST = UUID("0193aa10-0000-7000-8000-0000000000c1")


def example(name):
    return ROOT / "tests/fixtures/corpus/examples/config" / f"bootstrap.{name}.toml"


def local(tmp_path):
    return load_bootstrap(str(example("local")), {}, tmp_path)


@pytest.mark.parametrize("name", ["local", "profiles", "server"])
def test_v1_examples_materialize_and_keep_secrets_as_references(tmp_path, name):
    config = load_bootstrap(str(example(name)), {}, tmp_path)
    assert config.instance_id == INSTANCE
    assert config.access_mode == "embedded"
    assert isinstance(config.database_url, SecretRef)
    assert isinstance(config.token_pepper, SecretRef)
    assert config.database_pool_timeout_seconds == 10
    assert config.worktrees_root == config.state_dir / "worktrees"
    assert config.materialized_root == config.state_dir / "materialized"
    assert config.backups_root == config.state_dir / "backups"
    assert "secret://" not in repr(config)


@pytest.mark.parametrize(
    ("instance", "env", "cwd", "expected"),
    [
        ("personal", {"SKM_INSTANCE": "team"}, "team", "personal"),
        (None, {"SKM_INSTANCE": "team"}, "personal", "team"),
        (None, {}, "team", "team"),
        (None, {}, None, "personal"),
    ],
)
def test_instance_priority(tmp_path, instance, env, cwd, expected):
    config = load_bootstrap(str(example("profiles")), env, tmp_path, instance=instance, cwd_profile=cwd)
    assert config.instance_profile == expected
    assert config.profiles == ("personal", "team")
    assert config.state_dir == tmp_path / ".local/state/skm/instances" / expected
    assert config.blobs_root == tmp_path / ".local/share/skm/blobs" / expected
    if expected == "team":
        assert config.host_id == HOST
        assert config.api_credential == SecretRef.parse("secret://keyring/skm-team/cli-token")
        assert config.database_url is None
        assert config.token_pepper is None
    else:
        assert config.host_id == "auto"
        assert config.api_credential is None


@pytest.mark.parametrize("selector", ["cli", "env", "cwd", "default"])
def test_unknown_instance_never_falls_through(tmp_path, selector):
    path = example("profiles")
    if selector == "default":
        path = tmp_path / "bad-default.toml"
        path.write_text(
            example("profiles")
            .read_text()
            .replace('default_instance = "personal"', 'default_instance = "missing"'),
            encoding="utf-8",
        )
    with pytest.raises(NotFound) as caught:
        load_bootstrap(
            str(path),
            {"SKM_INSTANCE": "missing"} if selector == "env" else {},
            tmp_path,
            instance="missing" if selector == "cli" else None,
            cwd_profile="missing" if selector == "cwd" else None,
        )
    assert caught.value.code == "NOT_FOUND"
    assert caught.value.details == {
        "kind": "instance_profile",
        "name": "missing",
        "known": ["personal", "team"],
    }


def test_single_instance_env_selector_warns_and_is_ignored(tmp_path, caplog):
    config = load_bootstrap(str(example("local")), {"SKM_INSTANCE": "team"}, tmp_path)
    assert config.instance_profile is None
    assert "SKM_INSTANCE ignored" in caplog.text
    with pytest.raises(NotFound):
        load_bootstrap(str(example("local")), {}, tmp_path, instance="team")


def test_profile_specific_paths_and_environment_override(tmp_path):
    path = tmp_path / "profiles.toml"
    path.write_text(
        example("profiles")
        .read_text()
        .replace(
            "[instances.team]",
            '[instances.personal.paths]\nstate_dir="~/custom"\nblobs_root="${state_dir}/blobs"\n\n[instances.team]',
        ),
        encoding="utf-8",
    )
    config = load_bootstrap(str(path), {}, tmp_path)
    assert config.state_dir == tmp_path / "custom"
    assert config.blobs_root == tmp_path / "custom/blobs"
    env = {
        "SKM_STATE_DIR": "~/isolated",
        "SKM_HOST_ID": str(HOST),
        "SKM_DATABASE_URL": "postgresql://literal:secret@db/skm",
    }
    changed = load_bootstrap(str(path), env, tmp_path)
    assert changed.state_dir == tmp_path / "isolated"
    assert changed.blobs_root == changed.state_dir / "blobs"
    assert changed.worktrees_root == changed.state_dir / "worktrees"
    assert changed.database_url == env["SKM_DATABASE_URL"]
    assert changed.host_id == HOST
    assert "literal:secret" not in repr(changed)


@pytest.mark.parametrize("partial", ['blobs_root="~/shared-blobs"', 'worktrees_root="${state_dir}/jobs"', ""])
def test_partial_profile_paths_keep_state_isolated(tmp_path, partial):
    path = tmp_path / "profiles.toml"
    path.write_text(
        example("profiles")
        .read_text()
        .replace("[instances.team]", f"[instances.personal.paths]\n{partial}\n\n[instances.team]"),
        encoding="utf-8",
    )
    personal = load_bootstrap(str(path), {}, tmp_path, instance="personal")
    team = load_bootstrap(str(path), {}, tmp_path, instance="team")
    assert personal.state_dir == tmp_path / ".local/state/skm/instances/personal"
    assert team.state_dir == tmp_path / ".local/state/skm/instances/team"
    assert personal.state_dir / "host.json" != team.state_dir / "host.json"
    assert personal.state_dir / "cli-context.json" != team.state_dir / "cli-context.json"
    assert personal.state_dir / "secrets" != team.state_dir / "secrets"
    if partial.startswith("worktrees_root"):
        assert personal.worktrees_root == personal.state_dir / "jobs"
    if partial.startswith("blobs_root"):
        assert personal.blobs_root == tmp_path / "shared-blobs"


def test_single_instance_state_dir_does_not_gain_profile_suffix(tmp_path):
    config = local(tmp_path)
    assert config.state_dir == tmp_path / ".local/state/skm"


def test_search_order_uses_first_existing_file(tmp_path):
    cli, env, xdg, user = (tmp_path / name for name in ("cli.toml", "env.toml", "xdg", "user"))
    user_path = user / ".config/skm/bootstrap.toml"
    xdg_path = xdg / "skm/bootstrap.toml"
    for path in (cli, env, xdg_path, user_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(example("local").read_bytes())
    environ = {"SKM_BOOTSTRAP": str(env), "XDG_CONFIG_HOME": str(xdg)}
    assert load_bootstrap(str(cli), environ, user).source == str(cli)
    cli.unlink()
    assert load_bootstrap(str(cli), environ, user).source == str(env)
    env.unlink()
    assert load_bootstrap(None, environ, user).source == str(xdg_path)
    xdg_path.unlink()
    assert load_bootstrap(None, environ, user).source == str(user_path)


def test_invalid_first_file_does_not_fall_through_to_other_instance(tmp_path):
    path = tmp_path / "invalid.toml"
    path.write_text("schema = 'broken'", encoding="utf-8")
    with pytest.raises(ValidationFailed):
        load_bootstrap(str(path), {"SKM_BOOTSTRAP": str(example("local"))}, tmp_path)


def test_env_only_modes_and_missing_bootstrap(tmp_path, monkeypatch):
    # Isolate the machine-wide candidate without weakening product search behavior.
    original = Path.read_text

    def read(path, *args, **kwargs):
        if path == Path("/etc/skm/bootstrap.toml"):
            raise FileNotFoundError
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    with pytest.raises(PreconditionFailed, match="BOOTSTRAP_MISSING"):
        load_bootstrap(None, {}, tmp_path)
    config = load_bootstrap(None, {"SKM_DATABASE_URL": "postgresql://secret@db/skm"}, tmp_path)
    assert config.source == "env"
    assert config.instance_id is None
    assert config.database_url == "postgresql://secret@db/skm"
    config = load_bootstrap(
        None,
        {
            "SKM_API_ENDPOINT": "https://example.com/api/v1",
            "SKM_API_TOKEN": "literal",
            "SKM_INSTANCE_ID": str(INSTANCE),
        },
        tmp_path,
    )
    assert config.access_mode == "http"
    assert config.instance_id == INSTANCE
    assert config.api_credential == "literal"
    assert "literal" not in repr(config)


@pytest.mark.parametrize(
    "replacement",
    [
        ('schema = "urn:skm:config:bootstrap:v1"', 'schema = "urn:skm:config:bootstrap:v2"'),
        ('mode = "embedded"', 'mode = "invalid"'),
        ('id = "auto"', 'id = "invalid"'),
        ('url = "secret://env/SKM_DATABASE_URL"', 'url = "literal password"'),
        ('application_name = "skm"', "pool_min_size = -1"),
    ],
)
def test_schema_rejects_invalid_bootstrap_and_hides_raw_values(tmp_path, replacement):
    path = tmp_path / "bad.toml"
    path.write_text(example("local").read_text().replace(*replacement), encoding="utf-8")
    with pytest.raises(ValidationFailed) as caught:
        load_bootstrap(str(path), {}, tmp_path)
    assert caught.value.code == "CONFIG_INVALID"
    assert "literal password" not in str(caught.value.to_problem())


@pytest.mark.parametrize(
    "env",
    [
        {"SKM_HOST_ID": "invalid"},
        {"SKM_ACCESS_MODE": "invalid"},
        {"SKM_INSTANCE_ID": "invalid"},
        {"SKM_DATABASE_URL": ""},
    ],
)
def test_invalid_environment_is_validated_after_overrides(tmp_path, env):
    with pytest.raises(ValidationFailed):
        load_bootstrap(str(example("local")), env, tmp_path)


@pytest.mark.parametrize(("key", "value"), [("level", "debug"), ("format", "text")])
def test_logging_settings_are_rejected_in_bootstrap(tmp_path, key, value):
    path = tmp_path / "bootstrap.toml"
    path.write_text(example("local").read_text() + f'\n[logging]\n{key} = "{value}"\n', encoding="utf-8")
    with pytest.raises(ValidationFailed) as caught:
        load_bootstrap(str(path), {}, tmp_path)
    assert caught.value.code is ErrorCode.CONFIG_INVALID


def test_logging_environment_does_not_change_bootstrap(tmp_path):
    path = str(example("local"))
    assert load_bootstrap(path, {"SKM_LOG_LEVEL": "trace", "SKM_LOG_FORMAT": "invalid"}, tmp_path) == (
        load_bootstrap(path, {}, tmp_path)
    )


def test_profiles_cannot_inherit_root_credentials_or_host_identity(tmp_path):
    for extra in ('\n[host]\nid="auto"', '\n[database]\nurl="secret://env/DB"'):
        path = tmp_path / "mixed.toml"
        text = example("profiles").read_text()
        if extra.startswith("\n[host]"):
            text = text.replace('[host]\nname = "dev-laptop"', '[host]\nid = "auto"')
        else:
            text += extra
        path.write_text(text, encoding="utf-8")
        with pytest.raises(ValidationFailed):
            load_bootstrap(str(path), {}, tmp_path)


@pytest.mark.parametrize(
    ("surface", "values", "services", "minimum"),
    [
        (Surface.API, {"api.threadpool.size": 16}, ("scheduler", "relay"), 21),
        (Surface.BACKGROUND, {"api.threadpool.size": 2}, ("scheduler",), 6),
        (Surface.CLI, {}, (), 2),
        (Surface.HOOK, {}, (), 2),
        (Surface.MCP, {}, (), 2),
    ],
)
def test_pool_defaults_and_explicit_below_minimum(tmp_path, surface, values, services, minimum):
    config = local(tmp_path)
    process = ProcessConfig({}, values, 1, INSTANCE)
    applied = apply_process_config(config, process, surface=surface, enabled_background_services=services)
    assert applied.database_pool_max_size == minimum
    assert applied.instance_id == config.instance_id
    assert applied.host_id == config.host_id
    assert (
        pool_capacity(
            replace(config, database_pool_max_size=minimum),
            process,
            surface=surface,
            enabled_background_services=services,
        )
        == minimum
    )
    with pytest.raises(ValidationFailed) as caught:
        apply_process_config(
            replace(config, database_pool_max_size=minimum - 1),
            process,
            surface=surface,
            enabled_background_services=services,
        )
    assert caught.value.details == {"field": "database.pool_max_size", "minimum": minimum}


@pytest.fixture(scope="module")
def startup_registry():
    inputs = run_path(str(Path(__file__).with_name("test_registry_all_sections.py")))
    return inputs["real_registry"]()


def startup_configs(registry, *, capacity=None, instance_id=INSTANCE, host_id=HOST, generation=7):
    instance = ScopeRef(Level.INSTANCE, instance_id)
    host = ScopeRef(Level.HOST, host_id)
    instance_layer = Layer(LayerRef(Level.INSTANCE, instance_id), {})
    work = resolve(
        registry,
        ScopeChain(Chain.WORK, (instance,)),
        [defaults_layer(registry, Chain.WORK), instance_layer],
        generation=generation,
        pack_generation=0,
    )
    host_ref = LayerRef(Level.HOST, host_id)
    values = {} if capacity is None else {"worker.capacity": Contribution(host_ref, "set", capacity)}
    host_config = resolve(
        registry,
        ScopeChain(Chain.HOST, (instance, host)),
        [defaults_layer(registry, Chain.HOST), instance_layer, Layer(host_ref, values)],
        generation=generation,
        pack_generation=0,
    )
    return work, host_config


@pytest.mark.parametrize("helper", [pool_capacity, apply_process_config])
@pytest.mark.parametrize(("capacity", "minimum"), [(None, 6), (3, 8)])
@pytest.mark.parametrize("maximum_offset", [None, 0, -1])
def test_worker_pool_uses_live_capacity_from_captured_startup_host(
    tmp_path,
    startup_registry,
    helper,
    capacity,
    minimum,
    maximum_offset,
):
    work, host = startup_configs(startup_registry, capacity=capacity)
    assert startup_registry.spec("worker.capacity").reload is Reload.LIVE
    process = ProcessConfig.capture(work, host)
    assert "worker.capacity" not in process.host
    config = replace(
        local(tmp_path),
        host_id=HOST,
        database_pool_max_size=None if maximum_offset is None else minimum + maximum_offset,
    )
    if maximum_offset == -1:
        with pytest.raises(ValidationFailed) as caught:
            helper(config, process, surface=Surface.WORKER, startup_host=host)
        assert caught.value.code == "CONFIG_INVALID"
        assert caught.value.details == {"field": "database.pool_max_size", "minimum": minimum}
    else:
        result = helper(config, process, surface=Surface.WORKER, startup_host=host)
        if helper is pool_capacity:
            assert result == minimum
        else:
            assert result.database_pool_max_size == minimum
            assert result.instance_id == config.instance_id
            assert result.host_id == config.host_id


@pytest.mark.parametrize("helper", [pool_capacity, apply_process_config])
@pytest.mark.parametrize("mismatch", ["instance", "host", "generation", "chain", "missing"])
def test_worker_startup_host_must_match_process_snapshot(tmp_path, startup_registry, helper, mismatch):
    work, host = startup_configs(startup_registry)
    process = ProcessConfig.capture(work, host)
    if mismatch == "instance":
        _, candidate = startup_configs(startup_registry, instance_id=UUID(int=1))
    elif mismatch == "host":
        _, candidate = startup_configs(startup_registry, host_id=UUID(int=2))
    elif mismatch == "generation":
        _, candidate = startup_configs(startup_registry, generation=8)
    else:
        candidate = work if mismatch == "chain" else None
    with pytest.raises(ValidationFailed) as caught:
        helper(
            replace(local(tmp_path), host_id=HOST), process, surface=Surface.WORKER, startup_host=candidate
        )
    assert caught.value.code == "CONFIG_INVALID"


@pytest.mark.parametrize("helper", [pool_capacity, apply_process_config])
def test_worker_capacity_still_requires_a_schema_valid_effective_value(tmp_path, startup_registry, helper):
    work, host = startup_configs(startup_registry, capacity=65)
    process = ProcessConfig.capture(work, host)
    with pytest.raises(ValidationFailed, match="CONFIG_INVALID"):
        helper(replace(local(tmp_path), host_id=HOST), process, surface=Surface.WORKER, startup_host=host)


def test_process_identity_and_missing_values_fail_closed(tmp_path):
    config = replace(local(tmp_path), host_id=HOST)
    for process in (
        ProcessConfig({}, {}, 1),
        ProcessConfig({}, {}, 1, UUID(int=1)),
        ProcessConfig({}, {}, 1, INSTANCE, ScopeRef(Level.HOST, UUID(int=2))),
    ):
        with pytest.raises(ValidationFailed):
            apply_process_config(config, process, surface=Surface.CLI)
    with pytest.raises(ValidationFailed):
        pool_capacity(config, ProcessConfig({}, {}, 1, INSTANCE), surface=Surface.API)
    with pytest.raises(ValidationFailed):
        pool_capacity(
            replace(config, database_pool_min_size=3), ProcessConfig({}, {}, 1, INSTANCE), surface=Surface.CLI
        )
    process = ProcessConfig({}, {}, 1, INSTANCE, ScopeRef(Level.HOST, HOST))
    assert (
        apply_process_config(replace(config, instance_id=None), process, surface=Surface.CLI).instance_id
        == INSTANCE
    )


@pytest.mark.parametrize("mode", ["embedded", "http"])
def test_cli_auto_host_snapshot_uses_recorded_host_identity(tmp_path, mode):
    config = replace(local(tmp_path), access_mode=mode)
    config.state_dir.mkdir(parents=True)
    host_file = config.state_dir / "host.json"
    host_file.write_text('{"host_id": "' + str(HOST) + '"}', encoding="utf-8")
    process = ProcessConfig({}, {}, 1, INSTANCE, ScopeRef(Level.HOST, HOST))
    applied = apply_process_config(config, process, surface=Surface.CLI)
    assert applied.host_id == HOST
    assert pool_capacity(config, process, surface=Surface.CLI) == 2
    assert host_file.exists()
    with pytest.raises(ValidationFailed) as caught:
        apply_process_config(
            config, ProcessConfig({}, {}, 1, INSTANCE, ScopeRef(Level.HOST, UUID(int=2))), surface=Surface.CLI
        )
    assert caught.value.details["reason"] == "process_identity_mismatch"
    host_file.write_text('{"host_id": "invalid"}', encoding="utf-8")
    with pytest.raises(ValidationFailed) as caught:
        apply_process_config(config, process, surface=Surface.CLI)
    assert caught.value.details["reason"] == "host_state_invalid"
    host_file.unlink()
    with pytest.raises(PreconditionFailed) as caught:
        apply_process_config(config, process, surface=Surface.CLI)
    assert caught.value.details["reason"] == "host_not_registered"


def test_http_worker_auto_without_recorded_host_rejected_for_process_snapshot(tmp_path):
    config = replace(local(tmp_path), access_mode="http")
    process = ProcessConfig({}, {}, 1, INSTANCE, ScopeRef(Level.HOST, HOST))
    with pytest.raises(ValidationFailed) as caught:
        apply_process_config(config, process, surface=Surface.WORKER)
    assert caught.value.details["reason"] == "auto_forbidden_in_http"
    config.state_dir.mkdir(parents=True)
    (config.state_dir / "host.json").write_text('{"host_id": "' + str(HOST) + '"}', encoding="utf-8")
    assert apply_process_config(config, process, surface=Surface.WORKER).host_id == HOST


@pytest.mark.parametrize(
    ("mode", "surface", "code", "reason"),
    [
        ("http", Surface.WORKER, "CONFIG_INVALID", "auto_forbidden_in_http"),
        ("embedded", Surface.WORKER, "INVALID_TRANSITION", "host_not_registered"),
        ("http", Surface.HOOK, "INVALID_TRANSITION", "host_not_registered"),
    ],
)
def test_worker_and_hook_never_register_auto_host(tmp_path, mode, surface, code, reason):
    config = replace(local(tmp_path), access_mode=mode)
    with pytest.raises((ValidationFailed, PreconditionFailed)) as caught:
        validate_worker_host(config, surface=surface)
    assert caught.value.code == code
    assert caught.value.details["reason"] == reason
    config.state_dir.mkdir(parents=True)
    (config.state_dir / "host.json").write_text('{"host_id": "' + str(HOST) + '"}', encoding="utf-8")
    assert validate_worker_host(config, surface=surface).host_id == HOST
    assert validate_worker_host(config, surface=Surface.CLI).host_id == "auto"


def test_http_worker_concrete_host_and_invalid_host_state(tmp_path):
    team = load_bootstrap(str(example("profiles")), {}, tmp_path, instance="team")
    assert validate_worker_host(team) == team
    assert (
        apply_process_config(
            team,
            ProcessConfig({}, {}, 1, team.instance_id, ScopeRef(Level.HOST, HOST)),
            surface=Surface.WORKER,
        )
        == team
    )
    config = local(tmp_path)
    config.state_dir.mkdir(parents=True)
    (config.state_dir / "host.json").write_text('{"host_id": "bad"}', encoding="utf-8")
    with pytest.raises(ValidationFailed) as caught:
        validate_worker_host(config)
    assert caught.value.details["reason"] == "host_state_invalid"


def test_fast_bootstrap_validator_matches_json_schema_registry():
    from typing import Any, cast

    from skm.platform.config.bootstrap import _URN, _validate
    from skm.platform.config.sources.document import decode_document
    from skm.platform.schema.registry import SchemaRegistry

    schemas = SchemaRegistry.load_default()
    for name in ("local", "profiles", "server"):
        doc = decode_document(example(name).read_text(encoding="utf-8"), "toml")
        assert schemas.validate(_URN, doc) == ()
        _validate(doc)

    base = cast("dict[str, Any]", decode_document(example("local").read_text(encoding="utf-8"), "toml"))
    db_base = cast("dict[str, Any]", base["database"])
    invalid_docs: list[dict[str, Any]] = [
        {**base, "unknown_key": 1},
        {**base, "database": {**db_base, "migrate_on_start": "yes"}},
        {**base, "database": {**db_base, "pool_max_size": 0}},
        {**base, "database": {**db_base, "pool_timeout_seconds": True}},
        {**base, "access": {"mode": "http"}},
        {**base, "api": {"endpoint": "http://localhost:8000/bad", "credential": "secret://env/TOK"}},
        {
            **base,
            "api": {
                "endpoint": "http://localhost:8000/api/v1",
                "credential": "secret://env/TOK",
                "timeout_seconds": 0,
            },
        },
        {
            **base,
            "instances": {
                "dev": {"instance_id": str(INSTANCE), "access": {"mode": "embedded"}, "database": db_base}
            },
            "default_instance": "dev",
        },
    ]
    for bad in invalid_docs:
        assert schemas.validate(_URN, bad) != ()
        with pytest.raises(ValidationFailed):
            _validate(bad)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("state_dir", "state_dir"),
        ("blobs_root", "blobs_root"),
        ("blobs_root", "state_dir"),
    ],
)
@pytest.mark.parametrize("suffix", ["", "/nested"])
@pytest.mark.parametrize("alias", [False, True])
def test_profile_roots_cannot_overlap(tmp_path, left, right, suffix, alias):
    root = tmp_path / "root"
    root.mkdir()
    link = tmp_path / "alias"
    link.symlink_to(root, target_is_directory=True)
    path = tmp_path / "profiles.toml"
    doc = (
        example("profiles")
        .read_text()
        .replace("[instances.team]", f'[instances.personal.paths]\n{left}="{root}/future"\n[instances.team]')
    )
    path.write_text(doc + f'\n[instances.team.paths]\n{right}="{link if alias else root}/future{suffix}"\n')
    with pytest.raises(ValidationFailed) as caught:
        load_bootstrap(str(path), {}, tmp_path)
    assert caught.value.code is ErrorCode.CONFIG_INVALID


def test_profile_state_and_blobs_cannot_be_equal(tmp_path):
    path = tmp_path / "profiles.toml"
    path.write_text(
        example("profiles").read_text()
        + '\n[instances.team.paths]\nstate_dir="~/root"\nblobs_root="${state_dir}"\n'
    )
    with pytest.raises(ValidationFailed) as caught:
        load_bootstrap(str(path), {}, tmp_path)
    assert caught.value.code is ErrorCode.CONFIG_INVALID


def test_machine_database_and_identity_are_shared_across_profiles(tmp_path: Path) -> None:
    path = tmp_path / "bootstrap.toml"
    installation = "0193aa10-0000-7000-8000-0000000000c2"
    source = example("profiles").read_text(encoding="utf-8")
    source = source.replace(
        'default_instance = "personal"',
        f'default_instance = "personal"\ninstallation_id = "{installation}"',
    )
    source += (
        '\n[machine_database]\nurl = "secret://env/HOST_DB"\nmigrator_url = "secret://file/host-migrate"\n'
    )
    path.write_text(source, encoding="utf-8")
    for name in ("personal", "team"):
        config = load_bootstrap(str(path), {}, tmp_path, instance=name)
        assert config.installation_id == UUID(installation)
        assert config.machine_database_url == SecretRef.parse("secret://env/HOST_DB")
        assert config.machine_database_migrator_url == SecretRef.parse("secret://file/host-migrate")
        assert config.database_url != config.machine_database_url
        assert "secret://" not in repr(config)
    overridden = load_bootstrap(
        str(path), {"SKM_MACHINE_DATABASE_URL": "postgresql://host-test"}, tmp_path, instance="team"
    )
    assert overridden.machine_database_url == SecretRef.parse("secret://env/SKM_MACHINE_DATABASE_URL")
    assert "postgresql://" not in repr(overridden)
    assert overridden.database_url is None


def test_machine_database_rejects_literal_config_credentials(tmp_path: Path) -> None:
    path = tmp_path / "bootstrap.toml"
    text = example("local").read_text(encoding="utf-8")
    path.write_text(text + '\n[machine_database]\nurl = "postgresql://host-test"\n', encoding="utf-8")
    with pytest.raises(ValidationFailed) as caught:
        load_bootstrap(str(path), {}, tmp_path)
    assert caught.value.details["issues"] == [{"pointer": "/machine_database/url", "code": "pattern"}]
    assert "postgresql://" not in str(caught.value)
