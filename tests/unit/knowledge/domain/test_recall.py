import json
from dataclasses import replace
from datetime import timedelta
from uuid import UUID

from fakes.clock import DEFAULT_START
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.knowledge.domain.memory_entry import MemoryEntry, MemoryEntryId, forget, new_entry
from skm.modules.knowledge.domain.memory_kind import MemoryKind
from skm.modules.knowledge.domain.memory_scope import MemoryScope, MemoryScopeKind, recall_scopes
from skm.modules.knowledge.domain.recall import partition_recall, rank_entries, select_for_budget
from skm.modules.knowledge.domain.truncation import (
    TruncationReceipt,
    estimate_tokens_json,
    truncate_largest_list,
)
from skm.modules.knowledge.generated.settings import KnowledgeMemorySettings
from support.registries import settings_registry

_WORKSPACE = WorkspaceId(UUID(int=1))
_PROJECT = MemoryScope(MemoryScopeKind.PROJECT, ScopeId(UUID(int=2)), None, _WORKSPACE)
_SETTINGS = KnowledgeMemorySettings.from_settings(
    {spec.key: spec.default for spec in settings_registry().keys(section="knowledge")}
)


def _entry(
    key: int, body: str, *, kind: MemoryKind = MemoryKind.FACT, scope: MemoryScope = _PROJECT, shift: int = 0
) -> MemoryEntry:
    created = DEFAULT_START + timedelta(seconds=shift)
    return new_entry(
        entry_id=MemoryEntryId(UUID(int=key)),
        scope=scope,
        kind=kind,
        body=body,
        created_at=created,
        expires_at=created + timedelta(hours=48),
        created_by=PrincipalId(UUID(int=4)),
        writer="human",
        source="cli",
    )


def test_rank_uses_casefolded_unicode_tokens_kind_boost_and_recency() -> None:
    two_matches = _entry(1, "СБОРКА: die Straße ist frei", shift=-10)
    handoff = _entry(2, "Straße: handoff", kind=MemoryKind.ACTIVE_HANDOFF, shift=-6)
    blocker = _entry(3, "сборка остановлена", kind=MemoryKind.BLOCKER, shift=-5)
    older = _entry(4, "сборка продолжена", shift=-2)
    newer = _entry(5, "Straße: fertig", shift=-1)
    partial = _entry(6, "Пересборка. Я и x", shift=0)
    unmatched_boost = _entry(7, "No matches here", kind=MemoryKind.BLOCKER)
    entries = [older, unmatched_boost, newer, partial, handoff, two_matches, blocker]
    assert rank_entries(entries, "Сборка STRASSE Сборка я x", DEFAULT_START, _SETTINGS) == (
        two_matches,
        blocker,
        handoff,
        newer,
        older,
        unmatched_boost,
        partial,
    )
    assert rank_entries([older, newer], None, DEFAULT_START, _SETTINGS) == (newer, older)


def test_rank_excludes_expired_forgotten_future_and_beyond_configured_ttl() -> None:
    live = _entry(1, "Build: green")
    forgotten = forget(_entry(2, "Build: forgotten", kind=MemoryKind.BLOCKER), DEFAULT_START)
    expired = _entry(3, "Build: expired", shift=-48 * 3600)
    too_old = _entry(4, "Build: beyond the policy cap", shift=-12 * 3600)
    future = _entry(5, "Build: future", shift=61)
    settings = replace(_SETTINGS, max_ttl_hours=12, default_ttl_hours=12)
    assert rank_entries([forgotten, expired, too_old, future, live], "build", DEFAULT_START, settings) == (
        live,
    )


def test_shared_scope_quotas_preserve_private_and_exclude_unrequested_scopes() -> None:
    scopes = recall_scopes(_PROJECT, ("*", "ops", "team"), include_shared=True)
    private = [_entry(key, "private context", shift=-key) for key in range(1, 25)]
    shared = [
        [_entry(100 * index + key, "Build status", scope=scope, shift=-key) for key in range(1, 9)]
        for index, scope in enumerate(scopes[1:], start=1)
    ]
    foreign = _entry(900, "Build status", scope=replace(scopes[2], workspace_id=WorkspaceId(UUID(int=9))))
    other_project = _entry(901, "Build status", scope=replace(_PROJECT, scope_id=ScopeId(UUID(int=90))))
    ranked = rank_entries(
        [foreign, other_project, *private, *(entry for group in shared for entry in group)],
        "build",
        DEFAULT_START,
        _SETTINGS,
    )
    assert ranked[0] == foreign
    assert partition_recall(ranked, scopes, _SETTINGS) == (
        *private[:20],
        *(entry for group in shared for entry in group[:5]),
    )
    assert partition_recall(ranked, recall_scopes(_PROJECT, ("*", "ops")), _SETTINGS) == tuple(private[:20])
    assert partition_recall(ranked, scopes, replace(_SETTINGS, recall_shared_limit=0)) == tuple(private[:20])
    assert partition_recall(ranked, (), _SETTINGS) == ()


def test_digest_respects_per_item_and_total_budgets_at_word_boundaries() -> None:
    entries = [_entry(1, "alpha\tbeta gamma"), _entry(2, "сборка остановлена"), _entry(3, "rest")]
    assert select_for_budget(entries, budget_chars=16, item_max_chars=12) == ("alpha\tbeta", "сборка")
    assert select_for_budget(entries[:1], budget_chars=5, item_max_chars=12) == ("alpha",)
    assert select_for_budget(entries[1:], budget_chars=3) == ("\u0441\u0431\u043e",)
    assert select_for_budget(entries, budget_chars=0) == ()
    assert select_for_budget(entries, item_max_chars=0) == ()
    assert select_for_budget([_entry(4, "x" * 600)]) == ("x" * 500,)
    assert entries[0].body == "alpha\tbeta gamma"


def _compact_cost(payload: JsonValue) -> int:
    return estimate_tokens_json(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def test_compact_json_uses_unicode_length_and_inclusive_token_budget() -> None:
    assert estimate_tokens_json("") == 0
    assert estimate_tokens_json("абв") == 1
    assert estimate_tokens_json("абвг") == 2
    items: list[JsonValue] = ["абвг"] * 20
    payload: JsonObject = {"items": items}
    limit = _compact_cost(payload)
    assert estimate_tokens_json(json.dumps(payload, ensure_ascii=False, indent=2)) > limit
    assert truncate_largest_list(payload, limit) is payload


def test_truncation_fits_longest_prefix_of_largest_top_level_list() -> None:
    items: list[JsonValue] = [str(index) + "\u0430" * 100 for index in range(20)]
    others: list[JsonValue] = list(range(30))
    payload: JsonObject = {"primary": items, "others": others, "more": True}
    receipt: JsonObject = {
        "truncated": True,
        "returned_count": 6,
        "total_count": len(items),
        "hint": "response truncated by context limit; narrow your request (query/depth/project)",
    }
    expected: JsonObject = {**payload, "primary": items[:6], "primary_truncated": receipt}
    limit = _compact_cost(expected)
    actual = truncate_largest_list(payload, limit)
    assert actual == expected
    seven: JsonObject = {
        **expected,
        "primary": items[:7],
        "primary_truncated": {**receipt, "returned_count": 7},
    }
    assert _compact_cost(seven) > limit
    assert payload == {"primary": items, "others": others, "more": True}


def test_truncation_wraps_a_top_level_list_and_can_keep_zero_items() -> None:
    payload: list[JsonValue] = ["text" * 100] * 10
    result: JsonObject = {"items": payload[:2], **TruncationReceipt(2, 10).to_json()}
    limit = _compact_cost(result)
    assert truncate_largest_list(payload, limit) == result
    empty: JsonObject = {"items": [], **TruncationReceipt(0, 10).to_json()}
    assert truncate_largest_list(payload, _compact_cost(empty)) == empty
    assert truncate_largest_list(payload, 0) is payload


def test_truncation_leaves_errors_and_payloads_without_eligible_lists_intact() -> None:
    items: list[JsonValue] = ["long item" * 100] * 10
    error: JsonObject = {"code": "SCHEMA_INVALID", "issues": items}
    assert truncate_largest_list(error, 70, is_error=True) is error
    payloads: tuple[JsonObject, ...] = (
        {"nested": {"items": items}},
        {"items": [], "metadata": "long item" * 100},
        {"items": items, "items_truncated": "existing metadata"},
    )
    for payload in payloads:
        assert truncate_largest_list(payload, 70) is payload
