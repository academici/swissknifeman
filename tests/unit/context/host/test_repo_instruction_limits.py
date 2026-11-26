"""Instruction alternatives, inherited-file limits, self-loads and total read budgets."""

from dataclasses import replace

from skm.adapters.git.host_inputs import GitCheckoutReader
from skm.modules.context.domain.host_inputs import HostInputKind, HostReadStatus, HostSelector
from skm.modules.context.host.collect_host_blocks import collect_host_blocks
from unit.context.host.test_collect_host_blocks import EST, collect, request


def repo(path="", **changes):
    return request(path, kind=HostInputKind.REPO_INSTRUCTIONS, follow_symlinks=False, **changes)


def test_missing_carriers_do_not_consume_file_limit(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "c").mkdir()
    (tmp_path / "b/AGENTS.md").write_text("b")
    (tmp_path / "c/CLAUDE.md").write_text("c")
    requests = tuple(
        repo(path, request_id=f"hi:{index}") for index, path in enumerate(("", "a/", "b/", "c/"))
    )
    blocks, _ = collect(tmp_path, requests, repo_max_files=1)
    assert [b.status for b in blocks] == [
        HostReadStatus.MISSING,
        HostReadStatus.MISSING,
        HostReadStatus.OK,
        HostReadStatus.OVER_MAX_FILES,
    ]
    assert all(b.text is None for b in blocks if b.status is not HostReadStatus.OK)


def test_first_existing_alternative_wins_even_if_unreadable_or_oversized(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("too large")
    (tmp_path / "AGENTS.md").write_text("a")
    (block,), _ = collect(tmp_path, (repo(max_bytes=1),))
    assert block.status is HostReadStatus.TOO_LARGE
    assert block.resolved_path == "CLAUDE.md"
    (tmp_path / "CLAUDE.md").unlink()
    (block,), _ = collect(tmp_path, (repo(max_bytes=1),))
    assert block.status is HostReadStatus.OK
    assert block.text == "a"


def test_self_loaded_file_is_metadata_only_and_consumes_neither_limit(tmp_path, monkeypatch):
    (tmp_path / "AGENTS.md").write_text("runtime-owned instructions")
    reader = GitCheckoutReader({"repo": tmp_path})
    original, calls = reader.read, []

    def observed(*args, **kwargs):
        calls.append(kwargs["max_bytes"])
        return original(*args, **kwargs)

    monkeypatch.setattr(reader, "read", observed)
    (block,), _ = collect_host_blocks(
        (repo(skip_if_resolved_in=("AGENTS.md",)),),
        reader,
        EST,
        total_max_bytes=0,
        repo_max_files=0,
        max_work_paths=0,
        path_patterns=(),
        research={},
    )
    assert block.status is HostReadStatus.SELF_LOADED
    assert block.resolved_path == "AGENTS.md"
    assert block.text is None
    assert block.text_digest is None
    assert calls
    assert set(calls) == {0}


def test_instruction_count_increases_only_for_ok_selected_files(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Other\nbody\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src/AGENTS.md").write_text("# Security\nkeep\n")
    req = repo(selector=HostSelector("markdown_sections", ("Security",)))
    blocks, _ = collect(tmp_path, (req, replace(req, request_id="hi:1", path="src/")), repo_max_files=1)
    assert [b.status for b in blocks] == [HostReadStatus.NO_MATCHING_SECTIONS, HostReadStatus.OK]


def test_cumulative_budget_is_applied_across_file_kinds(tmp_path):
    (tmp_path / "AGENTS.md").write_text("12345")
    (tmp_path / "material.md").write_text("123456")
    blocks, _ = collect(tmp_path, (repo(), request("material.md", request_id="hi:1")), total_max_bytes=10)
    assert [b.status for b in blocks] == [HostReadStatus.OK, HostReadStatus.BUDGET_EXCEEDED]
    assert blocks[1].text is None


def test_zero_instruction_file_limit_never_reads_body(tmp_path):
    (tmp_path / "AGENTS.md").write_text("body")
    (block,), _ = collect(tmp_path, (repo(),), repo_max_files=0)
    assert block.status is HostReadStatus.OVER_MAX_FILES
    assert block.text is None
