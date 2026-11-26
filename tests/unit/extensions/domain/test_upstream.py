"""Unit tests for ``skm.modules.extensions.domain.upstream`` (extensions §9)."""

from __future__ import annotations

import hashlib
from datetime import date

import pytest

from skm.modules.extensions.domain.kinds import ResourceKind
from skm.modules.extensions.domain.provenance import (
    Provenance,
    ProvenanceSource,
    UpstreamFile,
    UpstreamStrategy,
)
from skm.modules.extensions.domain.upstream import (
    UpstreamFileResult,
    UpstreamItem,
    compare_upstream,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_local_provenance_reports_local_without_files() -> None:
    prov = Provenance(source=ProvenanceSource.LOCAL)
    result = compare_upstream(ResourceKind.SKILL, "review", prov, {"SKILL.md": b"# ignored"})
    assert result == UpstreamItem(
        kind=ResourceKind.SKILL,
        key="review",
        strategy=None,
        status="local",
        files=(),
    )
    assert result.to_json() == {
        "kind": "skill",
        "key": "review",
        "strategy": None,
        "status": "local",
        "files": [],
    }

    # Missing or empty manifest provenance also defaults to local
    assert compare_upstream(ResourceKind.STEERING, "style", None).status == "local"
    assert compare_upstream(ResourceKind.STEERING, "style", {"key": "style"}).status == "local"


@pytest.mark.parametrize(
    "strategy",
    [
        UpstreamStrategy.REPLACE,
        UpstreamStrategy.NOTIFY,
        UpstreamStrategy.FORK,
        UpstreamStrategy.MERGE,
    ],
)
def test_upstream_strategies_report_up_to_date_and_changed_without_mutation(
    strategy: UpstreamStrategy,
) -> None:
    v1_skill = b"# Skill v1\n"
    v1_ref = b"Reference v1\n"
    v2_skill = b"# Skill v2 (updated)\n"

    prov = Provenance(
        source=ProvenanceSource.UPSTREAM,
        repo="https://example.com/skills",
        strategy=strategy,
        upstream_sha=_sha(v1_skill),
        files=(
            UpstreamFile(
                path="SKILL.md",
                url="https://example.com/skills/SKILL.md",
                sha256=_sha(v1_skill),
                fetched_at=date(2026, 1, 1),
            ),
            UpstreamFile(
                path="references/guide.md",
                url="https://example.com/skills/references/guide.md",
                sha256=_sha(v1_ref),
                fetched_at=date(2026, 1, 1),
            ),
        ),
    )

    up_to_date = compare_upstream(
        ResourceKind.SKILL,
        "review",
        prov,
        {"SKILL.md": v1_skill, "references/guide.md": v1_ref},
    )
    assert up_to_date.status == "up_to_date"
    assert up_to_date.strategy == strategy.value
    assert up_to_date.files == (
        UpstreamFileResult(
            path="SKILL.md",
            recorded_sha256=_sha(v1_skill),
            upstream_sha256=_sha(v1_skill),
        ),
        UpstreamFileResult(
            path="references/guide.md",
            recorded_sha256=_sha(v1_ref),
            upstream_sha256=_sha(v1_ref),
        ),
    )

    changed = compare_upstream(
        ResourceKind.SKILL,
        "review",
        prov,
        {"SKILL.md": v2_skill, "references/guide.md": v1_ref},
    )
    assert changed.status == "changed"
    assert changed.strategy == strategy.value
    assert changed.files[0].recorded_sha256 == _sha(v1_skill)
    assert changed.files[0].upstream_sha256 == _sha(v2_skill)
    assert changed.files[1].recorded_sha256 == _sha(v1_ref)
    assert changed.files[1].upstream_sha256 == _sha(v1_ref)


@pytest.mark.parametrize(
    "strategy",
    [
        UpstreamStrategy.REPLACE,
        UpstreamStrategy.NOTIFY,
        UpstreamStrategy.FORK,
        UpstreamStrategy.MERGE,
    ],
)
def test_unreachable_is_never_treated_as_up_to_date(strategy: UpstreamStrategy) -> None:
    body = b"# Skill body\n"
    ref = b"# Reference body\n"
    prov = Provenance(
        source=ProvenanceSource.UPSTREAM,
        strategy=strategy,
        upstream_sha=_sha(body),
        files=(
            UpstreamFile(
                path="SKILL.md",
                url="https://example.com/SKILL.md",
                sha256=_sha(body),
                fetched_at=date(2026, 1, 1),
            ),
            UpstreamFile(
                path="references/ref.md",
                url="https://example.com/ref.md",
                sha256=_sha(ref),
                fetched_at=date(2026, 1, 1),
            ),
        ),
    )

    # All files unreachable (None or missing from fetched map)
    all_missing = compare_upstream(ResourceKind.SKILL, "review", prov, {})
    assert all_missing.status == "unreachable"
    assert all_missing.status != "up_to_date"
    assert all(f.upstream_sha256 is None for f in all_missing.files)

    # Partial failure: first file matches recorded sha256, second file is unreachable
    partial = compare_upstream(
        ResourceKind.SKILL,
        "review",
        prov,
        {"SKILL.md": body, "references/ref.md": None},
    )
    assert partial.status == "unreachable"
    assert partial.files[0].upstream_sha256 == _sha(body)
    assert partial.files[1].upstream_sha256 is None


def test_compare_upstream_accepts_manifest_mapping_url_keys_and_local_files() -> None:
    content = b"prompt content\n"
    digest = _sha(content)
    manifest = {
        "key": "review",
        "provenance": {
            "source": "upstream",
            "strategy": "fork",
            "upstream_sha": digest,
            "files": [
                {
                    "path": "SKILL.md",
                    "url": "https://example.com/SKILL.md",
                    "sha256": f"sha256:{digest}",
                    "fetched_at": "2026-02-01",
                }
            ],
        },
    }

    # Fetched keyed by URL and recorded digest with sha256: prefix
    res = compare_upstream(
        ResourceKind.SKILL,
        "review",
        manifest,
        {"https://example.com/SKILL.md": content},
    )
    assert res.status == "up_to_date"
    assert res.strategy == "fork"
    assert res.files[0].upstream_sha256 == f"sha256:{digest}"

    # Local divergence detected when local_files differs from upstream
    diverged = compare_upstream(
        ResourceKind.SKILL,
        "review",
        manifest,
        {"SKILL.md": content},
        local_files={"SKILL.md": b"locally edited fork\n"},
    )
    assert diverged.status == "changed"


def test_empty_upstream_files_list_reports_unreachable() -> None:
    prov = Provenance(
        source=ProvenanceSource.UPSTREAM,
        strategy=UpstreamStrategy.NOTIFY,
        files=(),
    )
    res = compare_upstream(ResourceKind.SKILL, "empty-upstream", prov, {})
    assert res.status == "unreachable"
    assert res.strategy == "notify"
    assert res.files == ()
