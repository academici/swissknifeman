"""PostgreSQL implementations of the ``runtimes`` repository ports (runtimes §6, §11; DDL ``0017``)."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Final, cast
from uuid import UUID, uuid4

import psycopg

from skm.adapters.postgres.errors import translate_pg_error
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.kernel.ids import HostId, ResourceVersionId, WorkerId
from skm.kernel.isolation import parse_isolation_profile
from skm.kernel.json_types import JsonObject
from skm.modules.runtimes.domain.capability import (
    Capability,
    CapabilityRecord,
    CapabilityStatus,
    VerificationContext,
    validate_verification_record,
)
from skm.modules.runtimes.domain.catalog import ModelStatus, Pricing
from skm.modules.runtimes.domain.catalog_records import (
    CanonicalModel,
    HostModelAvailability,
    ModelGuideline,
    ProviderModelOffering,
    WorkerModelSnapshot,
)
from skm.modules.runtimes.domain.classes import Effort, ModelClass, RoleId
from skm.modules.runtimes.domain.detection import VerificationRecord
from skm.modules.runtimes.domain.ids import Digest, RuntimeId
from skm.modules.runtimes.domain.installation import AuthState, RuntimeInstallation
from skm.platform.system_clock import SystemClock

__all__ = [
    "PostgresCapabilityVerificationRepository",
    "PostgresHostModelAvailabilityRepository",
    "PostgresHostRuntimeRepository",
    "PostgresModelCatalogRepository",
]

type _Row = tuple[object, ...]

_LIST_HOST: Final = """
SELECT host_id, runtime_id, version, binary_locator, auth_state, details, detected_at
  FROM skm_runtimes.host_runtimes
 WHERE host_id = %s
 ORDER BY runtime_id
"""

_UPSERT_HOST: Final = """
INSERT INTO skm_runtimes.host_runtimes
    (host_id, runtime_id, version, binary_locator, auth_state, details, detected_at, updated_at)
VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
ON CONFLICT (host_id, runtime_id) DO UPDATE SET
    version = EXCLUDED.version,
    binary_locator = EXCLUDED.binary_locator,
    auth_state = EXCLUDED.auth_state,
    details = EXCLUDED.details,
    detected_at = EXCLUDED.detected_at,
    updated_at = EXCLUDED.updated_at
"""

_DELETE_ALL_HOST: Final = "DELETE FROM skm_runtimes.host_runtimes WHERE host_id = %s"
_DELETE_MISSING_HOST: Final = """
DELETE FROM skm_runtimes.host_runtimes
 WHERE host_id = %s AND NOT (runtime_id = ANY(%s))
"""

_INSERT_VERIFICATION: Final = """
INSERT INTO skm_runtimes.capability_verifications (
    id, runtime_id, runtime_version, verification_context, verification_key,
    capability, status, evidence, limitations, verified_at, recorded_by, recorded_at
)
VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (
    runtime_id,
    coalesce(runtime_version, ''),
    coalesce(verification_key, ''),
    capability,
    verified_at,
    status
)
DO NOTHING
"""

_LATEST_VERIFICATIONS: Final = """
SELECT DISTINCT ON (capability)
    capability,
    status,
    evidence,
    runtime_version,
    limitations,
    verified_at,
    verification_context
  FROM skm_runtimes.capability_verifications
 WHERE runtime_id = %(rid)s
   AND (%(ver)s::text IS NULL OR runtime_version = %(ver)s::text OR runtime_version IS NULL)
   AND (%(vkey)s::text IS NULL OR verification_key = %(vkey)s::text OR verification_key IS NULL)
   AND (%(installation)s::jsonb IS NULL OR (
       runtime_version = %(ver)s::text AND verification_context - 'launch_config_digest'
       = %(installation)s::jsonb - 'launch_config_digest'
   ))
 ORDER BY
    capability,
    (%(vkey)s::text IS NOT NULL AND verification_key = %(vkey)s::text) DESC NULLS LAST,
    (%(ver)s::text IS NOT NULL AND runtime_version = %(ver)s::text) DESC NULLS LAST,
    recorded_at DESC,
    id DESC
"""


def _run[T](call: Callable[[], T]) -> T:
    try:
        return call()
    except psycopg.Error as exc:
        raise translate_pg_error(exc) from exc


def _damaged(table: str, ref: object, exc: Exception) -> InternalError:
    error = InternalError(
        ErrorCode.INTERNAL_ERROR,
        f"skm_runtimes.{table} row is malformed",
        details={"table": f"skm_runtimes.{table}", "id": str(ref)},
    )
    error.__cause__ = exc
    return error


def _context_to_json(ctx: VerificationContext | None) -> str | None:
    if ctx is None:
        return None
    payload = {
        "adapter_version": ctx.adapter_version,
        "binary_sha256": ctx.binary_sha256,
        "host_id": str(ctx.host_id),
        "isolation_profile": str(ctx.isolation_profile),
        "kernel": ctx.kernel,
        "launch_config_digest": ctx.launch_config_digest,
        "os": ctx.os,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _context_from_row(raw: object) -> VerificationContext | None:
    if raw is None:
        return None
    data = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(data, Mapping):
        raise ValueError("verification_context is not a JSON object")
    obj = cast("Mapping[str, object]", data)
    return VerificationContext(
        host_id=HostId(UUID(cast("str", obj["host_id"]))),
        binary_sha256=cast("str", obj["binary_sha256"]),
        os=cast("str", obj["os"]),
        kernel=cast("str", obj["kernel"]),
        adapter_version=cast("str", obj["adapter_version"]),
        isolation_profile=parse_isolation_profile(cast("str", obj["isolation_profile"])),
        launch_config_digest=cast("str", obj["launch_config_digest"]),
    )


class PostgresHostRuntimeRepository:
    """PostgreSQL ``HostRuntimeRepository`` over ``skm_runtimes.host_runtimes``."""

    def __init__(self, conn: psycopg.Connection, *, clock: Clock | None = None) -> None:
        self._conn = conn
        self._clock: Clock = clock if clock is not None else SystemClock()

    def list_for_host(self, host_id: HostId) -> tuple[RuntimeInstallation, ...]:
        rows = _run(lambda: self._conn.execute(_LIST_HOST, (host_id,)).fetchall())
        result: list[RuntimeInstallation] = []
        for row in rows:
            try:
                raw_details = row[5]
                parsed_details = json.loads(raw_details) if isinstance(raw_details, str) else raw_details
                if not isinstance(parsed_details, Mapping):
                    raise TypeError("details column must decode to a mapping")
                details = {str(k): str(v) for k, v in cast("Mapping[object, object]", parsed_details).items()}
                result.append(
                    RuntimeInstallation(
                        host_id=HostId(cast("UUID", row[0])),
                        runtime_id=cast("str", row[1]),
                        version=cast("str | None", row[2]),
                        binary_locator=cast("str | None", row[3]),
                        auth_state=AuthState(cast("str", row[4])),
                        details=details,
                        detected_at=cast("datetime", row[6]),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise _damaged("host_runtimes", f"{row[0]}:{row[1]}", exc) from exc
        return tuple(result)

    def upsert(self, installation: RuntimeInstallation) -> None:
        details_json = json.dumps(
            dict(installation.details), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        now = self._clock.now()
        _run(
            lambda: self._conn.execute(
                _UPSERT_HOST,
                (
                    installation.host_id,
                    installation.runtime_id,
                    installation.version,
                    installation.binary_locator,
                    installation.auth_state.value,
                    details_json,
                    installation.detected_at,
                    now,
                ),
            )
        )

    def remove_missing(self, host_id: HostId, present: frozenset[RuntimeId]) -> None:
        if not present:
            _run(lambda: self._conn.execute(_DELETE_ALL_HOST, (host_id,)))
            return
        _run(lambda: self._conn.execute(_DELETE_MISSING_HOST, (host_id, sorted(present))))


class PostgresCapabilityVerificationRepository:
    """PostgreSQL append-only ``CapabilityVerificationRepository``."""

    def __init__(self, conn: psycopg.Connection, *, clock: Clock | None = None) -> None:
        self._conn = conn
        self._clock: Clock = clock if clock is not None else SystemClock()

    def add(self, record: VerificationRecord) -> None:
        validate_verification_record(record)
        cap_rec = record.record
        assert cap_rec.last_verified_at is not None  # noqa: S101 - checked by _validate_verification
        ctx_json = _context_to_json(record.verification_context)
        now = self._clock.now()
        _run(
            lambda: self._conn.execute(
                _INSERT_VERIFICATION,
                (
                    uuid4(),
                    record.runtime_id,
                    record.runtime_version,
                    ctx_json,
                    record.verification_key,
                    cap_rec.capability.value,
                    cap_rec.status.value,
                    cap_rec.evidence,
                    cap_rec.limitations,
                    cap_rec.last_verified_at,
                    record.recorded_by,
                    now,
                ),
            )
        )

    def latest(
        self,
        runtime_id: RuntimeId,
        runtime_version: str | None,
        verification_key: Digest | None,
        *,
        installation: VerificationContext | None = None,
    ) -> tuple[CapabilityRecord, ...]:
        rows = _run(
            lambda: self._conn.execute(
                _LATEST_VERIFICATIONS,
                {
                    "rid": runtime_id,
                    "ver": runtime_version,
                    "vkey": verification_key,
                    "installation": _context_to_json(installation),
                },
            ).fetchall()
        )
        by_cap: dict[Capability, CapabilityRecord] = {}
        for row in rows:
            try:
                cap = Capability(cast("str", row[0]))
                by_cap[cap] = CapabilityRecord(
                    capability=cap,
                    status=CapabilityStatus(cast("str", row[1])),
                    evidence=cast("str", row[2]),
                    tested_runtime_version=cast("str | None", row[3]),
                    limitations=cast("str", row[4]),
                    last_verified_at=cast("date", row[5]),
                    verification_context=_context_from_row(row[6]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise _damaged("capability_verifications", f"{runtime_id}:{row[0]}", exc) from exc
        return tuple(by_cap[cap] for cap in Capability if cap in by_cap)


_UPSERT_OFFERING: Final = """
INSERT INTO skm_runtimes.provider_model_offerings (
    runtime_id, model_id, provider_model_id, display_name, context_window_tokens, max_output_tokens,
    patterns, status, verified_at, source, input_per_mtok_usd, output_per_mtok_usd, cache_read_per_mtok_usd,
    cache_write_per_mtok_usd, price_verified_at, price_source
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (runtime_id, model_id) DO UPDATE SET
    provider_model_id = EXCLUDED.provider_model_id, display_name = EXCLUDED.display_name,
    context_window_tokens = EXCLUDED.context_window_tokens, max_output_tokens = EXCLUDED.max_output_tokens,
    patterns = EXCLUDED.patterns, status = EXCLUDED.status, verified_at = EXCLUDED.verified_at,
    source = EXCLUDED.source, input_per_mtok_usd = EXCLUDED.input_per_mtok_usd,
    output_per_mtok_usd = EXCLUDED.output_per_mtok_usd,
    cache_read_per_mtok_usd = EXCLUDED.cache_read_per_mtok_usd,
    cache_write_per_mtok_usd = EXCLUDED.cache_write_per_mtok_usd,
    price_verified_at = EXCLUDED.price_verified_at,
    price_source = EXCLUDED.price_source
"""

_LIST_OFFERINGS: Final = """
SELECT runtime_id, model_id, provider_model_id, display_name, context_window_tokens, max_output_tokens,
       patterns, status, verified_at, source, input_per_mtok_usd, output_per_mtok_usd,
       cache_read_per_mtok_usd, cache_write_per_mtok_usd, price_verified_at, price_source
  FROM skm_runtimes.provider_model_offerings
 WHERE runtime_id = %s
 ORDER BY model_id COLLATE "C"
"""

_ADD_GUIDELINE: Final = """
INSERT INTO skm_runtimes.model_guidelines
    (resource_version_id, runtime_id, model_id, classes, suited_roles, notes)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (resource_version_id, runtime_id, model_id) DO NOTHING
"""

_LIST_GUIDELINES: Final = """
SELECT runtime_id, model_id, classes, suited_roles, notes
  FROM skm_runtimes.model_guidelines
 WHERE resource_version_id = %s
 ORDER BY runtime_id COLLATE "C", model_id COLLATE "C"
"""

_UPSERT_AVAILABILITY: Final = """
INSERT INTO skm_runtimes.host_model_availability
    (host_id, runtime_id, model_id, effort, observed_at, expires_at)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (host_id, runtime_id, model_id, effort) DO UPDATE SET
    observed_at = EXCLUDED.observed_at, expires_at = EXCLUDED.expires_at
WHERE EXCLUDED.observed_at > host_model_availability.observed_at
"""

_LIST_FRESH: Final = """
SELECT runtime_id, model_id, effort, observed_at, expires_at
  FROM skm_runtimes.host_model_availability
 WHERE host_id = %s AND observed_at <= %s AND expires_at > %s
 ORDER BY runtime_id COLLATE "C", model_id COLLATE "C", effort COLLATE "C"
"""


def _offering(row: _Row) -> ProviderModelOffering:
    pricing = None
    if row[10] is not None:
        pricing = Pricing(
            input_per_mtok_usd=cast("Decimal", row[10]),
            output_per_mtok_usd=cast("Decimal", row[11]),
            cache_read_per_mtok_usd=cast("Decimal | None", row[12]),
            cache_write_per_mtok_usd=cast("Decimal | None", row[13]),
            currency="USD",
            verified_at=cast("date", row[14]),
            source=cast("str", row[15]),
        )
    return ProviderModelOffering(
        runtime_id=cast("str", row[0]),
        model_id=cast("str", row[1]),
        provider_model_id=cast("str", row[2]),
        display_name=cast("str", row[3]),
        context_window_tokens=cast("int", row[4]),
        max_output_tokens=cast("int | None", row[5]),
        patterns=tuple(cast("list[str]", row[6])),
        status=ModelStatus(cast("str", row[7])),
        verified_at=cast("date", row[8]),
        source=cast("str", row[9]),
        pricing=pricing,
    )


class PostgresModelCatalogRepository:
    """Relational model identities, offerings and published guidelines."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def add_model(self, model: CanonicalModel) -> None:
        _run(
            lambda: self._conn.execute(
                "INSERT INTO skm_runtimes.canonical_models (model_id) VALUES (%s) ON CONFLICT DO NOTHING",
                (model.model_id,),
            )
        )

    def list_models(self) -> tuple[CanonicalModel, ...]:
        rows = _run(
            lambda: self._conn.execute(
                """SELECT model_id FROM skm_runtimes.canonical_models ORDER BY model_id COLLATE "C" """
            ).fetchall()
        )
        return tuple(CanonicalModel(cast("str", row[0])) for row in rows)

    def upsert_offering(self, offering: ProviderModelOffering) -> None:
        price = offering.pricing
        _run(
            lambda: self._conn.execute(
                _UPSERT_OFFERING,
                (
                    offering.runtime_id,
                    offering.model_id,
                    offering.provider_model_id,
                    offering.display_name,
                    offering.context_window_tokens,
                    offering.max_output_tokens,
                    list(offering.patterns),
                    offering.status.value,
                    offering.verified_at,
                    offering.source,
                    None if price is None else price.input_per_mtok_usd,
                    None if price is None else price.output_per_mtok_usd,
                    None if price is None else price.cache_read_per_mtok_usd,
                    None if price is None else price.cache_write_per_mtok_usd,
                    None if price is None else price.verified_at,
                    None if price is None else price.source,
                ),
            )
        )

    def list_offerings(self, runtime_id: RuntimeId) -> tuple[ProviderModelOffering, ...]:
        rows = _run(lambda: self._conn.execute(_LIST_OFFERINGS, (runtime_id,)).fetchall())
        return tuple(_offering(row) for row in rows)

    def add_guideline(self, guideline: ModelGuideline) -> None:
        _run(
            lambda: self._conn.execute(
                _ADD_GUIDELINE,
                (
                    guideline.resource_version_id,
                    guideline.runtime_id,
                    guideline.model_id,
                    sorted(cls.value for cls in guideline.classes),
                    sorted(role.value for role in guideline.suited_roles),
                    guideline.notes,
                ),
            )
        )

    def list_guidelines(self, resource_version_id: ResourceVersionId) -> tuple[ModelGuideline, ...]:
        rows = _run(lambda: self._conn.execute(_LIST_GUIDELINES, (resource_version_id,)).fetchall())
        return tuple(
            ModelGuideline(
                resource_version_id,
                cast("str", runtime_id),
                cast("str", model_id),
                frozenset(ModelClass(cls) for cls in cast("list[str]", classes)),
                frozenset(RoleId(role) for role in cast("list[str]", roles)),
                cast("str", notes),
            )
            for runtime_id, model_id, classes, roles, notes in rows
        )


_REPLACE_WORKER_SNAPSHOT: Final = """
INSERT INTO skm_runtimes.worker_model_offer_snapshots AS current
       (worker_id, publisher_token_id, observed_at, expires_at, snapshot)
VALUES (%s, %s, %s, %s, %s::jsonb)
ON CONFLICT (worker_id) DO UPDATE
SET publisher_token_id = EXCLUDED.publisher_token_id,
    observed_at = EXCLUDED.observed_at,
    expires_at = EXCLUDED.expires_at,
    snapshot = EXCLUDED.snapshot
WHERE current.publisher_token_id <> EXCLUDED.publisher_token_id
   OR current.observed_at < EXCLUDED.observed_at
"""

_WORKER_SNAPSHOT: Final = """
SELECT publisher_token_id, observed_at, expires_at, snapshot
  FROM skm_runtimes.worker_model_offer_snapshots
 WHERE worker_id = %s
"""


def _snapshot_document(snapshot: WorkerModelSnapshot) -> str:
    return json.dumps(
        {
            "installations": [
                {
                    "host_id": str(item.host_id),
                    "runtime_id": item.runtime_id,
                    "version": item.version,
                    "auth_state": item.auth_state.value,
                    "detected_at": item.detected_at.isoformat(),
                    "details": dict(item.details),
                }
                for item in snapshot.installations
            ],
            "offers": [
                {
                    "host_id": str(item.host_id),
                    "runtime_id": item.runtime_id,
                    "model_id": item.model_id,
                    "effort": item.effort.value,
                    "expires_at": item.expires_at.isoformat(),
                }
                for item in snapshot.offers
            ],
        }
    )


def _snapshot_installation(item: JsonObject) -> RuntimeInstallation:
    return RuntimeInstallation(
        HostId(UUID(cast("str", item["host_id"]))),
        cast("str", item["runtime_id"]),
        cast("str | None", item["version"]),
        None,
        AuthState(cast("str", item["auth_state"])),
        datetime.fromisoformat(cast("str", item["detected_at"])),
        cast("dict[str, str]", item["details"]),
    )


class PostgresHostModelAvailabilityRepository:
    """Observations keyed by host, runtime, model and effort."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def upsert(self, observation: HostModelAvailability) -> None:
        _run(
            lambda: self._conn.execute(
                _UPSERT_AVAILABILITY,
                (
                    observation.host_id,
                    observation.runtime_id,
                    observation.model_id,
                    observation.effort.value,
                    observation.observed_at,
                    observation.expires_at,
                ),
            )
        )

    def list_fresh(self, host_id: HostId, *, as_of: datetime) -> tuple[HostModelAvailability, ...]:
        rows = _run(lambda: self._conn.execute(_LIST_FRESH, (host_id, as_of, as_of)).fetchall())
        return tuple(
            HostModelAvailability(
                host_id,
                cast("str", runtime_id),
                cast("str", model_id),
                Effort(cast("str", effort)),
                cast("datetime", observed_at).astimezone(UTC),
                cast("datetime", expires_at).astimezone(UTC),
            )
            for runtime_id, model_id, effort, observed_at, expires_at in rows
        )

    def replace_worker_snapshot(self, snapshot: WorkerModelSnapshot) -> bool:
        return (
            _run(
                lambda: (
                    self._conn.execute(
                        _REPLACE_WORKER_SNAPSHOT,
                        (
                            snapshot.worker_id,
                            snapshot.publisher_token_id,
                            snapshot.observed_at,
                            snapshot.expires_at,
                            _snapshot_document(snapshot),
                        ),
                    ).rowcount
                )
            )
            == 1
        )

    def worker_snapshot(self, worker_id: WorkerId) -> WorkerModelSnapshot | None:
        row = _run(lambda: self._conn.execute(_WORKER_SNAPSHOT, (worker_id,)).fetchone())
        if row is None:
            return None
        publisher, observed_at, expires_at, document = row
        data = cast("JsonObject", document)
        observed = cast("datetime", observed_at).astimezone(UTC)
        return WorkerModelSnapshot(
            worker_id,
            cast("UUID", publisher),
            observed,
            cast("datetime", expires_at).astimezone(UTC),
            tuple(_snapshot_installation(item) for item in cast("list[JsonObject]", data["installations"])),
            tuple(
                HostModelAvailability(
                    HostId(UUID(cast("str", item["host_id"]))),
                    cast("str", item["runtime_id"]),
                    cast("str", item["model_id"]),
                    Effort(cast("str", item["effort"])),
                    observed,
                    datetime.fromisoformat(cast("str", item["expires_at"])),
                )
                for item in cast("list[JsonObject]", data["offers"])
            ),
        )
