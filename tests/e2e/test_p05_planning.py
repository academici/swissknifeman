"""P05.Z end-to-end acceptance tests for ``planning`` on PostgreSQL (authoring, rebase, restore)."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from skm.adapters.postgres.migrations.runner import discover_migrations
from skm.adapters.postgres.planning.revisions import PostgresRevisionRepository
from skm.bootstrap.composition import open_cli_app
from skm.entrypoints.cli.main import main as cli_main
from skm.entrypoints.cli.main import production_backend
from skm.kernel.ids import FileVersionId, ProjectId, RevisionId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.modules.artifacts import public as artifacts
from skm.modules.planning import public as planning_public
from skm.modules.planning.domain.canonical import normalize_document, specification_digest
from skm.modules.planning.domain.events import PlanRevisionPublished, PlanRevisionRestored
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.system_clock import SystemClock
from skm.platform.system_ids import Uuid7Generator

pytestmark = [pytest.mark.e2e, pytest.mark.pg]
ROOT = Path(__file__).resolve().parents[2]
ENTRY = "import sys; from skm.entrypoints.cli.main import main; sys.exit(main())"
PASSED = ("PATH", "PYTHONPATH", "LANG", "LC_ALL", "TMPDIR")
_SUB_KW: dict[str, Any] = {"stdin": subprocess.DEVNULL, "capture_output": True, "text": True, "timeout": 120}
ITEM_2_ID = "0192f5c4-0000-7000-8000-000000000011"
MAT_LAT_ID = "0192f5c4-0000-7000-8000-000000000070"
MAT_PIN_ID = "0192f5c4-0000-7000-8000-000000000071"

_BASE_SPEC_JSON = (
    '{"schema":"urn:skm:planning:specification:v1","title":"M2 System Architecture",'
    '"goal":"Deliver deterministic planning, revisions, rebase and restore.",'
    '"context_md":"Keep the run pinned.\\nAudit the new draft. 🧪\\n",'
    '"non_goals":["Container orchestration"],"rules":["Never mutate published revisions."],'
    '"requirements":[{"id":"0192f5c4-0000-7000-8000-000000000030","key":"R1","priority":"must",'
    '"statement":"Revisions must be immutable.","source":{"kind":"owner"},"owners":["P1.1"]}],'
    '"phases":[{"id":"0192f5c4-0000-7000-8000-00000000000a","key":"P1","title":"Core authoring",'
    '"goal":"Implement specification domain.","design_state":"skeleton",'
    '"contract":{"consumes":["schema registry"],"produces":["immutable revisions"]},'
    '"deliverables":["planning module"]},'
    '{"id":"0192f5c4-0000-7000-8000-00000000000b","key":"P2","title":"Follow-up slice",'
    '"goal":"Future phase with empty depends_on.","design_state":"skeleton","depends_on":[]}],'
    '"items":[{"id":"0192f5c4-0000-7000-8000-000000000010","key":"P1.1","phase":"P1","work_kind":"ops",'
    '"title":"Specification storage","summary":"Storage summary.","why":"Required.",'
    '"scope":{"include":["src/p1_1/**"],"exclude":[]},"guidance_md":"Guidance for P1.1.",'
    '"authority":{"kind":"routine"},"depends_on":[],"implements":["R1"],"decisions":["D1"],'
    '"review":{"mode":"required","independence":"separate_session","max_rounds":2},'
    '"work_policy":{"role_intensity":{"executor":"heavy","reviewer":"medium"},'
    '"verification_intensity":"heavy"},"deliverables":["deliverable-P1.1"]},'
    '{"id":"0192f5c4-0000-7000-8000-000000000011","key":"P1.2","phase":"P1","work_kind":"ops",'
    '"title":"Retry with backoff","summary":"Retry summary.","why":"Required.",'
    '"scope":{"include":["src/p1_2/**"],"exclude":[]},"guidance_md":"Guidance for P1.2.",'
    '"authority":{"kind":"routine"},"work_policy":{},"depends_on":["P1.1"],"implements":["R1"],'
    '"review":{"mode":"self","reason":"Unit check."},"deliverables":["deliverable-P1.2"]}],'
    '"units":[{"id":"0192f5c4-0000-7000-8000-000000000020","key":"P1.1/U1","title":"Typed writer unit",'
    '"goal":"Insert revision rows.","depends_on":[],"checks":["V1"],'
    '"work_policy":{"verification_intensity":"light"}}],'
    '"criteria":[{"id":"0192f5c4-0000-7000-8000-000000000040","key":"AC1","owner":"P1.1",'
    '"statement":"Typed reader reconstructs payload.","verification_mode":"manual",'
    '"checks":["P1.1:V1"],"requirements":["R1"]}],'
    '"checks":[{"id":"0192f5c4-0000-7000-8000-000000000050","key":"V1","owner":"P1.1","required":true,'
    '"title":"Storage parity check","category":"acceptance","kind":"manual",'
    '"definition":{"instructions_md":"Verify.","actor_role":"owner","allowed_verdicts":["pass","fail"]}}],'
    '"decisions":[{"id":"0192f5c4-0000-7000-8000-000000000060","key":"D1","title":"Append-only",'
    '"state":"accepted","question":"How stored?","decision":"Append-only tables.",'
    '"rationale":"Prevents mutation.","applies_to":["P1.1"]}],"materials":[]}'
)


@dataclass(frozen=True)
class Sandbox:
    root: Path
    dsn: str
    ws_id: UUID

    @property
    def home(self) -> Path:
        return self.root / "home"

    def env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        env = {name: os.environ[name] for name in PASSED if name in os.environ}
        r = self.root
        env.update(HOME=str(self.home), XDG_CONFIG_HOME=str(r / "config"), XDG_STATE_HOME=str(r / "state"))
        env.update(XDG_DATA_HOME=str(r / "data"), USER="p05-owner", SKM_DATABASE_URL=self.dsn)
        env.update(extra or {})
        return env


def run_sub(
    box: Sandbox, cmd: str, *rest: str, json_mode: bool = True, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    flags = ["--json", *cmd.split(), *rest] if json_mode else [*cmd.split(), *rest]
    return subprocess.run(
        [sys.executable, "-c", ENTRY, *flags], env=box.env(extra_env), cwd=box.root, check=False, **_SUB_KW
    )


def ok_sub(box: Sandbox, cmd: str, *rest: str, extra_env: dict[str, str] | None = None) -> dict[str, Any]:
    done = run_sub(box, cmd, *rest, json_mode=True, extra_env=extra_env)
    assert done.returncode == 0, f"cmd={cmd} {rest}\nstdout={done.stdout}\nstderr={done.stderr}"
    return cast("dict[str, Any]", json.loads(done.stdout)["result"])


def err_sub(
    box: Sandbox, code: int, cmd: str, *rest: str, extra_env: dict[str, str] | None = None
) -> dict[str, Any]:
    done = run_sub(box, cmd, *rest, json_mode=True, extra_env=extra_env)
    assert done.returncode == code, f"cmd={cmd} {rest}\nstdout={done.stdout}\nstderr={done.stderr}"
    return cast("dict[str, Any]", json.loads(done.stdout)["error"])


def _cli_json(box: Sandbox, expected_code: int, key: str, cmd: str, *rest: str) -> dict[str, Any]:
    out, err = io.StringIO(), io.StringIO()
    argv = ["--json", *cmd.split(), *rest]
    rc = cli_main(argv, stdout=out, stderr=err, environ=box.env(), backend=production_backend)
    assert rc == expected_code, f"cmd={cmd} {rest} rc={rc} out={out.getvalue()} err={err.getvalue()}"
    return cast("dict[str, Any]", json.loads(out.getvalue())[key])


def ok_cli(box: Sandbox, cmd: str, *rest: str) -> dict[str, Any]:
    return _cli_json(box, 0, "result", cmd, *rest)


def err_cli(box: Sandbox, expected_code: int, cmd: str, *rest: str) -> dict[str, Any]:
    return _cli_json(box, expected_code, "error", cmd, *rest)


def rows(dsn: str, query: str, *params: object) -> list[tuple[Any, ...]]:
    with psycopg.connect(dsn, autocommit=True) as conn:
        return [tuple(row) for row in conn.execute(query, params).fetchall()]  # pyright: ignore[reportArgumentType]


def assert_typed_equals_payload(dsn: str, revision_id: str | UUID) -> dict[str, Any]:
    rev_uuid = RevisionId(UUID(str(revision_id)))
    with psycopg.connect(dsn, autocommit=True) as conn:
        repo = PostgresRevisionRepository(conn)
        p_doc, t_doc = repo.get_document(rev_uuid), repo.load_typed_document(rev_uuid)
        meta = repo.get_meta(rev_uuid)
    assert (t_doc, specification_digest(t_doc)) == (p_doc, meta.content_digest)
    return cast("dict[str, Any]", p_doc)


def upload_file_version(
    box: Sandbox, project_id: UUID, content: bytes, *, filename: str, file_id: UUID | None = None
) -> tuple[UUID, FileVersionId]:
    env = box.env()
    boot = load_bootstrap(None, env, box.home, instance=None)
    app, actor = open_cli_app(boot, environ=env, invocation={}, as_token=None)
    try:
        client = app.client(actor=actor, surface=Surface.CLI)
        st = client.upload_blob(WorkspaceId(box.ws_id), [content], size=len(content), media_type="text/plain")
        b_str = json.dumps(st.to_json())
        head = (
            f'{{"blob":{b_str},"original_filename":"{filename}",'
            '"declared_media_type":"text/markdown","source":{"kind":"upload"},'
        )
        tail = (
            f'"workspace_id":"{box.ws_id}","project_id":"{project_id}","title":"{filename}","origin":"upload"}}'
            if file_id is None
            else f'"file_id":"{file_id}","expected_row_version":2}}'
        )
        cls: Any = artifacts.AddFile if file_id is None else artifacts.AddFileVersion
        cmd = cls.from_json(json.loads(head + tail))
        res = cast("Any", client.dispatch(cmd, idempotency_key=client.new_idempotency_key()))
        return UUID(str(file_id or res.file_id)), FileVersionId(UUID(str(res.file_version_id)))
    finally:
        app.close()


@pytest.fixture(scope="module")
def _db_cache(tmp_path_factory: pytest.TempPathFactory) -> Iterator[list[Any]]:
    state: list[Any] = [tmp_path_factory.mktemp("p05_box"), None, None, None]
    try:
        yield state
    finally:
        if state[1] is not None:
            drop_q = sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(state[2]))
            with psycopg.connect(state[1], autocommit=True, connect_timeout=5) as admin:
                admin.execute(drop_q)


@pytest.fixture
def sandbox(pg_dsn: str, _db_cache: list[Any]) -> Sandbox:
    if _db_cache[3] is not None:
        return cast("Sandbox", _db_cache[3])
    info = {k: str(v) for k, v in conninfo_to_dict(pg_dsn).items()}
    host, dbname = info.get("host", ""), info.get("dbname", "")
    local = host in {"", "localhost", "127.0.0.1", "::1"} or host.startswith("/")
    if not local or not dbname.endswith("_test"):
        pytest.fail("P05.Z e2e creates databases only on a local server through '*_test'", pytrace=False)
    root, db_name = cast("Path", _db_cache[0]), f"skm_t_p05_{os.getpid()}_{uuid4().hex[:8]}"
    _db_cache[1], _db_cache[2] = pg_dsn, db_name
    with psycopg.connect(pg_dsn, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
    dsn = make_conninfo(pg_dsn, dbname=db_name)
    init_res = ok_sub(Sandbox(root, dsn, UUID(int=0)), "init --database-url", dsn, "--host-name", "p05-host")
    assert init_res["already_initialized"] is False
    assert init_res["migrations"]["current"] == discover_migrations()[-1].version
    _db_cache[3] = Sandbox(root, dsn, UUID(str(init_res["workspace"]["workspace_id"])))
    return cast("Sandbox", _db_cache[3])


def _new_project(box: Sandbox, slug: str) -> UUID:
    proj = ok_cli(box, "project create", slug, "--workspace", "personal", "--title", f"Project {slug}")
    ok_cli(box, "use", f"personal/{slug}")
    return UUID(str(proj["project_id"]))


def _write_json(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")
    return path


def _make_item(
    item_id: str | None, key: str, phase: str, title: str, *, deps: list[str] | None = None
) -> dict[str, Any]:
    slug, id_part = key.lower().replace(".", "_"), f'"id":"{item_id}",' if item_id else ""
    raw = (
        f'{{{id_part}"key":"{key}","phase":"{phase}","title":"{title}","summary":"{title} summary.",'
        f'"why":"Required.","work_kind":"ops","scope":{{"include":["src/{slug}/**"],"exclude":[]}},'
        f'"guidance_md":"Guidance {key}.","authority":{{"kind":"routine"}},'
        f'"review":{{"mode":"self","reason":"Unit check."}},"depends_on":{json.dumps(deps or [])},'
        f'"implements":["R1"],"deliverables":["deliverable-{key}"]}}'
    )
    return cast("dict[str, Any]", json.loads(raw))


def _rich_spec(
    *, title: str = "M2 System Architecture", fv_lat: Any = None, fv_pin: Any = None, seed: int = 0
) -> dict[str, Any]:
    pfx = f"0192f5c4-{seed:04x}-"
    doc = cast("dict[str, Any]", json.loads(_BASE_SPEC_JSON.replace("0192f5c4-0000-", pfx)))
    doc["title"] = title
    if fv_lat is not None:
        raw_l = (
            f'{{"id":"{MAT_LAT_ID.replace("0192f5c4-0000-", pfx)}","key":"api-guide","title":"API Guide",'
            f'"kind":"file_version","file_version_id":"{fv_lat}","role":"input","required_for":["execution"],'
            f'"freshness":{{"policy":"latest_at_publish"}},"applies_to":["P1.1"]}}'
        )
        doc["materials"].append(json.loads(raw_l))
    if fv_pin is not None:
        raw_p = (
            f'{{"id":"{MAT_PIN_ID.replace("0192f5c4-0000-", pfx)}","key":"ref-notes","title":"Ref Notes",'
            f'"kind":"file_version","file_version_id":"{fv_pin}","role":"reference","required_for":["review"],'
            f'"freshness":{{"policy":"pinned"}},"applies_to":["P1.2"]}}'
        )
        doc["materials"].append(json.loads(raw_p))
    return doc


def _verify_r2_diff_and_portable_import(sb: Sandbox, tp: Path, r1_id: str, r1_doc: dict[str, Any]) -> None:
    d_noop = str(ok_cli(sb, "plan draft open PLAN1")["draft_id"])
    assert err_cli(sb, 6, "plan publish PLAN1 --reason noop --draft", d_noop)["code"] == "NO_CHANGES"
    new_item = _make_item(None, "P1.2", "P1", "Persist delivery attempts", deps=["P1.1"])
    ops = [
        {"op": "rekey", "target": "P1.2", "new_key": "P1.3"},
        {"op": "patch", "target": "P1.3", "merge_patch": {"summary": "Exponential backoff"}},
        {"op": "add", "kind": "item", "after": "P1.1", "entity": new_item},
    ]
    ch_f = _write_json(tp / "r2_ch.json", {"changes": ops})
    ok_cli(sb, "plan draft save PLAN1 --changes --draft", d_noop, str(ch_f))
    r2 = ok_cli(sb, "plan publish PLAN1 --draft", d_noop, "--reason", "Split delivery step")
    assert r2["revision_no"] == 2
    assert_typed_equals_payload(sb.dsn, r2["revision_id"])
    assert assert_typed_equals_payload(sb.dsn, r1_id) == r1_doc
    diff = ok_cli(sb, "plan diff PLAN1 1 2")
    e2 = {e["entity_id"]: e for e in diff["entities"]}[ITEM_2_ID]
    assert (e2["change"], e2["key_before"], e2["key_after"]) == ("changed", "P1.2", "P1.3")
    assert [e["key_after"] for e in diff["entities"] if e["change"] == "added"] == ["P1.2"]
    exp_path, mat_dir = tp / "r1_export.json", tp / "materials_bundle"
    ok_cli(sb, "plan export PLAN1 --revision 1 --output", str(exp_path))
    mat_dir.mkdir()
    (mat_dir / "api-guide.md").write_bytes(b"# API Guide v1\n")
    (mat_dir / "ref-notes.md").write_bytes(b"# Ref Notes v1\n")
    imp = ok_cli(sb, "plan import --new-plan --remap-ids --materials", str(mat_dir), str(exp_path))
    assert (imp["alias"], imp["counts"]["error"]) == ("PLAN2", 0)
    assert_typed_equals_payload(sb.dsn, ok_cli(sb, "plan publish PLAN2 --reason R1")["revision_id"])


def test_e2e_plan_full_authoring_cycle(sandbox: Sandbox, tmp_path: Path) -> None:
    """Full authoring cycle: create -> edit/validate -> preview -> publish r1/r2 -> diff -> export/import."""
    proj_id = _new_project(sandbox, "p-cycle")
    _, fv_lat = upload_file_version(sandbox, proj_id, b"# API Guide v1\n", filename="api-guide.md")
    _, fv_pin = upload_file_version(sandbox, proj_id, b"# Ref Notes v1\n", filename="ref-notes.md")
    created = ok_cli(sandbox, "plan create --no-draft", "M2 System Architecture")
    assert (created["alias"], created["draft_id"]) == ("PLAN1", None)
    d1_id = str(ok_cli(sandbox, "plan draft open PLAN1")["draft_id"])
    bad_spec = _rich_spec(fv_lat=fv_lat, fv_pin=fv_pin)
    bad_spec["criteria"][0]["checks"] = []
    bad_file = _write_json(tmp_path / "bad_spec.json", bad_spec)
    editor_py = tmp_path / "editor.py"
    ed_src = (
        "import pathlib, sys\n"
        f"pathlib.Path(sys.argv[1]).write_bytes(pathlib.Path({str(bad_file)!r}).read_bytes())\n"
    )
    editor_py.write_text(ed_src, encoding="utf-8")
    ed_env = {"SKM_EDITOR": f"{sys.executable} {editor_py}"}
    edited = ok_sub(sandbox, "plan draft edit PLAN1", extra_env=ed_env)
    assert (edited["edit_version"], edited["counts"]["error"] >= 1) == (2, True)
    val_human = run_sub(sandbox, "plan draft validate PLAN1", json_mode=False)
    assert (val_human.returncode, "criterion_unlinked" in (val_human.stdout + val_human.stderr)) == (1, True)
    assert err_cli(sandbox, 6, "plan publish PLAN1 --reason unready")["code"] == "PLAN_NOT_READY"
    vc_err = err_sub(sandbox, 6, "plan draft edit PLAN1 --expected-version 99", extra_env=ed_env)
    assert (vc_err["code"], Path(vc_err["details"]["path"]).is_file()) == ("VERSION_CONFLICT", True)
    good_file = _write_json(tmp_path / "good_spec.json", _rich_spec(fv_lat=fv_lat, fv_pin=fv_pin))
    saved = ok_cli(sandbox, "plan draft save PLAN1", str(good_file))
    assert (saved["edit_version"], saved["counts"]["error"]) == (3, 0)
    assert ok_cli(sandbox, "plan draft validate PLAN1")["publishable"] is True
    cand_digest = str(ok_cli(sandbox, "plan draft publication-preview PLAN1")["content_digest"])
    rev_q = "SELECT count(*) FROM skm_planning.plan_revisions WHERE plan_id = %s"
    assert rows(sandbox.dsn, rev_q, created["plan_id"]) == [(0,)]
    pub_cmd = f"plan publish PLAN1 --reason R1 --draft {d1_id} --expected-content-digest"
    r1 = ok_sub(sandbox, pub_cmd, cand_digest)
    r1_id = str(r1["revision_id"])
    assert (r1["revision_no"], r1["parent_revision_id"], r1["content_digest"]) == (1, None, cand_digest)
    pins = {m["material_key"]: m["resolved_from"] for m in r1["pinned_materials"]}
    assert pins == {"api-guide": "latest_at_publish", "ref-notes": "pinned"}
    r1_doc = assert_typed_equals_payload(sandbox.dsn, r1_id)
    pin_q = "SELECT count(*) FROM skm_planning.revision_file_bindings WHERE revision_id = %s"
    assert rows(sandbox.dsn, pin_q, r1_id) == [(2,)]
    tree_human = run_sub(sandbox, "plan show PLAN1 --tree", json_mode=False)
    assert (tree_human.returncode, "P1.1/U1  Typed writer unit" in tree_human.stdout) == (0, True)
    assert len(ok_cli(sandbox, "plan preview PLAN1")["waiting"]) >= 1
    assert ok_cli(sandbox, "plan stats PLAN1")["counts"]["items"] == 2
    _verify_r2_diff_and_portable_import(sandbox, tmp_path, r1_id, r1_doc)


def test_e2e_plan_rebase_on_stale_draft(sandbox: Sandbox, tmp_path: Path) -> None:
    """Three-way rebase on a stale draft resolves conflicts, preserves id-space refs, and publishes r3."""
    _new_project(sandbox, "p-rebase")
    ok_cli(sandbox, "plan create", "Rebase Workflow Plan")
    base_spec = _rich_spec(title="Rebase Workflow Plan", seed=2)
    ok_cli(sandbox, "plan draft save PLAN1", str(_write_json(tmp_path / "r1.json", base_spec)))
    r1_id = str(ok_cli(sandbox, "plan publish PLAN1 --reason R1")["revision_id"])
    exp_r1_file = tmp_path / "exported_r1.json"
    ok_cli(sandbox, "plan export PLAN1 --revision 1 --output", str(exp_r1_file))
    d2_id = str(ok_cli(sandbox, "plan draft open PLAN1")["draft_id"])
    d3_id = str(ok_cli(sandbox, "plan draft open PLAN1")["draft_id"])
    spec_d3 = copy.deepcopy(base_spec)
    spec_d3["goal"], spec_d3["items"][1]["key"] = "Goal updated in R2.", "P1.5"
    spec_d3["items"].append(_make_item("0192f5c4-0002-7000-8000-000000000014", "P1.4", "P1", "R2 P1.4"))
    ok_cli(sandbox, "plan draft save PLAN1 --draft", d3_id, str(_write_json(tmp_path / "d3.json", spec_d3)))
    r2_id = str(ok_cli(sandbox, "plan publish PLAN1 --reason R2 --draft", d3_id)["revision_id"])
    spec_d2 = copy.deepcopy(base_spec)
    spec_d2["goal"] = "Conflicting goal in Draft 2."
    i4_d2 = _make_item("0192f5c4-0002-7000-8000-000000000019", "P1.4", "P1", "D2 P1.4", deps=["P1.2"])
    spec_d2["items"].append(i4_d2)
    f_d2 = _write_json(tmp_path / "d2.json", spec_d2)
    d2_dig = str(ok_cli(sandbox, "plan draft save PLAN1 --draft", d2_id, str(f_d2))["document_digest"])
    stale_err = err_cli(sandbox, 6, "plan publish PLAN1 --reason stale --draft", d2_id)
    assert stale_err["code"] == "BASE_REVISION_CHANGED"
    assert stale_err["details"] == {"base_revision_id": r1_id, "current_revision_id": r2_id}
    reb_err = err_cli(sandbox, 6, "plan draft rebase PLAN1 --draft", d2_id)
    assert reb_err["code"] == "REBASE_CONFLICTS"
    c = {x["kind"]: x["conflict_id"] for x in reb_err["details"]["conflicts"]}
    d2_after = ok_cli(sandbox, "plan draft show PLAN1 --draft", d2_id)
    assert (d2_after["edit_version"], d2_after["document_digest"]) == (2, d2_dig)
    reb_cmd = f"plan draft rebase PLAN1 --draft {d2_id} --resolve {c['field']}=yours"
    rebased = ok_sub(sandbox, reb_cmd, "--rekey", f"{c['key_collision']}=P1.6")
    assert (rebased["base_revision_id"], rebased["edit_version"], rebased["resolved"]) == (r2_id, 3, 2)
    d2_doc = ok_cli(sandbox, "plan draft show PLAN1 --draft", d2_id)["document"]
    assert {it["key"]: it for it in d2_doc["items"]}["P1.6"]["depends_on"] == ["P1.5"]
    r3 = ok_cli(sandbox, "plan publish PLAN1 --reason R3 --draft", d2_id)
    assert (r3["revision_no"], r3["parent_revision_id"]) == (3, r2_id)
    assert_typed_equals_payload(sandbox.dsn, r3["revision_id"])
    imp_stale = ok_cli(sandbox, "plan import --new-draft --plan PLAN1", str(exp_r1_file))
    imp_did = str(imp_stale["draft_id"])
    assert (imp_stale["base_revision_id"], imp_stale["stale"]) == (r1_id, True)
    assert (
        err_cli(sandbox, 6, "plan publish PLAN1 --reason s --draft", imp_did)["code"]
        == "BASE_REVISION_CHANGED"
    )
    ok_cli(sandbox, "plan draft abandon PLAN1 --yes --draft", imp_did)
    d_cyc = str(ok_cli(sandbox, "plan draft open PLAN1")["draft_id"])
    cyc_op = {"op": "patch", "target": "P1.1", "merge_patch": {"depends_on": ["P1.5"]}}
    cyc_f = _write_json(tmp_path / "cyc.json", {"changes": [cyc_op]})
    saved_cyc = ok_cli(sandbox, "plan draft save PLAN1 --changes --draft", d_cyc, str(cyc_f))
    assert any(f["code"] == "dependency_cycle" for f in saved_cyc["findings"])
    assert err_cli(sandbox, 6, "plan publish PLAN1 --reason cyc --draft", d_cyc)["code"] == "PLAN_NOT_READY"


def test_e2e_plan_restore_creates_successor(sandbox: Sandbox, tmp_path: Path) -> None:
    """Restore publishes a new successor revision (r4) identical to r1 without mutating past revisions."""
    _new_project(sandbox, "p-restore")
    ok_cli(sandbox, "plan create", "Restore Workflow Plan")
    r1_f = _write_json(tmp_path / "r1.json", _rich_spec(title="R1", seed=3))
    ok_cli(sandbox, "plan draft save PLAN1", str(r1_f))
    r1 = ok_cli(sandbox, "plan publish PLAN1 --reason R1")
    r1_id, r1_digest = str(r1["revision_id"]), str(r1["content_digest"])
    for rev_no in (2, 3):
        d_id = str(ok_cli(sandbox, "plan draft open PLAN1")["draft_id"])
        pf = _write_json(tmp_path / f"p{rev_no}.json", {"title": f"Restore R{rev_no}"})
        ok_cli(sandbox, "plan draft save PLAN1 --patch --draft", d_id, str(pf))
        pub_n = ok_cli(sandbox, f"plan publish PLAN1 --reason R{rev_no} --draft", d_id)
        assert pub_n["revision_no"] == rev_no
    shown = ok_cli(sandbox, "plan show PLAN1")
    plan_id, r3_id = str(shown["plan_id"]), str(shown["current_revision_id"])
    open_before = str(ok_cli(sandbox, "plan draft open PLAN1")["draft_id"])
    hist_q = (
        "SELECT r.revision_no, r.id, r.content_digest, p.document, r.origin, r.restored_from_revision_id "
        "FROM skm_planning.plan_revisions r JOIN skm_planning.revision_payloads p ON p.revision_id = r.id "
        "WHERE r.plan_id = %s ORDER BY r.revision_no"
    )
    history_before = rows(sandbox.dsn, hist_q, plan_id)
    assert [row[0] for row in history_before] == [1, 2, 3]
    stale_cmd = f"plan restore PLAN1 1 --reason Stale --expected-current revision:{r1_id}"
    assert err_cli(sandbox, 6, stale_cmd)["code"] == "BASE_REVISION_CHANGED"
    res_cmd = f"plan restore PLAN1 1 --expected-current revision:{r3_id} --reason"
    r4 = ok_sub(sandbox, res_cmd, "Rollback to R1")
    assert (r4["revision_no"], r4["restored_from_revision_no"], r4["parent_revision_id"]) == (4, 1, r3_id)
    assert r4["content_digest"] == r1_digest
    history_after = rows(sandbox.dsn, hist_q, plan_id)
    assert history_after[:3] == history_before
    r4_row = history_after[3]
    assert (r4_row[0], r4_row[2], r4_row[3]) == (4, r1_digest, history_before[0][3])
    assert (r4_row[4], str(r4_row[5])) == ("restore", r1_id)
    assert_typed_equals_payload(sandbox.dsn, r4["revision_id"])
    ev_q = "SELECT event_type FROM skm_core.domain_events WHERE stream_id = %s ORDER BY recorded_at, id"
    ev_types = [row[0] for row in rows(sandbox.dsn, ev_q, plan_id)]
    assert ev_types[-2:] == [PlanRevisionPublished.event_type, PlanRevisionRestored.event_type]
    assert err_cli(sandbox, 6, "plan restore PLAN1 1 --reason Redundant")["code"] == "NO_CHANGES"
    st_err = err_cli(sandbox, 6, "plan publish PLAN1 --reason s --draft", open_before)
    assert st_err["code"] == "BASE_REVISION_CHANGED"


def _build_large_spec(fv_lat: FileVersionId, fv_pin: FileVersionId) -> dict[str, Any]:
    phases, items = [], []
    for p_idx in range(1, 6):
        pkey, dep = f"P{p_idx}", f',"depends_on":["P{p_idx - 1}"]' if p_idx > 1 else ""
        p_raw = (
            f'{{"id":"0192f5d0-0000-7000-8000-{p_idx:012x}","key":"{pkey}","title":"Phase {p_idx}",'
            f'"goal":"Deliver {pkey}.","design_state":"skeleton"{dep}}}'
        )
        phases.append(json.loads(p_raw))
        for i_idx in range(1, 202):
            seq, ikey = (p_idx - 1) * 201 + i_idx, f"{pkey}.{i_idx}"
            deps = [f"{pkey}.{i_idx - 1}"] if i_idx > 1 else []
            item_id = f"0192f5d1-0000-7000-8000-{seq:012x}"
            items.append(_make_item(item_id, ikey, pkey, f"Item {ikey}", deps=deps))
    spec = _rich_spec(title="Large 1005-Item Specification", fv_lat=fv_lat, fv_pin=fv_pin, seed=4)
    p1 = "Архитектурный контекст большого плана 🧪🚀.\n" * 8
    p2 = "Дополнительные секции проверки окон UTF-8.\n" * 8
    spec["context_md"] = p1 + "Audit the initial 1005-item draft.\n" + p2
    spec.update(phases=phases, items=items, units=[])
    spec["criteria"][0]["owner"], spec["requirements"][0]["owners"] = "P1.1", ["P1.1"]
    return spec


def _verify_large_outline_and_windows(sandbox: Sandbox) -> str:
    seen_keys: list[str] = []
    seen_ids: set[str] = set()
    cursor, pages = None, 0
    while True:
        extra = ("--after", cursor) if cursor else ()
        fn = ok_sub if pages == 0 else ok_cli
        page = fn(sandbox, "plan entities PLAN1 --revision 1 --kind item --limit 200", *extra)
        pages += 1
        seen_keys.extend(it["display_key"] for it in page["items"])
        seen_ids.update(it["entity_id"] for it in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert (pages, len(seen_keys), len(seen_ids)) == (6, 1005, 1005)
    assert (seen_keys[0], seen_keys[-1]) == ("P1.1", "P5.201")
    ent_p3 = ok_cli(sandbox, "plan show PLAN1 --revision 1 --entity P3.150")
    assert (ent_p3["display_key"], ent_p3["entity_kind"]) == ("P3.150", "item")
    win1 = ok_sub(sandbox, "plan text PLAN1 plan /context_md --revision 1 --max-bytes 90")
    assert (win1["truncated"], win1["omitted_bytes"] > 0) == (True, True)
    w2_cmd = "plan text PLAN1 plan /context_md --revision 1 --max-bytes 4096 --offset-bytes"
    win2 = ok_cli(sandbox, w2_cmd, str(win1["next_offset_bytes"]))
    assert win2["next_offset_bytes"] is None
    full_ctx = str(win1["text"]) + str(win2["text"])
    expected_digest = f"sha256:{hashlib.sha256(full_ctx.encode('utf-8')).hexdigest()}"
    assert win1["text_digest"] == expected_digest
    return expected_digest


def _verify_service_plan_and_catalog(sandbox: Sandbox, proj_id: UUID) -> None:
    env = sandbox.env()
    boot = load_bootstrap(None, env, sandbox.home, instance=None)
    app, actor = open_cli_app(boot, environ=env, invocation={}, as_token=None)
    try:
        clock = SystemClock()
        now = clock.now()
        with app.uow_factory(RequestMeta("req_" + "1" * 26, Surface.CLI, None, now), readonly=False) as uow:
            target = planning_public.CommitReviewTarget("commits", "a" * 40, "b" * 40)
            rr_spec = planning_public.ReviewRequestSpec(uuid4(), "main", target, "default", "Audit SQL.")
            rr_meta = planning_public.publish_review_request_revision(
                uow, actor, ProjectId(proj_id), rr_spec, ids=Uuid7Generator(clock), now=now
            )
            rr_summary = planning_public.get_plan_summary(uow, rr_meta.plan_id)
            uow.commit()
        assert rr_meta.plan_purpose == "review_requests"
        assert str(rr_summary.current_revision_id) == str(rr_meta.revision_id)
    finally:
        app.close()
    assert [p["alias"] for p in ok_cli(sandbox, "plan list --all")["items"]] == ["PLAN1"]
    assert err_cli(sandbox, 6, "plan draft open", str(rr_meta.plan_id))["code"] == "INVALID_TRANSITION"
    catalog = json.loads((ROOT / "src/skm/schemas/planning/data/finding-codes.json").read_text("utf-8"))
    mapped_legacy = {leg for entry in catalog["codes"] for leg in entry.get("legacy_codes", [])}
    dropped = set(catalog["dropped_legacy_codes"])
    assert len(mapped_legacy | dropped) == 68
    assert {"execution_commit_instruction", "execution_rules_conflict"}.issubset(dropped)


def test_e2e_planning_large_spec_queries(sandbox: Sandbox, tmp_path: Path) -> None:
    """Large spec (>= 1000 items, planning §15): outline pages, UTF-8 windows, atomic batch, material CAS."""
    proj_id = _new_project(sandbox, "p-large")
    file_1_id, fv_lat_1 = upload_file_version(sandbox, proj_id, b"# Guide v1\n", filename="large-guide.md")
    _, fv_pin_1 = upload_file_version(sandbox, proj_id, b"# Pinned v1\n", filename="large-pinned.md")
    plan_id = str(ok_cli(sandbox, "plan create", "Large 1005-Item Specification")["plan_id"])
    large_spec = _build_large_spec(fv_lat_1, fv_pin_1)
    ok_cli(sandbox, "plan draft save PLAN1", str(_write_json(tmp_path / "large.json", large_spec)))
    r1 = ok_cli(sandbox, "plan publish PLAN1 --reason", "Publish 1005-item R1")
    r1_id, r1_digest = str(r1["revision_id"]), str(r1["content_digest"])
    item_q = "SELECT count(*) FROM skm_planning.item_specs WHERE revision_id = %s"
    assert rows(sandbox.dsn, item_q, r1_id) == [(1005,)]
    assert_typed_equals_payload(sandbox.dsn, r1_id)
    expected_ctx_digest = _verify_large_outline_and_windows(sandbox)
    d2_id = str(ok_cli(sandbox, "plan draft open PLAN1")["draft_id"])
    d_page1 = ok_cli(sandbox, "plan entities PLAN1 --expected-version 1 --limit 50 --draft", d2_id)
    p_f = _write_json(tmp_path / "p.json", {"goal": "v2"})
    ok_cli(sandbox, "plan draft save PLAN1 --patch --draft", d2_id, str(p_f))
    vcp_cmd = f"plan entities PLAN1 --expected-version 1 --draft {d2_id} --after"
    vcp = err_cli(sandbox, 6, vcp_cmd, str(d_page1["next_cursor"]))
    vct = err_cli(sandbox, 6, "plan text PLAN1 plan /context_md --expected-version 1 --draft", d2_id)
    assert (vcp["code"], vct["code"]) == ("VERSION_CONFLICT", "VERSION_CONFLICT")
    d2_before = ok_cli(sandbox, "plan draft show PLAN1 --draft", d2_id)
    bad_ops = [
        {"op": "patch", "target": "P1.1", "merge_patch": {"summary": "Rolled back"}},
        {"op": "patch", "target": "P1.1", "merge_patch": {"id": str(uuid4())}},
    ]
    bad_f = _write_json(tmp_path / "bad_batch.json", {"changes": bad_ops})
    bad_err = err_cli(sandbox, 1, "plan draft save PLAN1 --changes --draft", d2_id, str(bad_f))
    assert bad_err["code"] == "FIELD_OWNED"
    d2_after = ok_cli(sandbox, "plan draft show PLAN1 --draft", d2_id)
    assert d2_after["edit_version"] == d2_before["edit_version"]
    assert d2_after["document_digest"] == d2_before["document_digest"]
    item_p1_2_id = str(large_spec["items"][1]["id"])
    new_chk = json.loads(
        '{"key":"V1","owner":"P1.202","title":"Check","category":"acceptance","kind":"manual",'
        '"required":true,"definition":{"instructions_md":"Verify.","actor_role":"owner",'
        '"allowed_verdicts":["pass","fail"]}}'
    )
    rep_op = json.loads(
        f'{{"op":"replace_text","target":"plan","pointer":"/context_md",'
        f'"expected_text_digest":"{expected_ctx_digest}",'
        '"old_text":"Audit the initial 1005-item draft.","new_text":"Validated the 1005-item atomic batch."}'
    )
    a_ops = [
        {"op": "rekey", "target": f"entity:{item_p1_2_id}", "new_key": "P1.202"},
        rep_op,
        {"op": "add", "kind": "check", "entity": new_chk},
        {"op": "patch", "target": "P1.3", "merge_patch": {"depends_on": ["P1.1"]}},
        {"op": "patch", "target": "P1.202", "merge_patch": {"depends_on": ["P1.1", "P1.3"]}},
    ]
    ab_f = _write_json(tmp_path / "ab.json", {"changes": a_ops})
    batch_saved = ok_cli(sandbox, "plan draft save PLAN1 --changes --draft", d2_id, str(ab_f))
    assert (batch_saved["edit_version"], batch_saved["counts"]["error"]) == (3, 0)
    prev1_cmd = "plan draft publication-preview PLAN1 --draft"
    digest_1 = str(ok_cli(sandbox, prev1_cmd, d2_id)["content_digest"])
    _, fv_lat_2 = upload_file_version(sandbox, proj_id, b"# v2\n", filename="g.md", file_id=file_1_id)
    assert fv_lat_2 != fv_lat_1
    c_cmd = f"plan publish PLAN1 --reason Stale --draft {d2_id} --expected-content-digest"
    cand_err = err_cli(sandbox, 6, c_cmd, digest_1)
    assert (cand_err["code"], cand_err["details"]["reason"]) == ("VERSION_CONFLICT", "candidate_changed")
    rev_q = "SELECT count(*) FROM skm_planning.plan_revisions WHERE plan_id = %s"
    assert rows(sandbox.dsn, rev_q, plan_id) == [(1,)]
    digest_2 = str(ok_cli(sandbox, prev1_cmd, d2_id)["content_digest"])
    assert digest_2 != digest_1
    p2_cmd = f"plan publish PLAN1 --reason R2 --draft {d2_id} --expected-content-digest"
    r2_doc = assert_typed_equals_payload(sandbox.dsn, ok_cli(sandbox, p2_cmd, digest_2)["revision_id"])
    assert "Validated the 1005-item atomic batch." in r2_doc["context_md"]
    r1_doc = assert_typed_equals_payload(sandbox.dsn, r1_id)
    assert specification_digest(normalize_document(r1_doc)) == r1_digest
    id_q = (
        "SELECT entity_kind, first_revision_id FROM skm_planning.plan_entity_identities "
        "WHERE plan_id = %s AND entity_id = %s"
    )
    assert rows(sandbox.dsn, id_q, plan_id, item_p1_2_id) == [("item", UUID(r1_id))]
    _verify_service_plan_and_catalog(sandbox, proj_id)
