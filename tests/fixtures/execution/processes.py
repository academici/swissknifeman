"""Owned worker subprocesses and synthetic scenario documents for M3."""

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

from support.service_runner import Instance


def scenario(
    path, role, *, content="answer = 42\n", target="src/target.py", model="fake-b", document=None, hang=False
):
    if document is None:
        document = {
            "schema": f"urn:skm:execution:role-result:{role}:v1",
            "status": "done",
            "summary": "Implemented",
            "changed_paths": [{"mount": "repo", "path": target, "change": "modified"}],
            "checks_run": [],
            "open_issues": [],
            "self_check": {"performed": True},
        }
    lines = ['scenario = "m3"', "[[step]]", 'action = "read_stdin"']
    if role == "executor":
        lines.extend(
            [
                "[[step]]",
                'action = "write_file"',
                "path = " + json.dumps(target),
                "content = " + json.dumps(content),
            ]
        )
    lines.extend(
        [
            "[[step]]",
            'action = "emit"',
            'event = {type = "session_started", model = '
            + json.dumps(model)
            + ", session_ref = "
            + json.dumps(f"m3-{role}-{path.stem}")
            + "}",
        ]
    )
    if hang:
        lines.insert(1, "hang = true")
        lines.extend(
            [
                "[[step]]",
                'action = "emit"',
                'event = {type = "usage_reported", cumulative = true, '
                "usage = {input_tokens = 10, output_tokens = 4}}",
            ]
        )
    lines.extend(
        [
            "[result]",
            "text = " + json.dumps(json.dumps(document)),
            "[usage]",
            "input_tokens = 10",
            "output_tokens = 4",
        ]
    )
    path.write_text("\n".join(lines) + "\n")
    return path


def script(path, entries):
    lines = []
    for role, key, invocation, scenario_path in entries:
        lines.extend(
            [
                "[[rule]]",
                f'role = "{role}"',
                f'task_key = "{key}"',
                f"invocation = {invocation}",
                "scenario = " + json.dumps(Path(scenario_path).name),
            ]
        )
    path.write_text("\n".join(lines) + "\n")
    return path


@contextmanager
def worker(side, repository, script_path):
    state = side.root / "state"
    state.mkdir(exist_ok=True)
    config = {
        "root": str(side.root),
        "state": str(state),
        "repository": str(repository),
        "dsn": side.dsn,
        "blobs_root": str(side.boot.blobs_root),
        "now": side.clock.now().isoformat(),
        "instance_id": str(side.app.instance_id),
        "secret": side.secret,
        "host_id": str(side.host1),
        "worker_id": str(side.worker1),
        "workspace_id": str(side.ws),
        "repository_id": str(side.repo_id),
        "script": str(script_path),
        "heartbeat_fault": getattr(side, "heartbeat_fault", False),
        "missing_visibility": getattr(side, "missing_visibility", False),
        "pause_before_result": getattr(side, "pause_before_result", None),
        "pause_run_id": str(getattr(side, "pause_run_id", "")),
        "owner_id": str(side.owner.principal_id),
    }
    path = side.root / "worker-input.json"
    path.write_text(json.dumps(config))
    path.chmod(0o600)
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2])}
    with (side.root / "worker.stdout").open("w+") as out, (side.root / "worker.stderr").open("w+") as err:
        process = subprocess.Popen(  # noqa: TID251 - intentionally exercise an external worker entrypoint
            [sys.executable, "-m", "fixtures.execution.worker_process", str(path)],
            cwd=side.root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
        )
        try:
            yield process
        finally:
            Instance.stop(process)
            for stream in ("stdout", "stderr"):
                (side.root / f"worker-{process.pid}.{stream}").write_bytes(
                    (side.root / f"worker.{stream}").read_bytes()
                )
