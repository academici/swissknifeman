"""Fake provider port with the production bounded transcript writer and real session events."""

import json
from dataclasses import asdict, replace
from pathlib import Path

from skm.adapters.runtimes._cli_session.transcript import TranscriptWriter


def read_only_profile_layer():
    """An empty command allowlist retains every catalog ceiling guard at pack installation."""
    from skm.modules.policy.application.composition import compose_effective
    from unit.policy.domain.layout import CatalogConfig

    commands = compose_effective(
        CatalogConfig(), profile_id=None, role_layer=None, task_layer=None, allow_unconfined=False
    ).commands
    layer = {
        "mode": "allowlist",
        "programs": [],
        "deny_patterns": list(commands.deny_patterns),
        "ask_patterns": list(commands.ask_patterns),
        "inline_interpreters": sorted(commands.inline_interpreters),
        "trust_inline_interpreters": False,
    }
    return "\n[permissions.layer.commands]\n" + "".join(
        f"{key} = {json.dumps(value)}\n" for key, value in layer.items()
    )


class RecordedRuntime:
    def __init__(self, inner, state, storage):
        self.inner, self.state, self.storage = inner, state, storage
        self.writers = {}

    def start(self, request):
        if request.role == "executor":
            with (Path(request.workdir) / "src/target.py").open("rb") as stream:
                initial = stream.read(2000).decode("utf-8")
            with (self.state / "executor-starts.jsonl").open("a") as stream:
                stream.write(json.dumps({"step_id": request.request_id, "initial": initial}) + "\n")
        root = self.state / "steps" / request.request_id
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        reservation = self.storage.reserve(
            root,
            owner_id=request.request_id,
            max_bytes=request.limits.max_output_bytes,
            min_free_bytes=0,
            max_files=3,
        )
        writer = TranscriptWriter(
            root, reservation, max_stream_bytes=request.limits.max_output_bytes, workdir=Path(request.workdir)
        )
        for value in request.secret_env.values():
            writer.register_secret(value.reveal())
        try:
            handle = self.inner.start(request)
        except BaseException:
            writer.close()
            raise
        self.writers[handle.request_id] = writer
        return handle

    def events(self, handle):
        writer = self.writers[handle.request_id]
        for event in self.inner.events(handle):
            data = json.dumps({"type": type(event).__name__, **asdict(event)}, default=str).encode() + b"\n"
            assert writer.write("stdout", data)[0]
            yield event

    def result(self, handle):
        result = self.inner.result(handle)
        writer = self.writers[handle.request_id]
        data = json.dumps({"type": "runtime_result", "final_text": result.final_text}).encode() + b"\n"
        assert writer.write("stdout", data)[0]
        writer.close()
        return replace(result, transcript_path=str(writer.step_dir / "stream.jsonl"))

    def __getattr__(self, name):
        return getattr(self.inner, name)
