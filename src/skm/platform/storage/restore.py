"""Verify the snapshot before staging and publish activation through a durable rename."""

from __future__ import annotations

import fcntl
import json
import os
import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from secrets import token_hex
from shutil import copyfileobj, rmtree
from tempfile import TemporaryDirectory, TemporaryFile
from typing import TYPE_CHECKING, cast
from urllib.parse import parse_qsl, unquote, urlsplit
from uuid import uuid4

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.platform.config.bootstrap import BootstrapConfig, configure_bootstrap
from skm.platform.config.secrets import SecretRef
from skm.platform.config.sources.document import decode_document
from skm.platform.fs.atomic_write import atomic_write, fsync_dir

if TYPE_CHECKING:
    from skm.platform.storage.backup import Blob, Snapshot

MARKER = "restore-quarantine.json"
RECEIPT = "restore-activation.json"
STAGING_RECORD = "staging-database.json"


@dataclass(frozen=True, slots=True)
class VerifiedBackup:
    directory: Path
    manifest: JsonObject
    manifest_digest: str
    closure: JsonObject
    blobs: tuple[Blob, ...]

    def require_snapshot(self, snapshot: Snapshot) -> None:
        from skm.platform.storage.backup import invalid

        source_version = cast("int", self.closure["server_version_num"])
        snapshot = replace(snapshot, server_version_num=source_version)
        if (
            snapshot.closure(str(self.closure["inventory_digest"])) != self.closure
            or snapshot.blobs != self.blobs
        ):
            raise invalid("restored_snapshot_closure_mismatch")

    @property
    def dependencies(self) -> list[JsonObject]:
        return cast("list[JsonObject]", self.manifest["external_dependencies"])


def read_document(root: Path, name: str) -> JsonObject:
    from skm.platform.storage.backup import json_object, open_regular

    with open_regular(root, name) as stream:
        return json_object(stream.read())


def verify_backup(
    directory: Path,
    known_schema_version: int,
    *,
    expected_baseline: tuple[str, str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> VerifiedBackup:
    from skm.platform.storage.backup import invalid

    directory = directory.absolute()
    try:
        return _verify(directory, known_schema_version, expected_baseline, environ or {})
    except OSError:
        raise invalid("backup_file_unavailable") from None


def _read_manifest(
    directory: Path, known_schema_version: int, expected_baseline: tuple[str, str] | None
) -> tuple[JsonObject, int, str]:
    from skm.platform.schema.registry import SchemaRegistry
    from skm.platform.storage.backup import (
        MANIFEST,
        URN,
        baseline_document,
        bytes_digest,
        invalid,
        json_object,
        open_regular,
    )

    with open_regular(directory, MANIFEST) as stream:
        data = stream.read()
    manifest = json_object(data)
    version = manifest.get("schema_version")
    if type(version) is not int:
        raise invalid("invalid_backup_manifest")
    if (
        manifest.get("schema") == URN
        and manifest.get("state") == "complete"
        and version > known_schema_version
    ):
        raise PreconditionFailed(
            ErrorCode.SCHEMA_TOO_NEW,
            "Backup schema is newer than this installation",
            details={"schema_version": version, "known_schema_version": known_schema_version},
        )
    if manifest.get("canonicalization_version") != 1 or SchemaRegistry.load_default().validate(URN, manifest):
        raise invalid("invalid_backup_manifest")
    if expected_baseline is not None and manifest.get("schema_baseline") != baseline_document(
        expected_baseline
    ):
        raise invalid("backup_schema_baseline_mismatch")
    return manifest, version, bytes_digest(data)


def _verify(
    directory: Path,
    known_schema_version: int,
    expected_baseline: tuple[str, str] | None,
    environ: Mapping[str, str],
) -> VerifiedBackup:
    from skm.platform.storage.backup import (
        CLOSURE,
        DUMP,
        INVENTORY,
        Blob,
        bytes_digest,
        fingerprint,
        invalid,
        json_object,
        open_regular,
    )

    manifest, version, manifest_digest = _read_manifest(directory, known_schema_version, expected_baseline)
    db = cast("JsonObject", manifest["database"])
    inventory = cast("JsonObject", manifest["blobs"])
    if db["file"] != DUMP or inventory["inventory_file"] != INVENTORY:
        raise invalid("unexpected_archive_layout")
    with open_regular(directory, DUMP) as stream:
        if stream.read(5) != b"PGDMP":
            raise invalid("invalid_dump_format")
    if fingerprint(directory, DUMP) != (db["digest"], db["size_bytes"]):
        raise invalid("dump_checksum_mismatch")
    with open_regular(directory, INVENTORY) as stream:
        raw = stream.read()
    if bytes_digest(raw) != inventory["inventory_digest"]:
        raise invalid("inventory_checksum_mismatch")
    header_line, _, records = raw.partition(b"\n")
    header = json_object(header_line)
    if type(header.get("inventory_size_bytes")) is not int or header["inventory_size_bytes"] != len(records):
        raise invalid("inventory_checksum_mismatch")
    blobs = tuple(Blob.from_json(json_object(line)) for line in records.splitlines())
    keys = {(blob.workspace_id, blob.digest) for blob in blobs}
    if (
        len(keys) != len(blobs)
        or len(blobs) != inventory["count"]
        or (sum(blob.size_bytes for blob in blobs) != inventory["total_bytes"])
    ):
        raise invalid("invalid_blob_inventory")
    for blob in blobs:
        if fingerprint(directory, blob.path) != (blob.digest, blob.size_bytes):
            raise invalid("blob_checksum_mismatch")

    dependencies = cast("list[JsonObject]", manifest["external_dependencies"])
    identities = {str(item["identity"]) for item in dependencies}
    if len(identities) != len(dependencies) or any(
        not re.fullmatch(rf"{item['kind']}:sha256:[0-9a-f]{{64}}", str(item["identity"]))
        or (item["state"] == "requires_rebind" and "reason_code" not in item)
        or (
            item.get("captured_in") == "blob_inventory" and (item["workspace_id"], item["digest"]) not in keys
        )
        for item in dependencies
    ):
        raise invalid("external_dependency_closure_mismatch")
    with open_regular(directory, CLOSURE) as stream:
        raw_closure = stream.read()
    expected: JsonObject = {
        "instance_id": manifest["instance_id"],
        "schema_version": version,
        "server_version_num": db["server_version_num"],
        "table_rows": db["table_rows"],
        "inventory_digest": bytes_digest(records),
        "external_dependencies": cast("list[JsonValue]", dependencies),
    }
    if "schema_baseline" in manifest:
        expected["schema_baseline"] = manifest["schema_baseline"]
    closure = json_object(raw_closure)
    if closure != expected or bytes_digest(raw_closure) != header.get("closure_digest"):
        raise invalid("snapshot_closure_mismatch")
    if _dump_blobs(directory, environ) != set(blobs):
        raise invalid("dump_blob_closure_mismatch")
    return VerifiedBackup(directory, manifest, manifest_digest, closure, blobs)


def _copy_rows(lines: Iterator[bytes]) -> Iterator[tuple[bytes, dict[bytes, bytes]]]:
    from skm.platform.storage.backup import invalid

    tables = {b"blobs", b"blob_locations"}
    for line in lines:
        match = re.fullmatch(rb"COPY skm_artifacts\.(blobs|blob_locations) \(([^)]+)\) FROM stdin;\n", line)
        if match is None:
            continue
        table, columns = match[1], match[2].split(b", ")
        if table not in tables or len(set(columns)) != len(columns):
            raise invalid("invalid_dump_blob_data")
        tables.remove(table)
        for record in lines:
            if record == b"\\.\n":
                break
            yield table, dict(zip(columns, record.removesuffix(b"\n").split(b"\t"), strict=True))
        else:
            raise invalid("invalid_dump_blob_data")
    if tables:
        raise invalid("invalid_dump_blob_data")


def _dump_blobs(directory: Path, environ: Mapping[str, str]) -> set[Blob]:
    from skm.platform.storage.backup import (
        DUMP,
        Blob,
        invalid,
        open_regular,
        postgres_environment,
        run_pg_tool,
    )

    # Render only the two table data sections to COPY text. Verification executes no SQL.
    args = ["--file=-", "--data-only", "--schema=skm_artifacts", "--table=blobs", "--table=blob_locations"]
    with open_regular(directory, DUMP) as dump, TemporaryFile() as data:
        # Keep PATH: a client installed outside the default search path (/usr/local, Homebrew) must be found.
        run_pg_tool("pg_restore", args, postgres_environment({}, environ), stdin=dump, stdout=data)
        data.seek(0)
        blobs: dict[tuple[bytes, bytes], Blob] = {}
        locations: dict[tuple[bytes, bytes], tuple[bytes, bytes, bytes]] = {}
        try:
            for table, row in _copy_rows(iter(data)):
                if table == b"blobs":
                    key = row[b"workspace_id"], row[b"id"]
                    blob = Blob(
                        key[0].decode(), "sha256:" + row[b"content_digest"].decode(), int(row[b"size_bytes"])
                    )
                    if key in blobs:
                        raise invalid("invalid_dump_blob_data")
                    blobs[key] = Blob.from_json(blob.to_json())
                else:
                    key = row[b"workspace_id"], row[b"blob_id"]
                    if key in locations:
                        raise invalid("invalid_dump_blob_data")
                    locations[key] = row[b"storage_key"], row[b"backend_id"], row[b"state"]
        except (KeyError, ValueError):
            raise invalid("invalid_dump_blob_data") from None
    if any(
        key not in blobs or row != (blobs[key].key.encode(), b"local-primary", b"present")
        for key, row in locations.items()
    ):
        raise invalid("unsupported_or_missing_blob_location")
    if locations.keys() != blobs.keys() or len(set(blobs.values())) != len(blobs):
        raise invalid("unsupported_or_missing_blob_location")
    return set(blobs.values())


@dataclass(frozen=True, slots=True)
class RestorePaths:
    state_dir: Path

    @property
    def blobs_root(self) -> Path:
        return self.state_dir / "blobs"

    @property
    def profile(self) -> Path:
        return self.state_dir / "bootstrap.toml"


def restore_backup(
    archive: VerifiedBackup,
    parent: Path,
    stage: Callable[[VerifiedBackup, RestorePaths, JsonObject, Path], None],
) -> JsonObject:
    from skm.platform.storage.backup import invalid

    restore_id = str(uuid4())
    paths = RestorePaths(parent.resolve() / restore_id)
    marker: JsonObject = {
        "restore_id": restore_id,
        "backup_id": archive.manifest["backup_id"],
        "manifest_digest": archive.manifest_digest,
        "archive": str(archive.directory),
    }
    try:
        paths.state_dir.mkdir(mode=0o700, parents=True)
    except OSError:
        raise invalid("staging_files_unavailable") from None
    staged: list[bool] = []

    def staging(archive: VerifiedBackup, paths: RestorePaths, marker: JsonObject, dump: Path) -> None:
        staged.append(True)
        stage(archive, paths, marker, dump)

    try:
        _fill_restore(archive, paths, marker, staging)
    except BaseException:
        # Before staging starts no database refers to this directory, and it holds a full copy of the
        # archive's blobs; keep it only once a staging database may record it as its quarantine.
        if not staged:
            rmtree(paths.state_dir, ignore_errors=True)
        raise
    return {
        "restore_id": restore_id,
        "backup_id": archive.manifest["backup_id"],
        "profile": str(paths.profile),
        "state": "quarantined",
        "requires_rebind": [dep for dep in archive.dependencies if dep["state"] == "requires_rebind"],
    }


def _fill_restore(
    archive: VerifiedBackup,
    paths: RestorePaths,
    marker: JsonObject,
    stage: Callable[[VerifiedBackup, RestorePaths, JsonObject, Path], None],
) -> None:
    from skm.platform.storage.backup import DUMP, copy_blob, fingerprint, invalid, json_bytes, open_regular

    try:
        fsync_dir(paths.state_dir.parent)
        atomic_write(paths.state_dir / MARKER, json_bytes(marker), mode=0o600)
        paths.blobs_root.mkdir(mode=0o700)
        for blob in archive.blobs:
            copy_blob(archive.directory, blob.path, paths.blobs_root, blob.key, blob)
        fsync_dir(paths.state_dir)
        with TemporaryDirectory(dir=paths.state_dir) as tmp:
            private = Path(tmp)
            with open_regular(archive.directory, DUMP) as incoming, (private / DUMP).open("xb") as outgoing:
                copyfileobj(incoming, outgoing)
            db = cast("JsonObject", archive.manifest["database"])
            if fingerprint(private, DUMP) != (db["digest"], db["size_bytes"]):
                raise invalid("dump_checksum_mismatch")
            stage(archive, paths, marker, private / DUMP)
    except OSError:
        raise invalid("staging_files_unavailable") from None


def activate_restore(
    state_dir: Path,
    known_schema_version: int,
    *,
    confirmed: bool,
    activate: Callable[[VerifiedBackup, JsonObject], JsonObject],
    activated_receipt: Callable[[], JsonObject | None],
    environ: Mapping[str, str] | None = None,
) -> JsonObject:
    from skm.platform.storage.backup import invalid, json_bytes

    if not confirmed:
        raise invalid("restore_activation_confirmation_required")
    try:
        fd = os.open(state_dir / ".restore.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not (state_dir / MARKER).exists():
                if receipt := activated_receipt():
                    return receipt
                raise invalid("restore_marker_missing")
            marker = read_document(state_dir, MARKER)
            directory = marker.get("archive")
            if not isinstance(directory, str) or not Path(directory).is_absolute():
                raise invalid("invalid_restore_marker")
            archive = verify_backup(Path(directory), known_schema_version, environ=environ)
            if archive.manifest_digest != marker.get("manifest_digest") or (
                archive.manifest["backup_id"] != marker.get("backup_id")
            ):
                raise invalid("restore_manifest_changed")
            receipt = activate(archive, marker)
            # The marker remains authoritative until this same-directory rename.
            atomic_write(state_dir / MARKER, json_bytes({**marker, **receipt}), mode=0o600)
            os.replace(state_dir / MARKER, state_dir / RECEIPT)
            fsync_dir(state_dir)
            return receipt
    except OSError:
        raise invalid("restore_state_unavailable") from None


_DATABASE_FILE = "secrets/database-url"
_PEPPER_FILE = "secrets/token-pepper"


def prepare_restore_profile(
    paths: RestorePaths, archive: VerifiedBackup, dsn: str
) -> tuple[BootstrapConfig, bytes]:
    state = paths.state_dir
    (state / "secrets").mkdir(mode=0o700)
    atomic_write(state / _DATABASE_FILE, dsn.encode(), mode=0o600, private=True)
    atomic_write(state / _PEPPER_FILE, token_hex(32).encode(), mode=0o600, private=True)
    profile = (
        'schema = "urn:skm:config:bootstrap:v1"\n'
        f'instance_id = "{archive.manifest["instance_id"]}"\n'
        '[access]\nmode = "embedded"\n[database]\n'
        f"url = {json.dumps(str(SecretRef('file', str(state / _DATABASE_FILE))))}\n"
        "[paths]\n"
        f"state_dir = {json.dumps(str(state))}\nblobs_root = {json.dumps(str(paths.blobs_root))}\n"
        "[secrets]\n"
        f"token_pepper = {json.dumps(str(SecretRef('file', str(state / _PEPPER_FILE))))}\n"
    )
    config = configure_bootstrap(str(paths.profile), decode_document(profile, "toml"), {}, state)
    return config, profile.encode()


def restore_profile_root(config: BootstrapConfig) -> Path | None:
    return next(
        (
            root
            for root in (Path(config.source).resolve().parent, config.state_dir.absolute())
            if any(os.path.lexists(root / name) for name in (MARKER, RECEIPT))
        ),
        None,
    )


def pin_restore_profile(config: BootstrapConfig, read_secret_file: Callable[[Path], str]) -> BootstrapConfig:
    if (root := restore_profile_root(config)) is None:
        return config
    return replace(
        config,
        state_dir=root,
        access_mode="embedded",
        blobs_root=root / "blobs",
        worktrees_root=root / "worktrees",
        materialized_root=root / "materialized",
        backups_root=root / "backups",
        database_url=read_secret_file(root / _DATABASE_FILE),
        database_migrate_on_start=False,
        database_migrator_url=None,
        api_endpoint=None,
        api_credential=None,
        api_ca_bundle=None,
        host_id="auto",
        token_pepper=SecretRef("file", str(root / _PEPPER_FILE)),
    )


def verification_report(archive: VerifiedBackup) -> JsonObject:
    return {
        "backup_id": archive.manifest["backup_id"],
        "state": "verified",
        "blobs": len(archive.blobs),
        "requires_rebind": [item for item in archive.dependencies if item["state"] == "requires_rebind"],
    }


def staging_database(url: str) -> tuple[str, str]:
    """Select a new catalog name and derive a maintenance URL on the same server."""
    from skm.platform.storage.backup import invalid, postgres_environment

    try:
        address = urlsplit(url)
        target = unquote(address.path.removeprefix("/"))
        parameters = dict(parse_qsl(address.query, strict_parsing=True, keep_blank_values=True))
        valid = (
            address.scheme in {"postgres", "postgresql"}
            and address.hostname
            and address.username
            and "," not in address.hostname
            and not address.fragment
            and not (parameters.keys() & {"dbname", "host", "user", "port", "password", "service"})
        )
        port = address.port
    except ValueError:
        raise invalid("invalid_staging_database_url") from None
    if not valid or port == 0:
        raise invalid("invalid_staging_database_url")
    if not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,62}", target) or target in {
        "postgres",
        "template0",
        "template1",
    }:
        raise invalid("invalid_staging_database_name")
    postgres_environment(parameters, {})
    return target, address._replace(path="/postgres").geturl()


@dataclass(frozen=True, slots=True)
class StagingRecord:
    """Target name of an unfinished restore. The caller supplies the credentials on retry."""

    name: str
    host: str
    port: int
    oid: int

    def matches_target(self, dsn: str) -> bool:
        address = urlsplit(dsn)
        return self.host == address.hostname and self.port == (address.port or 5432)


def write_staging_record(state_dir: Path, dsn: str, oid: int) -> None:
    name, _maintenance = staging_database(dsn)
    address = urlsplit(dsn)
    data = {"name": name, "host": address.hostname, "port": address.port or 5432, "oid": oid}
    atomic_write(state_dir / STAGING_RECORD, json.dumps(data).encode(), mode=0o600)


def read_staging_record(state_dir: Path) -> StagingRecord | None:
    from skm.platform.storage.backup import open_regular

    try:
        with open_regular(state_dir, STAGING_RECORD) as source:
            raw = source.read(65537)
            if len(raw) > 65536:
                return None
            data = json.loads(raw)
    except (OSError, ValueError, PreconditionFailed):
        return None
    # Older records also contained a URL. Never use credentials or destinations from a journal.
    if not isinstance(data, dict):
        return None
    fields = cast("dict[str, object]", data)
    name, host, port, oid = (fields.get(key) for key in ("name", "host", "port", "oid"))
    if (
        not isinstance(name, str)
        or not isinstance(host, str)
        or type(port) is not int
        or type(oid) is not int
    ):
        return None
    return StagingRecord(name, host, port, oid)


def is_incomplete_restore(state_dir: Path) -> bool:
    """True until the staged profile exists; a completed quarantine must never be dropped."""
    return not any(os.path.lexists(state_dir / name) for name in ("bootstrap.toml", RECEIPT))


def incomplete_staging_records(parent: Path) -> tuple[tuple[Path, StagingRecord], ...]:
    """Restore directories under ``parent`` that recorded a catalog but never finished staging."""
    if not parent.is_dir():
        return ()
    found: list[tuple[Path, StagingRecord]] = []
    for child in sorted(parent.iterdir()):
        if child.is_symlink() or not child.is_dir():
            continue
        record = read_staging_record(child)
        if record is not None and is_incomplete_restore(child):
            found.append((child, record))
    return tuple(found)
