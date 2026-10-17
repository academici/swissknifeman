"""gui.core.plugins: derive_state, sync, grants and digests, the admit gate, failures and quarantine, drain, views."""
import asyncio
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from aicore.util.digest import digest_json

from gui import contracts, settings
from gui.core import plugins
from gui.core.plugins import Facts, Observed, PluginError, derive_state
from gui.storage import db

D1 = digest_json({"v": 1})
D2 = digest_json({"v": 2})
D3 = digest_json({"v": 3})


class Clock:
    def __init__(self, start=1_800_000_000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def obs(plugin="ext", source="extension", digest=D1, effects=("read",), verdict="accepted", **kw):
    return Observed(plugin, source, verdict, digest, tuple(effects), root="/x", **kw)


def run(coro):
    return asyncio.run(coro)


class TestDerive(unittest.TestCase):
    TABLE = [
        # (facts, state): one row per rule of the state model, in order
        (Facts(verdict="incompatible"), "incompatible"),
        (Facts(verdict="invalid"), "invalid"),
        (Facts(verdict="missing"), "discovered"),
        (Facts(quarantined=True), "quarantined"),
        (Facts(desired="disabled"), "disabled"),
        (Facts(desired="new"), "compatible"),
        (Facts(reapproval=True), "permission_denied"),
        (Facts(inflight=1, last_ok=None), "starting"),
        (Facts(last_ok=False, recent_failures=2), "degraded"),
        (Facts(last_ok=True), "healthy"),
        (Facts(), "enabled"),
    ]

    def test_every_rule(self):
        for facts, state in self.TABLE:
            self.assertEqual(state, derive_state(facts), facts)

    def test_priority(self):
        everything = dict(quarantined=True, desired="disabled", reapproval=True, inflight=1, last_ok=False,
                          recent_failures=1)
        self.assertEqual("incompatible", derive_state(Facts(verdict="incompatible", **everything)))
        self.assertEqual("invalid", derive_state(Facts(verdict="invalid", **everything)))
        self.assertEqual("discovered", derive_state(Facts(verdict="missing", **everything)))
        self.assertEqual("quarantined", derive_state(Facts(**everything)))
        everything["quarantined"] = False
        self.assertEqual("disabled", derive_state(Facts(**everything)))
        everything["desired"] = "new"
        self.assertEqual("compatible", derive_state(Facts(**everything)))
        everything["desired"] = "enabled"
        self.assertEqual("permission_denied", derive_state(Facts(**everything)))
        everything["reapproval"] = False
        self.assertEqual("degraded", derive_state(Facts(**everything)))  # last_ok False is not None: not starting
        self.assertEqual("starting", derive_state(Facts(inflight=2, last_ok=None, recent_failures=3)))
        self.assertEqual("healthy", derive_state(Facts(last_ok=True, recent_failures=3)))
        self.assertEqual("enabled", derive_state(Facts(last_ok=False, recent_failures=0)))

    def test_flags_follow_the_active_states(self):
        for state in ("enabled", "starting", "healthy", "degraded", "permission_denied"):
            self.assertEqual((True, True), plugins.flags(state))
        for state in ("discovered", "compatible", "quarantined", "disabled", "incompatible", "invalid"):
            self.assertEqual((False, False), plugins.flags(state))

    def test_enforcement_never_claims_enforced(self):
        for source in ("unit", "extension"):
            for effect in plugins.EFFECTS:
                for declared in (True, False):
                    self.assertNotEqual("enforced", plugins.enforcement(effect, source, "linux", declared=declared))
        self.assertEqual("advisory", plugins.enforcement("network", "extension"))
        self.assertEqual("declared", plugins.enforcement("read", "extension"))
        self.assertEqual("declared", plugins.enforcement("network", "unit"))
        self.assertEqual("declared", plugins.enforcement("network", "extension", declared=False))


class HostCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.conn = db.open_db(tmp / "gui.db")
        self.addCleanup(self.conn.close)
        self.settings = settings.load({"HOME": str(tmp / "home"), "SKM_HOME": str(tmp / "skm")})
        self.clock = Clock()
        self.mono = Clock(0.0)
        self.events, self.audits = [], []
        self.runs = {}  # run id -> owner
        self.cancelled = []
        self.conformance_calls = []
        self.findings = []
        self.finish_on_cancel = True
        self.slept = 0
        self.host = self.make_host()

    def make_host(self):
        async def sleep(seconds):
            self.slept += 1
            self.mono.advance(seconds)

        def conformance(observed):
            self.conformance_calls.append(observed.id)
            return list(self.findings)

        async def cancel_run(run_id):
            self.cancelled.append(run_id)
            if self.finish_on_cancel:
                self.runs.pop(run_id, None)

        return plugins.PluginHost(
            self.conn, threading.RLock(), self.settings, lambda t, d, s: self.events.append((t, d, s)),
            lambda a, t, dec, det: self.audits.append((a, t, dec, det)),
            lambda owner: [rid for rid, who in sorted(self.runs.items()) if who == owner], cancel_run, conformance,
            clock=self.clock, monotonic=self.mono, sleep=sleep)

    def types(self, type_=None):
        return [e for e in self.events if type_ is None or e[0] == type_]

    def state(self, plugin="ext"):
        return self.host.view(plugin)["state"]

    def refuses(self, code, *args, **kw):
        with self.assertRaises(PluginError) as caught:
            self.host.admit(*args, **kw)
        self.assertEqual(code, caught.exception.code)
        return caught.exception

    def enabled_extension(self, effects=("read", "network"), digest=D1):
        self.host.sync([obs(effects=effects, digest=digest)])
        run(self.host.enable("ext"))

    def blow(self, code="PROCESS_TIMEOUT", n=1, plugin="ext"):
        for _ in range(n):
            self.host.admit(plugin, "query", ["read"], None).finish(code)
            self.clock.advance(1)


class TestSync(HostCase):
    def test_defaults_of_a_new_plugin(self):
        self.host.sync([obs("hub", "unit"), obs("ext")])
        self.assertEqual("enabled", self.state("hub"))
        self.assertEqual("compatible", self.state("ext"))
        self.assertTrue(self.host.visible("hub"))
        self.assertFalse(self.host.visible("ext"))
        self.assertFalse(self.host.visible("nobody"))
        self.assertEqual("enabled", self.conn.execute("SELECT desired FROM plugins WHERE id='hub'").fetchone()[0])
        self.assertEqual("new", self.conn.execute("SELECT desired FROM plugins WHERE id='ext'").fetchone()[0])

    def test_sync_is_idempotent_and_keeps_the_decision(self):
        self.enabled_extension()
        before = self.host.history("ext", 100)
        self.host.sync([obs(effects=("read", "network"))])
        self.assertEqual(before, self.host.history("ext", 100))
        self.assertEqual("enabled", self.state())

    def test_rejected_and_missing_plugins(self):
        self.host.sync([obs("old"), obs("bad", verdict="invalid"), obs("inc", verdict="incompatible",
                        compatibility={"protocol_ok": False, "missing_contracts": []})])
        self.assertEqual(["compatible", "invalid", "incompatible"], [self.state(p) for p in ("old", "bad", "inc")])
        self.assertFalse(self.host.view("inc")["compatibility"]["protocol_ok"])
        self.host.sync([])  # gone from the catalog
        self.assertEqual({"discovered"}, {self.state(p) for p in ("old", "bad", "inc")})
        self.assertFalse(self.host.visible("old"))
        self.assertEqual(3, len(self.host.views()))

    def test_state_change_events_and_history(self):
        self.host.sync([obs("hub", "unit")])
        self.host.sync([obs("hub", "unit", verdict="invalid")])
        states = [(d["from"], d["to"]) for t, d, s in self.types("gui.plugin.state")]
        self.assertEqual([("discovered", "enabled"), ("enabled", "invalid")], states)
        self.assertEqual(["state", "state"], [e["kind"] for e in self.host.history("hub")])

    def grant(self, capability="network", project=None, **kw):
        return self.host.grant("ext", capability, project, **kw)

    def test_changed_digest_without_wider_effects_moves_the_grants(self):
        self.enabled_extension()
        grant = self.grant()
        self.host.sync([obs(effects=("read", "network"), digest=D2)])
        view = self.host.view("ext")
        self.assertEqual(D2, view["manifest_digest"])
        self.assertEqual([grant["id"]], [g["id"] for g in view["grants"]])
        self.assertEqual(D2, view["grants"][0]["manifest_digest"])
        self.assertEqual("enabled", view["state"])
        self.assertEqual("rebound", [e for e in self.host.history("ext") if e["kind"] == "digest"][0]["code"])
        self.assertIn("grant.rebound", [a[0] for a in self.audits])
        self.host.admit("ext", "command", ["network"], None).finish()  # still allowed

    def test_narrower_effects_keep_the_grants(self):
        self.enabled_extension(effects=("read", "network", "process.spawn"))
        self.grant("network")
        self.host.sync([obs(effects=("read",), digest=D2)])
        self.assertEqual(1, len(self.host.view("ext")["grants"]))

    def test_wider_effects_void_the_grants_and_ask_again(self):
        self.enabled_extension()
        self.grant()
        self.host.sync([obs(effects=("read", "network", "process.spawn"), digest=D2)])
        view = self.host.view("ext")
        self.assertEqual([], view["grants"])
        self.assertEqual("permission_denied", view["state"])
        self.assertEqual("voided", [e for e in self.host.history("ext") if e["kind"] == "digest"][0]["code"])
        voided = self.conn.execute("SELECT voided_at, void_reason FROM grants").fetchone()
        self.assertEqual("manifest_widened", voided["void_reason"])
        self.assertIsNotNone(voided["voided_at"])
        self.assertEqual([{"plugin": "ext", "capability": "network", "project_id": None, "action": "voided"}],
                         [d for t, d, s in self.types("gui.plugin.grant") if d["action"] == "voided"])
        self.refuses("PERMISSION_DENIED", "ext", "command", ["network"], None)
        self.host.admit("ext", "query", ["read"], None).finish()  # queries stay
        # a new grant lifts the re-approval
        self.grant("network")
        self.assertEqual("healthy", self.state())  # the query above succeeded

    def test_a_voided_grant_does_not_come_back_with_the_old_digest(self):
        self.enabled_extension()
        self.grant()
        self.host.sync([obs(effects=("read", "network", "process.spawn"), digest=D2)])
        self.host.sync([obs(effects=("read", "network"), digest=D1)])
        self.assertEqual([], self.host.view("ext")["grants"])
        self.refuses("PERMISSION_DENIED", "ext", "command", ["network"], None)

    def test_widening_of_a_hub_unit_changes_nothing_else(self):
        self.host.sync([obs("hub", "unit", effects=("read",))])
        self.host.sync([obs("hub", "unit", effects=("read", "process.spawn"), digest=D2)])
        self.assertEqual("enabled", self.state("hub"))

    def test_changed_digest_forgets_the_conformance_result(self):
        self.enabled_extension()
        self.assertEqual(["ext"], self.conformance_calls)
        self.host.sync([obs(effects=("read", "network"), digest=D2)])
        run(self.host.disable("ext"))
        run(self.host.enable("ext"))
        self.assertEqual(["ext", "ext"], self.conformance_calls)


class TestAdmit(HostCase):
    def test_refusals(self):
        self.refuses("PLUGIN_UNAVAILABLE", "nobody", "query", ["read"], None)
        self.host.sync([obs("ext"), obs("bad", verdict="invalid"), obs("inc", verdict="incompatible")])
        self.refuses("PLUGIN_DISABLED", "ext", "query", ["read"], None)  # new: not enabled yet
        self.refuses("PLUGIN_UNAVAILABLE", "bad", "query", ["read"], None)
        self.refuses("PLUGIN_UNAVAILABLE", "inc", "query", ["read"], None)
        run(self.host.enable("ext"))
        self.host.admit("ext", "query", ["read"], None).finish()
        run(self.host.disable("ext"))
        self.refuses("PLUGIN_DISABLED", "ext", "query", ["read"], None)
        self.host.sync([])
        self.refuses("PLUGIN_UNAVAILABLE", "ext", "query", ["read"], None)

    def test_quarantine_refuses(self):
        self.enabled_extension()
        self.blow(n=3)
        error = self.refuses("PLUGIN_QUARANTINED", "ext", "query", ["read"], None)
        self.assertEqual("PROCESS_TIMEOUT", error.details["code"])

    def test_grant_gate_covers_each_effect_beyond_read(self):
        self.enabled_extension(effects=("read", "network", "project.write"))
        error = self.refuses("PERMISSION_DENIED", "ext", "command", ["read", "network"], "p1")
        self.assertEqual({"plugin": "ext", "effect": "network", "project_id": "p1"}, error.details)
        net = self.host.grant("ext", "network", "p1")
        ticket = self.host.admit("ext", "command", ["read", "network"], "p1")
        self.assertEqual([net["id"]], ticket.grants)
        ticket.finish()
        self.refuses("PERMISSION_DENIED", "ext", "command", ["network"], "p2")  # another project
        self.refuses("PERMISSION_DENIED", "ext", "command", ["network"], None)  # no project
        self.refuses("PERMISSION_DENIED", "ext", "command", ["network", "project.write"], "p1")
        everywhere = self.host.grant("ext", "project.write", None)
        self.host.grant("ext", "network", None)
        ticket = self.host.admit("ext", "command", ["network", "project.write"], "p9")
        self.assertEqual(2, len(ticket.grants))
        self.assertIn(everywhere["id"], ticket.grants)
        ticket.finish()

    def test_expiry_revoke_and_terminal(self):
        self.enabled_extension()
        stamp = self.host._iso(self.clock.now + 10)
        soon = self.host.grant("ext", "network", None, stamp)
        self.assertEqual(stamp, soon["expires_at"])
        self.host.admit("ext", "command", ["network"], None).finish()
        self.clock.advance(20)  # now past expiry
        self.refuses("PERMISSION_DENIED", "ext", "command", ["network"], None)
        self.assertEqual([], self.host.view("ext")["grants"])
        grant = self.host.grant("ext", "network")
        self.host.admit("ext", "command", ["network"], None).finish()
        self.host.revoke("ext", grant["id"])
        self.refuses("PERMISSION_DENIED", "ext", "command", ["network"], None)
        self.refuses("PERMISSION_DENIED", "ext", "command", ["terminal"], None)

    def test_revoke_does_not_stop_a_ticket_already_issued(self):
        self.enabled_extension()
        grant = self.host.grant("ext", "network")
        ticket = self.host.admit("ext", "command", ["network"], None)
        self.host.revoke("ext", grant["id"])
        ticket.finish()
        self.assertEqual("healthy", self.state())

    def test_hub_unit_needs_no_grants(self):
        self.host.sync([obs("hub", "unit", effects=("read", "process.spawn"))])
        ticket = self.host.admit("hub", "command", ["read", "process.spawn", "network"], None)
        self.assertEqual([], ticket.grants)
        ticket.finish()
        perms = {p["effect"]: p for p in self.host.view("hub")["permissions"]}
        self.assertTrue(perms["process.spawn"]["declared"])
        self.assertEqual("declared", perms["process.spawn"]["enforcement"])

    def test_inflight_states(self):
        self.host.sync([obs("hub", "unit")])
        ticket = self.host.admit("hub", "query", ["read"], None)
        self.assertEqual("starting", self.state("hub"))
        self.assertEqual(1, self.host.busy("hub"))
        ticket.finish()
        self.assertEqual("healthy", self.state("hub"))
        self.assertEqual(0, self.host.busy("hub"))
        self.assertEqual([("enabled", "starting"), ("starting", "healthy")],
                         [(d["from"], d["to"]) for t, d, s in self.types("gui.plugin.state")][1:])

    def test_a_ticket_as_context_manager_releases_without_judging(self):
        self.host.sync([obs("hub", "unit")])
        with self.host.admit("hub", "query", ["read"], None):
            self.assertEqual(1, self.host.busy("hub"))
        self.assertEqual(0, self.host.busy("hub"))
        self.assertEqual("enabled", self.state("hub"))

    def test_finish_twice_counts_once(self):
        self.host.sync([obs("hub", "unit")])
        first = self.host.admit("hub", "query", ["read"], None)
        second = self.host.admit("hub", "query", ["read"], None)
        first.finish()
        first.finish("PROCESS_EXIT")
        self.assertEqual(1, self.host.busy("hub"))
        second.finish()
        self.assertEqual(0, self.host.view("hub")["failures"]["count"])


class TestFailures(HostCase):
    def setUp(self):
        super().setUp()
        self.enabled_extension()

    def test_domain_errors_and_cancellations_are_not_failures(self):
        for code in ("PLAN_NOT_FOUND", "RUN_FAILED", "PERMISSION_DENIED", "PLUGIN_POINT_UNKNOWN", "INPUT_INVALID"):
            self.host.admit("ext", "query", ["read"], None).finish(code)
        self.host.admit("ext", "query", ["read"], None).finish("PROCESS_TIMEOUT", cancelled=True)
        self.assertEqual(0, self.host.view("ext")["failures"]["count"])
        self.assertEqual("healthy", self.state())

    def test_protocol_faults_and_output_invalid_count(self):
        for code in sorted(plugins.PROTOCOL_FAULTS | {"OUTPUT_INVALID"}):
            self.assertIn(code, plugins.FAILURE_CODES)
        self.blow("OUTPUT_INVALID")
        view = self.host.view("ext")
        self.assertEqual(1, view["failures"]["count"])
        self.assertEqual("OUTPUT_INVALID", view["failures"]["last_code"])
        self.assertEqual("degraded", view["state"])
        self.host.admit("ext", "query", ["read"], None).finish()  # success heals the state, keeps the rows
        view = self.host.view("ext")
        self.assertEqual("healthy", view["state"])
        self.assertEqual(1, view["failures"]["count"])

    def test_three_failures_in_the_window_quarantine_once(self):
        self.blow(n=2)
        self.assertEqual("degraded", self.state())
        self.blow("PLUGIN_RESPONSE_INVALID")
        self.assertEqual("quarantined", self.state())
        first = self.conn.execute("SELECT quarantined_at, quarantine_code FROM plugins").fetchone()
        self.assertEqual("PLUGIN_RESPONSE_INVALID", first["quarantine_code"])
        # a call that was already in flight fails later: recorded, no second quarantine
        self.host.sync([obs(effects=("read", "network"))])
        self.assertEqual(1, len([e for e in self.host.history("ext", 50) if e["code"] == "quarantined"]))
        self.assertEqual(1, len(self.types("gui.plugin.state")[-1:]))
        self.assertIn(("gui.plugin.state", "degraded", "quarantined"), [
            (t, d["from"], d["to"]) for t, d, s in self.events if d.get("to") == "quarantined"])
        self.assertEqual(1, len([a for a in self.audits if a[0] == "plugin.quarantine"]))
        self.assertEqual(first["quarantined_at"],
                         self.conn.execute("SELECT quarantined_at FROM plugins").fetchone()[0])

    def test_late_failure_while_quarantined_keeps_the_first_quarantine(self):
        late = [self.host.admit("ext", "query", ["read"], None) for _ in range(4)]
        for ticket in late[:3]:
            ticket.finish("PROCESS_TIMEOUT")
        stamp = self.conn.execute("SELECT quarantined_at, quarantine_code FROM plugins").fetchone()
        self.clock.advance(5)
        late[3].finish("PROTOCOL_STDOUT")
        self.assertEqual(tuple(stamp), tuple(self.conn.execute(
            "SELECT quarantined_at, quarantine_code FROM plugins").fetchone()))
        self.assertEqual(4, len([e for e in self.host.history("ext", 50) if e["kind"] == "failure"]))
        self.assertEqual(1, len([a for a in self.audits if a[0] == "plugin.quarantine"]))

    def test_failures_outside_the_window_are_not_counted(self):
        window = self.settings.plugins.quarantine_window_s
        self.blow(n=2)
        self.clock.advance(window)
        self.blow()
        self.assertEqual(1, self.host.view("ext")["failures"]["count"])
        self.assertEqual("degraded", self.state())

    def test_release_resets_the_count_and_keeps_the_history(self):
        self.blow(n=3)
        with self.assertRaises(PluginError) as caught:
            run(self.host.enable("ext"))
        self.assertEqual("PLUGIN_QUARANTINED", caught.exception.code)
        view = self.host.release("ext")
        self.assertEqual("enabled", view["state"])
        self.assertEqual(0, view["failures"]["count"])
        self.assertEqual(3, len([e for e in self.host.history("ext", 50) if e["kind"] == "failure"]))
        self.assertEqual("release", [e for e in self.host.history("ext", 50) if e["kind"] == "admin"][0]["code"])
        self.blow(n=2)
        self.assertNotEqual("quarantined", self.state())
        self.blow()
        self.assertEqual("quarantined", self.state())

    def test_release_of_a_plugin_without_failures_changes_nothing(self):
        before = self.host.history("ext", 50)
        self.assertEqual("enabled", self.host.release("ext")["state"])
        self.assertEqual(before, self.host.history("ext", 50))

    def test_quarantine_survives_a_restart(self):
        self.blow(n=3)
        again = self.make_host()
        again.sync([obs(effects=("read", "network"))])
        self.assertEqual("quarantined", again.view("ext")["state"])
        with self.assertRaises(PluginError):
            again.admit("ext", "query", ["read"], None)

    def test_quarantine_is_stronger_than_disabled(self):
        self.blow(n=3)
        run(self.host.disable("ext"))
        self.assertEqual("quarantined", self.state())
        self.host.release("ext")
        self.assertEqual("disabled", self.state())

    def test_release_of_an_unknown_plugin(self):
        with self.assertRaises(PluginError) as caught:
            self.host.release("nobody")
        self.assertEqual("NOT_FOUND", caught.exception.code)

    def test_finish_and_release_race_settles_by_lock_order(self):
        # failures recorded before the release never count afterwards, whichever thread comes first
        for _ in range(20):
            self.host.release("ext")
            tickets = [self.host.admit("ext", "query", ["read"], None) for _ in range(2)]
            threads = [threading.Thread(target=t.finish, args=("PROCESS_TIMEOUT",)) for t in tickets]
            threads.append(threading.Thread(target=self.host.release, args=("ext",)))
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(2, len([e for e in self.host.history("ext", 500) if e["kind"] == "failure"][:2]))
            quarantines = [e for e in self.host.history("ext", 500) if e["code"] == "quarantined"]
            self.assertEqual(0, len(quarantines))
        self.assertEqual(0, self.host.busy("ext"))


class TestEnableDisable(HostCase):
    def test_conformance_gate(self):
        self.host.sync([obs()])
        self.findings = [{"id": f"c{i}", "observed": f"bad {i}"} for i in range(12)]
        with self.assertRaises(PluginError) as caught:
            run(self.host.enable("ext"))
        error = caught.exception
        self.assertEqual("PLUGIN_CONFORMANCE_FAILED", error.code)
        lines = error.details["findings"].split("\n")
        self.assertEqual((12, 10, "c0: bad 0"), (error.details["count"], len(lines), lines[0]))
        self.assertEqual("compatible", self.state())
        self.findings = []
        self.assertEqual("enabled", run(self.host.enable("ext"))["state"])
        run(self.host.enable("ext"))  # cached by digest: no second check
        self.assertEqual(["ext", "ext"], self.conformance_calls)
        self.assertIn("plugin.enable", [a[0] for a in self.audits])

    def test_failing_helper_reads_check_results(self):
        results = [{"check_id": "a", "status": "ok", "observed": "fine"},
                   {"check_id": "b", "status": "fail", "observed": "broken"}]
        self.assertEqual([{"id": "b", "observed": "broken"}], plugins.failing(results))

    def test_hub_unit_enable_skips_the_gate(self):
        self.host.sync([obs("hub", "unit")])
        run(self.host.disable("hub"))
        run(self.host.enable("hub"))
        self.assertEqual([], self.conformance_calls)
        self.assertEqual("enabled", self.state("hub"))

    def test_enable_refuses_what_is_not_available(self):
        self.host.sync([obs("bad", verdict="invalid")])
        with self.assertRaises(PluginError) as caught:
            run(self.host.enable("bad"))
        self.assertEqual("PLUGIN_UNAVAILABLE", caught.exception.code)
        with self.assertRaises(PluginError) as caught:
            run(self.host.enable("nobody"))
        self.assertEqual("NOT_FOUND", caught.exception.code)

    def test_digest_changed_during_the_check_is_refused(self):
        self.host.sync([obs()])

        def conformance(observed):
            self.host.sync([obs(digest=D2)])
            return []

        self.host._conformance = conformance
        with self.assertRaises(PluginError) as caught:
            run(self.host.enable("ext"))
        self.assertEqual("PLUGIN_UNAVAILABLE", caught.exception.code)
        self.assertEqual("compatible", self.state())

    def test_disable_without_work_returns_at_once(self):
        self.enabled_extension()
        self.assertEqual({"drained": 0, "cancelled": 0}, run(self.host.disable("ext")))
        self.assertEqual("disabled", self.state())
        self.assertEqual(0, self.slept)
        self.assertEqual([], self.cancelled)
        self.assertFalse(self.host.visible("ext"))
        last = self.types("gui.plugin.state")[-1][1]
        self.assertEqual(("enabled", "disabled", "disable"), (last["from"], last["to"], last["reason"]))

    def test_disable_waits_for_runs_that_finish_in_time(self):
        self.enabled_extension()
        self.runs = {"run-1": "ext", "run-2": "ext", "run-3": "other"}
        ticks = []

        async def sleep(seconds):
            ticks.append(seconds)
            self.mono.advance(seconds)
            if len(ticks) == 4:
                self.runs.pop("run-1")
                self.runs.pop("run-2")

        self.host._sleep = sleep
        self.assertEqual({"drained": 2, "cancelled": 0}, run(self.host.disable("ext")))
        self.assertEqual(4, len(ticks))
        self.assertEqual([], self.cancelled)

    def test_disable_cancels_runs_left_after_the_timeout(self):
        self.enabled_extension()
        self.runs = {"run-1": "ext", "run-2": "ext"}
        started = self.mono.now
        self.assertEqual({"drained": 0, "cancelled": 2}, run(self.host.disable("ext")))
        self.assertEqual(["run-1", "run-2"], self.cancelled)
        self.assertGreaterEqual(self.mono.now - started, self.settings.plugins.drain_timeout_s)
        self.assertLess(self.mono.now - started, self.settings.plugins.drain_timeout_s + 1)  # cancelled runs left at once
        self.assertEqual("disabled", self.state())

    def test_disable_waits_the_grace_for_runs_that_do_not_stop(self):
        self.enabled_extension()
        self.runs = {"run-1": "ext"}
        self.finish_on_cancel = False
        started = self.mono.now
        self.assertEqual({"drained": 0, "cancelled": 1}, run(self.host.disable("ext")))
        waited = self.mono.now - started
        self.assertGreaterEqual(waited, self.settings.plugins.drain_timeout_s + self.settings.runs.cancel_grace_s)

    def test_closing_blocks_admit_while_draining(self):
        self.enabled_extension()
        self.runs = {"run-1": "ext"}
        seen = []

        async def sleep(seconds):
            self.mono.advance(seconds)
            try:
                self.host.admit("ext", "query", ["read"], None)
            except PluginError as error:
                seen.append(error.code)
            try:
                run_in_loop = self.host.lock  # enable cannot run inside the drain: the plugin is closing
                with run_in_loop:
                    self.host._enable_precheck("ext", self.host._row("ext"))
            except PluginError as error:
                seen.append(error.code)
            self.runs.clear()

        self.host._sleep = sleep
        run(self.host.disable("ext"))
        self.assertEqual(["PLUGIN_DISABLED", "PLUGIN_DISABLED"], seen)
        self.assertEqual(set(), self.host._closing)

    def test_disable_waits_for_calls_in_flight(self):
        self.enabled_extension()
        ticket = self.host.admit("ext", "query", ["read"], None)

        async def sleep(seconds):
            self.mono.advance(seconds)
            ticket.finish()

        self.host._sleep = sleep
        self.assertEqual({"drained": 0, "cancelled": 0}, run(self.host.disable("ext")))
        self.assertEqual(0, self.host.busy("ext"))

    def test_admit_after_disable_never_succeeds_across_threads(self):
        self.enabled_extension()
        closed = threading.Event()
        stop = threading.Event()
        violations, successes = [], []

        def worker():
            while not stop.is_set():
                was_closed = closed.is_set()
                try:
                    ticket = self.host.admit("ext", "query", ["read"], None)
                except PluginError:
                    continue
                successes.append(1)
                if was_closed:
                    violations.append(1)
                ticket.finish()

        async def quick_sleep(seconds):
            self.mono.advance(seconds / 1000)
            await asyncio.sleep(0)

        self.host._sleep = quick_sleep
        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        while not successes:
            pass
        result = run(self.host.disable("ext"))
        closed.set()
        for _ in range(200):
            pass
        stop.set()
        for thread in threads:
            thread.join()
        self.assertEqual([], violations)
        self.assertEqual(0, self.host.busy("ext"))
        self.assertEqual({"drained": 0, "cancelled": 0}, result)
        self.refuses("PLUGIN_DISABLED", "ext", "query", ["read"], None)


class TestGrantRules(HostCase):
    def setUp(self):
        super().setUp()
        self.host.sync([obs(effects=("read", "network", "terminal"))])

    def refuses_grant(self, code, *args, **kw):
        with self.assertRaises(PluginError) as caught:
            self.host.grant("ext", *args, **kw)
        self.assertEqual(code, caught.exception.code)

    def test_capability_must_be_a_declared_grantable_effect(self):
        self.refuses_grant("INPUT_INVALID", "read")
        self.refuses_grant("INPUT_INVALID", "terminal")
        self.refuses_grant("INPUT_INVALID", "process.spawn")  # not declared
        self.refuses_grant("INPUT_INVALID", "bogus")
        self.assertEqual("network", self.host.grant("ext", "network")["capability"])

    def test_expiry_rules(self):
        now = self.clock.now
        iso = self.host._iso
        self.refuses_grant("INPUT_INVALID", "network", None, iso(now - 5))
        self.refuses_grant("INPUT_INVALID", "network", None, iso(now + 366 * 86400))
        self.refuses_grant("INPUT_INVALID", "network", None, "tomorrow")
        self.refuses_grant("INPUT_INVALID", "network", None, 12)
        ok = self.host.grant("ext", "network", "p", iso(now + 365 * 86400))
        self.assertEqual(iso(now + 365 * 86400), ok["expires_at"])
        self.assertRegex(ok["id"], r"^grant-[0-9a-f]{32}$")
        self.assertEqual("browser", ok["granted_by"])
        self.assertEqual("cli", self.host.grant("ext", "network", granted_by="cli")["granted_by"])

    def test_grant_on_a_stale_digest_is_refused(self):
        self.refuses_grant("PLUGIN_UNAVAILABLE", "network", digest=D3)
        self.host.sync([obs(effects=("read", "network", "terminal"), digest=D2)])
        self.refuses_grant("PLUGIN_UNAVAILABLE", "network", digest=D1)
        grant = self.host.grant("ext", "network", digest=D2)
        self.assertEqual(D2, grant["manifest_digest"])

    def test_grant_refused_in_unavailable_states(self):
        self.host.sync([obs(effects=("read", "network", "terminal"), verdict="invalid")])
        self.refuses_grant("PLUGIN_UNAVAILABLE", "network")
        self.host.sync([obs(effects=("read", "network", "terminal"))])
        run(self.host.enable("ext"))
        self.blow(n=3)
        self.refuses_grant("PLUGIN_QUARANTINED", "network")
        self.host.release("ext")
        run(self.host.disable("ext"))
        self.refuses_grant("PLUGIN_UNAVAILABLE", "network")
        with self.assertRaises(PluginError) as caught:
            self.host.grant("nobody", "network")
        self.assertEqual("NOT_FOUND", caught.exception.code)

    def test_hub_unit_takes_no_grants(self):
        self.host.sync([obs("hub", "unit", effects=("read", "network"))])
        with self.assertRaises(PluginError) as caught:
            self.host.grant("hub", "network")
        self.assertEqual("INPUT_INVALID", caught.exception.code)

    def test_revoke(self):
        grant = self.host.grant("ext", "network")
        with self.assertRaises(PluginError) as caught:
            self.host.revoke("ext", "grant-" + "0" * 32)
        self.assertEqual("NOT_FOUND", caught.exception.code)
        self.host.revoke("ext", grant["id"])
        self.host.revoke("ext", grant["id"])  # idempotent
        self.assertEqual([], self.host.view("ext")["grants"])
        self.assertEqual(1, len([d for t, d, s in self.types("gui.plugin.grant") if d["action"] == "revoked"]))
        self.assertEqual(["granted", "revoked"], [d["action"] for t, d, s in self.types("gui.plugin.grant")])
        self.assertEqual(["plugin.grant", "plugin.revoke"], [a[0] for a in self.audits])

    def test_view_filters_grants_by_project(self):
        every = self.host.grant("ext", "network", None)
        one = self.host.grant("ext", "network", "p1")
        self.host.grant("ext", "network", "p2")
        ids = lambda project: sorted(g["id"] for g in self.host.view("ext", project)["grants"])
        self.assertEqual([every["id"]], ids(None))
        self.assertEqual(sorted([every["id"], one["id"]]), ids("p1"))
        self.assertEqual(2, len(self.host.views("p1")[0]["grants"]))


class TestAtomicity(HostCase):
    def rows(self):
        return {table: self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("plugins", "plugin_events", "grants")}

    def test_error_in_the_middle_of_a_grant_leaves_nothing(self):
        self.enabled_extension()
        before = self.rows()
        original = self.host._history

        def boom(*args, **kw):
            raise RuntimeError("disk")

        self.host._history = boom
        with self.assertRaises(RuntimeError):
            self.host.grant("ext", "network")
        self.host._history = original
        self.assertEqual(before, self.rows())
        self.assertFalse(self.conn.in_transaction)
        self.assertEqual("enabled", self.state())
        self.host.grant("ext", "network")  # the lock was released and the connection is usable

    def test_error_in_the_middle_of_sync_leaves_nothing_and_the_old_catalog(self):
        self.enabled_extension()
        self.host.grant("ext", "network")
        before = self.rows()

        def boom(*args, **kw):
            raise RuntimeError("disk")

        self.host._history = boom
        with self.assertRaises(RuntimeError):
            self.host.sync([obs(effects=("read", "network", "process.spawn"), digest=D2), obs("new", "unit")])
        del self.host._history
        self.assertEqual(before, self.rows())
        self.assertEqual(D1, self.host._observed["ext"].digest)
        self.assertEqual(1, len(self.host.view("ext")["grants"]))

    def test_error_in_the_middle_of_a_failure_keeps_inflight_consistent(self):
        self.enabled_extension()
        before = self.rows()
        ticket = self.host.admit("ext", "query", ["read"], None)

        def boom(*args, **kw):
            raise RuntimeError("disk")

        self.host._history = boom
        with self.assertRaises(RuntimeError):
            ticket.finish("PROCESS_TIMEOUT")
        del self.host._history
        self.assertEqual(before, self.rows())
        self.assertEqual(0, self.host.busy("ext"))

    def test_events_are_sent_after_the_commit(self):
        seen = []

        def publish(type_, data, subject):
            seen.append((type_, self.conn.in_transaction,
                         self.conn.execute("SELECT COUNT(*) FROM plugins").fetchone()[0]))

        host = plugins.PluginHost(self.conn, threading.RLock(), self.settings, publish, lambda *a: None, lambda o: [],
                                  lambda r: None, lambda o: [], clock=self.clock)
        host.sync([obs("hub", "unit")])
        self.assertEqual([("gui.plugin.state", False, 1)], seen)

    def test_a_failing_subscriber_does_not_undo_the_change(self):
        def publish(*args):
            raise RuntimeError("subscriber")

        host = plugins.PluginHost(self.conn, threading.RLock(), self.settings, publish, lambda *a: 1 / 0,
                                  lambda o: [], lambda r: None, lambda o: [], clock=self.clock)
        host.sync([obs("hub", "unit")])
        self.assertEqual("enabled", host.view("hub")["state"])


class TestHistory(HostCase):
    def test_limit_trim_and_order(self):
        self.enabled_extension()
        limit = self.settings.plugins.history_limit
        for _ in range(limit + 30):
            self.host.admit("ext", "query", ["read"], None).finish("PLAN_NOT_FOUND")
        with self.host._mutation():
            for i in range(limit + 30):
                self.host._history("ext", "admin", "note", f"n{i}")
        entries = self.host.history("ext", 5000)
        self.assertEqual(limit, len(entries))
        self.assertEqual("n%d" % (limit + 29), entries[0]["detail"])
        self.assertEqual(sorted((e["id"] for e in entries), reverse=True), [e["id"] for e in entries])
        self.assertEqual(3, len(self.host.history("ext", 3)))
        self.assertEqual(1, len(self.host.history("ext", 0)))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM plugin_events WHERE plugin = 'ext'").fetchone()[0],
                         limit)

    def test_history_is_per_plugin(self):
        self.host.sync([obs("a", "unit"), obs("b", "unit")])
        with self.host._mutation():
            for i in range(self.settings.plugins.history_limit + 5):
                self.host._history("a", "admin", "note", "x")
        self.assertEqual(1, len(self.host.history("b")))

    def test_detail_is_redacted_and_cut(self):
        self.enabled_extension()
        secret = "ghp_" + "a" * 36
        self.host.admit("ext", "query", ["read"], None).finish("PROCESS_EXIT", f"token {secret}\x1b[31m " + "z" * 900)
        detail = self.host.history("ext")[1]["detail"]  # [0] is the state change to degraded
        self.assertNotIn(secret, detail)
        self.assertNotIn("\x1b", detail)
        self.assertLessEqual(len(detail), 500)

    def test_unknown_plugin(self):
        with self.assertRaises(PluginError) as caught:
            self.host.history("nobody")
        self.assertEqual("NOT_FOUND", caught.exception.code)


class TestViews(HostCase):
    def walk(self, node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from self.walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from self.walk(value)
        else:
            yield node

    def assertValid(self, view):
        self.assertEqual([], contracts.validate(view, "trust"), view)
        leaves = list(self.walk(view))
        self.assertNotIn("enforced", leaves)
        self.assertFalse([x for x in leaves if isinstance(x, float)])
        json.dumps(view)

    def test_every_state_is_a_valid_trust_document(self):
        self.host.sync([obs("hub", "unit", effects=("read", "process.spawn")), obs("ext", effects=("read", "network")),
                        obs("bad", verdict="invalid"),
                        obs("inc", verdict="incompatible",
                            compatibility={"protocol_ok": False, "missing_contracts": [
                                {"id": "urn:swissknifeman:gui:view-data", "version": "v9"}]}),
                        obs("gone")])
        seen = set()
        run(self.host.enable("ext"))
        self.host.grant("ext", "network", "p1", "2027-02-01T00:00:00Z")
        ticket = self.host.admit("ext", "query", ["read"], None)
        seen.add(self.state())
        ticket.finish()
        seen.add(self.state())
        self.blow("PLUGIN_TIMEOUT")
        seen.add(self.state())
        self.blow(n=2)
        seen.add(self.state())
        self.host.sync([obs("hub", "unit", effects=("read", "process.spawn")), obs("ext", effects=("read", "network")),
                        obs("bad", verdict="invalid"), obs("inc", verdict="incompatible")])
        seen.add(self.state("gone"))
        self.host.release("ext")
        run(self.host.disable("hub"))
        self.host.sync([obs("hub", "unit", effects=("read", "process.spawn")),
                        obs("ext", effects=("read", "network", "secrets.read"), digest=D2),
                        obs("bad", verdict="invalid"), obs("inc", verdict="incompatible")])
        seen.add(self.state())
        seen.update(self.state(p) for p in ("hub", "bad", "inc"))
        self.assertLessEqual({"starting", "healthy", "degraded", "quarantined", "discovered", "disabled", "invalid",
                              "incompatible", "permission_denied"}, seen)
        for view in self.host.views("p1"):
            self.assertValid(view)

    def test_permissions_list_every_effect_with_its_status(self):
        self.host.sync([obs("ext", effects=("read", "network"))])
        perms = {p["effect"]: p for p in self.host.view("ext")["permissions"]}
        self.assertEqual(list(plugins.EFFECTS), [p["effect"] for p in self.host.view("ext")["permissions"]])
        self.assertEqual((True, "declared"), (perms["read"]["declared"], perms["read"]["enforcement"]))
        self.assertEqual((True, "advisory"), (perms["network"]["declared"], perms["network"]["enforcement"]))
        self.assertEqual((False, "declared"), (perms["plan.write"]["declared"], perms["plan.write"]["enforcement"]))

    def test_unknown_plugin(self):
        with self.assertRaises(PluginError) as caught:
            self.host.view("nobody")
        self.assertEqual("NOT_FOUND", caught.exception.code)

    def test_failures_report_the_window(self):
        self.enabled_extension()
        self.assertEqual({"count": 0, "window_s": self.settings.plugins.quarantine_window_s},
                         self.host.view("ext")["failures"])


class TestErrors(unittest.TestCase):
    def test_new_codes_work_before_they_are_registered(self):
        error = PluginError("PLUGIN_DISABLED", "off", details={"plugin": "x"})
        self.assertEqual(("PLUGIN_DISABLED", "off", {"plugin": "x"}), (error.code, error.message, error.details))
        self.assertIn("PLUGIN_DISABLED", str(error))

    def test_registered_codes_build_envelopes(self):
        envelope = PluginError("PLUGIN_QUARANTINED", "q").envelope("c1")
        self.assertEqual("PLUGIN_QUARANTINED", envelope["error"]["code"])


class TestObserve(unittest.TestCase):
    def test_digest_effects_and_rejections_from_a_catalog(self):
        from gui import backend
        from gui.catalog import sources

        fixtures = Path(__file__).resolve().parent / "fixtures" / "units"
        roots = [fixtures / "exec-demo" / "xdemo", fixtures / "valid-one" / "demo"]
        collected = sources.Collected(sources=sources.unit_sources(roots), problems=[])
        catalog = backend.build_catalog(collected)
        found = plugins.observe(catalog)
        self.assertTrue(found)
        self.assertEqual(sorted(entry.id for entry in found), [entry.id for entry in found])
        for entry in found:
            self.assertEqual("accepted", entry.verdict)
            self.assertEqual("unit", entry.source)
            owner = catalog.owners[entry.id]
            contribution = next(c["digest"] for c in catalog.document["contributions"] if c["owner"] == entry.id)
            self.assertEqual(digest_json({"contribution": contribution, "handler": plugins._handler_digest(owner.handler)}),
                             entry.digest)
            commands = {effect for command in owner.document.get("commands", ()) for effect in command["effects"]}
            self.assertLessEqual(commands, set(entry.effects))
            self.assertEqual(entry.effects, tuple(sorted(entry.effects, key=plugins.EFFECTS.index)))
        self.assertEqual(found, plugins.PluginHost.observe(None, catalog))

    def test_rejected_owners_are_observed_with_their_verdict(self):
        from gui import backend
        from gui.catalog import sources

        fixtures = Path(__file__).resolve().parent / "fixtures" / "units"
        roots = sorted((fixtures / "conflict-id").iterdir())
        found = plugins.observe(backend.build_catalog(sources.Collected(sources=sources.unit_sources(roots),
                                                                         problems=[])))
        self.assertEqual([("demo", "invalid", ())], [(e.id, e.verdict, e.effects) for e in found])
        self.assertEqual({"protocol_ok": True, "missing_contracts": []}, found[0].compatibility)
        self.assertTrue(found[0].digest.startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
