"""Observe bytes consumed by the actual runtime child, retaining its scenario protocol."""

import io
import json
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any, cast, override

if __name__ == "__main__" and sys.argv[1] == "child":
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from fixtures.execution import worker_process
from fixtures.execution.runtime import RecordedRuntime
from skm.adapters.runtimes.fake import runtime, scenarios
from skm.modules.runtimes.public import SelfLoadedSource


class ObservedRuntime(RecordedRuntime):
    def self_loaded_context(self, request):
        instructions = Path(request.workdir) / "AGENTS.md"
        instructions.read_bytes()
        return (
            SelfLoadedSource(
                cast(Any, "project_instructions"), str(instructions), ("AGENTS.md",), "start", "untrusted"
            ),
        )

    @override
    def start(self, request):
        spawn = runtime.spawn
        root = self.state / "m4-handoff"
        root.mkdir(exist_ok=True)

        def capture(argv: Any, **kwargs: Any) -> Any:
            assert argv[1:3] == ("-m", "skm.adapters.runtimes.fake.scenarios")
            return spawn(
                (argv[0], str(Path(__file__).resolve()), "child", str(root / request.request_id), *argv[3:]),
                **kwargs,
            )

        runtime.spawn = capture
        try:
            return super().start(request)
        finally:
            runtime.spawn = spawn


def child():
    target = Path(sys.argv[2])
    data = sys.stdin.buffer.read()
    target.with_suffix(".prompt").write_bytes(data)
    target.with_suffix(".json").write_text(json.dumps({"digest": "sha256:" + sha256(data).hexdigest()}))
    sys.stdin = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8")
    sys.argv = ["scenarios", *sys.argv[3:]]
    scenarios._process()


if __name__ == "__main__":
    if sys.argv[1] == "child":
        child()
    else:
        worker_process.RecordedRuntime = ObservedRuntime
        raise SystemExit(worker_process.run(sys.argv[1]))


def assert_explanation(explained: Any, manifest: Any) -> None:
    from skm.modules.context.domain.reasons import HIDDEN_REASONS

    visible = [
        b
        for b in manifest.blocks
        if b.reason not in HIDDEN_REASONS
        or (
            b.reason == "not_found"
            and b.source_kind == "repository_path"
            and any(
                b.block_ref == f"h:{r.request_id}" and b.source_ref == r.source_ref
                for r in manifest.host_inputs
            )
        )
    ]
    ordered = sorted(visible, key=lambda b: (b.position is None, b.position or 0, b.ordinal))
    assert len(explained["rows"]) == len(ordered)
    for row, block in zip(explained["rows"], ordered, strict=True):
        assert {k: row[k] for k in ("source", "tokens", "digest", "reason", "trust", "included")} == {
            "source": block.source_ref,
            "tokens": block.tokens_estimate,
            "digest": (block.content_digest or "").removeprefix("sha256:")[:12],
            "reason": block.reason,
            "trust": block.trust.value,
            "included": block.included,
        }
    assert explained["excluded"] == [
        {"block_type": b.block_type.value, "source_ref": b.source_ref, "reason": b.reason, "detail": b.detail}
        for b in visible
        if b.included is False
    ]
    assert explained["runtime_self_loads"] == manifest.route.get(
        "self_loads_observed", manifest.route.get("self_loads", [])
    )
