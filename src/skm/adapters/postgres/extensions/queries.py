"""SQL of the extensions PostgreSQL adapters (extensions §11.2; DDL ``0018``).

Static text only, each statement behind one named function; values are always bound. Newest-first order is
``version_major DESC, version_minor DESC, version_patch DESC, (prerelease IS NULL) DESC, prerelease DESC``;
the exact SemVer order of prerelease identifiers is the domain's (``SemVer``).
"""

from collections.abc import Mapping, Sequence
from typing import Final

import psycopg

from skm.adapters.postgres.extensions.mapping import Row

__all__ = [
    "add_pack",
    "add_pack_version",
    "add_quarantine",
    "add_resource",
    "add_resource_files",
    "add_resource_version",
    "find_pack_by_slug",
    "find_pack_version",
    "find_resource",
    "get_pack",
    "get_pack_version",
    "get_resource_version",
    "in_pack_versions",
    "in_pack_versions_of_kind",
    "lock_registry",
    "owner_trust",
    "pack_version_state",
    "quarantined",
    "release_quarantine",
    "resource_bodies",
    "resource_files",
    "retire_pack_version",
    "summaries",
    "versions_of",
]

type Params = Sequence[object] | Mapping[str, object]

# ``pg_advisory_xact_lock(class, 0)``, class 0x534B4D58 = "SKMX"; held until the transaction ends
_LOCK_REGISTRY: Final = "SELECT pg_advisory_xact_lock(1397443928, 0)"

_PACK: Final = "SELECT id, slug, title, publisher, trust, created_at FROM skm_extensions.packs "
_GET_PACK: Final = _PACK + "WHERE id = %s"
_FIND_PACK_BY_SLUG: Final = _PACK + "WHERE slug = %s"
_ADD_PACK: Final = """
INSERT INTO skm_extensions.packs (id, slug, title, publisher, trust, created_at)
VALUES (%s, %s, %s, %s, %s, %s)
"""

_PACK_VERSION: Final = """
SELECT id, pack_id, version, digest, manifest, state, origin, installed_at, installed_by
  FROM skm_extensions.pack_versions
"""
_GET_PACK_VERSION: Final = _PACK_VERSION + " WHERE id = %s"
_FIND_PACK_VERSION: Final = _PACK_VERSION + " WHERE pack_id = %s AND version = %s"
_ADD_PACK_VERSION: Final = """
INSERT INTO skm_extensions.pack_versions
    (id, pack_id, version, version_major, version_minor, version_patch, prerelease, digest, manifest,
     priority, state, origin, installed_at, installed_by)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""
# ``(pack_id IS NULL OR ...)``: one static statement for every filter
_SUMMARIES: Final = """
SELECT v.id, v.pack_id, p.slug, p.title, p.trust, v.version, v.digest, v.priority, v.state, v.installed_at
  FROM skm_extensions.pack_versions v
  JOIN skm_extensions.packs p ON p.id = v.pack_id
 WHERE (%(pack_id)s::uuid IS NULL OR v.pack_id = %(pack_id)s)
   AND (%(state)s::text IS NULL OR v.state = %(state)s)
 ORDER BY p.slug, v.version_major DESC, v.version_minor DESC, v.version_patch DESC,
          (v.prerelease IS NULL) DESC, v.prerelease DESC
"""
_RETIRE_PACK_VERSION: Final = """
UPDATE skm_extensions.pack_versions SET state = 'retired' WHERE id = %s AND state = 'active' RETURNING id
"""
_PACK_VERSION_STATE: Final = "SELECT state FROM skm_extensions.pack_versions WHERE id = %s"

_FIND_RESOURCE: Final = """
SELECT id, kind, key, first_pack_id, created_at FROM skm_extensions.resources WHERE kind = %s AND key = %s
"""
_ADD_RESOURCE: Final = """
INSERT INTO skm_extensions.resources (id, kind, key, first_pack_id, created_at) VALUES (%s, %s, %s, %s, %s)
"""
_OWNER_TRUST: Final = """
SELECT p.trust
  FROM skm_extensions.resources r
  JOIN skm_extensions.packs p ON p.id = r.first_pack_id
 WHERE r.kind = %s AND r.key = %s
"""
_ADD_RESOURCE_VERSION: Final = """
INSERT INTO skm_extensions.resource_versions
    (id, resource_id, pack_version_id, version, digest, manifest, tokens_estimate, compat_verdict,
     compat_report, created_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""
_ADD_RESOURCE_FILE: Final = """
INSERT INTO skm_extensions.resource_files (resource_version_id, path, size_bytes, digest, media_type, content)
VALUES (%s, %s, %s, %s, %s, %s)
"""
_GET_RESOURCE_VERSION: Final = """
SELECT v.id, v.resource_id, r.kind, r.key, v.pack_version_id, v.version, v.digest, v.manifest,
       v.tokens_estimate, v.compat_report, v.created_at
  FROM skm_extensions.resource_versions v
  JOIN skm_extensions.resources r ON r.id = v.resource_id
 WHERE v.id = %s
"""
_RESOURCE_FILES: Final = """
SELECT path, size_bytes, digest, media_type FROM skm_extensions.resource_files
 WHERE resource_version_id = %s ORDER BY path
"""
_RESOURCE_BODIES: Final = """
SELECT path, content FROM skm_extensions.resource_files WHERE resource_version_id = %s
"""
_SUMMARY: Final = """
SELECT v.id, r.kind, r.key, v.pack_version_id, v.version, v.digest, v.compat_verdict
  FROM skm_extensions.resource_versions v
  JOIN skm_extensions.resources r ON r.id = v.resource_id
"""
_VERSIONS_OF: Final = (
    _SUMMARY + " WHERE r.kind = %s AND r.key = %s AND v.pack_version_id = ANY(%s) ORDER BY v.id"
)
_IN_PACK_VERSIONS: Final = _SUMMARY + " WHERE v.pack_version_id = ANY(%s) ORDER BY r.kind, r.key, v.id"
_IN_PACK_VERSIONS_OF_KIND: Final = (
    _SUMMARY + " WHERE v.pack_version_id = ANY(%s) AND r.kind = %s ORDER BY r.kind, r.key, v.id"
)

_QUARANTINED: Final = """
SELECT resource_version_id FROM skm_extensions.resource_quarantine
 WHERE released_at IS NULL AND resource_version_id = ANY(%s)
"""
_ADD_QUARANTINE: Final = """
INSERT INTO skm_extensions.resource_quarantine
    (id, resource_version_id, reason_kind, reasons, report, created_by, created_at)
VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s)
"""
_RELEASE_QUARANTINE: Final = """
UPDATE skm_extensions.resource_quarantine
   SET released_by = %s, released_at = %s, release_reason = %s
 WHERE resource_version_id = %s AND released_at IS NULL
RETURNING id
"""


def lock_registry(conn: psycopg.Connection) -> None:
    conn.execute(_LOCK_REGISTRY)


def get_pack(conn: psycopg.Connection, params: Params) -> Row | None:
    return conn.execute(_GET_PACK, params).fetchone()


def find_pack_by_slug(conn: psycopg.Connection, params: Params) -> Row | None:
    return conn.execute(_FIND_PACK_BY_SLUG, params).fetchone()


def add_pack(conn: psycopg.Connection, params: Params) -> None:
    conn.execute(_ADD_PACK, params)


def get_pack_version(conn: psycopg.Connection, params: Params) -> Row | None:
    return conn.execute(_GET_PACK_VERSION, params).fetchone()


def find_pack_version(conn: psycopg.Connection, params: Params) -> Row | None:
    return conn.execute(_FIND_PACK_VERSION, params).fetchone()


def add_pack_version(conn: psycopg.Connection, params: Params) -> None:
    conn.execute(_ADD_PACK_VERSION, params)


def summaries(conn: psycopg.Connection, params: Params) -> list[Row]:
    return conn.execute(_SUMMARIES, params).fetchall()


def retire_pack_version(conn: psycopg.Connection, params: Params) -> Row | None:
    return conn.execute(_RETIRE_PACK_VERSION, params).fetchone()


def pack_version_state(conn: psycopg.Connection, params: Params) -> Row | None:
    return conn.execute(_PACK_VERSION_STATE, params).fetchone()


def find_resource(conn: psycopg.Connection, params: Params) -> Row | None:
    return conn.execute(_FIND_RESOURCE, params).fetchone()


def add_resource(conn: psycopg.Connection, params: Params) -> None:
    conn.execute(_ADD_RESOURCE, params)


def owner_trust(conn: psycopg.Connection, params: Params) -> Row | None:
    return conn.execute(_OWNER_TRUST, params).fetchone()


def add_resource_version(conn: psycopg.Connection, params: Params) -> None:
    conn.execute(_ADD_RESOURCE_VERSION, params)


def add_resource_files(conn: psycopg.Connection, rows: Sequence[Params]) -> None:
    with conn.cursor() as cursor:
        cursor.executemany(_ADD_RESOURCE_FILE, rows)


def get_resource_version(conn: psycopg.Connection, params: Params) -> Row | None:
    return conn.execute(_GET_RESOURCE_VERSION, params).fetchone()


def resource_files(conn: psycopg.Connection, params: Params) -> list[Row]:
    return conn.execute(_RESOURCE_FILES, params).fetchall()


def resource_bodies(conn: psycopg.Connection, params: Params) -> list[Row]:
    return conn.execute(_RESOURCE_BODIES, params).fetchall()


def versions_of(conn: psycopg.Connection, params: Params) -> list[Row]:
    return conn.execute(_VERSIONS_OF, params).fetchall()


def in_pack_versions(conn: psycopg.Connection, params: Params) -> list[Row]:
    return conn.execute(_IN_PACK_VERSIONS, params).fetchall()


def in_pack_versions_of_kind(conn: psycopg.Connection, params: Params) -> list[Row]:
    return conn.execute(_IN_PACK_VERSIONS_OF_KIND, params).fetchall()


def quarantined(conn: psycopg.Connection, params: Params) -> list[Row]:
    return conn.execute(_QUARANTINED, params).fetchall()


def add_quarantine(conn: psycopg.Connection, params: Params) -> None:
    conn.execute(_ADD_QUARANTINE, params)


def release_quarantine(conn: psycopg.Connection, params: Params) -> Row | None:
    return conn.execute(_RELEASE_QUARANTINE, params).fetchone()
