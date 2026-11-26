"""Phase-B selectors, dependency facts, bounded reads and honest missing inputs."""

from dataclasses import replace
from typing import override

import pytest

from skm.adapters.git.host_inputs import GitCheckoutReader
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed
from skm.modules.context.domain.blocks import BlockType, TrustLevel
from skm.modules.context.domain.finalize import sha256_text
from skm.modules.context.domain.host_inputs import (
    HostInputKind,
    HostInputRequest,
    HostReadStatus,
    HostSelector,
)
from skm.modules.context.domain.render import format_host_block, render_block_text
from skm.modules.context.domain.research import ResearchBatch
from skm.modules.context.public import collect_host_blocks
from skm.platform.tokens.heuristic import HeuristicTokenEstimator

EST = HeuristicTokenEstimator()
MD = "# Guide\nintro\n## Security\nkeep\n### Nested\n- preserve\n## Testing\ndrop\n"


def request(
    path="guide.md", *, request_id="hi:0", kind=HostInputKind.REPOSITORY_PATH, selector=None, **changes
):
    value = HostInputRequest(
        request_id,
        kind,
        "repo",
        path,
        ("CLAUDE.md", "AGENTS.md") if kind is HostInputKind.REPO_INSTRUCTIONS else (),
        selector or HostSelector("whole"),
        65536,
        False,
        None
        if kind is HostInputKind.DEPENDENCY_MANIFEST
        else BlockType.REPO_INSTRUCTIONS
        if kind is HostInputKind.REPO_INSTRUCTIONS
        else BlockType.RESEARCH
        if kind is HostInputKind.RESEARCH_QUERY
        else BlockType.MATERIALS,
        TrustLevel.EXTERNAL if kind is HostInputKind.RESEARCH_QUERY else TrustLevel.REPOSITORY,
        f"repo:repo/{path}",
        kind is HostInputKind.REPOSITORY_PATH,
        (),
        None,
    )
    return replace(value, **changes)


def collect(root, requests, **changes):
    reader = GitCheckoutReader({"repo": root}, baseline={"repo": "a" * 40})
    options = {
        "total_max_bytes": 2097152,
        "max_work_paths": 300,
        "repo_max_files": 8,
        "path_patterns": (),
        "research": {},
    }
    options.update(changes)
    return collect_host_blocks(requests, reader, EST, **options)


@pytest.mark.parametrize(
    ("selector", "text"),
    [
        (HostSelector("whole"), MD),
        (HostSelector("markdown_heading", heading="Security"), "## Security\nkeep\n### Nested\n- preserve\n"),
        (
            HostSelector("markdown_sections", ("Security", "Testing")),
            "## Security\nkeep\n### Nested\n- preserve\n## Testing\ndrop\n",
        ),
        (HostSelector("line_range", line_from=3, line_to=4), "## Security\nkeep\n"),
    ],
)
def test_selected_text_size_digest_and_deferred_tokens_are_exact(tmp_path, selector, text):
    (tmp_path / "guide.md").write_text(MD)
    req = request(selector=selector)
    (block,), facts = collect(tmp_path, (req,))
    assert block.status is HostReadStatus.OK
    assert block.text == text
    assert block.text_digest == sha256_text(text)
    assert block.size_bytes == len(text.encode())
    assert block.tokens_estimate is None  # finalized only after the draft render snapshot is known
    assert facts.baseline == {"repo": "a" * 40}


@pytest.mark.parametrize(
    "selector",
    [
        HostSelector("markdown_heading", heading="Absent"),
        HostSelector("markdown_sections", ()),
        HostSelector("line_range", line_from=99, line_to=100),
    ],
)
def test_missing_selection_has_no_text_or_digest(tmp_path, selector):
    (tmp_path / "guide.md").write_text(MD)
    (block,), _ = collect(tmp_path, (request(selector=selector),))
    assert block.status is HostReadStatus.NO_MATCHING_SECTIONS
    assert block.text is None
    assert block.text_digest is None
    assert block.tokens_estimate is None


@pytest.mark.parametrize(
    "status", ["missing", "too_large", "binary", "path_invalid", "no_matching_sections", "budget_exceeded"]
)
def test_required_unavailable_input_stops_before_runtime(tmp_path, status):
    req = request(required=True)
    options = {}
    if status != "missing":
        (tmp_path / "guide.md").write_bytes(b"\x00" if status == "binary" else b"body")
    if status == "too_large":
        req = replace(req, max_bytes=1)
    elif status == "path_invalid":
        req = replace(req, path="../outside")
    elif status == "no_matching_sections":
        req = replace(req, selector=HostSelector("markdown_heading", heading="Missing"))
    elif status == "budget_exceeded":
        options["total_max_bytes"] = 0
    with pytest.raises(PreconditionFailed) as caught:
        collect(tmp_path, (req,), **options)
    assert caught.value.code is ErrorCode.CONTEXT_INPUT_MISSING
    assert dict(caught.value.details) == {"request_id": "hi:0", "path": req.path, "status": status}


def test_dependency_manifests_are_inert_facts_and_not_blocks(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies=["httpx>=1"]\n')
    blocks, facts = collect(tmp_path, (request("pyproject.toml", kind=HostInputKind.DEPENDENCY_MANIFEST),))
    assert blocks == ()
    assert facts.deps == frozenset({"pip:httpx"})
    blocks, facts = collect(tmp_path, (request("missing.json", kind=HostInputKind.DEPENDENCY_MANIFEST),))
    assert blocks == ()
    assert facts.deps == frozenset()


def test_work_path_templates_and_expansion_share_one_bound(tmp_path):
    (tmp_path / "a.py").write_text("a")
    (tmp_path / "b.py").write_text("b")
    (tmp_path / "c.py").write_text("c")
    _, facts = collect(tmp_path, (), path_patterns=(("repo", "*.py"),), max_work_paths=3)
    assert facts.work_paths == (("repo", "*.py"), ("repo", "a.py"), ("repo", "b.py"))
    assert facts.work_paths_truncated
    _, exact = collect(tmp_path, (), path_patterns=(("repo", "a.py"),), max_work_paths=1)
    assert exact.work_paths == (("repo", "a.py"),)
    assert not exact.work_paths_truncated
    _, zero = collect(tmp_path, (), path_patterns=(("repo", "*.py"),), max_work_paths=0)
    assert zero.work_paths == ()
    assert zero.work_paths_truncated


def test_research_renders_recorded_batch_and_preserves_query_ids(tmp_path, monkeypatch):
    from unit.context.research_support import normalized

    batch = ResearchBatch("query", "digest", (replace(normalized(), query_id="rq:1"),))
    called = []

    def render(batch):
        called.append(batch)
        return "Source unavailable; limitations: timeout\n"

    monkeypatch.setattr("skm.modules.context.public.render_research", render)
    req = request("", kind=HostInputKind.RESEARCH_QUERY)
    (block,), _ = collect(tmp_path, (req,), research={req.request_id: batch})
    assert block.status is HostReadStatus.OK
    assert block.text is not None
    assert "timeout" in block.text
    assert block.research_query_ids == ("rq:1",)
    assert called == [batch]
    assert block.text_digest == sha256_text(block.text)
    (missing,), _ = collect(tmp_path, (req,))
    assert missing.status is HostReadStatus.MISSING
    (limited,), _ = collect(tmp_path, (req,), research={req.request_id: batch}, total_max_bytes=1)
    assert limited.status is HostReadStatus.BUDGET_EXCEEDED


@pytest.mark.parametrize(
    ("content", "limit", "status"),
    [
        (b"1234", 3, "too_large"),
        (b"\x00text", 100, "binary"),
        (b"\xff", 100, "binary"),
        ("ёж".encode(), 4, "ok"),
        (b"", 0, "ok"),
    ],
)
def test_reader_bounded_text_statuses(tmp_path, content, limit, status):
    (tmp_path / "guide.md").write_bytes(content)
    result = GitCheckoutReader({"repo": tmp_path}).read(
        "repo", "guide.md", max_bytes=limit, follow_symlinks=False
    )
    assert result.status == status
    assert (result.data is not None) == (status == "ok")


def test_collector_consumes_raw_bytes_before_applying_selector(tmp_path):
    (tmp_path / "guide.md").write_text(MD)
    (tmp_path / "other.md").write_text("extra")
    blocks, _ = collect(
        tmp_path,
        (
            request(selector=HostSelector("line_range", line_from=1, line_to=1)),
            request("other.md", request_id="hi:1"),
        ),
        total_max_bytes=len(MD.encode()),
    )
    assert [b.status for b in blocks] == [HostReadStatus.OK, HostReadStatus.BUDGET_EXCEEDED]


def test_growth_after_fstat_is_still_capped(tmp_path, monkeypatch):
    import os

    (tmp_path / "guide.md").write_text("small")
    original = os.fstat

    def grow(fd):
        result = original(fd)
        if result.st_size == 5:
            (tmp_path / "guide.md").write_text("x" * 100)
        return result

    monkeypatch.setattr(os, "fstat", grow)
    outcome = GitCheckoutReader({"repo": tmp_path}).read(
        "repo", "guide.md", max_bytes=10, follow_symlinks=False
    )
    assert outcome.status == "too_large"
    assert outcome.size == 11


@pytest.mark.parametrize("supply_draft", [False, True])
@pytest.mark.parametrize("use_plan", [False, True])
def test_custom_draft_render_agrees_with_collected_and_finalized_tokens(tmp_path, supply_draft, use_plan):
    from uuid import UUID

    from skm.kernel.ids import FileVersionId
    from skm.modules.context.application.commands.finalize_manifest import FinalizeManifest, _host_inputs
    from skm.modules.context.domain.finalize import finalize
    from skm.modules.context.generated.commands import finalize_manifest_from_json
    from skm.modules.context.public import ContextOwnerClaim, finalize_command
    from unit.context.domain.test_finalize import _make_draft, _mandatory_six

    (tmp_path / "guide.md").write_text("reference content")
    req = request()
    mandatory, _ = _mandatory_six()
    draft = _make_draft(mandatory, host_inputs=(req,))
    template = "## {{block.title}}\n\n{{block.content}}\n\nRuntime {{runtime.id}} " + "context " * 80
    templates = dict(draft.templates)
    templates["custom/material"] = template
    if not use_plan:
        templates["shared/block_wrapper"] = template
    draft = replace(
        draft,
        templates=templates,
        prompt_plan={BlockType.MATERIALS: ("custom/material",)} if use_plan else {},
    )
    blocks, facts = collect(tmp_path, (req,), **({"draft": draft} if supply_draft else {}))
    block_type, title, body, source = format_host_block(req, blocks[0])
    expected = EST.estimate(
        render_block_text(
            block_type=block_type,
            title=title,
            content=body,
            source_ref=source,
            templates=draft.templates,
            prompt_plan=draft.prompt_plan,
            variables=draft.variables,
        )
    )
    if supply_draft:
        assert blocks[0].tokens_estimate == expected
    else:
        assert blocks[0].tokens_estimate is None
    finalized = finalize(draft, blocks, facts, EST)
    host = next(b for b in finalized.manifest.blocks if b.block_ref == "h:hi:0")
    assert host.tokens_estimate == expected
    assert "Runtime codex_cli" in finalized.rendered_prompt
    payload = finalize_command(
        draft,
        finalized,
        blocks,
        facts,
        FileVersionId(UUID(int=7)),
        claim=ContextOwnerClaim(UUID(int=1), UUID(int=2), UUID(int=3), 1),
        store_content=False,
        runtime_self_loaded=(),
    )
    cmd = FinalizeManifest(finalize_manifest_from_json(payload))
    metas, _ = _host_inputs(cmd, finalized.manifest)
    assert metas[0].tokens_estimate == expected


def test_rejected_growing_reads_exhaust_total_byte_budget(tmp_path, monkeypatch):
    import os

    for name in ("a.md", "b.md", "c.md"):
        (tmp_path / name).write_text("tiny")
    original = os.fstat
    reads = []

    def grow(fd):
        info = original(fd)
        if info.st_size == 4:
            reads.append(fd)
            for name in ("a.md", "b.md", "c.md"):
                path = tmp_path / name
                if path.stat().st_ino == info.st_ino:
                    path.write_text("x" * 100)
        return info

    monkeypatch.setattr(os, "fstat", grow)
    blocks, _ = collect(
        tmp_path,
        tuple(
            request(name, request_id=f"hi:{index}", max_bytes=10)
            for index, name in enumerate(("a.md", "b.md", "c.md"))
        ),
        total_max_bytes=15,
    )
    assert [b.status for b in blocks] == [
        HostReadStatus.TOO_LARGE,
        HostReadStatus.BUDGET_EXCEEDED,
        HostReadStatus.BUDGET_EXCEEDED,
    ]
    assert [b.size_bytes for b in blocks] == [11, 5, None]
    assert len(reads) == 2
    assert all(b.text is None and b.text_digest is None for b in blocks)


def test_stat_only_size_rejection_spends_no_read_budget(tmp_path):
    (tmp_path / "large.md").write_text("x" * 100)
    (tmp_path / "small.md").write_text("safe")
    blocks, _ = collect(
        tmp_path,
        (request("large.md", max_bytes=10), request("small.md", request_id="hi:1")),
        total_max_bytes=4,
    )
    assert [b.status for b in blocks] == [HostReadStatus.TOO_LARGE, HostReadStatus.OK]
    assert blocks[1].text == "safe"


def test_reader_without_measurements_is_charged_for_rejected_bounded_read(tmp_path):
    from skm.modules.context.ports import ReadOutcome

    class Reader(GitCheckoutReader):
        calls = 0

        @override
        def read(self, mount, rel_path, *, max_bytes, follow_symlinks):
            self.calls += 1
            return ReadOutcome("too_large", None, max_bytes + 1, rel_path)

    reader = Reader({"repo": tmp_path})
    blocks, _ = collect_host_blocks(
        tuple(request(request_id=f"hi:{i}", max_bytes=10) for i in range(3)),
        reader,
        EST,
        total_max_bytes=11,
        max_work_paths=0,
        repo_max_files=8,
        path_patterns=(),
        research={},
    )
    assert reader.calls == 1
    assert [b.status for b in blocks] == [
        HostReadStatus.TOO_LARGE,
        HostReadStatus.BUDGET_EXCEEDED,
        HostReadStatus.BUDGET_EXCEEDED,
    ]
