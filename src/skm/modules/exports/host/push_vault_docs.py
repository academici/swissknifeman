"""Publish admitted checkout documents to a locally bound writer vault."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Generator, Iterable, Iterator, Sequence
from contextlib import AbstractContextManager, ExitStack, contextmanager, nullcontext
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING, Protocol, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import (
    BackendUnavailable,
    CapabilityUnavailable,
    Forbidden,
    PreconditionFailed,
    SkmError,
    ValidationFailed,
)
from skm.kernel.gateways import host_gateway
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.access.public import WhoAmI, WhoAmIView
from skm.modules.exports.domain.docs_push import destination, matches, safe_pattern, sensitive
from skm.modules.exports.domain.note import validate_relative_path
from skm.modules.exports.generated.host import push_vault_docs_request_from_json
from skm.modules.exports.generated.settings import ExportsDocsSettings
from skm.modules.exports.ports import VaultFs
from skm.modules.workspace.public import CheckoutLocationView, ResolveCheckout

from .locate_vault import Budget, Catalog, HostSettings, VaultBackend, discover, vault_settings

if TYPE_CHECKING:
    from skm.application_bus.host import HostContext

_MAX_FILES = 1000
_MAX_BYTES = 100 << 20
_OUTCOMES = ("copied", "identical", "conflicts", "refused")


class SourceRefused(Exception):
    """The gateway rejected a single source. Its reason is a fixed diagnostic code."""


class DocumentTree(Protocol):
    def entries(
        self, visit: Callable[[], None], exclude: Callable[[str], bool]
    ) -> Iterator[tuple[str, str | None]]:
        """Charge each entry and prune excluded/protected directories before opening them."""
        ...

    def read(self, path: str, max_bytes: int, budget: Budget) -> bytes:
        """Open beneath the pinned root once and verify the descriptor before and after the read."""
        ...


@host_gateway
class DocsCheckoutFs(Protocol):
    def open_checkout(self, locator: str, *, vault_root: str) -> AbstractContextManager[DocumentTree]: ...


def _exhausted() -> BackendUnavailable:
    return BackendUnavailable(
        ErrorCode.BACKEND_UNAVAILABLE,
        "Document export budget exceeded",
        details={"reason": "budget_exceeded"},
    )


def _admit(ctx: HostContext, project: UUID) -> None:
    identity = cast("WhoAmIView", ctx.client.ask(WhoAmI(project)))
    if not identity.modules.get("exports"):
        raise PreconditionFailed(ErrorCode.MODULE_DISABLED, "Exports are disabled")
    if (
        identity.principal.kind not in {"human", "service"}
        or (identity.token and identity.token.kind == "assignment")
        or not {"file.read", "export.run"}.issubset(identity.effective_permissions)
    ):
        raise Forbidden(ErrorCode.FORBIDDEN, "Publishing documents requires export.run and file.read")


def _settings(config: object, project: UUID) -> ExportsDocsSettings:
    for_scope = getattr(config, "for_scope", None)
    values = cast("HostSettings", for_scope("project", project) if for_scope else config)
    keys = ("exports.docs.patterns", "exports.docs.max_file_bytes", "exports.docs.vault_subfolder")
    return ExportsDocsSettings.from_settings(
        {key: value for key in keys if (value := values.get(key)) is not None}
    )


@dataclass(frozen=True, slots=True)
class Candidate:
    source: str
    target: str | None
    refusal: str | None


def _select(
    entries: Iterable[tuple[str, str | None]],
    patterns: Sequence[tuple[str, ...]],
    folder: str,
    subfolder: str,
) -> Iterator[Candidate]:
    selected: list[Candidate] = []
    for path, refusal in entries:
        pruned = refusal in {"sensitive_path", "protected_path"}
        if not any(matches(path, pattern, subtree=pruned) for pattern in patterns):
            continue
        if len(selected) >= _MAX_FILES:
            raise _exhausted()
        try:
            target = destination(folder, subfolder, path)
        except ValidationFailed:
            selected.append(Candidate(path, None, refusal or "unsafe_path"))
        else:
            selected.append(Candidate(path, target, refusal))

    counts = Counter(item.target.casefold() for item in selected if item.target)
    for item in sorted(selected, key=lambda item: item.source):
        if item.target and counts[item.target.casefold()] > 1:
            yield Candidate(item.source, item.target, "destination_collision")
        else:
            yield item


class Push:
    def __init__(
        self, fs: VaultBackend, budget: Budget, meta: JsonObject, *, dry_run: bool, force: bool
    ) -> None:
        self.fs, self.budget = fs, budget
        self.dry_run, self.force = dry_run, force
        self.rows: dict[str, list[JsonValue]] = {key: [] for key in _OUTCOMES}
        self.report: JsonObject = {**meta, **self.rows, "dry_run": dry_run, "force": force, "partial": False}
        self.state = fs.state()
        self.writable = _MAX_BYTES
        self.sequence = 0
        self.prefix = f"docs/{meta['vault_id']}/{fs.monotonic().hex()}"
        self.started = False

    def reserve(self, size: int) -> None:
        self.budget.check()
        if size > self.writable:
            raise _exhausted()
        self.writable -= size

    def start(self) -> None:
        if self.dry_run:
            return
        self.report["host_report"] = self.prefix
        header = json.dumps({**self.report, "partial": True, "reason": "in_progress"}).encode()
        self.reserve(len(header) + 1024)  # keep room for terminal totals even after budget exhaustion
        if not self.state.create_new(self.prefix + "/report.json", header):
            raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "Document export report already exists")
        self.started = True

    def finish(self) -> JsonObject:
        totals: JsonObject = {key: len(rows) for key, rows in self.rows.items()}
        self.report["totals"] = totals
        self._write_outcome()
        if not self.report["partial"] and self.budget.fs.monotonic() >= self.budget.deadline:
            self.report.update(partial=True, reason="budget_exceeded")
            self._write_outcome()
        return self.report

    def _write_outcome(self) -> None:
        if self.started:
            summary = {k: self.report[k] for k in ("partial", "reason", "totals") if k in self.report}
            self.state.write_atomic(self.prefix + "/outcome.json", json.dumps(summary).encode(), replace=True)

    def existing(self, target: str, data: bytes) -> str | None:
        version = self.fs.version(target)
        if version is None:
            return None
        if version[2] != len(data):
            return "conflicts"
        size = len(data) + 1
        self.budget.check(size=size)
        try:
            observed = self.fs.read_bounded(target, max_bytes=len(data))
        except ValidationFailed:
            # The file may have grown between stat and read. Fail closed on unsafe targets.
            raise SourceRefused("destination_changed") from None
        self.budget.check(size=len(observed or b"") - size)
        if observed is None:
            return None
        return "identical" if observed == data else "conflicts"

    def publish(self, target: str, data: bytes) -> str:
        self.budget.check()
        if self.force:
            self.fs.write_atomic(target, data, replace=True)
        elif not self.fs.create_new(target, data):
            current = self.existing(target, data)
            if current is None:
                raise SourceRefused("destination_changed")
            return current
        return "copied"

    def process(self, tree: DocumentTree, item: Candidate, max_bytes: int, guard: Callable[[], None]) -> None:
        self.sequence += 1
        row: JsonObject = {
            "source": item.source,
            "destination": item.target,
            "classification": "restricted",
            "classification_basis": "conservative_unknown",
        }
        record_path = f"{self.prefix}/{self.sequence}.json"
        outcome = "refused"
        reserved = 0
        try:
            if item.refusal or item.target is None:
                raise SourceRefused(item.refusal or "unsafe_path")
            guard()
            data = tree.read(item.source, max_bytes, self.budget)
            row.update(digest="sha256:" + sha256(data).hexdigest(), bytes=len(data))
            current = self.existing(item.target, data)
            if current == "identical" or (current == "conflicts" and not self.force):
                outcome = current
            else:
                guard()
                if not self.dry_run:
                    planned = json.dumps({**row, "outcome": "planned"}).encode()
                    reserved = len(planned) + 128
                    self.reserve(len(planned) + reserved + len(data))
                    self.state.write_atomic(record_path, planned, replace=True)
                    outcome = self.publish(item.target, data)
                else:
                    self.reserve(len(data))
                    outcome = "copied"
        except SourceRefused as error:
            row["reason"] = str(error)
        except ValidationFailed as error:
            if error.code is not ErrorCode.INTEGRATION_UNSAFE_TARGET:
                raise
            row["reason"] = error.details.get("reason", "unsafe_path")
        self.rows[outcome].append(row)
        if not self.dry_run:
            observed = json.dumps({**row, "outcome": outcome}).encode()
            if not reserved:
                self.reserve(len(observed))
            self.state.write_atomic(record_path, observed, replace=True)


def push_vault_docs(
    ctx: HostContext,
    *,
    project_id: UUID,
    mount: str = "main",
    patterns: Sequence[str] | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> JsonObject:
    # The gateway clock is available before admission or any filesystem access.
    try:
        budget = Budget(ctx, cast("VaultBackend", ctx.gateways.get(VaultFs)))
    except CapabilityUnavailable:
        _admit(ctx, project_id)
        raise

    meta: JsonObject = {"host_id": str(ctx.host_id), "project_id": str(project_id), "mount": mount}
    push: Push | None = None
    try:
        _admit(ctx, project_id)
        budget.check()
        vault = vault_settings(ctx.config)
        settings = _settings(ctx.config, project_id)
        globs = tuple(safe_pattern(item) for item in (settings.patterns if patterns is None else patterns))
        gateway = ctx.gateways.get(DocsCheckoutFs) if globs else None
        validate_relative_path(settings.vault_subfolder)
        _, fs = discover(ctx, vault)
        budget.check(size=2 * 8193)
        identity = fs.require_writer(ctx.host_id)
        meta["vault_id"] = str(identity.vault_id)
        budget.check()
        catalog = Catalog(fs, vault.projects_dir, budget)
        checkout_query = ResolveCheckout(project_id, mount, ctx.host_id)
        location = cast("CheckoutLocationView", ctx.client.ask(checkout_query))
        budget.check()
        if location.state != "active" or location.is_stale:
            raise PreconditionFailed(ErrorCode.CHECKOUT_UNBOUND, "An active local checkout is required")
        meta["binding_id"] = str(location.binding_id)
        push = Push(fs, budget, meta, dry_run=dry_run, force=force)

        def guard() -> None:
            _admit(ctx, project_id)
            if ctx.client.ask(checkout_query) != location:
                raise PreconditionFailed(ErrorCode.CHECKOUT_MISMATCH, "Checkout binding changed")
            budget.check(size=2 * 8193)
            if fs.require_writer(ctx.host_id) != identity:
                raise PreconditionFailed(ErrorCode.INVALID_TRANSITION, "Vault writer binding changed")
            catalog.check_unchanged()

        match = catalog.find(project_id)
        budget.check()
        if match is None:
            raise PreconditionFailed(ErrorCode.EXPORT_VAULT_PROJECT_UNKNOWN, "No vault project mapping")
        with nullcontext() if dry_run else _lock(fs, budget, identity.vault_id, vault.lock_deadline_seconds):
            guard()
            push.start()
            if gateway is not None:
                with gateway.open_checkout(location.local_locator, vault_root=str(fs.root)) as tree:
                    paths = tree.entries(lambda: budget.check(entries=1), sensitive)
                    for candidate in _select(paths, globs, match.folder, settings.vault_subfolder):
                        budget.check()
                        push.process(tree, candidate, settings.max_file_bytes, guard)
        budget.check()
    except SkmError as error:
        reason = error.details.get("reason")
        if reason != "budget_exceeded" and (push is None or not push.started):
            raise
        if push is None:
            return {
                **meta,
                **{key: [] for key in _OUTCOMES},
                "totals": dict.fromkeys(_OUTCOMES, 0),
                "dry_run": dry_run,
                "force": force,
                "partial": True,
                "reason": reason,
            }
        push.report.update(
            partial=True,
            reason=error.details.get("outcome") or reason or error.code.value,
        )
    return push.finish()


@contextmanager
def _lock(fs: VaultBackend, budget: Budget, vault_id: UUID, timeout: int) -> Generator[None]:
    remaining = budget.deadline - budget.fs.monotonic()
    if remaining <= 0:
        raise _exhausted()
    with ExitStack() as stack:
        try:
            stack.enter_context(fs.lock(vault_id, deadline_seconds=min(remaining, timeout)))
        except BackendUnavailable:
            budget.check()
            raise
        budget.check()
        yield


def run(ctx: HostContext, request: JsonObject) -> JsonObject:
    try:
        args = cast("JsonObject", push_vault_docs_request_from_json(request))
    except ValueError:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid docs-push request") from None
    return push_vault_docs(
        ctx,
        project_id=UUID(cast("str", args["project_id"])),
        mount=cast("str", args.get("mount", "main")),
        patterns=cast("list[str] | None", args.get("patterns")),
        dry_run=args.get("dry_run") is True,
        force=args.get("force") is True,
    )
