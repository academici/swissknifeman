"""Publish an archive only after the exported snapshot and its immutable bytes agree."""

import json
import os
import re
import signal
import subprocess
from collections.abc import Callable, Generator, Iterable, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import datetime
from hashlib import file_digest, sha256
from importlib.metadata import version
from io import BufferedReader
from pathlib import Path
from shutil import copyfileobj, rmtree
from stat import S_ISREG
from typing import IO, cast
from uuid import UUID, uuid4

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.platform.fs.atomic_write import atomic_write, fsync_dir
from skm.platform.fs.safe_paths import safe_join
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.system_clock import SystemClock

URN = "urn:skm:platform:backup-manifest:v1"
MANIFEST = "backup-manifest.v1.json"
DUMP = "database.dump"
INVENTORY = "blobs.jsonl"
CLOSURE = "snapshot-closure.json"


def invalid(reason: str) -> PreconditionFailed:
    return PreconditionFailed(
        ErrorCode.INVALID_TRANSITION, "Backup or recovery precondition failed", details={"reason": reason}
    )


def json_bytes(value: JsonValue) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def json_object(data: bytes) -> JsonObject:
    def unique(items: list[tuple[str, JsonValue]]) -> JsonObject:
        result = dict(items)
        if len(result) != len(items):
            raise ValueError("Duplicate JSON key")
        return result

    def reject(value: str) -> JsonValue:
        raise ValueError(f"Invalid JSON constant {value}")

    try:
        value = json.loads(data, object_pairs_hook=unique, parse_constant=reject)
    except (ValueError, RecursionError):
        raise invalid("invalid_backup_json") from None
    if not isinstance(value, dict):
        raise invalid("invalid_backup_json")
    return cast("JsonObject", value)


@contextmanager
def open_regular(root: Path, relative: str) -> Generator[BufferedReader]:
    """Walk from an open directory without following symlinks, including parent components."""
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise invalid("unsafe_backup_path")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    folder = os.open(root, flags)
    try:
        for part in parts[:-1]:
            child = os.open(part, flags, dir_fd=folder)
            os.close(folder)
            folder = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
        with os.fdopen(fd, "rb") as stream:
            if not S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise invalid("unsafe_backup_file")
            yield stream
    finally:
        os.close(folder)


def fingerprint(root: Path, relative: str) -> tuple[str, int]:
    with open_regular(root, relative) as stream:
        digest = file_digest(stream, "sha256").hexdigest()
        return f"sha256:{digest}", stream.tell()


def bytes_digest(data: bytes) -> str:
    return "sha256:" + sha256(data).hexdigest()


@dataclass(frozen=True, slots=True)
class Blob:
    workspace_id: str
    digest: str
    size_bytes: int

    @property
    def key(self) -> str:
        raw = self.digest.removeprefix("sha256:")
        return f"{self.workspace_id}/objects/{raw[:2]}/{raw}"

    @property
    def path(self) -> str:
        return f"blobs/{self.key}"

    def to_json(self) -> JsonObject:
        return {
            "workspace_id": self.workspace_id,
            "digest": self.digest,
            "size_bytes": self.size_bytes,
            "path": self.path,
        }

    @classmethod
    def from_json(cls, value: JsonObject) -> "Blob":
        ws, digest, size = value.get("workspace_id"), value.get("digest"), value.get("size_bytes")
        if not isinstance(ws, str) or not isinstance(digest, str) or type(size) is not int or size < 0:
            raise invalid("invalid_blob_inventory")
        try:
            canonical_ws = str(UUID(ws))
        except ValueError:
            raise invalid("invalid_blob_inventory") from None
        blob = cls(ws, digest, size)
        if ws != canonical_ws or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest) or value != blob.to_json():
            raise invalid("invalid_blob_inventory")
        return blob


@dataclass(frozen=True, slots=True)
class Snapshot:
    instance_id: UUID
    schema_version: int
    server_version_num: int
    table_rows: dict[str, int]
    blobs: tuple[Blob, ...]
    dependencies: list[JsonObject]
    schema_baseline: tuple[str, str]

    def closure(self, inventory_digest: str) -> JsonObject:
        return {
            "instance_id": str(self.instance_id),
            "schema_version": self.schema_version,
            "schema_baseline": baseline_document(self.schema_baseline),
            "server_version_num": self.server_version_num,
            "table_rows": dict(self.table_rows),
            "inventory_digest": inventory_digest,
            "external_dependencies": list(self.dependencies),
        }


@dataclass(frozen=True, slots=True)
class ExportedSnapshot:
    snapshot: Snapshot
    dump: Callable[[Path], None]


def baseline_document(baseline: tuple[str, str]) -> JsonObject:
    epoch, chain_sha256 = baseline
    return {"epoch": epoch, "chain_sha256": chain_sha256}


def copy_blob(source: Path, relative: str, target: Path, key: str, blob: Blob) -> None:
    dest = safe_join(target, key)
    dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open_regular(source, relative) as incoming, dest.open("xb") as outgoing:
        copyfileobj(incoming, outgoing)
        outgoing.flush()
        os.fchmod(outgoing.fileno(), 0o444)
        os.fsync(outgoing.fileno())
    if fingerprint(target, key) != (blob.digest, blob.size_bytes):
        raise invalid("blob_checksum_mismatch")
    for folder in dest.parents:
        fsync_dir(folder)
        if folder == target:
            break


def create_backup(
    output: Path,
    blobs_root: Path,
    export: Callable[[], AbstractContextManager[ExportedSnapshot]],
) -> JsonObject:
    started = SystemClock().now()
    output = output.absolute()
    created = False
    try:
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        try:
            output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            output.mkdir(mode=0o700)
            created = True
        except FileExistsError:
            raise invalid("backup_path_already_exists") from None
        except OSError:
            raise invalid("backup_file_unavailable") from None
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)
        return _fill_backup(output, started, blobs_root, export)
    except BaseException:
        if created:
            rmtree(output)
        raise


def _fill_backup(
    output: Path,
    started: datetime,
    blobs_root: Path,
    export: Callable[[], AbstractContextManager[ExportedSnapshot]],
) -> JsonObject:
    try:
        fsync_dir(output.parent)
        with export() as exported:
            snapshot = exported.snapshot
            if snapshot.server_version_num < 160000:
                raise invalid("postgres_version_unsupported")
            # pg_dump creates its --file under the process umask; the dump holds the whole control plane,
            # so it is created owner-only first, like the archive's other files, and kept that way.
            os.close(os.open(output / DUMP, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
            exported.dump(output / DUMP)
            with open_regular(output, DUMP) as stream:
                os.fchmod(stream.fileno(), 0o600)
                os.fsync(stream.fileno())
        for blob in snapshot.blobs:
            copy_blob(blobs_root, blob.key, output, blob.path, blob)
        dump_digest, dump_size = fingerprint(output, DUMP)
        inventory = b"".join(json_bytes(blob.to_json()) for blob in snapshot.blobs)
        closure = json_bytes(snapshot.closure(bytes_digest(inventory)))
        atomic_write(output / CLOSURE, closure, mode=0o600)
        header: JsonObject = {"closure_digest": bytes_digest(closure), "inventory_size_bytes": len(inventory)}
        inventory = json_bytes(header) + inventory
        atomic_write(output / INVENTORY, inventory, mode=0o600)
        inventory_digest, size = fingerprint(output, INVENTORY)
        if (inventory_digest, size) != (bytes_digest(inventory), len(inventory)):
            raise invalid("inventory_checksum_mismatch")
        manifest: JsonObject = {
            "schema": URN,
            "state": "complete",
            "backup_id": str(uuid4()),
            "instance_id": str(snapshot.instance_id),
            "skm_version": version("skm"),
            "schema_version": snapshot.schema_version,
            "schema_baseline": baseline_document(snapshot.schema_baseline),
            "canonicalization_version": 1,
            "started_at": started.isoformat(),
            "completed_at": SystemClock().now().isoformat(),
            "recovery_scope": "control_plane_and_blobs",
            "external_dependencies": list(snapshot.dependencies),
            "database": {
                "file": DUMP,
                "format": "pg_dump_custom",
                "digest": dump_digest,
                "size_bytes": dump_size,
                "server_version_num": snapshot.server_version_num,
                "table_rows": dict(snapshot.table_rows),
            },
            "blobs": {
                "inventory_file": INVENTORY,
                "inventory_digest": inventory_digest,
                "count": len(snapshot.blobs),
                "total_bytes": sum(blob.size_bytes for blob in snapshot.blobs),
            },
        }
        SchemaRegistry.load_default().require_valid(URN, manifest)
        atomic_write(output / MANIFEST, json_bytes(manifest), mode=0o600)
    except FileExistsError:
        raise invalid("backup_path_already_exists") from None
    except OSError:
        raise invalid("backup_file_unavailable") from None
    return {"backup_id": manifest["backup_id"], "manifest": str(output / MANIFEST), "state": "complete"}


def run_pg_tool(
    program: str,
    args: list[str],
    environ: Mapping[str, str],
    *,
    stdin: IO[bytes] | int = subprocess.DEVNULL,
    stdout: IO[bytes] | int = subprocess.DEVNULL,
) -> None:
    try:
        subprocess.run(
            [program, "--no-password", *args],
            env={**environ, "PGPASSFILE": os.devnull},
            stdin=stdin,
            stdout=stdout,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        raise invalid(f"{program}_failed") from None


_USES = {
    "git_output": "output_read run_resume",
    "prepared_effect": "effect_reconcile run_resume",
    "writer_binding": "effect_reconcile external_delivery run_resume",
    "host_configuration": "run_resume",
    "runtime_session": "run_resume",
    "secret_provider": "run_resume external_delivery",
}


def dependency_inventory(
    references: Iterable[tuple[str, bool, str, UUID | None, UUID | None, UUID | None]],
) -> tuple[list[JsonObject], list[str]]:
    rows: dict[str, JsonObject] = {}
    runs: set[str] = set()
    for kind, captured, key, workspace, host, run_id in references:
        identity = f"{kind}:{bytes_digest(str(key).encode())}"
        item: JsonObject = {"kind": kind, "identity": identity, "required_for": list(_USES[kind].split())}
        if workspace:
            item["workspace_id"] = str(workspace)
        if host:
            item["host_id"] = str(host)
        if captured:
            item.update(state="captured", captured_in="database")
        else:
            item.update(state="requires_rebind", reason_code="RESTORE_BINDING_REQUIRED")
            if run_id:
                runs.add(str(run_id))
        rows[identity] = item
    return [rows[key] for key in sorted(rows)], sorted(runs)


_PG_KEYS = {
    "dbname",
    "host",
    "hostaddr",
    "port",
    "user",
    "password",
    "sslmode",
    "sslrootcert",
    "sslcert",
    "sslkey",
    "sslcrl",
    "sslcrldir",
    "gssencmode",
    "connect_timeout",
    "require_auth",
}


def postgres_environment(parameters: Mapping[str, object], environ: Mapping[str, str]) -> dict[str, str]:
    defaults = {"application_name"}
    if parameters.get("sslcertmode") == "allow":
        defaults.add("sslcertmode")
    if set(parameters) - _PG_KEYS - defaults:
        raise invalid("unsupported_backup_database_options")
    env = {key: environ[key] for key in ("PATH", "SYSTEMROOT") if key in environ}
    env.update({"PG" + key.upper(): str(value) for key, value in parameters.items() if key in _PG_KEYS})
    if "PGDBNAME" in env:
        env["PGDATABASE"] = env.pop("PGDBNAME")
    return env
