"""P00 contract declarations; behavior belongs to the owning implementation leaf."""

from __future__ import annotations

from skm.kernel.json_types import JsonObject

type Candidate = JsonObject
type Compatible = JsonObject
type Diagnostic = JsonObject
type Digest = str
type DraftMeta = JsonObject
type FindingItem = JsonObject
type HostFactsMeta = JsonObject
type MemoryHit = JsonObject
type Page[T] = JsonObject
type RouteRecord = JsonObject
type Selected = JsonObject
type SelfLoadView = JsonObject
type SkillSelectionTrace = JsonObject
type SnapshotBlock = JsonObject
type StoredResearchResult = JsonObject
type Validated = JsonObject
