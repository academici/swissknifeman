"""Fast pure-Python structural validator for ``urn:skm:config:bootstrap:v1``."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from ipaddress import ip_network
from typing import cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonValue

__all__ = ["BOOTSTRAP_URN", "validate_bootstrap_document"]

BOOTSTRAP_URN = "urn:skm:config:bootstrap:v1"
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
_PROFILE_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}\Z")
_HOST_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,62}\Z")
_APP_NAME_RE = re.compile(r"^[a-z0-9-]{1,40}\Z")
_ENDPOINT_RE = re.compile(r"^https?://[^\s]+/api/v1\Z")
_SECRET_REF_RE = re.compile(
    r"^secret://(env/[A-Z_][A-Z0-9_]{0,127}|file/[^\s]{1,1024}|"
    r"keyring/[A-Za-z0-9._-]{1,128}/[A-Za-z0-9._@-]{1,128})(?![\s\S])"
)
_ROOT_KEYS = frozenset(
    {
        "schema",
        "instance_id",
        "installation_id",
        "machine_database",
        "access",
        "database",
        "api",
        "secrets",
        "web_auth",
        "default_instance",
        "instances",
        "paths",
        "host",
    }
)
_PROFILE_KEYS = frozenset(
    {"instance_id", "access", "database", "api", "secrets", "web_auth", "paths", "host"}
)
_WEB_AUTH_KEYS = frozenset(
    {
        "mode",
        "forwarded_allow_ips",
        "session_ttl_seconds",
        "cookie_samesite",
        "login_rate_limit_max",
        "login_rate_limit_window_seconds",
    }
)
_DB_KEYS = frozenset(
    {
        "url",
        "migrate_on_start",
        "migrator_url",
        "application_name",
        "pool_min_size",
        "pool_max_size",
        "pool_timeout_seconds",
    }
)
_API_KEYS = frozenset({"endpoint", "credential", "ca_bundle", "timeout_seconds"})
_PATH_KEYS = frozenset({"state_dir", "blobs_root", "worktrees_root", "materialized_root", "backups_root"})


def _matches(value: object, pattern: re.Pattern[str]) -> bool:
    return isinstance(value, str) and pattern.match(value) is not None


def _check_mapping(
    value: object,
    pointer: str,
    allowed: frozenset[str],
    required: tuple[str, ...],
    issues: list[tuple[str, str]],
) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping):
        issues.append((pointer or "/", "type"))
        return None
    typed = cast("Mapping[str, object]", value)
    issues.extend((f"{pointer}/{req}", "required") for req in required if req not in typed)
    issues.extend((f"{pointer}/{key}", "additionalProperties") for key in typed if key not in allowed)
    return typed


def _check_int(value: object, pointer: str, lo: int, hi: int, issues: list[tuple[str, str]]) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        issues.append((pointer, "type"))
    elif value < lo or value > hi:
        issues.append((pointer, "minimum" if value < lo else "maximum"))


def _check_database(value: object, pointer: str, issues: list[tuple[str, str]]) -> None:
    db = _check_mapping(value, f"{pointer}/database", _DB_KEYS, ("url",), issues)
    if db is None:
        return
    issues.extend(
        (f"{pointer}/database/{key}", "pattern")
        for key in ("url", "migrator_url")
        if key in db and not _matches(db[key], _SECRET_REF_RE)
    )
    if "migrate_on_start" in db and not isinstance(db["migrate_on_start"], bool):
        issues.append((f"{pointer}/database/migrate_on_start", "type"))
    if "application_name" in db and not _matches(db["application_name"], _APP_NAME_RE):
        issues.append((f"{pointer}/database/application_name", "pattern"))
    for key, lo, hi in (
        ("pool_min_size", 0, 64),
        ("pool_max_size", 1, 256),
        ("pool_timeout_seconds", 1, 300),
    ):
        if key in db:
            _check_int(db[key], f"{pointer}/database/{key}", lo, hi, issues)


def _check_api(value: object, pointer: str, issues: list[tuple[str, str]]) -> None:
    api = _check_mapping(value, f"{pointer}/api", _API_KEYS, ("endpoint", "credential"), issues)
    if api is None:
        return
    if "endpoint" in api and not _matches(api["endpoint"], _ENDPOINT_RE):
        issues.append((f"{pointer}/api/endpoint", "pattern"))
    if "credential" in api and not _matches(api["credential"], _SECRET_REF_RE):
        issues.append((f"{pointer}/api/credential", "pattern"))
    if "ca_bundle" in api and (not isinstance(api["ca_bundle"], str) or not api["ca_bundle"]):
        issues.append((f"{pointer}/api/ca_bundle", "minLength"))
    if "timeout_seconds" in api:
        timeout = api["timeout_seconds"]
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout):
            issues.append((f"{pointer}/api/timeout_seconds", "type"))
        elif timeout < 1 or timeout > 600:
            issues.append((f"{pointer}/api/timeout_seconds", "minimum" if timeout < 1 else "maximum"))


def _check_web_auth(value: object, pointer: str, issues: list[tuple[str, str]]) -> None:
    cfg = _check_mapping(value, f"{pointer}/web_auth", _WEB_AUTH_KEYS, (), issues)
    if cfg is None:
        return
    if "mode" in cfg and cfg["mode"] not in ("admin_login", "none"):
        issues.append((f"{pointer}/web_auth/mode", "enum"))
    if "cookie_samesite" in cfg and cfg["cookie_samesite"] not in ("lax", "strict"):
        issues.append((f"{pointer}/web_auth/cookie_samesite", "enum"))
    for key, lo, hi in (
        ("session_ttl_seconds", 300, 2_592_000),
        ("login_rate_limit_max", 1, 1000),
        ("login_rate_limit_window_seconds", 1, 3600),
    ):
        if key in cfg:
            _check_int(cfg[key], f"{pointer}/web_auth/{key}", lo, hi, issues)
    if "forwarded_allow_ips" in cfg:
        raw_ips = cfg["forwarded_allow_ips"]
        if not isinstance(raw_ips, list):
            issues.append((f"{pointer}/web_auth/forwarded_allow_ips", "type"))
            return
        seen: set[str] = set()
        for idx, item in enumerate(cast("list[object]", raw_ips)):
            if not isinstance(item, str) or not 1 <= len(item) <= 64:
                issues.append((f"{pointer}/web_auth/forwarded_allow_ips/{idx}", "type"))
                continue
            if item in seen:
                issues.append((f"{pointer}/web_auth/forwarded_allow_ips", "uniqueItems"))
                continue
            seen.add(item)
            try:
                ip_network(item, strict=False)
            except ValueError:
                issues.append((f"{pointer}/web_auth/forwarded_allow_ips/{idx}", "pattern"))


def _check_host(value: object, pointer: str, *, root: bool, issues: list[tuple[str, str]]) -> None:
    keys = frozenset({"id", "name"}) if root else frozenset({"id"})
    host = _check_mapping(value, f"{pointer}/host", keys, (), issues)
    if host is None:
        return
    if "id" in host and host["id"] != "auto" and not _matches(host["id"], _UUID_RE):
        issues.append((f"{pointer}/host/id", "anyOf"))
    if root and "name" in host and not _matches(host["name"], _HOST_NAME_RE):
        issues.append((f"{pointer}/host/name", "pattern"))


def _check_scope_fields(
    table: Mapping[str, object], pointer: str, *, root: bool, issues: list[tuple[str, str]]
) -> None:
    if "instance_id" in table and not _matches(table["instance_id"], _UUID_RE):
        issues.append((f"{pointer}/instance_id", "pattern"))
    if "access" in table:
        acc = _check_mapping(table["access"], f"{pointer}/access", frozenset({"mode"}), ("mode",), issues)
        if acc is not None and "mode" in acc and acc["mode"] not in ("embedded", "http"):
            issues.append((f"{pointer}/access/mode", "enum"))
    if "database" in table:
        _check_database(table["database"], pointer, issues)
    if "api" in table:
        _check_api(table["api"], pointer, issues)
    if "secrets" in table:
        sec = _check_mapping(table["secrets"], f"{pointer}/secrets", frozenset({"token_pepper"}), (), issues)
        if sec is not None and "token_pepper" in sec and not _matches(sec["token_pepper"], _SECRET_REF_RE):
            issues.append((f"{pointer}/secrets/token_pepper", "pattern"))
    if "web_auth" in table:
        _check_web_auth(table["web_auth"], pointer, issues)
    if "paths" in table:
        paths = _check_mapping(table["paths"], f"{pointer}/paths", _PATH_KEYS, (), issues)
        if paths is not None:
            issues.extend(
                (f"{pointer}/paths/{key}", "minLength")
                for key, val in paths.items()
                if key in _PATH_KEYS and (not isinstance(val, str) or not val)
            )
    if "host" in table:
        _check_host(table["host"], pointer, root=root, issues=issues)


def _check_access_rules(table: Mapping[str, object], pointer: str, issues: list[tuple[str, str]]) -> None:
    access = table.get("access")
    mode = cast("Mapping[str, object]", access).get("mode") if isinstance(access, Mapping) else None
    if mode == "embedded" and "database" not in table:
        issues.append((f"{pointer}/database", "required"))
    elif mode == "http" and "api" not in table:
        issues.append((f"{pointer}/api", "required"))


def _check_instances(value: object, issues: list[tuple[str, str]]) -> None:
    if not isinstance(value, Mapping):
        issues.append(("/instances", "type"))
        return
    typed = cast("Mapping[str, object]", value)
    if len(typed) < 1 or len(typed) > 32:
        issues.append(("/instances", "minProperties" if len(typed) < 1 else "maxProperties"))
    for name, raw_profile in typed.items():
        if not _matches(name, _PROFILE_NAME_RE):
            issues.append((f"/instances/{name}", "propertyNames"))
        prof = _check_mapping(
            raw_profile, f"/instances/{name}", _PROFILE_KEYS, ("instance_id", "access"), issues
        )
        if prof is not None:
            _check_scope_fields(prof, f"/instances/{name}", root=False, issues=issues)
            _check_access_rules(prof, f"/instances/{name}", issues)


def validate_bootstrap_document(document: Mapping[str, JsonValue]) -> None:
    issues: list[tuple[str, str]] = []
    doc = _check_mapping(document, "", _ROOT_KEYS, ("schema",), issues)
    if doc is not None:
        if "schema" in doc and doc["schema"] != BOOTSTRAP_URN:
            issues.append(("/schema", "const"))
        _check_scope_fields(doc, "", root=True, issues=issues)
        if "installation_id" in doc and not _matches(doc["installation_id"], _UUID_RE):
            issues.append(("/installation_id", "pattern"))
        if "machine_database" in doc:
            machine = _check_mapping(
                doc["machine_database"],
                "/machine_database",
                frozenset({"url", "migrator_url"}),
                ("url",),
                issues,
            )
            if machine is not None:
                issues.extend(
                    (f"/machine_database/{key}", "pattern")
                    for key in ("url", "migrator_url")
                    if key in machine and not _matches(machine[key], _SECRET_REF_RE)
                )
        if "default_instance" in doc and not _matches(doc["default_instance"], _PROFILE_NAME_RE):
            issues.append(("/default_instance", "pattern"))
        if "instances" in doc:
            _check_instances(doc["instances"], issues)
        single = (
            "instance_id" in doc
            and "access" in doc
            and "instances" not in doc
            and "default_instance" not in doc
        )
        host_doc = doc.get("host")
        multi = (
            "instances" in doc
            and "default_instance" in doc
            and not (set(doc) & {"instance_id", "access", "database", "api", "secrets"})
            and not (isinstance(host_doc, Mapping) and "id" in host_doc)
        )
        if single == multi:
            issues.append(("/", "oneOf"))
        elif single:
            _check_access_rules(doc, "", issues)
    if issues:
        # Schema messages can quote rejected literal credentials: retain pointers/codes only.
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            "Invalid bootstrap v1 document",
            details={"issues": [{"pointer": ptr, "code": code} for ptr, code in issues]},
        )
