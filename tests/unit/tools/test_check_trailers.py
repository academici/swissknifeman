"""Trailer invariants and exit codes against real Git commit messages."""

import subprocess
import sys
from importlib import util
from pathlib import Path
from uuid import uuid4

import pytest

from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.integration import commit_trailers

SCRIPT = Path(__file__).resolve().parents[3] / "tools" / "check_trailers.py"
_SPEC = util.spec_from_file_location("check_trailers", SCRIPT)
assert _SPEC is not None
assert _SPEC.loader is not None
_check_trailers = util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_check_trailers)
check_message = _check_trailers.check_message


def message() -> str:
    inputs: JsonObject = {
        **{name: str(uuid4()) for name in ("run_id", "plan_id", "attempt_id", "output_id", "effect_id")},
        "revision_no": 1,
        "task_key": "T1",
        "plan": "demo",
        "plan_ref": "T1",
        "output_no": 2,
        "review_id": str(uuid4()),
        "review_round": 3,
        "findings": ["fk-" + "b" * 16, "fk-" + "c" * 16],
        "task_spec_ref": f"skm:revision:{uuid4()}#entity:{uuid4()}",
        "task_spec_digest": "sha256:" + "a" * 64,
        "executed_by": ["codex/model/high", "codex/model/high"],
        "executor_session": ["session-a", "session-b"],
    }
    return "fix: resolve finding\n\n" + "\n".join(f"{key}: {value}" for key, value in commit_trailers(inputs))


@pytest.mark.parametrize(
    ("corrupt", "expected"),
    [
        (lambda msg: msg + "\nSKM-Output: " + str(uuid4()), "duplicate SKM-Output"),
        (lambda msg: msg.replace("SKM-Effect: ", "Unrelated: "), "missing SKM-Effect"),
        (lambda msg: msg.replace("SKM-Output-No: 2", "SKM-Output-No: 0"), "invalid SKM-Output-No"),
        (lambda msg: msg.replace("SKM-Review-Round:", "Unrelated:"), "must occur together"),
        (lambda msg: msg.replace("SKM-Review-Round: 3", "SKM-Review-Round: 03"), "invalid SKM-Review-Round"),
        (lambda msg: msg.replace("Plan-Ref: T1", "Plan-Ref: T2"), "Plan-Ref differs from SKM-Task"),
        (lambda msg: msg.replace("SKM-Findings: fk-", "SKM-Findings: PRIVATE-"), "invalid SKM-Findings"),
        (
            lambda msg: msg.replace("Task-Spec-Digest: sha256:", "Task-Spec-Digest: private "),
            "invalid Task-Spec-Digest",
        ),
        (lambda msg: msg.replace("Task-Spec-Ref:", "Unrelated:"), "must occur together"),
        (lambda msg: msg.replace("SKM-Run:", "skm-run:"), "noncanonical SKM-Run"),
        (lambda msg: msg + "\n continuation", "malformed trailer line"),
        (lambda msg: msg + "\nExecutor-Session: orphan", "Executor-Session requires matching Executed-By"),
        (lambda msg: "SKM-Run: forged\n\n" + msg, "identity trailers must occur only"),
    ],
)
def test_rejects_corrupt_managed_trailers(corrupt, expected):
    assert any(expected in error for error in check_message(corrupt(message())))


def test_ignores_unmanaged_commits_and_accepts_repeated_provenance():
    assert check_message("docs: update guide\n\nPlan-Ref: T1") == ()
    assert check_message("skm: attempt output\n\nSKM-Attempt: x\nSKM-Output-No: 1") == ()
    assert check_message(message()) == ()


def test_cli_checks_head_or_range_and_reports_only_commit_id_and_diagnostics(tmp_path):
    def git(*args: str, stdin: str | None = None) -> str:
        return subprocess.run(
            ["git", "-C", str(tmp_path), *args],  # noqa: S607
            input=stdin,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    def commit(text: str) -> str:
        git(
            "-c",
            "user.name=Test Worker",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-F",
            "-",
            stdin=text,
        )
        return git("rev-parse", "HEAD")

    git("init", "--initial-branch=main")
    start = commit("ordinary commit")
    good = commit(message())
    bad = commit(message().replace("SKM-Effect: ", "Unrelated: ") + "\nSKM-Findings: PRIVATE TEXT")
    main = [sys.executable, str(SCRIPT), "--repo", str(tmp_path)]
    passed = subprocess.run([*main, f"{start}..{good}"], capture_output=True, text=True, check=False)
    assert passed.returncode == 0
    assert not passed.stdout
    failed = subprocess.run([*main, f"{start}..HEAD"], capture_output=True, text=True, check=False)
    assert failed.returncode == 1
    assert f"{bad}: missing SKM-Effect" in failed.stdout
    assert "PRIVATE TEXT" not in failed.stdout
    assert subprocess.run(main, capture_output=True, check=False).returncode == 1
    assert subprocess.run([*main, "missing-ref"], capture_output=True, check=False).returncode == 2
