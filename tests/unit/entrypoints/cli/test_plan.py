"""Unit tests for ``skm plan`` CLI commands and planning settings integration."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from collections.abc import Generator
from dataclasses import dataclass, replace
from io import StringIO
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from fakes.app import FakeScopeChain
from fakes.authorizer import FakeAuthorizer
from skm.bootstrap.composition import App, CompositionOverrides, build_app
from skm.entrypoints.cli.commands import GROUPS
from skm.entrypoints.cli.commands.plan import _HELP, GROUP
from skm.entrypoints.cli.main import Backend, app_backend, main
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.ids import PrincipalId, ScopeId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.ports import PrincipalRepository
from skm.modules.planning.domain.canonical import normalize_document, specification_digest
from skm.modules.planning.generated.commands import ImportSpecification
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.logging import setup
from skm.platform.system_clock import SystemClock

ACTOR = Actor(PrincipalId(UUID(int=100)), PrincipalKind.HUMAN, "fixture CLI owner")
INSTANCE_ID = ScopeId(UUID(int=1))


def _valid_spec(title: str = "Refresh token rotation") -> dict[str, Any]:
    return {
        "schema": "urn:skm:planning:specification:v1",
        "title": title,
        "goal": "Rotate refresh tokens on every use and revoke compromised token families.",
        "context_md": "Today refresh tokens remain valid for 30 days. We need rotation.",
        "non_goals": ["Single sign-on"],
        "rules": ["Never log secret tokens."],
        "requirements": [
            {
                "id": "0192f5c4-0000-7000-8000-000000000001",
                "key": "R1",
                "statement": "Rotated tokens reject reuse and revoke the token family.",
                "priority": "must",
                "source": {"kind": "owner"},
                "owners": ["P1.1"],
            }
        ],
        "phases": [
            {
                "id": "0192f5c4-0000-7000-8000-00000000000a",
                "key": "P1",
                "title": "Storage and rotation",
                "goal": "Implement token family storage and rotation.",
                "contract": {"consumes": ["users table"], "produces": ["token family store"]},
                "design_state": "detailed",
                "deliverables": ["token family store"],
            }
        ],
        "items": [
            {
                "id": "0192f5c4-0000-7000-8000-000000000010",
                "key": "P1.1",
                "phase": "P1",
                "title": "Rotate refresh token family",
                "summary": "Store and rotate token families on refresh.",
                "why": "Prevent replay of stolen refresh tokens.",
                "work_kind": "ops",
                "scope": {"include": ["src/auth/**"], "exclude": []},
                "guidance_md": "Store and rotate token family records.",
                "authority": {"kind": "routine"},
                "review": {"mode": "required", "independence": "separate_session"},
                "depends_on": [],
                "implements": ["R1"],
                "deliverables": ["token repository"],
            }
        ],
        "units": [
            {
                "id": "0192f5c4-0000-7000-8000-000000000020",
                "key": "P1.1/U1",
                "title": "Token store repository",
                "goal": "Persist refresh token family records.",
                "depends_on": [],
                "checks": ["V1"],
            }
        ],
        "criteria": [
            {
                "id": "0192f5c4-0000-7000-8000-000000000030",
                "key": "AC1",
                "owner": "P1.1",
                "statement": "Reused refresh token is rejected and revokes family.",
                "verification_mode": "manual",
                "checks": ["V1"],
                "requirements": ["R1"],
            }
        ],
        "checks": [
            {
                "id": "0192f5c4-0000-7000-8000-000000000040",
                "key": "V1",
                "owner": "P1.1",
                "category": "acceptance",
                "kind": "manual",
                "required": True,
                "definition": {
                    "instructions_md": "Verify token family revocation",
                    "actor_role": "owner",
                },
            }
        ],
        "decisions": [],
        "materials": [],
    }


@dataclass
class Cli:
    app: App
    authorizer: FakeAuthorizer
    state_dir: Path | None
    env: dict[str, str]

    def run(
        self,
        *args: str,
        json_mode: bool = True,
        extra_env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        out, err = StringIO(), StringIO()
        merged_env = {**self.env, **(extra_env or {})}

        def backend(options: object, environ: object) -> Backend:
            attached = app_backend(self.app, ACTOR)
            return Backend(attached.client, state_dir=self.state_dir, instance_id=self.app.instance_id)

        code = main(
            [*(["--json", "--quiet"] if json_mode else []), *args],
            environ=merged_env,
            stdout=out,
            stderr=err,
            backend=backend,
        )
        return code, out.getvalue(), err.getvalue()

    def result(self, *args: str, extra_env: dict[str, str] | None = None) -> Any:
        code, out, err = self.run(*args, extra_env=extra_env)
        assert code == 0, (code, out, err)
        envelope = json.loads(out)
        assert envelope["ok"] is True, envelope
        return envelope["result"]

    def error(self, *args: str, extra_env: dict[str, str] | None = None) -> tuple[int, dict[str, Any]]:
        code, out, err = self.run(*args, extra_env=extra_env)
        assert code != 0, (code, out, err)
        envelope = json.loads(out)
        assert envelope["ok"] is False, envelope
        return code, envelope["error"]


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Cli]:
    monkeypatch.setattr(setup._state, "settings", setup._state.settings)
    authorizer = FakeAuthorizer()
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    app = build_app(
        load_bootstrap(None, {"SKM_DATABASE_URL": "postgresql://unused"}, tmp_path),
        surface=Surface.CLI,
        environ={},
        invocation={},
        overrides=CompositionOverrides(
            authorizer=authorizer, scopes=FakeScopeChain(), instance_id=INSTANCE_ID
        ),
    )
    now = SystemClock().now()
    with app.uow_factory(RequestMeta("req_" + "0" * 26, Surface.CLI, None, now)) as uow:
        uow.repo(ScopeRegistry).create(INSTANCE_ID, ScopeKind.INSTANCE, parent=None, workspace_id=None)
        pid, pkind, pname = ACTOR.principal_id, ACTOR.kind, ACTOR.display_name
        uow.repo(PrincipalRepository).add(
            new_principal(principal_id=pid, kind=pkind, display_name=pname, created_by=None, now=now)
        )
        uow.commit()
    helper = Cli(app, authorizer, state_dir, {})
    ws = helper.result("workspace", "create", "ws1")
    proj = helper.result("project", "create", "proj1", "--workspace", ws["workspace_id"])
    helper.env.update(SKM_WORKSPACE=ws["workspace_id"], SKM_PROJECT=proj["project_id"])
    yield helper
    app.close()


def test_discovered_group_and_all_help_need_no_backend() -> None:
    assert GROUP in GROUPS
    for argv in (["plan", "--help"], *(["plan", v, "--help"] for v in _HELP)):
        out, err = StringIO(), StringIO()
        code = main(
            argv,
            environ={},
            stdout=out,
            stderr=err,
            backend=lambda *_: pytest.fail("help must not open the backend"),
        )
        assert (code, err.getvalue()) == (0, "")
        assert "usage: skm plan" in out.getvalue()

    for dverb in "open show edit save validate publication-preview preview rebase abandon".split():  # noqa: SIM905
        out, err = StringIO(), StringIO()
        code = main(
            ["plan", "draft", dverb, "--help"],
            environ={},
            stdout=out,
            stderr=err,
            backend=lambda *_: pytest.fail("draft help must not open the backend"),
        )
        assert (code, err.getvalue()) == (0, "")


def test_cli_plan_create_and_show(cli: Cli, tmp_path: Path) -> None:
    created = cli.result("plan", "create", "Refresh token rotation")
    assert created["alias"] == "PLAN1"
    assert created["draft_id"] is not None
    assert created["edit_version"] == 1

    no_draft = cli.result("plan", "create", "Second plan", "--no-draft")
    assert no_draft["alias"] == "PLAN2"
    assert no_draft["draft_id"] is None

    listed = cli.result("plan", "list", "--all")
    assert [p["alias"] for p in listed["items"]] == ["PLAN2", "PLAN1"]

    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(_valid_spec()), encoding="utf-8")
    saved = cli.result("plan", "draft", "save", "PLAN1", str(spec_file))
    assert (saved["edit_version"], saved["counts"]["error"]) == (2, 0)
    code, raw_draft, _ = cli.run("plan", "draft", "show", "PLAN1", "--raw", json_mode=False)
    assert (code, json.loads(raw_draft)["title"]) == (0, "Refresh token rotation")

    code, pub_out, pub_err = cli.run(
        "plan", "publish", "PLAN1", "--reason", "Initial release", json_mode=False
    )
    assert (code, "published r1 (" in pub_out, "preview: digest sha256:" in pub_err) == (0, True, True)
    code, exp_stdout, _ = cli.run("plan", "export", "PLAN1", json_mode=False)
    assert (code, json.loads(exp_stdout)["export_meta"]["content_digest"][:7]) == (0, "sha256:")

    shown = cli.result("plan", "show", "PLAN1")
    assert shown["alias"] == "PLAN1"
    assert shown["current_revision_no"] == 1

    # Verify --format json on `skm plan show` works even when global --json is not set.
    code, fmt_json, err = cli.run("plan", "show", "PLAN1", "--format", "json", json_mode=False)
    assert (code, err) == (0, "")
    assert json.loads(fmt_json)["result"]["alias"] == "PLAN1"

    code, human_tree, err = cli.run("plan", "show", "PLAN1", "--tree", json_mode=False)
    assert (code, err) == (0, "")
    assert "P1.1  Rotate refresh token family" in human_tree
    assert "P1.1/U1  Token store repository" in human_tree

    # Configure planning.display.tree_depth = 1 at plan scope and verify units/items are hidden.
    cli.result(
        "config",
        "set",
        "planning.display.tree_depth",
        "1",
        "--scope",
        f"plan:{created['plan_id']}",
    )
    code, shallow_tree, _ = cli.run("plan", "show", "PLAN1", "--tree", json_mode=False)
    assert code == 0
    assert "P1  Storage and rotation" in shallow_tree
    assert "P1.1/U1" not in shallow_tree

    ent = cli.result("plan", "show", "PLAN1", "--entity", "P1.1")
    assert ent["display_key"] == "P1.1"
    assert ent["entity_kind"] == "item"

    entities = cli.result("plan", "entities", "PLAN1", "--kind", "item", "--all")
    assert [i["display_key"] for i in entities["items"]] == ["P1.1"]

    txt = cli.result("plan", "text", "PLAN1", "plan", "/context_md", "--max-bytes", "12")
    assert txt["text"] == "Today refres"
    assert txt["truncated"] is True
    txt_cont = cli.result(
        "plan", "text", "PLAN1", "plan", "/context_md", "--offset-bytes", str(txt["next_offset_bytes"])
    )
    assert txt_cont["text"].startswith("h tokens remain")

    # Open a draft and verify read guard (--expected-version mismatch -> VERSION_CONFLICT).
    cli.result("plan", "draft", "open", "PLAN1")
    _, err_vc = cli.error(
        "plan", "text", "PLAN1", "plan", "/context_md", "--draft", "--expected-version", "99"
    )
    assert err_vc["code"] == "VERSION_CONFLICT"


def test_cli_draft_editor_conflict_preserves_buffer(cli: Cli, tmp_path: Path) -> None:
    created = cli.result("plan", "create", "Editor test plan")
    draft_id = created["draft_id"]
    assert cli.state_dir is not None
    edits_buf = cli.state_dir / "edits" / f"draft-{draft_id}.json"
    tmp_buf = cli.state_dir / "tmp" / f"draft-{draft_id}.json"

    # 1. Invalid JSON written by editor -> SCHEMA_INVALID, buffer preserved.
    bad_json_script = tmp_path / "bad_json_editor.py"
    bad_json_script.write_text(
        "import pathlib, sys\npathlib.Path(sys.argv[1]).write_text('{not valid json', encoding='utf-8')\n",
        encoding="utf-8",
    )
    code, err = cli.error(
        "plan",
        "draft",
        "edit",
        "PLAN1",
        extra_env={"SKM_EDITOR": f"{sys.executable} {bad_json_script}"},
    )
    assert code == 1
    assert err["code"] == "SCHEMA_INVALID"
    assert err["details"]["path"] == str(edits_buf)
    assert edits_buf.read_text(encoding="utf-8") == "{not valid json"
    assert tmp_buf.read_text(encoding="utf-8") == "{not valid json"

    # 2. Schema-invalid specification written by editor -> SCHEMA_INVALID from save_draft, buffer preserved.
    bad_schema_doc = _valid_spec()
    bad_schema_doc["phases"][0]["unknown_field"] = "forbidden"
    bad_schema_file = tmp_path / "bad_schema.json"
    bad_schema_file.write_text(json.dumps(bad_schema_doc), encoding="utf-8")
    copy_script = tmp_path / "copy_editor.py"
    copy_src = f"import pathlib, sys\np = pathlib.Path({str(bad_schema_file)!r})\n"
    copy_script.write_text(
        copy_src + "pathlib.Path(sys.argv[1]).write_bytes(p.read_bytes())\n", encoding="utf-8"
    )
    code, err = cli.error(
        "plan",
        "draft",
        "edit",
        "PLAN1",
        extra_env={"SKM_EDITOR": f"{sys.executable} {copy_script}"},
    )
    assert code == 1
    assert err["code"] == "SCHEMA_INVALID"
    assert err["details"]["path"] == str(edits_buf)
    assert edits_buf.is_file()
    assert tmp_buf.is_file()

    # 3. Valid spec written by editor with stale --expected-version -> VERSION_CONFLICT, buffer preserved.
    good_file = tmp_path / "good_spec.json"
    good_file.write_text(json.dumps(_valid_spec()), encoding="utf-8")
    good_script = tmp_path / "good_editor.py"
    good_src = f"import pathlib, sys\np = pathlib.Path({str(good_file)!r})\n"
    good_script.write_text(
        good_src + "pathlib.Path(sys.argv[1]).write_bytes(p.read_bytes())\n", encoding="utf-8"
    )
    code, err = cli.error(
        "plan",
        "draft",
        "edit",
        "PLAN1",
        "--expected-version",
        "99",
        extra_env={"SKM_EDITOR": f"{sys.executable} {good_script}"},
    )
    assert code == 6
    assert err["code"] == "VERSION_CONFLICT"
    assert err["details"]["path"] == str(edits_buf)
    assert edits_buf.is_file()
    assert tmp_buf.is_file()

    # 4. Valid edit with matching version (SKM_EDITOR overrides VISUAL/EDITOR) -> saved and buffers removed.
    good_env = {"SKM_EDITOR": f"{sys.executable} {good_script}", "VISUAL": "false", "EDITOR": "false"}
    saved = cli.result("plan", "draft", "edit", "PLAN1", extra_env=good_env)
    assert saved["edit_version"] == 2
    assert (edits_buf.exists(), tmp_buf.exists()) == (False, False)

    # 5. Unchanged bytes in editor (and state_dir=None) -> exit 0 with changed=False and temp dir cleaned up.
    noop_script = tmp_path / "noop_editor.py"
    noop_script.write_text("import sys\n", encoding="utf-8")
    no_state_cli = replace(cli, state_dir=None)
    noop_env = {"SKM_EDITOR": f"{sys.executable} {noop_script}"}
    noop_res = no_state_cli.result("plan", "draft", "edit", "PLAN1", extra_env=noop_env)
    assert noop_res == {"draft_id": draft_id, "edit_version": 2, "changed": False}
    _, save_err = cli.error("plan", "draft", "save", "PLAN1", str(good_file), "--patch", "--changes")
    assert save_err["code"] == "SCHEMA_INVALID"


def test_cli_plan_publish_flow(cli: Cli, tmp_path: Path) -> None:
    cli.result("plan", "create", "Publish flow plan")

    # Draft with semantic error (unknown phase P99) -> draft validate exits with code 1 (validation).
    sem_bad = _valid_spec()
    sem_bad["items"][0]["phase"] = "P99"
    sem_file = tmp_path / "sem_bad.json"
    sem_file.write_text(json.dumps(sem_bad), encoding="utf-8")
    cli.result("plan", "draft", "save", "PLAN1", str(sem_file))

    code, out, _ = cli.run("plan", "draft", "validate", "PLAN1")
    assert code == 1
    val_env = json.loads(out)
    assert val_env["result"]["publishable"] is False

    # Publishing unready draft fails with PLAN_NOT_READY.
    _, err = cli.error("plan", "publish", "PLAN1", "--reason", "too early")
    assert err["code"] == "PLAN_NOT_READY"

    # Save valid specification and validate -> exit 0.
    spec_file = tmp_path / "valid.json"
    spec_file.write_text(json.dumps(_valid_spec()), encoding="utf-8")
    cli.result("plan", "draft", "save", "PLAN1", str(spec_file))

    v_ok = cli.result("plan", "draft", "validate", "PLAN1")
    assert v_ok["publishable"] is True

    prev = cli.result("plan", "draft", "publication-preview", "PLAN1")
    assert prev["publishable"] is True
    assert prev["content_digest"].startswith("sha256:")

    # Publish with mismatched --expected-content-digest -> VERSION_CONFLICT without publishing.
    _, cand_err = cli.error(
        "plan", "publish", "PLAN1", "--expected-content-digest", f"sha256:{'0' * 64}", "--reason", "stale"
    )
    assert cand_err["code"] == "VERSION_CONFLICT"

    # Publish without explicit --expected-content-digest auto-runs preview_publication and succeeds.
    pub = cli.result("plan", "publish", "PLAN1", "--reason", "Publish r1")
    assert pub["revision_no"] == 1
    assert pub["content_digest"] == prev["content_digest"]

    # Opening a new draft from current and publishing without changes -> NO_CHANGES.
    cli.result("plan", "draft", "open", "PLAN1")
    _, err = cli.error("plan", "publish", "PLAN1", "--reason", "unchanged")
    assert err["code"] == "NO_CHANGES"


def test_cli_plan_rebase_and_restore_requires_expected_current(cli: Cli, tmp_path: Path) -> None:
    cli.result("plan", "create", "Rebase and restore plan")
    spec = _valid_spec()
    f1 = tmp_path / "r1.json"
    f1.write_text(json.dumps(spec), encoding="utf-8")
    cli.result("plan", "draft", "save", "PLAN1", str(f1))
    cli.result("plan", "publish", "PLAN1", "--reason", "r1")

    # Open two drafts on r1: d_a and d_b.
    d_a = cli.result("plan", "draft", "open", "PLAN1")["draft_id"]
    d_b = cli.result("plan", "draft", "open", "PLAN1")["draft_id"]

    # Advance plan to r2 via d_a (change goal and add unit P1.1/U2).
    spec_r2 = copy.deepcopy(spec)
    spec_r2["goal"] = "Updated goal in r2 for token rotation."
    u2_a = {**copy.deepcopy(spec["units"][0]), "id": "0192f5c4-0000-7000-8000-000000000021", "key": "P1.1/U2"}
    spec_r2["units"].append(u2_a)
    f2 = tmp_path / "r2.json"
    f2.write_text(json.dumps(spec_r2), encoding="utf-8")
    cli.result("plan", "draft", "save", "PLAN1", "--draft", d_a, str(f2))
    cli.result("plan", "publish", "PLAN1", "--draft", d_a, "--reason", "r2")

    # Conflicting goal + duplicate key P1.1/U2 in d_b -> REBASE_CONFLICT, resolved with --resolve and --rekey.
    spec_b = copy.deepcopy(spec)
    spec_b["goal"] = "Conflicting goal in draft B for token rotation."
    u2_b = {**copy.deepcopy(spec["units"][0]), "id": "0192f5c4-0000-7000-8000-000000000022", "key": "P1.1/U2"}
    spec_b["units"].append(u2_b)
    fb = tmp_path / "b.json"
    fb.write_text(json.dumps(spec_b), encoding="utf-8")
    cli.result("plan", "draft", "save", "PLAN1", "--draft", d_b, str(fb))

    _, reb_err = cli.error("plan", "draft", "rebase", "PLAN1", "--draft", d_b)
    assert reb_err["code"] == "REBASE_CONFLICTS"
    c_by_k = {c["kind"]: c["conflict_id"] for c in reb_err["details"]["conflicts"]}
    res_arg, rek_arg = f"{c_by_k['field']}=yours", f"{c_by_k['key_collision']}=P1.1/U3"
    rebased = cli.result(
        "plan", "draft", "rebase", "PLAN1", "--draft", d_b, "--resolve", res_arg, "--rekey", rek_arg
    )
    assert rebased["draft_id"] == d_b

    # Verify revisions, diff (including A -> current and explicit "current"), preview, stats.
    revs = cli.result("plan", "revisions", "PLAN1")
    assert [r["revision_no"] for r in revs["items"]] == [2, 1]
    diff = cli.result("plan", "diff", "PLAN1", "r1", "r2")
    diff_to_cur = cli.result("plan", "diff", "PLAN1", "r1")
    diff_exp_cur = cli.result("plan", "diff", "PLAN1", "r1", "current")
    assert diff["from_digest"] != diff["to_digest"]
    assert (diff_to_cur["to_digest"], diff_exp_cur["to_digest"]) == (diff["to_digest"], diff["to_digest"])
    assert diff_to_cur["from_digest"] == diff["from_digest"]
    assert len(cli.result("plan", "preview", "PLAN1")["lanes"]) >= 1
    assert cli.result("plan", "stats", "PLAN1")["counts"]["units"] == 2

    # Restore r1 with stale --expected-current r1 fails with BASE_REVISION_CHANGED.
    _, err = cli.error("plan", "restore", "PLAN1", "1", "--expected-current", "r1", "--reason", "stale")
    assert err["code"] == "BASE_REVISION_CHANGED"
    restored = cli.result("plan", "restore", "PLAN1", "1", "--reason", "Rollback to r1")
    assert (restored["revision_no"], restored["restored_from_revision_no"]) == (3, 1)

    # Archive requires --yes in non-interactive mode.
    _, err = cli.error("plan", "archive", "PLAN1")
    assert err["code"] == "SCHEMA_INVALID"
    assert cli.result("plan", "archive", "PLAN1", "--yes")["lifecycle_state"] == "archived"


def test_cli_plan_export_and_import(cli: Cli, tmp_path: Path) -> None:
    created = cli.result("plan", "create", "Export source plan")
    spec = _valid_spec()
    f1 = tmp_path / "spec.json"
    f1.write_text(json.dumps(spec), encoding="utf-8")
    cli.result("plan", "draft", "save", "PLAN1", str(f1))
    r1_pub = cli.result("plan", "publish", "PLAN1", "--reason", "r1")

    exp_file = tmp_path / "exported.json"
    exp = cli.result("plan", "export", "PLAN1", "--output", str(exp_file))
    assert (exp_file.is_file(), exp["export_meta"]["content_digest"][:7]) == (True, "sha256:")

    # Mutually exclusive flags and missing/conflicting new-draft base provenance fail before bus call.
    for bad_args in (
        (str(exp_file), "--new-plan", "--new-draft"),
        (str(exp_file), "--keep-ids", "--remap-ids"),
        (str(f1), "--new-draft", "--plan", "PLAN1"),
        (str(exp_file), "--new-draft", "--plan", "PLAN1", "--base", "empty"),
    ):
        assert cli.error("plan", "import", *bad_args)[1]["code"] == "SCHEMA_INVALID"

    # Advance PLAN1 to r2 so exported r1 envelope has a stale base.
    d2 = cli.result("plan", "draft", "open", "PLAN1")["draft_id"]
    f2 = tmp_path / "spec_r2.json"
    f2.write_text(json.dumps({**copy.deepcopy(spec), "goal": "Updated goal in r2."}), encoding="utf-8")
    cli.result("plan", "draft", "save", "PLAN1", "--draft", d2, str(f2))
    cli.result("plan", "publish", "PLAN1", "--draft", d2, "--reason", "r2")

    # ench6: Feed same export envelope through CLI import and embedded ImportSpecification DTO on PLAN1.
    imp_cli = cli.result("plan", "import", str(exp_file), "--new-draft", "--plan", "PLAN1")
    cli_did = imp_cli["draft_id"]
    cli_show = cli.result("plan", "draft", "show", "PLAN1", "--draft", cli_did)
    cli_val = json.loads(cli.run("plan", "draft", "validate", "PLAN1", "--draft", cli_did)[1])["result"]
    cli_diff = cli.result("plan", "diff", "PLAN1", "r1", "--draft", cli_did)
    _, stale_err = cli.error("plan", "publish", "PLAN1", "--draft", cli_did, "--reason", "stale")
    assert stale_err["code"] == "BASE_REVISION_CHANGED"
    cli.result("plan", "draft", "abandon", "PLAN1", "--draft", cli_did, "--yes")

    raw_env = json.loads(exp_file.read_text(encoding="utf-8"))
    dto_q: dict[str, Any] = {
        "project_id": cli.env["SKM_PROJECT"],
        "plan_id": created["plan_id"],
        "keep_ids": True,
    }
    dto_q.update(mode="new_draft", document=raw_env["document"], export_meta=raw_env["export_meta"])
    dto_q["source_base_revision_id"] = r1_pub["revision_id"]
    dto = ImportSpecification.from_json(dto_q)
    raw_dto_res = app_backend(cli.app, ACTOR).client.dispatch(dto, idempotency_key="ik-dto-1")
    imp_dto = cast("Any", raw_dto_res).to_json()
    dto_did = str(imp_dto["draft_id"])
    dto_show = cli.result("plan", "draft", "show", "PLAN1", "--draft", dto_did)
    dto_val = json.loads(cli.run("plan", "draft", "validate", "PLAN1", "--draft", dto_did)[1])["result"]
    dto_diff = cli.result("plan", "diff", "PLAN1", "r1", "--draft", dto_did)
    assert (cli_show["document"], cli_show["document_digest"]) == (
        dto_show["document"],
        dto_show["document_digest"],
    )
    assert (cli_val["findings"], imp_cli["counts"]) == (dto_val["findings"], imp_dto["counts"])
    assert (cli_diff["summary"], cli_show["base_revision_id"]) == (dto_diff["summary"], r1_pub["revision_id"])
    assert cli_show["document"]["items"][0]["id"] == spec["items"][0]["id"]

    # Import as new plan with --remap-ids and --materials auto-upload/rebind.
    mat_dir = tmp_path / "mats"
    mat_dir.mkdir()
    mat_bytes = b"# Architecture material\n"
    (mat_dir / "arch.md").write_bytes(mat_bytes)
    mat_dig = f"sha256:{hashlib.sha256(mat_bytes).hexdigest()}"
    m_id, fv_id = "0192f5c4-0000-7000-8000-000000000050", "0192f5c4-0000-7000-8000-000000000099"
    mat_d: dict[str, Any] = {"id": m_id, "key": "arch-doc", "title": "Arch doc", "kind": "file_version"}
    mat_d.update(role="reference", required_for=["execution"], freshness={"policy": "pinned"})
    mat_d.update(file_version_id=fv_id, why="Arch ref.", applies_to=["P1.1"])
    raw_env["document"]["materials"] = [mat_d]
    raw_env["export_meta"]["content_digest"] = specification_digest(normalize_document(raw_env["document"]))
    mat_m: dict[str, Any] = {"material_key": "arch-doc", "file_version_id": fv_id, "content_digest": mat_dig}
    mat_m.update(size=len(mat_bytes), original_filename="arch.md", media_type="text/plain")
    raw_env["export_meta"]["materials"] = [mat_m]
    exp_mat_file = tmp_path / "exported_mat.json"
    exp_mat_file.write_text(json.dumps(raw_env), encoding="utf-8")
    imp_plan = cli.result(
        "plan", "import", str(exp_mat_file), "--new-plan", "--remap-ids", "--materials", str(mat_dir)
    )
    p2_doc = cli.result("plan", "draft", "show", "PLAN2")["document"]
    assert (imp_plan["alias"], p2_doc["materials"][0]["file_version_id"] != fv_id) == ("PLAN2", True)
    imp_f = cli.result(
        "plan", "import", str(exp_file), "--new-draft", "--plan", "PLAN2", "--base", "empty", "--remap-ids"
    )
    assert imp_f["alias"] == "PLAN2"


def test_cli_plan_design_resolves_alias_and_records_the_brief(cli: Cli, tmp_path: Path) -> None:
    from skm.kernel.ids import PlanId
    from skm.modules.planning.ports import PlanRepository

    plan = cli.result("plan", "create", "Plan intake")
    payload = tmp_path / "brief.json"
    payload.write_text(
        json.dumps({"goal": "Describe the increment", "constraints": ["Preserve existing data"]})
    )
    result = cli.result("plan", "design", plan["alias"], str(payload))
    assert result["plan_id"] == plan["plan_id"]
    meta = RequestMeta("req_" + "5" * 26, Surface.CLI, None, SystemClock().now())
    with cli.app.uow_factory(meta, readonly=True) as uow:
        stored = uow.repo(PlanRepository).get_design_brief(
            PlanId(UUID(result["plan_id"])), UUID(result["design_brief_id"])
        )
        assert stored.goal == "Describe the increment"
    payload.write_text('"not an object"')
    _, error = cli.error("plan", "design", plan["alias"], str(payload))
    assert error["code"] == "SCHEMA_INVALID"


def test_cli_plan_simulate_reports_unknown_for_draft_and_current_revision(cli: Cli, tmp_path: Path) -> None:
    cli.result("plan", "create", "Estimate work")
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(_valid_spec()), encoding="utf-8")
    saved = cli.result("plan", "draft", "save", "PLAN1", str(spec))
    draft = cli.result(
        "plan", "simulate", "PLAN1", "--draft", "--expected-version", str(saved["edit_version"])
    )
    assert draft["source"]["kind"] == "draft"
    assert draft["source"]["edit_version"] == saved["edit_version"]
    assert draft["basis"] == "heuristic"
    assert draft["task_count"] == 1
    assert [draft[key] for key in ("tokens", "cost_usd_micros", "duration_seconds")] == [None] * 3

    published = cli.result("plan", "publish", "PLAN1", "--reason", "Review the estimate")
    current = cli.result("plan", "simulate", "PLAN1", "--tokens-per-second", "50")
    assert current["source"]["revision_id"] == published["revision_id"]
    assert current["tokens_per_second"] == 50
    code, out, err = cli.run("plan", "simulate", "PLAN1", "--revision", "1", json_mode=False)
    assert (code, err) == (0, "")
    assert "heuristic" in out
    assert out.count("unknown") == 3
