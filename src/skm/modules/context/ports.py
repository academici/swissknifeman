"""P00 contract declarations; behavior belongs to the owning implementation leaf."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.gateways import control_plane_gateway, host_gateway
from skm.kernel.ports_uow import repository_port

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime
    from uuid import UUID

    from skm.kernel.actor import Actor
    from skm.kernel.cancel import CancelToken
    from skm.kernel.ids import ContextManifestId, ProjectId, WorkspaceId
    from skm.kernel.json_types import JsonObject
    from skm.kernel.ports_uow import UnitOfWork
    from skm.modules.context.domain.contracts import Digest, MemoryHit, Page, StoredResearchResult
    from skm.modules.context.domain.manifest import ContextManifest, ManifestBlock
    from skm.modules.context.domain.research import (
        RawSourceReply,
        ResearchDocument,
        ResearchSourceConfig,
        SourceQuery,
    )


@dataclass(frozen=True, slots=True)
class ContextOwnerClaim:
    assignment_id: UUID
    attempt_id: UUID
    worker_id: UUID
    fencing_token: int

    def __post_init__(self) -> None:
        if type(self.fencing_token) is not int or self.fencing_token < 1:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "fencing_token must be positive")


@control_plane_gateway
class ContextOwnerGuard(Protocol):
    def require_current(
        self, uow: UnitOfWork, actor: Actor, owner_ref: str, claim: ContextOwnerClaim, now: datetime
    ) -> None: ...

    def research_policy(
        self,
        uow: UnitOfWork,
        actor: Actor,
        project_id: ProjectId,
        *,
        step_ref: str | None,
        for_update: bool,
        now: datetime,
        permission: str = "context.read",
    ) -> JsonObject: ...

    # Server source constraints come from instance/authenticated host config; human step refs are scoped.
    # implemented adapters/execution/context_owner.py; locks execution ownership until UoW commit


@repository_port
class ContextRepository(Protocol):
    def add_draft(self, manifest: ContextManifest) -> None: ...  # state='draft' + блоки фазы A
    def get(self, manifest_id: ContextManifestId, *, for_update: bool = False) -> ContextManifest: ...
    def for_step(self, step_ref: str) -> ContextManifest: ...
    def finalize(
        self, manifest: ContextManifest, host_rows: Sequence[ManifestBlock]
    ) -> None: ...  # state draft→final, UPDATE … WHERE state='draft'


@repository_port
class TextStore(Protocol):  # content-addressed тексты
    def put_many(self, texts: Mapping[Digest, str]) -> None: ...  # ON CONFLICT DO NOTHING
    def get_many(self, digests: Sequence[Digest]) -> Mapping[Digest, str]: ...


# MemoryHit различает source_kind=memory_entry|lesson, source_ref и exact source_version/content_digest;
# DraftBlock/ManifestBlock source_kind остаётся допустимым enum memory: lesson → source_ref knowledge:<id>,
# entry → memory:<id>; MemoryHit.source_kind не копируется в wire enum.
# только source_kind=lesson попадает в exposed_lesson_refs. Lesson metadata включает applicability/freshness
# и atomic_group из knowledge conflict group; текст и refs сохраняют исходный scope/classification.
@control_plane_gateway
class MemoryRetriever(Protocol):  # gateway ctx.gateways.memory_retriever
    def search(
        self,
        uow: UnitOfWork,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        project_id: ProjectId,
        query: str,
        top_k: int,
    ) -> tuple[MemoryHit, ...]: ...


@host_gateway
class CheckoutReader(Protocol):  # host gateway checkout_fs
    def read(
        self, mount: str, rel_path: str, *, max_bytes: int, follow_symlinks: bool
    ) -> ReadOutcome: ...  # ReadOutcome(status, data: bytes | None, size, resolved_path)
    def first_existing(
        self, mount: str, rel_dir: str, names: Sequence[str], *, max_bytes: int, follow_symlinks: bool
    ) -> ReadOutcome: ...
    def expand(self, mount: str, glob: str, *, limit: int) -> tuple[tuple[str, ...], bool]: ...
    def mount_root(
        self, mount: str
    ) -> str: ...  # абсолютный путь mount в среде попытки (для filesystem-источника)


type CodeGraphAction = Literal["init", "index", "status", "doctor"]


@host_gateway
class CodeGraphIndex(Protocol):
    def manage(self, action: CodeGraphAction, checkout: str, *, cancel: CancelToken) -> JsonObject: ...


@host_gateway
class ResearchSource(Protocol):
    kind: str

    def validate_config(
        self, config: ResearchSourceConfig
    ) -> tuple[str, ...]: ...  # проблемы → RESEARCH_SOURCE_INVALID
    def search(
        self, config: ResearchSourceConfig, query: SourceQuery, *, cancel: CancelToken
    ) -> RawSourceReply: ...

    # исключения: SourceBusy (повторяемо: timeout/занят) | SourceFailed(code, message)


@host_gateway
class ResearchSourceRegistry(Protocol):  # HostGateways.research_sources
    def kinds(self) -> frozenset[str]: ...
    def get(self, kind: str) -> ResearchSource: ...  # NotFound(kind="research_source_kind")


@repository_port
class ResearchRepository(Protocol):
    def add_results(
        self, results: Sequence[StoredResearchResult]
    ) -> None: ...  # research_queries + external_sources
    def find_cached(
        self, *, workspace_id: WorkspaceId, project_id: ProjectId, cache_key: Digest, now: datetime
    ) -> StoredResearchResult | None: ...
    def get(self, query_id: str) -> StoredResearchResult: ...
    def documents(self, document_ids: Sequence[str]) -> tuple[ResearchDocument, ...]: ...
    def results_for_step(self, step_ref: str) -> tuple[StoredResearchResult, ...]: ...
    def list_documents(
        self,
        *,
        workspace_id: WorkspaceId,
        project_id: ProjectId,
        query_id: str | None,
        origin_prefix: str | None,
        after: str | None,
        limit: int,
    ) -> Page[ResearchDocument]: ...


@dataclass(frozen=True, slots=True)
class ReadOutcome:
    status: str
    data: bytes | None
    size: int | None
    resolved_path: str | None
