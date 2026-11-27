"""End-to-end CLI tests for ``skm ext`` on PostgreSQL (extensions §7, §9, §10)."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from skm.adapters.resources.builtin_packs import PackagedBuiltinPacks
from skm.adapters.resources.pack_reader import FilesystemPackReader
from skm.adapters.resources.upstream_http import HttpUpstreamFetcher
from skm.application_bus.host import HostServices
from skm.bootstrap.composition import open_cli_app
from skm.bootstrap.modules import MANIFESTS
from skm.entrypoints.cli.context import CliOptions
from skm.entrypoints.cli.main import Backend, BackendFactory, app_backend
from skm.entrypoints.cli.main import main as cli_main
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId
from skm.kernel.ports_uow import Surface
from skm.kernel.tokens import TokenEstimator
from skm.modules.extensions.ports import BuiltinPacks, PackReader, UpstreamFetcher
from skm.platform.config.bootstrap import load_bootstrap

pytestmark = [pytest.mark.e2e, pytest.mark.pg]

PACKS_ROOT = Path(__file__).resolve().parents[2] / "resources/packs"
ENTRY = "import sys; from skm.entrypoints.cli.main import main; sys.exit(main())"
PASSED = ("PATH", "PYTHONPATH", "LANG", "LC_ALL", "TMPDIR")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _checked_admin(dsn: str) -> None:
    info = {key: str(value) for key, value in conninfo_to_dict(dsn).items()}
    host = info.get("host", "")
    local = host in {"", "localhost", "127.0.0.1", "::1"} or host.startswith("/")
    if not local or not info.get("dbname", "").endswith("_test"):
        pytest.fail("e2e tests create databases only on a local server through '*_test'", pytrace=False)


@dataclass(frozen=True)
class ScratchDb:
    admin_dsn: str
    name: str
    dsn: str


@pytest.fixture
def scratch_db(pg_dsn: str) -> Iterator[ScratchDb]:
    _checked_admin(pg_dsn)
    name = f"skm_t_ext_{os.getpid()}_{uuid4().hex[:8]}"
    with psycopg.connect(pg_dsn, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            yield ScratchDb(pg_dsn, name, make_conninfo(pg_dsn, dbname=name))
        finally:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


class _TestTokenEstimator:
    estimator_id = "heuristic-v1"

    def estimate(self, text: str) -> int:
        return max(1, len(text) // 4) if text else 0


@dataclass
class CliSandbox:
    root: Path
    dsn: str
    builtin_root: Path | None = None
    urlopen: Callable[..., Any] | None = None
    extra_gateways: dict[type[object], object] = field(default_factory=dict)

    @property
    def home(self) -> Path:
        return self.root / "home"

    def env(self) -> dict[str, str]:
        env = {name: os.environ[name] for name in PASSED if name in os.environ}
        env.update(
            HOME=str(self.home),
            XDG_CONFIG_HOME=str(self.root / "config"),
            XDG_STATE_HOME=str(self.root / "state"),
            XDG_DATA_HOME=str(self.root / "data"),
            USER="ext-owner",
            PYTHONDONTWRITEBYTECODE="1",
            SKM_DATABASE_URL=self.dsn,
        )
        return env

    def backend_factory(self) -> BackendFactory:
        def _open(options: CliOptions, environ: Mapping[str, str]) -> Backend:
            home = Path(environ["HOME"]) if "HOME" in environ else self.home
            bootstrap = load_bootstrap(options.bootstrap, environ, home, instance=options.instance)
            invocation: dict[str, Any] = {
                "set": list(options.sets),
                "config": options.config or [],
            }
            app, actor = open_cli_app(
                bootstrap,
                environ=environ,
                invocation=invocation,
                as_token=options.actor_hint,
            )
            cp_entries = dict(app.bus._gateways.entries)
            cp_entries[BuiltinPacks] = PackagedBuiltinPacks(self.builtin_root)
            cp_entries[TokenEstimator] = _TestTokenEstimator()
            app.bus._gateways = GatewayTable(cp_entries, "control_plane_gateway")

            host_id = (
                HostId(bootstrap.host_id) if isinstance(bootstrap.host_id, UUID) else HostId(app.instance_id)
            )
            host = HostServices(
                host_id=host_id,
                surface=Surface.CLI,
                gateways=GatewayTable(
                    {
                        PackReader: FilesystemPackReader(),
                        UpstreamFetcher: HttpUpstreamFetcher(urlopen=self.urlopen),
                    },
                    "host_gateway",
                ),
                host_config=dict,
                operations={spec.name: spec for manifest in MANIFESTS for spec in manifest.host_operations},
            )
            app = replace(app, host=host)
            return replace(app_backend(app, actor), state_dir=bootstrap.state_dir)

        return _open


def run_cli(box: CliSandbox, *argv: str) -> tuple[int, dict[str, Any]]:
    out = io.StringIO()
    err = io.StringIO()
    code = cli_main(
        ["--json", *argv],
        stdout=out,
        stderr=err,
        environ=box.env(),
        backend=box.backend_factory(),
    )
    raw = out.getvalue().strip()
    assert raw, f"empty stdout (code={code}, stderr={err.getvalue()})"
    parsed = cast("dict[str, Any]", json.loads(raw))
    if code == 70:
        err2 = io.StringIO()
        cli_main(
            ["-vv", *argv],
            stdout=io.StringIO(),
            stderr=err2,
            environ=box.env(),
            backend=box.backend_factory(),
        )
        parsed["_traceback"] = err2.getvalue()
    return code, parsed


def run_cli_human(box: CliSandbox, *argv: str) -> tuple[int, str]:
    out = io.StringIO()
    err = io.StringIO()
    code = cli_main(
        list(argv),
        stdout=out,
        stderr=err,
        environ=box.env(),
        backend=box.backend_factory(),
    )
    return code, out.getvalue()


def ok(box: CliSandbox, *argv: str) -> dict[str, Any]:
    code, payload = run_cli(box, *argv)
    assert code == 0, json.dumps(payload, indent=2)
    assert payload["ok"] is True
    return cast("dict[str, Any]", payload["result"])


def _write_pack(
    pack_dir: Path,
    *,
    slug: str = "team-pack",
    version: str = "1.0.0",
    trust: str = "operator",
    files: dict[str, bytes],
) -> None:
    pack_toml = (
        'schema = "urn:skm:extensions:pack:v1"\n'
        f'slug = "{slug}"\n'
        f'version = "{version}"\n'
        f'title = "Pack {slug}"\n'
        'description = "E2E test pack"\n'
        'publisher = "skm-test"\n'
        f'trust = "{trust}"\n'
        'license = "MIT"\n'
        'requires_skm = ">=0.1.0,<1"\n'
    )
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "pack.toml").write_text(pack_toml, encoding="utf-8")
    for rel, content in files.items():
        dest = pack_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)


def _skill_manifest(
    key: str, *, url: str | None = None, sha: str | None = None, strategy: str = "notify"
) -> bytes:
    base = f'schema = "urn:skm:extensions:skill-manifest:v1"\nkey = "{key}"\nversion = "1.0.0"\n'
    if url is None or sha is None:
        return base.encode("utf-8")
    prov = (
        "\n[provenance]\n"
        'source = "upstream"\n'
        'repo = "https://example.com/skills"\n'
        f'strategy = "{strategy}"\n'
        f'upstream_sha = "{sha}"\n'
        "[[provenance.files]]\n"
        'path = "SKILL.md"\n'
        f'url = "{url}"\n'
        f'sha256 = "{sha}"\n'
        'fetched_at = "2026-01-15"\n'
    )
    return (base + prov).encode("utf-8")


class _MockHttpResp:
    def __init__(self, body: bytes) -> None:
        self._buf = io.BytesIO(body)
        self.status = 200
        self.headers = {"Content-Length": str(len(body))}

    def read(self, amt: int = -1) -> bytes:
        return self._buf.read(amt)

    def __enter__(self) -> _MockHttpResp:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _count_rows(dsn: str, schema: str, table: str) -> int:
    query = sql.SQL("SELECT count(*) FROM {}.{}").format(sql.Identifier(schema), sql.Identifier(table))
    with psycopg.connect(dsn, autocommit=True) as conn:
        row = conn.execute(query).fetchone()
        return int(row[0]) if row else 0


def test_extensions_cli_lifecycle_and_upstream_check_without_auto_apply(  # noqa: PLR0915
    tmp_path: Path,
    scratch_db: ScratchDb,
) -> None:
    builtin_root = tmp_path / "builtin_packs"
    _write_pack(
        builtin_root / "core",
        slug="core",
        version="1.0.0",
        trust="builtin",
        files={
            "skills/core-base/manifest.toml": _skill_manifest("core-base"),
            "skills/core-base/SKILL.md": b"# Core base skill\n",
        },
    )

    box = CliSandbox(tmp_path / "sandbox", scratch_db.dsn, builtin_root=builtin_root)
    box.home.mkdir(parents=True)

    # 1. Initialize instance and sync built-in core pack
    init_res = ok(box, "init", "--database-url", scratch_db.dsn, "--host-name", "ext-e2e")
    assert init_res["already_initialized"] is False

    sync_res = ok(box, "ext", "sync")
    assert any(item["slug"] == "core" for item in sync_res["installed"])

    # Verify subprocess CLI invocation works end-to-end as well
    sub = subprocess.run(
        [sys.executable, "-c", ENTRY, "--json", "ext", "list"],
        env=box.env(),
        cwd=box.root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert sub.returncode == 0, sub.stdout + sub.stderr
    packs_initial = json.loads(sub.stdout)["result"]["items"]
    initial_slugs = {pack["slug"] for pack in packs_initial}
    packaged_slugs = {
        tomllib.loads(pack.manifest_text)["slug"] for pack in PackagedBuiltinPacks(PACKS_ROOT).payloads()
    }
    assert initial_slugs == packaged_slugs
    assert len(packs_initial) == len(initial_slugs)

    # 2. Prepare external pack with upstream-tracked and local skills
    clean_body = b"# Clean Skill v1\nFollow the specification.\n"
    fork_body = b"# Fork Skill v1\nLocal fork baseline.\n"
    dead_body = b"# Unreachable Skill v1\nTracked from unreachable host.\n"
    local_body = b"# Local Skill\nAuthored locally.\n"

    url_clean = "https://example.com/skills/clean/SKILL.md"
    url_fork = "https://example.com/skills/fork/SKILL.md"
    url_dead = "https://example.com/skills/dead/SKILL.md"

    pack_dir = tmp_path / "team-pack"
    _write_pack(
        pack_dir,
        slug="team-pack",
        version="1.0.0",
        files={
            "skills/clean/manifest.toml": _skill_manifest(
                "clean", url=url_clean, sha=_sha(clean_body), strategy="notify"
            ),
            "skills/clean/SKILL.md": clean_body,
            "skills/forked/manifest.toml": _skill_manifest(
                "forked", url=url_fork, sha=_sha(fork_body), strategy="fork"
            ),
            "skills/forked/SKILL.md": fork_body,
            "skills/dead/manifest.toml": _skill_manifest(
                "dead", url=url_dead, sha=_sha(dead_body), strategy="replace"
            ),
            "skills/dead/SKILL.md": dead_body,
            "skills/local-one/manifest.toml": _skill_manifest("local-one"),
            "skills/local-one/SKILL.md": local_body,
        },
    )

    # 3. Dry-run install does not persist pack
    dry = ok(box, "ext", "install", str(pack_dir), "--trust", "operator", "--dry-run")
    assert dry["status"] == "dry_run"
    assert ok(box, "ext", "list")["items"] == packs_initial

    # 4. Real install with --no-quarantine and enable pack in config
    installed = ok(box, "ext", "install", str(pack_dir), "--trust", "operator", "--no-quarantine")
    assert installed["status"] == "installed"
    assert installed["slug"] == "team-pack"
    assert len(installed["resources"]) == 4

    ok(
        box,
        "config",
        "set",
        "extensions.packs.enabled",
        '["core", "team-pack"]',
        "--scope",
        "instance",
    )

    # 5. List, show (both bare slug and pack:<slug>), and resolve resources
    res_list = ok(box, "ext", "list", "--kind", "skill", "--pack", "team-pack", "--scope", "instance")
    assert {item["key"] for item in res_list["items"]} == {"clean", "forked", "dead", "local-one"}

    h_code, h_table = run_cli_human(box, "ext", "list", "--kind", "skill", "--pack", "team-pack")
    assert h_code == 0
    assert "digest" in h_table
    assert "sha256:" in h_table

    pack_view = ok(box, "ext", "show", "pack:team-pack")
    assert pack_view["slug"] == "team-pack"

    skill_view = ok(box, "ext", "show", "skill:clean", "--bodies")
    assert skill_view["key"] == "clean"
    assert "SKILL.md" in (skill_view.get("bodies") or {})

    resolved = ok(box, "ext", "resolve", "skill:clean")
    assert resolved["candidates"][0]["pack"] == "team-pack"
    clean_rv_id = resolved["chosen"]["resource_version_id"]

    # 6. Quarantine and release lifecycle
    q_res = ok(box, "ext", "quarantine", clean_rv_id, "--reason", "security review")
    assert q_res["quarantined"] is True

    while_quarantined = ok(box, "ext", "resolve", "skill:clean")
    assert while_quarantined["chosen"] is None
    assert any(c["reason"] == "quarantined" for c in while_quarantined["candidates"])

    q_show_code, q_show_err = run_cli(box, "ext", "show", "skill:clean")
    assert q_show_code == 6
    assert q_show_err["error"]["code"] == "RESOURCE_QUARANTINED"

    rel_res = ok(box, "ext", "release", clean_rv_id, "--reason", "cleared by owner")
    assert rel_res["quarantined"] is False

    resolved_again = ok(box, "ext", "resolve", "skill:clean")
    assert resolved_again["chosen"]["resource_version_id"] == clean_rv_id

    # 7. Upstream check is read-only, idempotent, and never auto-applies or treats unreachable as up_to_date
    remote_fork_updated = b"# Fork Skill v2 (remote changed)\n"

    def fake_urlopen(req: Any, timeout: float = 0.0) -> _MockHttpResp:
        url = req.full_url
        if url == url_clean:
            return _MockHttpResp(clean_body)
        if url == url_fork:
            return _MockHttpResp(remote_fork_updated)
        raise urllib.error.URLError(f"unreachable: {url}")

    box.urlopen = fake_urlopen

    events_before = _count_rows(scratch_db.dsn, "skm_core", "domain_events")
    versions_before = _count_rows(scratch_db.dsn, "skm_extensions", "resource_versions")

    # Test both positional PACK and --pack flag
    up1 = ok(box, "ext", "upstream", "check", "team-pack")
    up2 = ok(box, "ext", "upstream", "check", "--pack", "team-pack")
    assert up1 == up2

    up_h_code, up_h_table = run_cli_human(box, "ext", "upstream", "check", "team-pack")
    assert up_h_code == 0
    assert "upstream_digest" in up_h_table
    assert _sha(remote_fork_updated) in up_h_table

    by_key = {item["key"]: item for item in up1["items"]}
    assert by_key["clean"]["status"] == "up_to_date"
    assert by_key["clean"]["strategy"] == "notify"

    assert by_key["forked"]["status"] == "changed"
    assert by_key["forked"]["strategy"] == "fork"
    assert by_key["forked"]["files"][0]["recorded_sha256"] == _sha(fork_body)
    assert by_key["forked"]["files"][0]["upstream_sha256"] == _sha(remote_fork_updated)

    assert by_key["dead"]["status"] == "unreachable"
    assert by_key["dead"]["strategy"] == "replace"
    assert by_key["dead"]["files"][0]["upstream_sha256"] is None

    assert by_key["local-one"]["status"] == "local"
    assert by_key["local-one"]["files"] == []

    assert _count_rows(scratch_db.dsn, "skm_core", "domain_events") == events_before
    assert _count_rows(scratch_db.dsn, "skm_extensions", "resource_versions") == versions_before

    # Local content of forked skill was NOT overwritten by upstream check
    fork_after = ok(box, "ext", "show", "skill:forked", "--bodies")
    assert fork_after["bodies"]["SKILL.md"] == fork_body.decode("utf-8")

    # 8. Uninstall / retire pack version
    uninstalled = ok(box, "ext", "uninstall", "team-pack@1.0.0")
    assert uninstalled["state"] == "retired"
