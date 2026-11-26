"""Read attempt artifacts through the client, retaining the facade's payload visibility checks."""

import argparse
import codecs
import time
from typing import Any

from skm.entrypoints.cli._run_io import ask, identifier, operations, show
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.output import render, render_waiting
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, ValidationFailed
from skm.kernel.ids import FileVersionId
from skm.kernel.outcomes import Waiting

GetAttempt = operations("execution").GetAttempt
GetStep = operations("execution").GetStep


def logs(args: argparse.Namespace, ctx: CliContext) -> int:
    seen: dict[str, int] = {}
    last_steps: str | None = None
    while True:
        attempt = ask(ctx, GetAttempt, attempt_id=str(identifier(args.ref, "attempt")))
        steps: list[Any] = list(attempt.steps)
        if args.step:
            wanted = identifier(args.step, "step")
            steps = [step for step in steps if str(step["step_id"]) == str(wanted)]
            if not steps:
                raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "step does not belong to this attempt")
        if not args.transcript:
            signature = repr(steps)
            if signature != last_steps:
                show(ctx, "execution.get_attempt", {"attempt_id": attempt.attempt_id, "steps": steps})
                last_steps = signature

        for item in steps if args.transcript else ():
            step = ask(ctx, GetStep, step_id=str(item["step_id"]))
            if step.payload_visibility == "restricted":
                raise Forbidden(ErrorCode.FORBIDDEN, "file.read is required for this transcript")
            version = step.transcript_file_version_id
            if version is None or str(version) in seen:
                continue
            # File-version bytes are immutable; do not tail by byte offset or decode chunks separately.
            with ctx.client.open_file_version_content(FileVersionId(version)) as stream:
                decoder = codecs.getincrementaldecoder("utf-8")("replace")
                while chunk := stream.read(65536):
                    text = decoder.decode(chunk)
                    render(
                        ctx,
                        {"step_id": step.step_id, "text": text},
                        human=lambda _, line=text: line,
                        command="run.logs",
                        essential=lambda _, line=text: line,
                    )
                text = decoder.decode(b"", final=True)
                if text:
                    render(ctx, {"text": text}, human=lambda _, line=text: line, command="run.logs")
            seen[str(version)] = 1
        if args.follow and attempt.state == "waiting":
            return render_waiting(
                ctx, Waiting(ErrorCode.WAITING_FOR_ANSWER, "skm inbox list"), command="run.logs"
            )
        if not args.follow or attempt.state in {"completed", "ownership_lost", "abandoned"}:
            return 0
        time.sleep(0.5)


__all__ = ["GetAttempt", "GetStep", "logs"]
