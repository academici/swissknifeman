"""Local CLI rendering, cleanup boundaries, and mismatched PID records."""

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import asdict, replace
from datetime import timedelta
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from integration.git.conftest import make_repo
from skm.adapters.git.environments.worktree import WorktreeManager
from skm.application_bus.client import SkmClient
from skm.bootstrap.lifecycle import LocalProcesses
from skm.bootstrap.local_cleanup import clean_files, clean_worktrees
from skm.entrypoints.cli.main import main
from skm.kernel.ids import AttemptId, RepositoryId
from skm.modules.execution.domain.environment import EnvironmentKind, attempt_branch
from skm.modules.execution.host.environment import EnvironmentMount, EnvironmentSpec
from skm.modules.execution.public import (
    AttemptView,
    ExecutionEnvironmentsView,
    GetAttempt,
    ListExecutionEnvironments,
)
from skm.platform.config.bootstrap import BOOTSTRAP_URN, BootstrapConfig, load_bootstrap
from skm.platform.process.identity import identity_of
from skm.platform.system_clock import SystemClock


@pytest.fixture
def profile(tmp_path: Path) -> tuple[BootstrapConfig, dict[str, str]]:
    config = tmp_path / "bootstrap.toml"
    config.write_text(
        f'schema = "{BOOTSTRAP_URN}"\ninstance_id = "{uuid4()}"\n'
        f'[paths]\nstate_dir = "{tmp_path / "state"}"\nblobs_root = "{tmp_path / "blobs"}"\n'
        '[access]\nmode = "embedded"\n'
        '[database]\nurl = "secret://env/SKM_DATABASE_URL"\n'
    )
    env = {"HOME": str(tmp_path), "SKM_BOOTSTRAP": str(config), "SKM_DATABASE_URL": "postgresql://local/db"}
    return load_bootstrap(str(config), env, tmp_path), env


def invoke(env: Mapping[str, str], *args: str) -> tuple[int, str, str]:
    out, err = StringIO(), StringIO()
    code = main(list(args), stdout=out, stderr=err, environ=env)
    return code, out.getvalue(), err.getvalue()


def file_at(path: Path, *, age_days: int = 0, text: str = "data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    stamp = (SystemClock().now() - timedelta(days=age_days)).timestamp()
    os.utime(path, (stamp, stamp))
    return path


def snapshot(root: Path) -> dict[Path, tuple[int, int, int]]:
    return {
        path.relative_to(root): (info.st_ino, info.st_mtime_ns, info.st_size)
        for path in root.rglob("*")
        if (info := path.lstat())
    }


def test_clean_without_targets_and_dry_run(profile: tuple[BootstrapConfig, dict[str, str]]) -> None:
    config, env = profile
    log = file_at(config.state_dir / "logs" / "serve.log", age_days=21)
    fresh = file_at(log.with_name("worker.log"), age_days=2)
    before = snapshot(config.state_dir)
    code, out, err = invoke(env, "local", "clean", "--yes")
    assert (code, err) == (0, "")
    assert "Select cleanup targets" in out
    assert snapshot(config.state_dir) == before

    code, out, err = invoke(env, "local", "clean", "--logs", "--dry-run", "--json")
    assert (code, err) == (0, "")
    assert json.loads(out)["result"]["targets"] == {"logs": [str(log)]}
    assert snapshot(config.state_dir) == before

    code, out, err = invoke(env, "local", "clean", "--logs", "--older-than", "1d", "--yes")
    assert (code, err) == (0, "")
    assert "removed logs" in out
    assert not log.exists()
    assert not fresh.exists()


def test_clean_staging_and_materialized_never_remove_final_objects(
    profile: tuple[BootstrapConfig, dict[str, str]],
) -> None:
    config, _ = profile
    root = config.blobs_root
    final = file_at(root / str(uuid4()) / "objects" / "ab" / ("ab" * 32), age_days=45)
    staged = file_at(root / "staging" / str(uuid4()) / f"{uuid4()}.part", age_days=3)
    recent = file_at(staged.parent / f"{uuid4()}.part")
    linked = root / "staging" / str(uuid4())
    linked.symlink_to(final)
    terminal, active = uuid4(), uuid4()
    old = file_at(config.materialized_root / str(terminal) / str(uuid4()))
    running = file_at(config.materialized_root / str(active) / str(uuid4()))

    def ask(query: GetAttempt) -> object:
        return SimpleNamespace(state="completed" if query.attempt_id == terminal else "running")

    client = cast("SkmClient", SimpleNamespace(ask=ask))
    before = snapshot(config.state_dir.parent)
    processes = LocalProcesses(config)
    for dry_run in (True, False):
        assert clean_files(
            config,
            processes,
            client,
            log_age=None,
            staging_age=timedelta(hours=24),
            materialized=True,
            dry_run=dry_run,
        ) == {"staging": [str(staged)], "materialized": [str(old.parent)]}
        if dry_run:
            assert snapshot(config.state_dir.parent) == before
    assert final.read_text() == "data"
    assert recent.is_file()
    assert linked.is_symlink()
    assert running.is_file()
    assert not staged.exists()
    assert not old.parent.exists()


def test_logs_escape_controls_and_token_requires_explicit_reveal(
    profile: tuple[BootstrapConfig, dict[str, str]],
) -> None:
    config, env = profile
    token = "opaque-local-owner-secret"
    token_file = file_at(config.state_dir / "secrets" / "owner.token", text=token + "\n")
    token_file.parent.chmod(0o700)
    token_file.chmod(0o600)
    worker_token = "skm_abcdefgh_" + "k" * 43
    file_at(config.state_dir / "logs" / "serve.log", text=f"old\n\x1b[31m{token} {worker_token}\n")
    code, out, err = invoke(env, "local", "logs", "serve", "--lines", "1", "--follow")
    assert code == 0
    assert not err
    assert "old" not in out
    assert token not in out
    assert worker_token not in out
    assert "\x1b" not in out

    code, out, err = invoke(env, "local", "token", "--json")
    assert (code, err) == (0, "")
    assert json.loads(out)["result"] == {"path": str(token_file)}
    assert token not in out
    code, out, err = invoke(env, "local", "token", "--show", "--json")
    assert (code, err) == (0, "")
    assert json.loads(out)["result"]["token"] == token
    assert invoke(env, "local", "token", "--show") == (0, token + "\n", "")


@pytest.mark.parametrize("field", ["start_ticks", "boot_id"])
def test_stale_identity_never_signals_real_process(
    profile: tuple[BootstrapConfig, dict[str, str]],
    field: str,
) -> None:
    config, _ = profile
    processes = LocalProcesses(config)
    with (
        processes.lock().hold(timeout_seconds=1),
        subprocess.Popen(  # noqa: TID251 -- a real live PID with other identity facts
            [sys.executable, "-c", "import time; time.sleep(60)"]
        ) as victim,
    ):
        try:
            identity = identity_of(victim.pid)
            assert identity is not None
            assert identity.start_ticks is not None
            record = {**asdict(identity), "role": "worker", "instance_id": str(config.instance_id)}
            record[field] = identity.start_ticks + 1 if field == "start_ticks" else str(uuid4())
            (processes.pids / "worker.pid").write_text(json.dumps(record))
            assert processes.lookup("worker") is None
            processes.stop("worker", grace=0)
            assert victim.poll() is None
        finally:
            victim.terminate()


def test_serve_rejects_multiple_workers_before_loading_bootstrap() -> None:
    code, out, err = invoke({}, "serve", "--workers", "2", "--json")
    assert code == 1
    assert not err
    assert json.loads(out)["error"]["code"] == "CONFIG_INVALID"


def test_clean_worktrees_plans_real_git_removal_and_marks_only_terminal_attempts(
    profile: tuple[BootstrapConfig, dict[str, str]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = replace(profile[0], host_id=uuid4())
    repo = tmp_path / "repo"
    git, base = make_repo(repo)
    manager = WorktreeManager(git, worktrees_root=config.worktrees_root)
    active, terminal = AttemptId(uuid4()), AttemptId(uuid4())
    mount = EnvironmentMount("main", RepositoryId(uuid4()), str(repo), base)
    environment_rows: list[dict[str, object]] = []
    locators: dict[AttemptId, str] = {}
    for attempt in (active, terminal):
        prepared = manager.prepare(
            EnvironmentSpec(
                attempt,
                EnvironmentKind.GIT_WORKTREE,
                (mount,),
                attempt_branch(attempt),
                config.worktrees_root,
                None,
                None,
            )
        )
        locators[attempt] = prepared.locator
        environment_rows.append(
            {
                "environment_id": str(prepared.environment_id),
                "attempt_id": str(attempt),
                "kind": "git_worktree",
                "state": "discarded",
                "removable": True,
                "discarded_at": (SystemClock().now() - timedelta(days=10)).isoformat(),
                "local_locator": prepared.locator,
            }
        )
    removed: list[str] = []

    def ask(query: object) -> object:
        if isinstance(query, GetAttempt):
            return AttemptView.from_json(
                {
                    "attempt_id": str(query.attempt_id),
                    "attempt_no": 1,
                    "state": "completed" if query.attempt_id == terminal else "running",
                    "worker_id": None,
                    "host_id": str(config.host_id),
                    "started_at": SystemClock().now().isoformat(),
                    "finished_at": None,
                    "end_reason": "ACCEPTED",
                    **dict.fromkeys(
                        (
                            "stages",
                            "steps",
                            "outputs",
                            "checks",
                            "reviews",
                            "findings",
                            "effects",
                            "recoveries",
                        ),
                        (),
                    ),
                }
            )
        assert isinstance(query, ListExecutionEnvironments)
        assert query.limit == 200
        assert query.removable_only is True
        page = environment_rows[:1] if query.after is None else environment_rows[1:]
        return ExecutionEnvironmentsView.from_json(
            {
                "items": [row for row in page if str(row["environment_id"]) not in removed],
                "next_after": "next-page" if query.after is None else None,
            }
        )

    def dispatch(command: dict[str, object], *, idempotency_key: str) -> object:
        assert idempotency_key.startswith("idem_")
        assert command["host_id"] == str(config.host_id)
        assert not Path(locators[terminal]).exists()
        removed.extend(cast("list[str]", command["environment_ids"]))
        return {"marked": len(removed)}

    client = cast("SkmClient", SimpleNamespace(ask=ask, dispatch=dispatch))
    before = snapshot(tmp_path)
    active_skip = {locators[active]: "terminal ownership unconfirmed"}
    assert clean_worktrees(config, client, {}, dry_run=True) == {
        "planned": [locators[terminal]],
        "skipped": active_skip,
    }
    assert removed == []
    assert snapshot(tmp_path) == before
    with subprocess.Popen(  # noqa: TID251 -- a real live cwd inside this attempt
        [sys.executable, "-c", "import time; time.sleep(60)"], cwd=locators[terminal]
    ) as child:
        try:
            preview = cast("dict", clean_worktrees(config, client, {}, dry_run=True))
            assert preview["skipped"][locators[terminal]] == "containment unconfirmed"
            assert cast("dict", clean_worktrees(config, client, {}, dry_run=False))["marked"] == 0
        finally:
            child.terminate()

    marker = config.state_dir / "identities" / f"{uuid4()}.json"
    file_at(marker, text=json.dumps({"owner": {"attempt_id": str(terminal)}})).chmod(0o600)
    assert (
        cast("dict", clean_worktrees(config, client, {}, dry_run=False))["skipped"][locators[terminal]]
        == "containment unconfirmed"
    )
    marker.unlink()
    evidence = config.state_dir / "evidence" / str(terminal)
    file_at(evidence / str(uuid4()) / "raw.json")
    assert (
        cast("dict", clean_worktrees(config, client, {}, dry_run=False))["skipped"][locators[terminal]]
        == "recovery evidence unsettled"
    )
    evidence.rename(evidence.with_name(str(uuid4())))

    # Introduce a live descriptor between selection and the manager's locked recheck.
    original = WorktreeManager.remove

    def race(manager: WorktreeManager, locator: str):
        with (Path(locator) / "main" / ".git").open("rb"):
            return original(manager, locator)

    with monkeypatch.context() as patch:
        patch.setattr(WorktreeManager, "remove", race)
        assert cast("dict", clean_worktrees(config, client, {}, dry_run=False))["marked"] == 0
    assert Path(locators[terminal]).exists()
    result = cast("dict[str, int]", clean_worktrees(config, client, {}, dry_run=False))
    assert result["marked"] == 1
    assert Path(locators[active]).is_dir()
    again = cast("dict", clean_worktrees(config, client, {}, dry_run=False))
    assert again["marked"] == again["freed_bytes"] == 0
    assert set(again["skipped"]) == {locators[active]}


@pytest.mark.parametrize("migrate_on_start", [False, True])
def test_serve_startup_never_uses_app_login_as_migrator(profile, monkeypatch, migrate_on_start):
    from contextlib import nullcontext

    from skm.bootstrap import composition, lifecycle
    from skm.kernel.error_codes import ErrorCode
    from skm.kernel.errors import BackendUnavailable

    config, env = profile
    path = Path(config.source)
    startup_setting = "true" if migrate_on_start else "false"
    path.write_text(
        path.read_text().replace(
            "[database]",
            f'[database]\nmigrate_on_start = {startup_setting}\nmigrator_url = "secret://env/UNSET_MIGRATOR"',
        )
    )
    connected, migrated = [], []

    def connect(settings):
        connected.append(settings.dsn)
        return nullcontext(SimpleNamespace(info=SimpleNamespace(host="localhost", hostaddr="127.0.0.1")))

    def runner(dsn):
        migrated.append(dsn)
        return SimpleNamespace(migrate=lambda: (), status=lambda: ())

    def after_migration(*args, **kwargs):
        raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "composition reached")

    monkeypatch.setattr(lifecycle, "connect_single", connect)
    monkeypatch.setattr(lifecycle, "local_migration_runner", runner)
    monkeypatch.setattr(composition, "build_app", after_migration)
    code, out, _ = invoke(env, "--json", "serve")
    assert code
    error = json.loads(out)["error"]
    if migrate_on_start:
        assert error["message"] == "Secret reference could not be resolved"
    else:
        assert error["message"] == "composition reached"
    assert connected == migrated == []
