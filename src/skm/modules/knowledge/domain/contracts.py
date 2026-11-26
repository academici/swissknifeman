"""P00 declarations; behavior is implemented by the owning leaf."""

from __future__ import annotations

from uuid import UUID

from skm.kernel.json_types import JsonObject

type Adjacency = JsonObject

type CandidateId = UUID
type GraphQueryEcho = JsonObject
type GraphStats = JsonObject
type LessonView = JsonObject
type MemoryEntryView = JsonObject
type ReplaceStats = JsonObject
