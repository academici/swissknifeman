"""Discover a vault and resolve bounded project mappings on the caller's host."""

from __future__ import annotations

import json
from collections.abc import Iterable
from hashlib import sha256
from typing import TYPE_CHECKING, Protocol, cast
from unicodedata import normalize
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, Forbidden, NotFound, PreconditionFailed, SkmError
from skm.kernel.ids import HostId
from skm.modules.exports.domain.frontmatter import FrontmatterValue, read
from skm.modules.exports.domain.note import validate_relative_path
from skm.modules.exports.domain.vault import VaultIdentity, VaultLocation
from skm.modules.exports.domain.vault_catalog import VaultProjectMatch
from skm.modules.exports.generated.settings import ExportsVaultSettings
from skm.modules.exports.ports import VaultFs
from skm.modules.workspace.public import CheckoutLocationView, GetProject, ProjectView, ResolveCheckout

if TYPE_CHECKING:
    from skm.application_bus.host import HostContext
    from skm.kernel.json_types import JsonObject, JsonValue

__all__ = ["run"]

_MAX_CATALOG = 1 << 20
_MAX_HEAD = 8192


class VaultBackend(VaultFs, Protocol):
    """Local capabilities used by discovery, binding and the delivery journal."""

    def at(self, root: str) -> VaultBackend: ...
    def state(self) -> VaultBackend: ...
    def monotonic(self) -> float: ...
    def retry_time(self) -> float: ...
    def retry_jitter(self) -> float: ...
    def normalize_locator(self, locator: str) -> str: ...
    def version(self, rel: str) -> tuple[int, ...] | None: ...
    def read_identity(self) -> VaultIdentity | None: ...
    def require_writer(self, host_id: HostId) -> VaultIdentity: ...
    def update_identity(self, host_id: HostId, *, fork: bool, deadline_seconds: float) -> VaultIdentity: ...


class HostSettings(Protocol):
    def get(self, key: str) -> object: ...


def _vault_not_found() -> PreconditionFailed:
    return PreconditionFailed(
        ErrorCode.EXPORT_VAULT_NOT_FOUND,
        "No vault was found",
        details={"hint": "skm config set exports.vault.path <dir> --level host"},
    )


def vault_settings(config: object) -> ExportsVaultSettings:
    values = cast("HostSettings", config)
    settings = {
        key: value
        for key in (
            "exports.vault.path",
            "exports.vault.candidates",
            "exports.vault.projects_dir",
            "exports.vault.lock_deadline_seconds",
            "exports.vault.push_interval_seconds",
        )
        if (value := values.get(key)) is not None
    }
    if "exports.vault.path" not in settings and "exports.vault.candidates" not in settings:
        raise _vault_not_found()
    return ExportsVaultSettings.from_settings(settings)


def discover(ctx: HostContext, settings: ExportsVaultSettings) -> tuple[VaultLocation, VaultBackend]:
    gateway = cast("VaultBackend", ctx.gateways.get(VaultFs))
    if settings.path is not None:
        fs = gateway.at(settings.path)
        if not fs.is_dir("."):
            raise PreconditionFailed(ErrorCode.EXPORT_VAULT_MISSING, "Configured vault directory is missing")
        return VaultLocation(str(fs.root), "config", fs.is_dir(".obsidian")), fs
    for candidate in settings.candidates:
        ctx.cancel.raise_if_cancelled()
        fs = gateway.at(candidate)
        if fs.is_dir(".obsidian"):
            return VaultLocation(str(fs.root), "candidate", True), fs
    raise _vault_not_found()


class Budget:
    def __init__(self, ctx: HostContext, fs: VaultBackend) -> None:
        self.ctx, self.fs = ctx, fs
        self.deadline = fs.monotonic() + 60
        self.scan: JsonObject = {"entries": 10000, "include_dirs": True, "deadline": self.deadline}
        self.remaining = 100 << 20

    def check(self, *, entries: int = 0, size: int = 0) -> None:
        self.ctx.cancel.raise_if_cancelled()
        remaining = cast("int", self.scan["entries"]) - entries
        self.scan["entries"] = remaining
        self.remaining -= size
        if remaining < 0 or self.remaining < 0 or self.fs.monotonic() >= self.deadline:
            raise BackendUnavailable(
                ErrorCode.BACKEND_UNAVAILABLE,
                "Vault operation budget exceeded",
                details={"reason": "budget_exceeded"},
            )


def _mapping_error(reason: str, candidates: list[str] | None = None) -> PreconditionFailed:
    paths: list[JsonValue] = list(candidates or ())
    return PreconditionFailed(
        ErrorCode.EXPORT_VAULT_PROJECT_UNKNOWN,
        "Vault project mapping requires attention",
        details={"reason": reason, "candidates": paths},
    )


def _folder(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("missing vault destination")
    folder = "/".join(normalize("NFC", part) for part in value.split("/") if part not in {"", "."})
    if value.startswith(("/", "~")):
        raise ValueError("absolute vault destination")
    validate_relative_path(folder)
    return folder


def _strings(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, tuple) and all(isinstance(item, str) for item in cast("tuple[object, ...]", value)):
        return cast("tuple[str, ...]", value)
    raise ValueError("invalid project selector")


type MappingRow = tuple[tuple[str, ...], tuple[str, ...], str]


class Catalog:
    def __init__(self, fs: VaultBackend, projects_dir: str, budget: Budget) -> None:
        self.fs, self.projects_dir, self.budget = fs, projects_dir, budget
        self.versions: dict[str, tuple[int, ...] | None] = {}
        self._catalog: list[MappingRow] | None = None
        self._controls: list[MappingRow] | None = None
        self._matches: dict[UUID, VaultProjectMatch | None] = {}
        self._invalid: dict[UUID, PreconditionFailed] = {}

    def _version(self, path: str) -> None:
        self.budget.check(entries=1)
        self.versions[path] = self.fs.version(path)

    def check_unchanged(self) -> None:
        for path, previous in self.versions.items():
            self.budget.check(entries=1)
            try:
                current = self.fs.version(path)
            except (OSError, SkmError):
                raise _mapping_error("invalid_or_unreadable_mapping") from None
            if current != previous:
                raise _mapping_error("mapping_changed")

    def path_versions(self, paths: Iterable[str], *, missing: bool = False) -> str:
        """Fingerprint only paths that could unblock a failed delivery."""
        versions = sha256()
        for path in paths:
            self.budget.check(entries=1)
            value: tuple[int | str | None, ...] | None
            try:
                value = None if missing else self.fs.version(path)
            except OSError as exc:
                value = (exc.errno,)
            except SkmError as exc:
                value = (exc.code.value,)
            versions.update(repr((path, value)).encode())
        return versions.hexdigest()

    def _load_catalog(self) -> list[MappingRow]:
        path = ".projects.json"
        self._version(path)
        self.budget.check(size=_MAX_CATALOG)
        raw = self.fs.read_bounded(path, max_bytes=_MAX_CATALOG)
        self.budget.check(size=len(raw or b"") - _MAX_CATALOG)
        if raw is None:
            return []
        document = json.loads(raw)
        rows = document["projects"]
        if not isinstance(rows, list):
            raise ValueError("invalid projects catalog")
        return [
            (_strings(row.get("skm_project")), _strings(row.get("repo")), _folder(row["vault_path"]))
            for row in cast("list[JsonObject]", rows)
        ]

    def _load_controls(self) -> list[MappingRow]:
        self._version(self.projects_dir)
        result: list[MappingRow] = []
        for path in self.fs.glob(self.projects_dir, "*.md", budget=self.budget.scan):
            self._version(path)
            if path.endswith("/"):
                continue
            self.budget.check(size=_MAX_HEAD)
            raw = self.fs.read_head(path, limit=_MAX_HEAD)
            if raw is None:
                raise _mapping_error("mapping_changed")
            self.budget.check(size=len(raw) - _MAX_HEAD)
            fields: dict[str, FrontmatterValue] = {}
            header = raw.replace(b"\r\n", b"\n")
            if header.startswith(b"---\n"):
                end = header.find(b"\n---\n", 3)
                if end < 0 and len(raw) < _MAX_HEAD and header.endswith(b"\n---"):
                    header += b"\n"
                    end = len(header) - 5
                parsed = read(header[: end + 5].decode("utf-8")) if end >= 0 else None
                if parsed is None:
                    raise _mapping_error("invalid_control_note")
                fields = dict(parsed)
            project, repos = _strings(fields.get("skm_project")), _strings(fields.get("repo"))
            if project or repos:
                result.append((project, repos, _folder(path.rpartition("/")[0])))
        return result

    def _checkout(self, project: ProjectView) -> str | None:
        mount = next((m for m in project.mounts if m.role == "primary"), None)
        if mount is None:
            return None
        ctx = self.budget.ctx
        try:
            locator = cast(
                "CheckoutLocationView",
                ctx.client.ask(ResolveCheckout(project.project_id, mount.mount_name, ctx.host_id)),
            )
        except NotFound:
            return None
        return self.fs.normalize_locator(locator.local_locator) if locator.state == "active" else None

    def _select(
        self,
        rows: list[MappingRow],
        project: ProjectView,
        via: str,
    ) -> VaultProjectMatch | None:
        keys = {str(project.project_id), project.slug}
        matches = {folder for projects, _, folder in rows if keys.intersection(projects)}
        if any(repos for projects, repos, _ in rows if not projects):
            root = self._checkout(project)
            if root is not None:
                matches.update(
                    folder
                    for projects, repos, folder in rows
                    if not projects and any(self.fs.normalize_locator(repo) == root for repo in repos)
                )
        if len(matches) > 1:
            raise _mapping_error("ambiguous_mapping", sorted(matches))
        if not matches:
            return None
        return VaultProjectMatch(
            matches.pop(), project.slug, "catalog" if via == "catalog" else "control_note"
        )

    def _find(self, project_id: UUID) -> VaultProjectMatch | None:
        ctx = self.budget.ctx
        project = cast("ProjectView", ctx.client.ask(GetProject(project_id)))
        if project.state != "active":
            raise Forbidden(ErrorCode.FORBIDDEN, "Archived project cannot receive vault notes")
        if self._catalog is None:
            self._catalog = self._load_catalog()
        match = self._select(self._catalog, project, "catalog")
        if match is not None:
            return match
        if self._controls is None:
            self._controls = self._load_controls()
        return self._select(self._controls, project, "control_note")

    def find(self, project_id: UUID) -> VaultProjectMatch | None:
        if project_id in self._invalid:
            raise self._invalid[project_id]
        if project_id not in self._matches:
            try:
                self._matches[project_id] = self._find(project_id)
            except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
                error = self._invalid[project_id] = _mapping_error("invalid_or_unreadable_mapping")
                raise error from None
            except SkmError as exc:
                if exc.code in (ErrorCode.INTEGRATION_UNSAFE_TARGET, ErrorCode.SCHEMA_INVALID):
                    error = self._invalid[project_id] = _mapping_error("invalid_or_unreadable_mapping")
                    raise error from None
                if isinstance(exc, PreconditionFailed) and exc.code == ErrorCode.EXPORT_VAULT_PROJECT_UNKNOWN:
                    self._invalid[project_id] = exc
                raise
        return self._matches[project_id]

    def mapping_valid(self, project_id: UUID) -> bool:
        try:
            self.find(project_id)
        except SkmError as exc:
            if exc.code != ErrorCode.EXPORT_VAULT_PROJECT_UNKNOWN:
                raise
            return False
        return True


def run(ctx: HostContext, request: JsonObject) -> JsonObject:
    settings = vault_settings(ctx.config)
    location, fs = discover(ctx, settings)
    identity = fs.read_identity()
    report: JsonObject = {
        "root": location.root,
        "source": location.source,
        "obsidian": location.obsidian,
    }
    project_id = request.get("project_id")
    if project_id is not None:
        try:
            match = Catalog(fs, settings.projects_dir, Budget(ctx, fs)).find(UUID(str(project_id)))
            report["project_folder"] = match.folder if match else None
        except SkmError as exc:
            report["mapping_error"] = {"code": exc.code.value, **exc.details}
    fork, writer = request.get("fork_identity", False), request.get("bind_writer")
    if fork or writer is not None:
        if (fork and writer is not None) or (writer is not None and writer != str(ctx.host_id)):
            raise Forbidden(ErrorCode.FORBIDDEN, "Writer binding requires this host's ID")
        if "mapping_error" not in report:
            identity = fs.update_identity(
                ctx.host_id, fork=bool(fork), deadline_seconds=settings.lock_deadline_seconds
            )
    report["vault_id"] = str(identity.vault_id) if identity else None
    report["writer_host_id"] = str(identity.writer_host_id) if identity and identity.writer_host_id else None
    return report
