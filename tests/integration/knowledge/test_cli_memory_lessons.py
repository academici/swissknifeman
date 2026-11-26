"""Exercise all knowledge CLI verbs against a composed bus in both output modes."""

import json
from io import StringIO
from pathlib import Path

import pytest

from contracts.execution.harness import PEPPER, ExecSide, exec_side
from contracts.knowledge.harness import KnowledgeSide, knowledge_side
from contracts.knowledge.test_lessons import _promote
from skm.entrypoints.cli.main import Backend, main
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import CreateToken, CreateTokenResult
from skm.modules.settings.public import SetValue
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "exec_side", "knowledge_side", "pg_session", "test_database"]


@pytest.mark.parametrize("knowledge_side", ["memory"], indirect=True)
@pytest.mark.parametrize("json_mode", [True, False])
def test_memory_and_lessons(knowledge_side: KnowledgeSide, json_mode: bool) -> None:
    side = knowledge_side
    client = side.app.client(actor=side.owner, surface=Surface.CLI)

    def invoke(group: str, verb: str, *args: str) -> str:
        out, err = StringIO(), StringIO()
        scope = (
            ["--project", str(side.project)] if group == "memory" else ["--workspace", str(side.workspace)]
        )
        code = main(
            [group, verb, *args, *scope, *(["--json"] if json_mode else [])],
            stdout=out,
            stderr=err,
            environ={"HOME": "/unused"},
            backend=lambda *_: Backend(client, instance_id=side.app.instance_id),
        )
        assert code == 0, out.getvalue() + err.getvalue()
        if json_mode:
            envelope = json.loads(out.getvalue())
            assert envelope["ok"]
            return json.dumps(envelope["result"])
        return out.getvalue()

    assert "entry_id" in invoke("memory", "remember", "Pool unavailable", "--key", "active_handoff")
    assert "Pool unavailable" in invoke("memory", "search", "Pool")
    assert "Pool unavailable" in invoke("memory", "list", "--all")
    assert "forgotten" in invoke("memory", "forget", "--handoff")
    entry = side.remember(body="Pool recovered")["entry_id"]
    assert "forgotten" in invoke("memory", "forget", entry, "--scope", "project")
    assert "Pool recovered" not in invoke("memory", "search", "recovered")
    lesson = str(_promote(side, "Wait for the pool"))
    assert "Wait for the pool" in invoke("lessons", "list", "--all")
    shown = invoke("lessons", "show", lesson)
    assert ("confidence" if json_mode else "source association") in shown
    assert "applicability" in shown
    assert "deprecated" in invoke(
        "lessons", "deprecate", lesson, "--reason", "Replaced", "--expected-version", "1", "--yes"
    )


@pytest.mark.parametrize("exec_side", [pytest.param("postgres", marks=pytest.mark.pg)], indirect=True)
def test_disabled_groups_use_the_selected_instance(exec_side: ExecSide, tmp_path: Path) -> None:
    exec_side.client.dispatch(
        SetValue.from_json(
            {
                "scope": {"level": "instance"},
                "key": "modules.knowledge.enabled",
                "value": False,
                "reason": "Disable knowledge for the CLI test",
            }
        )
    )
    token = exec_side.client.dispatch(CreateToken(name="knowledge CLI"))
    assert isinstance(token, CreateTokenResult)
    path = tmp_path / "bootstrap.toml"
    path.write_text(
        'schema = "urn:skm:config:bootstrap:v1"\ndefault_instance = "unused"\n'
        '[instances.unused]\ninstance_id = "00000000-0000-7000-8000-000000000000"\n'
        'access = { mode = "embedded" }\ndatabase = { url = "secret://env/SKM_DATABASE_URL" }\n'
        "[instances.review]\n"
        f'instance_id = "{exec_side.app.instance_id}"\naccess = {{ mode = "embedded" }}\n'
        "[instances.review.database]\n"
        'url = "secret://env/SKM_DATABASE_URL"\n[instances.review.secrets]\n'
        'token_pepper = "secret://env/SKM_TEST_TOKEN_PEPPER"\n'
    )
    assert exec_side.dsn is not None
    env = {"HOME": str(tmp_path), "SKM_DATABASE_URL": exec_side.dsn, "SKM_TEST_TOKEN_PEPPER": PEPPER.decode()}
    flags = ["--bootstrap", str(path), "--instance", "review", "--as-token", token.secret]
    for group, flag in (("memory", "--project"), ("lessons", "--workspace")):
        out, err = StringIO(), StringIO()
        assert main([*flags, "--json", group, "list", flag, "bad/ref/"], stdout=out, stderr=err, environ=env)
        failure = json.loads(out.getvalue())["error"]
        assert failure["code"] == "MODULE_DISABLED", failure
    out, err = StringIO(), StringIO()
    assert main([*flags, "--help"], stdout=out, stderr=err, environ=env) == 0
    groups = {line.strip().split()[0] for line in out.getvalue().splitlines() if line.strip()}
    assert {"memory", "lessons"}.isdisjoint(groups)


@pytest.mark.parametrize("knowledge_side", ["memory"], indirect=True)
def test_memory_argument_errors(knowledge_side: KnowledgeSide, tmp_path: Path) -> None:
    side = knowledge_side
    client = side.app.client(actor=side.owner, surface=Surface.CLI)

    def error(*args: str) -> str:
        out, err = StringIO(), StringIO()
        assert main(
            ["--json", "memory", *args],
            stdout=out,
            stderr=err,
            environ={"HOME": str(tmp_path)},
            backend=lambda *_: Backend(client, instance_id=side.app.instance_id),
        )
        return json.loads(out.getvalue())["error"]["code"]

    assert error("list") == "MEMORY_SCOPE_REQUIRED"
    assert (
        error("remember", "Waiting for pool", "--key", "bogus", "--project", str(side.project))
        == "SCHEMA_INVALID"
    )
