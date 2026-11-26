"""One selected M3 item, real services and Git; suitable for complete recovery traces."""

import json
from types import SimpleNamespace

from fixtures.execution.harness import system_dispatch
from fixtures.execution.m3 import KEYS, dag, start
from fixtures.execution.processes import scenario, script, worker
from fixtures.execution.protocol import AUTHOR
from integration.git.conftest import make_repo
from skm.modules.execution.ports import AttemptRepository, RunRepository, TaskRepository


def single_run(side):
    repository = side.root / "repository"
    git, _ = make_repo(repository)
    (repository / "src").mkdir()
    (repository / "src/target.py").write_text("answer = 0\n")
    git.run(repository, ["add", "."])
    git.run_bytes(repository, ["commit", "-m", "recovery baseline"], env=AUTHOR)
    started = start(side, dag(side), keys=(KEYS[0],))
    git.run(repository, ["branch", f"skm/integration/{started.run_id}", "main"])
    system_dispatch(side, "schedule_ready_tasks")
    with side.uow(readonly=True) as uow:
        (task,) = uow.repo(TaskRepository).list_for_run(started.run_id)
        attempt = uow.repo(AttemptRepository).get(task.current_attempt_id)
        run = uow.repo(RunRepository).get(started.run_id)
    return SimpleNamespace(repository=repository, git=git, run=run, task=task, attempt=attempt)


def successful_script(side, key, *, interrupted=False, bad_check=False):
    entries = []
    invocation = 1
    if interrupted or bad_check:
        initial = scenario(
            side.root / "initial.toml",
            "executor",
            content="answer = 41\n",
            hang=interrupted,
            model="fake-a",
        )
        entries.append(("executor", key, invocation, initial))
        invocation += 1
    good = scenario(side.root / "complete.toml", "executor", model="fake-b" if bad_check else "fake-a")
    green = scenario(
        side.root / "review.toml",
        "reviewer",
        document={
            "schema": "urn:skm:execution:role-result:reviewer:v1",
            "verdict": "green",
            "summary": "Verified",
            "findings": [],
            "residual_risk": "None",
        },
    )
    entries.extend([("executor", key, invocation, good), ("reviewer", key, 1, green)])
    return script(side.root / "single-script.toml", entries)


def run_worker(side, case, script_path):
    with worker(side, case.repository, script_path) as process:
        process.wait(timeout=300)
        out = (side.root / "worker.stdout").read_text()
        assert process.returncode == 0, out + (side.root / "worker.stderr").read_text()
        slots = json.loads(out)["slots"]
        assert sum(slot["assignments"] for slot in slots) == 1, out
        assert all(slot.get("reason") is None for slot in slots), out
