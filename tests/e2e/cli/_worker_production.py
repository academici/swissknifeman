"""Real production CLI/PG worker fixture; no App, host or entrypoint replacements."""

import json
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

import psycopg
import pytest

from e2e.test_m1_config_on_postgres import ENTRY, Sandbox, Scratch, rows
from skm.entrypoints.cli.main import main


def ok(box: Sandbox, *args: str, workspace_id: str | None = None) -> dict[str, Any]:
    out, err = StringIO(), StringIO()
    env = box.env()
    if workspace_id is not None:
        env["SKM_WORKSPACE"] = workspace_id
    code = main(["--json", *args], environ=env, stdout=out, stderr=err)
    assert code == 0, out.getvalue() + err.getvalue()
    return json.loads(out.getvalue())["result"]


@dataclass(frozen=True)
class ProductionWorker:
    box: Sandbox
    workspace_id: str
    worker_id: str
    token_id: str
    secret: str
    token_path: Path

    @property
    def args(self) -> list[str]:
        return [
            "worker",
            "start",
            "--worker",
            self.worker_id,
            "--token",
            "secret://file/" + str(self.token_path),
        ]

    def env(self) -> dict[str, str]:
        return {**self.box.env(), "SKM_WORKSPACE": self.workspace_id}

    def invoke(self, *extra: str) -> tuple[int, str, str]:
        out, err = StringIO(), StringIO()
        code = main(["--json", *self.args, *extra], environ=self.env(), stdout=out, stderr=err)
        return code, out.getvalue(), err.getvalue()

    def expire_soon(self) -> None:
        # Real credential, real authentication and real rotation clock; only the fixture expiry is aged.
        with psycopg.connect(self.box.dsn, autocommit=True) as conn:
            conn.execute(
                "UPDATE skm_access.api_tokens SET expires_at = now() + interval '1 hour' WHERE id = %s",
                (self.token_id,),
            )

    def assert_rotated(self) -> None:
        replacement = self.token_path.read_text().strip()
        assert replacement != self.secret
        assert self.token_path.stat().st_mode & 0o777 == 0o600
        assert rows(
            self.box.dsn, "SELECT superseded_by FROM skm_access.api_tokens WHERE id = %s", self.token_id
        )[0][0]

    def stop_with_sigterm(self) -> tuple[int, dict[str, Any], str]:
        self.expire_soon()
        process = subprocess.Popen(  # noqa: TID251 - exercise a real CLI process and its SIGTERM handler
            [sys.executable, "-c", ENTRY, "--json", *self.args, "--capacity", "2"],
            cwd=self.box.root,
            env=self.env(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 120
            # Rotation is performed from inside the live loop, after the entrypoint installed SIGTERM.
            while process.poll() is None and self.token_path.read_text().strip() == self.secret:
                if time.monotonic() >= deadline:
                    pytest.fail("production worker did not reach its rotation tick")
                time.sleep(0.02)
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
            out, err = process.communicate(timeout=15)
            assert process.returncode == 0, out + err
            self.assert_rotated()
            assert self.secret not in out + err
            assert self.token_path.read_text().strip() not in out + err
            return process.returncode, json.loads(out), err
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)


@pytest.fixture
def production_worker(scratch: Scratch, tmp_path: Path) -> ProductionWorker:
    box = Sandbox(tmp_path, scratch.dsn)
    box.home.mkdir()
    initialized = ok(box, "init", "--database-url", scratch.dsn, "--host-name", "production-worker")
    workspace = initialized["workspace"]["workspace_id"]
    host = ok(box, "host", "register", "production-worker", workspace_id=workspace)
    registered = ok(
        box,
        "worker",
        "register",
        "production-worker",
        "--host",
        host["host_id"],
        "--no-save-token",
        "--skm-version",
        "2.0.0",
        workspace_id=workspace,
    )
    token = box.root / "worker.token"
    token.write_text(registered["token_secret"])
    token.chmod(0o600)
    principal = registered["principal_id"]
    token_id = str(
        rows(box.dsn, "SELECT id FROM skm_access.api_tokens WHERE principal_id = %s", principal)[0][0]
    )
    box.owner_token.unlink()  # Production worker authentication must use --token, without an owner secret.
    return ProductionWorker(
        box, workspace, registered["worker_id"], token_id, registered["token_secret"], token
    )
