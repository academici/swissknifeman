"""``PluginHost``: trust, grants, failures and life cycle of the plugins of the GUI (decisions D22-D24; stdlib + aicore).

A plugin is a hub bridge (``source = unit``) or an external extension (``source = extension``) that provides a GUI
contribution. Only the operator's decision, the grants and the history are stored (``gui.db`` migration 3: ``plugins``,
``plugin_events``, ``grants``); the life cycle ``state`` is derived by the pure :func:`derive_state` from those facts and
from what the process remembers (calls in flight, the outcome of the last call). All work of a plugin goes through
:meth:`PluginHost.admit`; a refusal is a :class:`PluginError`.

Every mutation holds ``host.lock`` and then ``db_lock`` and runs in one ``BEGIN IMMEDIATE`` transaction; events and
audit rows are sent after ``COMMIT`` (I11), still under ``host.lock``, so their order is the order of the changes.
Time and waiting are injected (``clock``, ``monotonic``, ``sleep``); nothing here sleeps for real in a test.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Set, Tuple

from aicore.ext.plugins import safe_text
from aicore.util.digest import digest_json, sha256_tagged
from aicore.util.redact import redact_text

from ..catalog import resolve
from ..errors import CODES, GuiError

CONTRACT = "urn:swissknifeman:gui:trust:v1"

EFFECTS = ("read", "project.write", "plan.write", "config.write", "process.spawn", "network", "secrets.read",
           "terminal")
# Effects no grant can cover: read is free, terminal is reserved (the resolver refuses it).
UNGRANTABLE = frozenset({"read", "terminal"})

# Codes of the extension layer that blame the plugin (a broken process or protocol), and OUTPUT_INVALID (a query
# answer that is not the view it declared). A domain error of the plugin (its own code), a non-zero exit of an argv
# command and a cancellation by the user are NOT failures.
PROTOCOL_FAULTS = frozenset({"PROCESS_SPAWN", "PROCESS_TIMEOUT", "PLUGIN_TIMEOUT", "PROCESS_EXIT", "PROTOCOL_STDOUT",
                             "PROTOCOL_STDOUT_TOO_LARGE", "PLUGIN_HANDSHAKE_MISMATCH", "PLUGIN_RESPONSE_INVALID",
                             "PLUGIN_MANIFEST_INVALID", "PLUGIN_ID_MISMATCH", "PLUGIN_UNAVAILABLE"})
FAILURE_CODES = PROTOCOL_FAULTS | {"OUTPUT_INVALID"}

ACTIVE_STATES = frozenset({"enabled", "starting", "healthy", "degraded", "permission_denied"})
ACCEPTED, INCOMPATIBLE, INVALID, MISSING = "accepted", "incompatible", "invalid", "missing"

DETAIL_LIMIT = 500
MAX_GRANT_DAYS = 365
FINDINGS_SHOWN = 10
POLL_S = 0.05
_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class PluginError(GuiError):
    """A refusal of the host with a ``code`` and optional ``details``.

    ``PLUGIN_DISABLED`` and ``PLUGIN_CONFORMANCE_FAILED`` are registered in ``gui.errors`` by the API item; until then
    such an error still carries ``code``, ``message`` and ``details`` but cannot build an ``envelope``.
    """

    def __init__(self, code: str, message: str, *, details: Optional[Mapping[str, object]] = None) -> None:
        if code in CODES:
            super().__init__(code, message, details=details)
        else:
            Exception.__init__(self, f"{code}: {message}")
            self.code, self.message, self.details, self.issues = code, message, dict(details or {}), []


# --- the pure part ------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Facts:
    """What :func:`derive_state` needs; ``last_ok`` is ``None`` before the first call of this process."""

    verdict: str = ACCEPTED  # accepted | incompatible | invalid | missing
    desired: str = "enabled"  # new | enabled | disabled
    quarantined: bool = False
    reapproval: bool = False
    inflight: int = 0
    last_ok: Optional[bool] = None
    recent_failures: int = 0


def derive_state(facts: Facts) -> str:
    """The ``plugin_state`` of the facts: the first matching rule of knowledge/p5-design#state-model."""
    if facts.verdict == INCOMPATIBLE:
        return "incompatible"
    if facts.verdict == MISSING:
        return "discovered"
    if facts.verdict != ACCEPTED:
        return "invalid"
    if facts.quarantined:
        return "quarantined"
    if facts.desired == "disabled":
        return "disabled"
    if facts.desired == "new":
        return "compatible"
    if facts.reapproval:
        return "permission_denied"
    if facts.inflight > 0 and facts.last_ok is None:
        return "starting"
    if facts.last_ok is False and facts.recent_failures > 0:
        return "degraded"
    if facts.last_ok is True:
        return "healthy"
    return "enabled"


def flags(state: str) -> Tuple[bool, bool]:
    """``(runtime_enabled, ui_enabled)`` of a state: both are on for the same set of states."""
    on = state in ACTIVE_STATES
    return on, on


def needs_grant(effect: str, source: str) -> bool:
    """Whether the start gate wants a grant for ``effect``: only for extensions and only beyond ``read``.
    ``terminal`` needs one too and none can be given, so it is always refused."""
    return source == "extension" and effect != "read"


def enforcement(effect: str, source: str, platform: Optional[str] = None, *, declared: bool = True) -> str:
    """How an effect is limited (I12, D23): ``declared`` or ``advisory``; never ``enforced``.

    The platform has no sandbox in v1 (``platform`` is reserved for one), so an effect that needs a grant is shown
    ``advisory``: the grant gates the start, it does not restrict the running process.
    """
    return "advisory" if declared and needs_grant(effect, source) else "declared"


def failing(results: Iterable[Mapping[str, Any]]) -> List[Dict[str, str]]:
    """The failing checks of ``check-result/v1`` documents as ``{id, observed}`` (what ``conformance`` returns)."""
    return [{"id": str(item.get("check_id", "")), "observed": str(item.get("observed", ""))}
            for item in results if item.get("status") == "fail"]


@dataclass(frozen=True)
class Observed:
    """One plugin as the catalog shows it: ``digest`` is the manifest digest of an accepted contribution."""

    id: str
    source: str  # unit | extension
    verdict: str  # accepted | incompatible | invalid
    digest: str
    effects: Tuple[str, ...] = ()
    compatibility: Mapping[str, Any] = field(default_factory=lambda: {"protocol_ok": True, "missing_contracts": []})
    root: Optional[str] = None  # owner root, for the conformance check


def _declared_effects(document: Mapping[str, Any]) -> Tuple[str, ...]:
    found: Set[str] = set()
    if document.get("queries"):
        found.add("read")
    for command in document.get("commands", ()):
        found.update(effect for effect in command.get("effects", ()) if effect in EFFECTS)
    return tuple(effect for effect in EFFECTS if effect in found)


def _handler_digest(handler: Optional[Path]) -> Optional[str]:
    if handler is None:
        return None
    try:
        return sha256_tagged(Path(handler).read_bytes())
    except OSError:
        return None


def observe(catalog: Any) -> List[Observed]:
    """The plugins of a catalog: every accepted owner, and every owner a source declared that the resolver rejected.

    ``manifest_digest`` = ``digest_json({"contribution": <catalog digest>, "handler": <sha256 of the handler manifest>})``.
    Executable files of argv commands are not part of it (the broker pins them per run).
    """
    digests = {entry["owner"]: entry["digest"] for entry in catalog.document.get("contributions", ())}
    found: Dict[str, Observed] = {}
    for owner, entry in catalog.owners.items():
        digest = digest_json({"contribution": digests.get(owner), "handler": _handler_digest(entry.handler)})
        found[owner] = Observed(owner, entry.source.kind, ACCEPTED, digest, _declared_effects(entry.document),
                                {"protocol_ok": True, "missing_contracts": []}, str(entry.source.root))
    codes: Dict[str, Set[str]] = {}
    for entry in catalog.document.get("rejected", ()):
        if entry.get("owner") and entry["owner"] not in found:
            codes.setdefault(entry["owner"], set()).add(entry.get("code", ""))
    for owner, owner_codes in sorted(codes.items()):
        source = catalog.sources.get(owner)
        if source is None:
            continue
        verdict = INCOMPATIBLE if resolve.INCOMPATIBLE in owner_codes else INVALID
        found[owner] = Observed(owner, source.kind, verdict, digest_json({"rejected": sorted(owner_codes)}), (),
                                resolve.compatibility(source), str(source.root))
    return [found[owner] for owner in sorted(found)]


# --- tickets ------------------------------------------------------------------------------------------------


class Ticket:
    """Permission to do one piece of work of a plugin (a context manager).

    :meth:`finish` reports the outcome once: ``code`` is ``None`` for success or the result code; a code of
    ``FAILURE_CODES`` is a plugin failure that counts toward quarantine, any other code (a domain error, a non-zero
    exit of an argv command) is not; ``cancelled=True`` is a cancellation by the user and judges nothing. Leaving the
    ``with`` block without ``finish`` releases the ticket as cancelled.
    """

    def __init__(self, host: "PluginHost", plugin: str, kind: str, grants: Sequence[str]) -> None:
        self.host, self.plugin, self.kind, self.grants = host, plugin, kind, list(grants)
        self.finished = False
        self._guard = threading.Lock()

    def finish(self, code: Optional[str] = None, detail: Optional[str] = None, *, cancelled: bool = False) -> None:
        with self._guard:
            if self.finished:
                return
            self.finished = True
        self.host._finish(self, code, detail, cancelled)

    def __enter__(self) -> "Ticket":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.finish(cancelled=True)


# --- the host -----------------------------------------------------------------------------------------------


class PluginHost:
    def __init__(self, conn: sqlite3.Connection, db_lock: Any, settings: Any, publish: Callable[..., Any],
                 audit: Callable[..., Any], active_runs: Callable[[str], Iterable[str]],
                 cancel_run: Callable[[str], Any], conformance: Callable[[Observed], Sequence[Mapping[str, Any]]],
                 clock: Optional[Callable[[], float]] = None, monotonic: Optional[Callable[[], float]] = None,
                 sleep: Optional[Callable[[float], Any]] = None) -> None:
        self.conn = conn
        self.db_lock = db_lock
        self.lock = threading.RLock()
        self._settings = settings
        self._publish = publish
        self._audit = audit
        self._active_runs = active_runs
        self._cancel_run = cancel_run
        self._conformance = conformance
        self._clock = clock or time.time
        self._monotonic = monotonic or time.monotonic
        self._sleep = sleep or asyncio.sleep
        self._observed: Dict[str, Observed] = {}
        self._inflight: Dict[str, int] = {}
        self._last_ok: Dict[str, Optional[bool]] = {}
        self._closing: Set[str] = set()
        self._conformed: Dict[str, str] = {}  # plugin -> digest whose conformance passed

    # --- plumbing ---

    def observe(self, catalog: Any) -> List[Observed]:
        return observe(catalog)

    def _cfg(self) -> Any:
        settings = self._settings() if callable(self._settings) else self._settings
        return settings.plugins

    def _runs_cfg(self) -> Any:
        settings = self._settings() if callable(self._settings) else self._settings
        return settings.runs

    def _epoch(self) -> float:
        return float(self._clock())

    def _iso(self, epoch: Optional[float] = None) -> str:
        return datetime.fromtimestamp(self._epoch() if epoch is None else epoch, timezone.utc).strftime(_TIME_FORMAT)

    def _clean(self, text: Optional[str]) -> Optional[str]:
        if text is None:
            return None
        return safe_text(redact_text(str(text)), DETAIL_LIMIT)

    def _fetch(self, sql: str, params: Sequence[Any] = ()) -> List[sqlite3.Row]:
        with self.db_lock:
            return self.conn.execute(sql, tuple(params)).fetchall()

    def _row(self, plugin: str) -> Optional[sqlite3.Row]:
        found = self._fetch("SELECT * FROM plugins WHERE id = ?", (plugin,))
        return found[0] if found else None

    @contextmanager
    def _mutation(self) -> Iterator[List[Callable[[], None]]]:
        """``host.lock`` + ``db_lock`` + ``BEGIN IMMEDIATE``; the callbacks queued in the yielded list run after COMMIT."""
        with self.lock:
            after: List[Callable[[], None]] = []
            with self.db_lock:
                self.conn.execute("BEGIN IMMEDIATE")
                try:
                    yield after
                except BaseException:
                    self.conn.execute("ROLLBACK")
                    raise
                self.conn.execute("COMMIT")
            for callback in after:
                try:
                    callback()
                except Exception:  # noqa: BLE001 - a failing subscriber never undoes a committed change
                    pass

    def _send(self, type_: str, data: Mapping[str, Any], subject: str) -> None:
        try:
            self._publish(type_, dict(data), subject)
        except Exception:  # noqa: BLE001
            pass

    def _log(self, action: str, target: str, details: Mapping[str, Any]) -> None:
        try:
            self._audit(action, target, "allowed", dict(details))
        except Exception:  # noqa: BLE001
            pass

    def _history(self, plugin: str, kind: str, code: Optional[str] = None, detail: Optional[str] = None) -> None:
        """One history row (in the open transaction); the oldest rows beyond ``history_limit`` go."""
        self.conn.execute("INSERT INTO plugin_events (plugin, at, kind, code, detail) VALUES (?, ?, ?, ?, ?)",
                          (plugin, self._iso(), kind, code, self._clean(detail)))
        self.conn.execute(
            "DELETE FROM plugin_events WHERE plugin = ? AND id <= COALESCE("
            "(SELECT id FROM plugin_events WHERE plugin = ? ORDER BY id DESC LIMIT 1 OFFSET ?), 0)",
            (plugin, plugin, int(self._cfg().history_limit)))

    # --- facts and state ---

    def _failures(self, plugin: str) -> Tuple[int, Optional[str]]:
        """Failures inside the window after the last release, and the code of the last one."""
        window = int(self._cfg().quarantine_window_s)
        since = self._iso(self._epoch() - window)
        marker = self._fetch("SELECT COALESCE(MAX(id), 0) FROM plugin_events WHERE plugin = ? AND kind = 'admin' "
                             "AND code = 'release'", (plugin,))[0][0]
        rows = self._fetch("SELECT code FROM plugin_events WHERE plugin = ? AND kind = 'failure' AND id > ? "
                           "AND at >= ? ORDER BY id", (plugin, marker, since))
        return len(rows), (rows[-1][0] if rows else None)

    def _facts(self, plugin: str, row: sqlite3.Row) -> Facts:
        observed = self._observed.get(plugin)
        return Facts(verdict=observed.verdict if observed else MISSING, desired=row["desired"],
                     quarantined=row["quarantined_at"] is not None, reapproval=bool(row["reapproval"]),
                     inflight=self._inflight.get(plugin, 0), last_ok=self._last_ok.get(plugin),
                     recent_failures=self._failures(plugin)[0])

    def _state(self, plugin: str, row: Optional[sqlite3.Row] = None) -> str:
        row = row if row is not None else self._row(plugin)
        return "discovered" if row is None else derive_state(self._facts(plugin, row))

    def _watch(self, after: List[Callable[[], None]], plugin: str, before: str, reason: str) -> None:
        """In a transaction: when the derived state changed, write the history row and queue the event."""
        current = self._state(plugin)
        if current != before:
            self._history(plugin, "state", current, f"{before} -> {current}: {reason}")
            after.append(lambda: self._send("gui.plugin.state", {"plugin": plugin, "from": before, "to": current,
                                                                  "reason": reason}, plugin))

    def _announce(self, plugin: str, before: str, reason: str) -> None:
        """Outside a transaction (memory-only changes): publish a state change."""
        current = self._state(plugin)
        if current != before:
            self._send("gui.plugin.state", {"plugin": plugin, "from": before, "to": current, "reason": reason}, plugin)

    def _require(self, plugin: str) -> sqlite3.Row:
        row = self._row(plugin)
        if row is None:
            raise PluginError("NOT_FOUND", f"no plugin {plugin!r}")
        return row

    # --- sync ---

    def sync(self, observed: Iterable[Observed]) -> None:
        """Make the stored plugins agree with the catalog (at start and after every catalog refresh).

        A new plugin gets its default decision (hub unit: ``enabled``, extension: ``new``). A changed digest keeps the
        effective grants (rebinding them to the new digest) unless the plugin now declares an effect it did not declare
        before: then they are all voided, ``reapproval`` is set and a grant that was voided never comes back.
        """
        incoming = {entry.id: entry for entry in observed}
        with self._mutation() as after:
            previous = self._observed
            try:
                rows = {row["id"]: row for row in self._fetch("SELECT * FROM plugins")}
                ids = sorted(set(rows) | set(incoming))
                before = {plugin: self._state(plugin, rows[plugin]) if plugin in rows else "discovered"
                          for plugin in ids}
                reasons: Dict[str, str] = {}
                now = self._iso()
                for plugin, entry in sorted(incoming.items()):
                    row = rows.get(plugin)
                    accepted = entry.verdict == ACCEPTED
                    if row is None:
                        self.conn.execute(
                            "INSERT INTO plugins (id, desired, digest, effects_json, source, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            (plugin, "enabled" if entry.source == "unit" else "new", entry.digest if accepted else None,
                             json.dumps(list(entry.effects) if accepted else []), entry.source, now))
                        reasons[plugin] = "discovered"
                    elif accepted and row["digest"] != entry.digest:
                        reasons[plugin] = self._rebind(after, row, entry, now)
                    elif row["source"] != entry.source:
                        self.conn.execute("UPDATE plugins SET source = ?, updated_at = ? WHERE id = ?",
                                          (entry.source, now, plugin))
                self._observed = dict(incoming)
                for plugin in ids:
                    self._watch(after, plugin, before[plugin], reasons.get(plugin, "sync"))
            except BaseException:
                self._observed = previous
                raise

    def _rebind(self, after: List[Callable[[], None]], row: sqlite3.Row, entry: Observed, now: str) -> str:
        """The digest of ``row`` changed: move or void its grants, store the new digest and effects."""
        plugin = row["id"]
        self._conformed.pop(plugin, None)
        old_effects = set(json.loads(row["effects_json"]))
        widened = bool(set(entry.effects) - old_effects) if row["digest"] is not None else False
        reason, reapproval, code = "digest", row["reapproval"], "changed"
        live = self._fetch("SELECT * FROM grants WHERE plugin = ? AND revoked_at IS NULL AND voided_at IS NULL "
                           "ORDER BY id", (plugin,))
        if live and not widened:
            self.conn.execute("UPDATE grants SET manifest_digest = ? WHERE plugin = ? AND revoked_at IS NULL "
                              "AND voided_at IS NULL", (entry.digest, plugin))
            code = "rebound"
            after.append(lambda: self._log("grant.rebound", plugin, {"grants": len(live), "digest": entry.digest}))
        elif live and widened:
            self.conn.execute("UPDATE grants SET voided_at = ?, void_reason = 'manifest_widened' WHERE plugin = ? "
                              "AND revoked_at IS NULL AND voided_at IS NULL", (now, plugin))
            code, reason = "voided", "manifest_widened"
            if entry.source == "extension":
                reapproval = 1
            after.append(lambda: self._log("grant.voided", plugin, {"grants": len(live), "digest": entry.digest}))
            for grant in live:
                data = {"plugin": plugin, "capability": grant["capability"], "project_id": grant["project_id"],
                        "action": "voided"}
                after.append(lambda data=data: self._send("gui.plugin.grant", data, plugin))
        self.conn.execute("UPDATE plugins SET digest = ?, effects_json = ?, source = ?, reapproval = ?, updated_at = ? "
                          "WHERE id = ?", (entry.digest, json.dumps(list(entry.effects)), entry.source, reapproval,
                                           now, plugin))
        self._history(plugin, "digest", code, f"{row['digest']} -> {entry.digest}")
        return reason

    # --- admit and finish ---

    def admit(self, owner: str, kind: str, effects: Iterable[str], project_id: Optional[str]) -> Ticket:
        """The one way to run work of a plugin (PI1). Refuses with ``PLUGIN_UNAVAILABLE``, ``PLUGIN_QUARANTINED``,
        ``PLUGIN_DISABLED`` or ``PERMISSION_DENIED`` (the grant gate of an extension); counts the call in flight."""
        needed = list(dict.fromkeys(effects))
        with self.lock:
            row = self._row(owner)
            observed = self._observed.get(owner)
            if row is None or observed is None or observed.verdict != ACCEPTED:
                raise PluginError("PLUGIN_UNAVAILABLE", f"plugin {owner!r} is not available")
            if row["quarantined_at"] is not None:
                raise PluginError("PLUGIN_QUARANTINED", f"plugin {owner!r} is in quarantine; release it first",
                                  details={"plugin": owner, "code": row["quarantine_code"]})
            if owner in self._closing or row["desired"] != "enabled":
                raise PluginError("PLUGIN_DISABLED", f"plugin {owner!r} is not enabled", details={"plugin": owner})
            grants = self._gate(row, needed, project_id)
            before = self._state(owner, row)
            self._inflight[owner] = self._inflight.get(owner, 0) + 1
            self._announce(owner, before, "call")
            return Ticket(self, owner, kind, grants)

    def _gate(self, row: sqlite3.Row, effects: Sequence[str], project_id: Optional[str]) -> List[str]:
        """Ids of the grants that cover every effect beyond ``read`` of an extension, else ``PERMISSION_DENIED``."""
        used: List[str] = []
        if row["source"] != "extension":
            return used
        now = self._iso()
        for effect in effects:
            if not needs_grant(effect, row["source"]):
                continue
            found = self._fetch(
                "SELECT id FROM grants WHERE plugin = ? AND capability = ? AND manifest_digest = ? AND revoked_at IS NULL "
                "AND voided_at IS NULL AND (expires_at IS NULL OR expires_at > ?) "
                "AND (project_id IS NULL OR project_id = ?) ORDER BY id LIMIT 1",
                (row["id"], effect, row["digest"], now, project_id))
            if not found:
                raise PluginError("PERMISSION_DENIED", f"plugin {row['id']!r} has no grant for {effect}",
                                  details={"plugin": row["id"], "effect": effect, "project_id": project_id})
            if found[0][0] not in used:
                used.append(found[0][0])
        return used

    def _finish(self, ticket: Ticket, code: Optional[str], detail: Optional[str], cancelled: bool) -> None:
        plugin = ticket.plugin
        with self.lock:
            before = self._state(plugin)
            self._inflight[plugin] = max(0, self._inflight.get(plugin, 0) - 1)
            failure = not cancelled and code in FAILURE_CODES
            if not cancelled:
                self._last_ok[plugin] = not failure
            if not failure:
                self._announce(plugin, before, "call")
                return
            with self._mutation() as after:
                row = self._row(plugin)
                if row is None:
                    return
                self._history(plugin, "failure", code, detail)
                count, _last = self._failures(plugin)
                if row["quarantined_at"] is None and count >= int(self._cfg().quarantine_failures):
                    self.conn.execute("UPDATE plugins SET quarantined_at = ?, quarantine_code = ?, updated_at = ? "
                                      "WHERE id = ?", (self._iso(), code, self._iso(), plugin))
                    after.append(lambda: self._log("plugin.quarantine", plugin, {"code": code, "failures": count}))
                self._watch(after, plugin, before, "failure")

    def busy(self, plugin: str) -> int:
        """Calls in flight plus active runs of the plugin: what Disable would wait for."""
        with self.lock:
            return self._inflight.get(plugin, 0) + len(list(self._active_runs(plugin)))

    def active_runs(self, plugin: str) -> List[str]:
        return list(self._active_runs(plugin))

    # --- operator decisions ---

    async def enable(self, plugin: str) -> Dict[str, Any]:
        """Turn the plugin on. An extension first passes the conformance gate (the check of ``gui check``)."""
        with self.lock:
            row = self._require(plugin)
            observed = self._enable_precheck(plugin, row)
            digest = observed.digest
            cached = self._conformed.get(plugin) == digest
        if row["source"] == "extension" and not cached:
            findings = await asyncio.to_thread(self._conformance, observed)
            shown = [{"id": str(item.get("id", ""))[:200], "observed": self._clean(item.get("observed", ""))}
                     for item in list(findings)[:FINDINGS_SHOWN]]
            if findings:
                raise PluginError("PLUGIN_CONFORMANCE_FAILED", f"plugin {plugin!r} fails the conformance check",
                                  details={"findings": shown})
        with self._mutation() as after:
            row = self._require(plugin)
            observed = self._enable_precheck(plugin, row)
            if observed.digest != digest:
                raise PluginError("PLUGIN_UNAVAILABLE", f"plugin {plugin!r} changed during the check; try again")
            before = self._state(plugin, row)
            if row["source"] == "extension":
                self._conformed[plugin] = digest
            if row["desired"] != "enabled":
                self.conn.execute("UPDATE plugins SET desired = 'enabled', updated_at = ? WHERE id = ?",
                                  (self._iso(), plugin))
                self._history(plugin, "admin", "enable")
                after.append(lambda: self._log("plugin.enable", plugin, {"source": row["source"]}))
            self._watch(after, plugin, before, "enable")
        return self.view(plugin)

    def _enable_precheck(self, plugin: str, row: sqlite3.Row) -> Observed:
        observed = self._observed.get(plugin)
        if observed is None or observed.verdict != ACCEPTED:
            raise PluginError("PLUGIN_UNAVAILABLE", f"plugin {plugin!r} is not available")
        if row["quarantined_at"] is not None:
            raise PluginError("PLUGIN_QUARANTINED", f"plugin {plugin!r} is in quarantine; release it first",
                              details={"plugin": plugin, "code": row["quarantine_code"]})
        if plugin in self._closing:
            raise PluginError("PLUGIN_DISABLED", f"plugin {plugin!r} is being disabled", details={"plugin": plugin})
        return observed

    async def disable(self, plugin: str) -> Dict[str, int]:
        """Close the plugin (no new work from the moment this returns its first step), then drain: wait for the calls
        and runs in flight up to ``drain_timeout_s``, cancel the runs left and wait ``runs.cancel_grace_s`` for them.
        Returns ``{drained, cancelled}``: runs that finished on their own and runs cancelled."""
        with self._mutation() as after:
            row = self._require(plugin)
            before = self._state(plugin, row)
            self._closing.add(plugin)
            self.conn.execute("UPDATE plugins SET desired = 'disabled', updated_at = ? WHERE id = ?",
                              (self._iso(), plugin))
            self._history(plugin, "admin", "disable")
            after.append(lambda: self._log("plugin.disable", plugin, {"source": row["source"]}))
            self._watch(after, plugin, before, "disable")
        try:
            started = set(self.active_runs(plugin))
            await self._wait(plugin, int(self._cfg().drain_timeout_s))
            remaining = self.active_runs(plugin)
            for run_id in remaining:
                try:
                    result = self._cancel_run(run_id)
                    if inspect.isawaitable(result):
                        await result
                except Exception:  # noqa: BLE001 - a run that cannot be cancelled is waited for below
                    pass
            if remaining:
                await self._wait(plugin, int(self._runs_cfg().cancel_grace_s))
            return {"drained": len(started - set(remaining)), "cancelled": len(remaining)}
        finally:
            with self.lock:
                self._closing.discard(plugin)

    async def _wait(self, plugin: str, seconds: int) -> None:
        deadline = self._monotonic() + seconds
        while self.busy(plugin) > 0 and self._monotonic() < deadline:
            result = self._sleep(POLL_S)
            if inspect.isawaitable(result):
                await result

    def release(self, plugin: str) -> Dict[str, Any]:
        """Lift the quarantine and start counting failures anew; the history stays. A plugin with neither a quarantine nor
        a failure in the window is left as it is."""
        with self._mutation() as after:
            row = self._require(plugin)
            if row["quarantined_at"] is not None or self._failures(plugin)[0] > 0:
                before = self._state(plugin, row)
                self.conn.execute("UPDATE plugins SET quarantined_at = NULL, quarantine_code = NULL, updated_at = ? "
                                  "WHERE id = ?", (self._iso(), plugin))
                self._history(plugin, "admin", "release")
                self._last_ok.pop(plugin, None)
                after.append(lambda: self._log("plugin.release", plugin, {"code": row["quarantine_code"]}))
                self._watch(after, plugin, before, "release")
        return self.view(plugin)

    # --- grants ---

    def grant(self, plugin: str, capability: str, project_id: Optional[str] = None, expires_at: Optional[str] = None,
              *, granted_by: str = "browser", digest: Optional[str] = None) -> Dict[str, Any]:
        """Give an extension one effect, in one project or in every one (``project_id`` ``None``).

        ``digest`` is the manifest digest the client saw; when it is no longer the current one the grant is refused
        (``PLUGIN_UNAVAILABLE``) so it is never made for an outdated manifest. The project is not checked here.
        """
        with self._mutation() as after:
            row = self._require(plugin)
            observed = self._observed.get(plugin)
            if observed is None or observed.verdict != ACCEPTED or row["desired"] == "disabled":
                raise PluginError("PLUGIN_UNAVAILABLE", f"plugin {plugin!r} is not available for a grant")
            if row["quarantined_at"] is not None:
                raise PluginError("PLUGIN_QUARANTINED", f"plugin {plugin!r} is in quarantine; release it first",
                                  details={"plugin": plugin})
            if row["source"] != "extension":
                raise PluginError("INPUT_INVALID", f"{plugin!r} is a hub unit and needs no grants")
            if capability in UNGRANTABLE or capability not in json.loads(row["effects_json"]):
                raise PluginError("INPUT_INVALID", f"{capability!r} is not a grantable effect of {plugin!r}")
            if project_id is not None and (not isinstance(project_id, str) or not project_id):
                raise PluginError("INPUT_INVALID", "project_id must be a project id or null")
            if observed.digest != row["digest"] or (digest is not None and digest != row["digest"]):
                raise PluginError("PLUGIN_UNAVAILABLE", f"the manifest of {plugin!r} changed; reload and try again")
            expiry = self._expiry(expires_at)
            before = self._state(plugin, row)
            grant_id = "grant-" + uuid.uuid4().hex
            now = self._iso()
            self.conn.execute(
                "INSERT INTO grants (id, plugin, capability, project_id, manifest_digest, granted_at, expires_at, "
                "granted_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (grant_id, plugin, capability, project_id, row["digest"], now, expiry, granted_by))
            self.conn.execute("UPDATE plugins SET reapproval = 0, updated_at = ? WHERE id = ?", (now, plugin))
            where = "every project" if project_id is None else f"project {project_id}"
            self._history(plugin, "grant", "granted", f"{capability} for {where}")
            details = {"capability": capability, "project_id": project_id, "expires_at": expiry, "grant": grant_id}
            after.append(lambda: self._log("plugin.grant", plugin, details))
            data = {"plugin": plugin, "capability": capability, "project_id": project_id, "action": "granted"}
            after.append(lambda: self._send("gui.plugin.grant", data, plugin))
            self._watch(after, plugin, before, "grant")
            return _grant_doc(self.conn.execute("SELECT * FROM grants WHERE id = ?", (grant_id,)).fetchone())

    def _expiry(self, expires_at: Optional[str]) -> Optional[str]:
        if expires_at is None:
            return None
        try:
            if not isinstance(expires_at, str):
                raise ValueError
            moment = datetime.strptime(expires_at, _TIME_FORMAT).replace(tzinfo=timezone.utc)
        except ValueError:
            raise PluginError("INPUT_INVALID", "expires_at must be RFC 3339 UTC like 2026-10-16T12:00:00Z") from None
        now = datetime.fromtimestamp(self._epoch(), timezone.utc)
        if moment <= now or moment > now + timedelta(days=MAX_GRANT_DAYS):
            raise PluginError("INPUT_INVALID", f"expires_at must be in the future and at most {MAX_GRANT_DAYS} days away")
        return expires_at

    def revoke(self, plugin: str, grant_id: str) -> Dict[str, Any]:
        """Revoke a grant for new work; a run that already started is not cancelled (Disable does that)."""
        with self._mutation() as after:
            self._require(plugin)
            found = self._fetch("SELECT * FROM grants WHERE id = ? AND plugin = ?", (grant_id, plugin))
            if not found:
                raise PluginError("NOT_FOUND", f"no grant {grant_id!r} of plugin {plugin!r}")
            row = found[0]
            if row["revoked_at"] is None:
                before = self._state(plugin)
                self.conn.execute("UPDATE grants SET revoked_at = ? WHERE id = ?", (self._iso(), grant_id))
                self._history(plugin, "grant", "revoked", f"{row['capability']}")
                details = {"capability": row["capability"], "project_id": row["project_id"], "grant": grant_id}
                after.append(lambda: self._log("plugin.revoke", plugin, details))
                data = {"plugin": plugin, "capability": row["capability"], "project_id": row["project_id"],
                        "action": "revoked"}
                after.append(lambda: self._send("gui.plugin.grant", data, plugin))
                self._watch(after, plugin, before, "revoke")
            return _grant_doc(self.conn.execute("SELECT * FROM grants WHERE id = ?", (grant_id,)).fetchone())

    # --- views ---

    def visible(self, plugin: str) -> bool:
        """``ui_enabled``: routes, widgets and docs of the plugin are shown."""
        with self.lock:
            row = self._row(plugin)
            return row is not None and flags(self._state(plugin, row))[1]

    def view(self, plugin: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        """The ``trust/v1`` document of a plugin; grants are the effective ones of every project and of ``project_id``."""
        with self.lock:
            row = self._require(plugin)
            observed = self._observed.get(plugin)
            state = self._state(plugin, row)
            runtime, ui = flags(state)
            declared = set(json.loads(row["effects_json"]))
            count, last = self._failures(plugin)
            failures: Dict[str, Any] = {"count": count, "window_s": int(self._cfg().quarantine_window_s)}
            if last is not None:
                failures["last_code"] = last
            rows = self._fetch(
                "SELECT * FROM grants WHERE plugin = ? AND revoked_at IS NULL AND voided_at IS NULL "
                "AND (expires_at IS NULL OR expires_at > ?) AND (project_id IS NULL OR project_id = ?) ORDER BY id",
                (plugin, self._iso(), project_id))
            return {
                "$schema": CONTRACT, "id": plugin, "source": row["source"], "state": state,
                "runtime_enabled": runtime, "ui_enabled": ui,
                "manifest_digest": observed.digest if observed else row["digest"] or digest_json({"absent": plugin}),
                "compatibility": dict(observed.compatibility) if observed else
                {"protocol_ok": True, "missing_contracts": []},
                "failures": failures,
                "permissions": [{"effect": effect, "declared": effect in declared,
                                 "enforcement": enforcement(effect, row["source"], declared=effect in declared)}
                                for effect in EFFECTS],
                "grants": [_grant_doc(entry) for entry in rows]}

    def views(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.lock:
            ids = sorted(row["id"] for row in self._fetch("SELECT id FROM plugins"))
            return [self.view(plugin, project_id) for plugin in ids]

    def history(self, plugin: str, limit: int = 50) -> List[Dict[str, Any]]:
        """History entries of the plugin, newest first (at most ``limit``, itself at most ``history_limit``)."""
        self._require(plugin)
        size = max(1, min(int(limit), int(self._cfg().history_limit)))
        rows = self._fetch("SELECT id, at, kind, code, detail FROM plugin_events WHERE plugin = ? "
                           "ORDER BY id DESC LIMIT ?", (plugin, size))
        entries = []
        for row in rows:
            entry: Dict[str, Any] = {"id": row["id"], "at": row["at"], "kind": row["kind"]}
            if row["code"] is not None:
                entry["code"] = row["code"]
            if row["detail"] is not None:
                entry["detail"] = row["detail"]
            entries.append(entry)
        return entries


def _grant_doc(row: sqlite3.Row) -> Dict[str, Any]:
    return {"id": row["id"], "plugin": row["plugin"], "capability": row["capability"], "project_id": row["project_id"],
            "manifest_digest": row["manifest_digest"], "granted_at": row["granted_at"],
            "expires_at": row["expires_at"], "granted_by": row["granted_by"]}
