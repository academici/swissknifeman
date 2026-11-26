"""P00 declarations; behavior is implemented by the owning leaf."""

from __future__ import annotations

from skm.kernel.json_types import JsonObject

type AdoptOutcome = JsonObject
type AgentPayload = JsonObject
type ClientLayer = JsonObject
type Diagnostic = JsonObject
type DriftReport = JsonObject
type HookBinding = JsonObject
type HookOutput = JsonObject
type InstructionBlock = JsonObject
type McpServerSpec = JsonObject
type NormalizedPermissions = JsonObject
type SkillPayload = JsonObject
type SourceRef = JsonObject

type SecretRef = str
type ScopeLevel = str
