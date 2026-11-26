"""Unit and CLI surface tests for ``skm plan create --template`` (P09.08)."""

from __future__ import annotations

import json
from argparse import Namespace
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from tests.unit.entrypoints.cli.test_plan import (
    ACTOR,
    INSTANCE_ID,
    Cli,
)

from fakes.app import FakeScopeChain
from fakes.authorizer import FakeAuthorizer
from skm.adapters.resources.builtin_packs import PackagedBuiltinPacks
from skm.bootstrap.composition import CompositionOverrides, build_app
from skm.entrypoints.cli.commands import plan
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.gateways import GatewayTable
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.kernel.tokens import TokenEstimator
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.ports import PrincipalRepository
from skm.modules.extensions.ports import BuiltinPacks
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.logging import setup
from skm.platform.system_clock import SystemClock


class _SimpleEstimator:
    estimator_id = "heuristic-v1"

    def estimate(self, text: str) -> int:
        return max(1, len(text) // 4)


@pytest.fixture
def cli_with_packs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Cli]:
    monkeypatch.setattr(setup._state, "settings", setup._state.settings)
    authorizer = FakeAuthorizer()
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    gateways = GatewayTable(
        {
            TokenEstimator: _SimpleEstimator(),
            BuiltinPacks: PackagedBuiltinPacks(Path("resources/packs")),
        },
        "control_plane_gateway",
    )
    app = build_app(
        load_bootstrap(None, {"SKM_DATABASE_URL": "postgresql://unused"}, tmp_path),
        surface=Surface.CLI,
        environ={},
        invocation={},
        overrides=CompositionOverrides(
            authorizer=authorizer,
            scopes=FakeScopeChain(),
            gateways=gateways,
            instance_id=INSTANCE_ID,
        ),
    )
    now = SystemClock().now()
    with app.uow_factory(RequestMeta("req_" + "0" * 26, Surface.CLI, None, now)) as uow:
        uow.repo(ScopeRegistry).create(INSTANCE_ID, ScopeKind.INSTANCE, parent=None, workspace_id=None)
        uow.repo(PrincipalRepository).add(
            new_principal(
                principal_id=ACTOR.principal_id,
                kind=ACTOR.kind,
                display_name=ACTOR.display_name,
                created_by=None,
                now=now,
            )
        )
        uow.commit()
    helper = Cli(app, authorizer, state_dir, {})
    helper.result("ext", "sync")
    ws = helper.result("workspace", "create", "ws-tpl")
    proj = helper.result("project", "create", "proj-tpl", "--workspace", ws["workspace_id"])
    helper.env.update(SKM_WORKSPACE=ws["workspace_id"], SKM_PROJECT=proj["project_id"])
    yield helper
    app.close()


@pytest.mark.parametrize(
    ("inputs", "template", "no_draft"),
    [
        (["goal=one", "goal=two"], "feature", False),
        (["=empty"], "feature", False),
        (["missing_equals"], "feature", False),
        (["goal=one"], None, False),
        (["title=a", "goal=b"], "feature", True),
    ],
)
def test_invalid_template_flags_and_input_keys_fail_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    inputs: list[str],
    template: str | None,
    no_draft: bool,
) -> None:
    monkeypatch.setattr(plan, "resolve_project_id", lambda *_: "project")
    monkeypatch.setattr(plan, "_dispatch", lambda *_: pytest.fail("unexpected dispatch"))
    args = Namespace(
        plan_verb="create",
        command_name="planning.create_plan",
        project=None,
        title="Plan",
        template=template,
        inputs=inputs,
        no_draft=no_draft,
    )
    with pytest.raises(ValidationFailed) as error:
        plan._run_top(args, cast("Any", object()))
    assert error.value.code is ErrorCode.SCHEMA_INVALID


def test_cli_plan_create_template_json_and_human_modes(cli_with_packs: Cli) -> None:
    created = cli_with_packs.result(
        "plan",
        "create",
        "Feature Rollout",
        "--template",
        "feature",
        "--input",
        "title=Implement feature X",
        "--input",
        "goal=Ship verified templates with --dash and ² symbols",
    )
    assert created["alias"] == "PLAN1"
    assert created["draft_id"] is not None
    assert created["edit_version"] == 1

    code, raw_doc, err = cli_with_packs.run("plan", "draft", "show", "PLAN1", "--raw", json_mode=False)
    assert (code, err) == (0, "")
    doc = json.loads(raw_doc)
    assert doc["title"] == "Feature Rollout"
    assert doc["goal"] == "Ship verified templates with --dash and ² symbols"
    assert doc["items"][0]["title"] == "Implement feature X"
    assert UUID(doc["phases"][0]["id"])
    assert UUID(doc["items"][0]["id"])
    prov = doc["extensions"]["core/template"]
    assert prov["schema_version"] == 1
    assert prov["value"]["key"] == "feature"
    assert prov["value"]["version"] == "2.0.0"
    assert str(prov["value"]["digest"]).startswith("sha256:")

    code, human_out, _ = cli_with_packs.run(
        "plan",
        "create",
        "Bugfix Rollout",
        "--template",
        "bugfix",
        "--input",
        "title=Fix edge case",
        "--input",
        "goal=--5 stays string",
        json_mode=False,
    )
    assert code == 0
    lines = human_out.strip().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("created plan PLAN2 (")
    assert lines[1].startswith("draft: ")
    assert lines[1].endswith(" (v1)")


def test_cli_plan_create_template_errors_and_atomic_rollback(cli_with_packs: Cli) -> None:
    # Wrong scalar types (int / bool instead of string), unknown input, missing required, dead flag combos
    for bad_args in (
        ("plan", "create", "BadInt", "--template", "feature", "--input", "title=123", "--input", "goal=ok"),
        ("plan", "create", "BadBool", "--template", "feature", "--input", "title=true", "--input", "goal=ok"),
        (
            "plan",
            "create",
            "UnknownInput",
            "--template",
            "feature",
            "--input",
            "title=ok",
            "--input",
            "goal=ok",
            "--input",
            "undeclared=val",
        ),
        ("plan", "create", "MissingGoal", "--template", "feature", "--input", "title=only"),
        ("plan", "create", "OrphanInput", "--input", "goal=val"),
        (
            "plan",
            "create",
            "ConflictingNoDraft",
            "--template",
            "feature",
            "--input",
            "title=ok",
            "--input",
            "goal=ok",
            "--no-draft",
        ),
    ):
        _, err_obj = cli_with_packs.error(*bad_args)
        assert err_obj["code"] == "SCHEMA_INVALID", (bad_args, err_obj)

    _, missing_err = cli_with_packs.error("plan", "create", "NoSuchTpl", "--template", "does-not-exist")
    assert missing_err["code"] == "NOT_FOUND"

    # Human mode error path formats cleanly without crashing or creating partial plans
    h_code, h_out, h_err = cli_with_packs.run(
        "plan",
        "create",
        "HumanBad",
        "--template",
        "feature",
        "--input",
        "title=123",
        "--input",
        "goal=ok",
        json_mode=False,
    )
    assert h_code != 0
    assert h_out == ""
    assert "SCHEMA_INVALID" in h_err or "invalid template input" in h_err

    # Verify atomic rollback: zero plans created and next valid plan still receives PLAN1
    assert cli_with_packs.result("plan", "list", "--all")["items"] == []
    first_valid = cli_with_packs.result("plan", "create", "Clean First Plan")
    assert first_valid["alias"] == "PLAN1"
