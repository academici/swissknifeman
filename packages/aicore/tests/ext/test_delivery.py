"""aicore.ext.delivery: subscriptions, cursors, one deliverer, dead letters, replay, status, emit modes.

Subscribers are the scripts in ``fixtures/subscribers`` run with ``sys.executable``. Every test delivers
synchronously except the background one, which waits for the deliverer it started.
"""
import io
import json
import os
import sys
import time
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from aicore.ext import delivery, events, journal, process
from aicore.ext.errors import CODES, ExtError

from tests.ext.support import SUBSCRIBERS, TempCase, run_cli


def command(script, *args):
    return [sys.executable, str(SUBSCRIBERS / script), *args]


def toml_list(items):
    return "[" + ", ".join(json.dumps(str(item)) for item in items) + "]"


class DeliveryCase(TempCase):
    def setUp(self):
        super().setUp()
        empty = self.tmp / "no-units"
        empty.mkdir()
        self.env["SKM_UNITS_PATH"] = str(empty)  # no module subscriptions unless a test asks for them
        self.out = self.tmp / "out.jsonl"
        self.config = ""

    # configuration -------------------------------------------------------------------------------------------
    def subscribe(self, name, run, on=("demo.*",), **extra):
        lines = [f"[aicore.subscriptions.{json.dumps(name)}]", f"on = {toml_list(on)}", f"run = {toml_list(run)}"]
        lines += [f"{key} = {json.dumps(value) if not isinstance(value, (list, tuple)) else toml_list(value)}"
                  for key, value in extra.items()]
        self.machine("\n".join(lines) + "\n")

    def machine(self, text):
        self.config += text
        path = self.tmp / "skm" / "config" / "config.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("schema_version = 1\n" + self.config, encoding="utf-8")

    def project_file(self, text):
        (self.project / ".swissknifeman" / "config.toml").write_text("schema_version = 1\n" + text, encoding="utf-8")

    # actions -------------------------------------------------------------------------------------------------
    def emit(self, type="demo.thing.happened", delivery_mode="off", **kwargs):
        return events.emit(type, source=type.split(".")[0], project=self.project, delivery=delivery_mode,
                           env=self.env, home=self.home, **kwargs)

    def deliver(self, **kwargs):
        return delivery.deliver(self.journal, project=self.project, env=self.env, home=self.home, **kwargs)

    def replay(self, name, **kwargs):
        return delivery.replay(self.journal, name, project=self.project, env=self.env, home=self.home, **kwargs)

    def status(self):
        return delivery.delivery_status(self.journal, project=self.project, env=self.env, home=self.home)

    def row(self, name):
        return [item for item in self.status()["subscriptions"] if item["id"] == name][0]

    # observations --------------------------------------------------------------------------------------------
    def got(self, path=None):
        target = path or self.out
        if not target.exists():
            return []
        return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]

    def cursors(self):
        return json.loads(delivery.cursors_path(self.journal).read_text(encoding="utf-8"))["subscriptions"]

    def log(self):
        return delivery._read_records(delivery.deliveries_path(self.journal))

    def dead_letters(self):
        return delivery._read_records(delivery.dead_letter_path(self.journal))


class TestSubscriptions(DeliveryCase):
    def test_delivery_by_pattern(self):
        self.subscribe("mine", command("ok.py", str(self.out)), on=["demo.thing.*"])
        first = self.emit(delivery_mode="sync")
        self.emit("demo.other.done", delivery_mode="sync")
        third = self.emit(delivery_mode="sync")
        self.assertEqual([item["id"] for item in self.got()], [first.id, third.id])
        self.assertEqual(self.cursors()["mine"]["offset"], journal.size(self.journal))
        self.assertEqual(self.row("mine")["lag"], 0)

    def test_order_is_journal_order(self):
        self.subscribe("mine", command("ok.py", str(self.out)))
        sent = [self.emit(delivery_mode="sync")]
        sent += [self.emit(subject=str(index)) for index in range(5)]
        self.assertEqual(self.row("mine")["lag"], 5)
        report = self.deliver()
        self.assertEqual((report.delivered, report.ok), (5, True))
        self.assertEqual([item["id"] for item in self.got()], [event.id for event in sent])

    def test_subscriber_environment_and_cwd(self):
        self.env["AWS_SECRET_ACCESS_KEY"] = "SENTINEL"
        self.subscribe("mine", command("ok.py", str(self.out)))
        self.emit(delivery_mode="sync")
        seen = self.got()[0]
        self.assertEqual((seen["subscription"], seen["attempt"]), ("mine", "1"))
        self.assertEqual((seen["project"], seen["cwd"]), (str(self.project), os.path.realpath(self.project)))
        self.assertEqual(seen["journal"], str(self.journal))
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", seen["names"])
        self.assertIn("SKM_EXT_PROTOCOL", seen["names"])

    def test_projects_filter(self):
        other = self.tmp / "other"
        self.subscribe("there", command("ok.py", str(self.tmp / "there.jsonl")), projects=[str(other)])
        self.subscribe("here", command("ok.py", str(self.out)), projects=[str(self.project)])
        self.emit(delivery_mode="sync")
        self.assertEqual(len(self.got()), 1)
        self.assertEqual(self.got(self.tmp / "there.jsonl"), [])
        rows = {item["id"]: item for item in self.status()["subscriptions"]}
        self.assertEqual((rows["here"]["active"], rows["there"]["active"]), (True, False))

    def test_project_can_switch_off_a_machine_subscription(self):
        self.subscribe("mine", command("ok.py", str(self.out)))
        self.project_file('[aicore.subscriptions.mine]\nenabled = false\n')
        self.emit(delivery_mode="sync")
        self.assertEqual(self.got(), [])
        self.assertFalse(self.row("mine")["enabled"])

    def test_module_subscription_runs_and_switches_off_by_full_id(self):
        from tests.ext.support import UNITS
        self.env["SKM_UNITS_PATH"] = str(UNITS)
        self.env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")  # demo-sub starts through /usr/bin/env
        self.emit(delivery_mode="sync")
        self.assertEqual([(item["subscription"], item["outcome"]) for item in self.log()], [("demo:log", "ok")])
        self.assertEqual(self.row("demo:log")["origin"], "unit")
        self.machine('[aicore.subscriptions."demo:log"]\nenabled = false\n')
        self.emit(delivery_mode="sync")
        self.assertEqual(len(self.log()), 1)
        self.assertFalse(self.row("demo:log")["enabled"])

    def test_configuration_cannot_replace_the_command_of_a_module_subscription(self):
        from tests.ext.support import UNITS
        self.env["SKM_UNITS_PATH"] = str(UNITS)
        self.subscribe("demo:log", command("ok.py", str(self.out)), timeout_seconds=5)
        loaded = delivery._settings.load(self.project, env=self.env, home=self.home)
        found, problems = delivery.resolve_subscriptions(loaded, delivery._units.discover_units(self.env))
        subscription = {item.id: item for item in found}["demo:log"]
        self.assertTrue(subscription.run[0].endswith("demo-sub"))
        self.assertEqual(subscription.timeout_seconds, 5)
        self.assertEqual([item["code"] for item in problems], ["SUBSCRIPTION_INVALID"])

    def test_invalid_configuration_entries_are_problems(self):
        self.machine('[aicore.subscriptions.both]\non = ["demo.*"]\nrun = ["x"]\nplugin = "p"\n'
                     '[aicore.subscriptions.none]\non = ["demo.*"]\n'
                     '[aicore.subscriptions.patternless]\nrun = ["x"]\n'
                     '[aicore.subscriptions."gone:log"]\nenabled = false\n'
                     '[aicore.subscriptions.relative]\non = ["demo.*"]\nrun = ["x"]\nprojects = ["here"]\n')
        status = self.status()
        invalid = sorted(item["subscription"] for item in status["problems"] if item["code"] == "SUBSCRIPTION_INVALID")
        self.assertEqual(invalid, ["both", "none", "patternless", "relative"])
        self.assertEqual([item["id"] for item in status["subscriptions"]], ["relative"])
        self.assertFalse(status["subscriptions"][0]["active"])

    def test_plugin_subscription_is_unavailable_and_keeps_no_cursor(self):
        self.machine('[aicore.subscriptions.viaplugin]\non = ["demo.*"]\nplugin = "tool"\n')
        self.emit()
        report = self.deliver()
        self.assertEqual([item["code"] for item in report.problems], ["PLUGIN_UNAVAILABLE"])
        self.assertFalse(delivery.cursors_path(self.journal).exists())
        self.assertIn("PLUGIN_UNAVAILABLE", [item["code"] for item in self.status()["problems"]])

    def test_match(self):
        subscription = delivery.Subscription("x", ("plan.*.closed", "demo.thing.happened"), ("x",), None, (), 1,
                                             True, "config", None)
        self.assertTrue(delivery.match(subscription, "plan.item.closed"))
        self.assertTrue(delivery.match(subscription, "demo.thing.happened"))
        self.assertFalse(delivery.match(subscription, "Demo.thing.happened"))
        self.assertFalse(delivery.match(subscription, "plan.item.opened"))

    def test_codes_are_registered(self):
        for code in ("SUBSCRIPTION_INVALID", "SUBSCRIPTION_UNKNOWN", "SUBSCRIPTION_INACTIVE", "PLUGIN_UNAVAILABLE",
                     "DELIVERY_LOCKED", "DELIVERY_IO", "DELIVERY_SPAWN", "DELIVERY_CURSORS_INVALID",
                     "JOURNAL_RESET"):
            self.assertIn(code, CODES)


class TestFailures(DeliveryCase):
    def test_failed_event_blocks_the_subscription_until_the_next_run(self):
        self.subscribe("mine", command("fail_once.py", str(self.out)))
        first = self.emit(delivery_mode="sync")
        self.assertEqual(self.got(), [])
        cursor = self.cursors()["mine"]
        self.assertEqual((cursor["offset"], cursor["pending"]["attempts"], cursor["pending"]["last_error"]),
                         (first.offset, 1, "PROCESS_EXIT"))
        self.assertEqual(self.row("mine")["lag"], 1)
        second = self.emit()
        report = self.deliver()  # first succeeds on attempt 2, second fails once and stops the subscription
        self.assertEqual((report.delivered, report.failed, report.ok), (1, 1, False))
        self.assertEqual([(item["id"], item["attempt"]) for item in self.got()], [(first.id, "2")])
        self.assertEqual(self.cursors()["mine"]["offset"], second.offset)
        report = self.deliver()
        self.assertEqual([item["id"] for item in self.got()], [first.id, second.id])
        failed = [item for item in self.log() if item["outcome"] == "failed"]
        self.assertEqual({item["code"] for item in failed}, {"PROCESS_EXIT"})
        self.assertEqual(failed[0]["exit"], 3)
        self.assertIn("failing once on purpose", failed[0]["stderr_tail"])

    def test_dead_letter_after_max_attempts_then_the_cursor_moves_on(self):
        self.subscribe("mine", command("always_fail.py"))
        poisoned = self.emit(delivery_mode="sync")
        self.deliver()
        self.assertEqual(self.cursors()["mine"]["pending"]["attempts"], 2)
        self.assertEqual(self.dead_letters(), [])
        report = self.deliver()
        self.assertEqual(report.dead_lettered, 1)
        letter = self.dead_letters()[0]
        self.assertEqual((letter["subscription"], letter["event_id"], letter["offset"], letter["attempts"],
                          letter["last_error"]), ("mine", poisoned.id, poisoned.offset, 3, "PROCESS_EXIT"))
        cursor = self.cursors()["mine"]
        self.assertEqual((cursor["offset"], cursor["pending"], cursor["last_id"]),
                         (journal.size(self.journal), None, poisoned.id))
        self.assertEqual(self.row("mine")["dead_letters"], 1)
        nxt = self.emit(delivery_mode="sync")  # the queue is not blocked by the poisoned event
        self.assertEqual(self.log()[-1]["event_id"], nxt.id)

    def test_max_attempts_comes_from_the_configuration(self):
        self.machine("[aicore.events]\nmax_attempts = 1\n")
        self.subscribe("mine", command("always_fail.py"))
        self.emit(delivery_mode="sync")
        self.assertEqual(len(self.dead_letters()), 1)

    def test_replay_event_delivers_a_dead_letter(self):
        self.machine("[aicore.events]\nmax_attempts = 1\n")
        self.subscribe("mine", command("always_fail.py"))
        poisoned = self.emit(delivery_mode="sync")
        self.assertEqual(self.row("mine")["dead_letters"], 1)
        self.config = "[aicore.events]\nmax_attempts = 1\n"  # the subscriber was fixed
        self.subscribe("mine", command("ok.py", str(self.out)))
        report = self.replay("mine", event_id=poisoned.id)
        self.assertEqual((report.delivered, report.ok), (1, True))
        self.assertEqual([item["id"] for item in self.got()], [poisoned.id])
        self.assertEqual(self.row("mine")["dead_letters"], 0)
        self.assertTrue(self.log()[-1]["replay"])

    def test_redelivery_carries_the_same_id(self):
        self.subscribe("mine", command("ok.py", str(self.out)))
        self.emit(delivery_mode="sync")
        before = delivery.cursors_path(self.journal).read_bytes()
        event = self.emit()
        self.deliver()
        delivery.cursors_path(self.journal).write_bytes(before)  # a crash before the cursor write
        self.deliver()
        repeats = [item for item in self.got() if item["id"] == event.id]
        self.assertEqual([item["repeat"] for item in repeats], [False, True])

    def test_text_on_stdout_is_a_protocol_failure(self):
        self.subscribe("mine", command("noisy_stdout.py"))
        self.emit(delivery_mode="sync")
        self.assertEqual(self.log()[-1]["code"], "PROTOCOL_STDOUT")
        self.assertIsNotNone(self.cursors()["mine"]["pending"])

    def test_status_answers(self):
        self.subscribe("skips", command("ok.py", str(self.out), "skipped"))
        self.subscribe("odd", command("ok.py", str(self.tmp / "odd.jsonl"), "maybe"))
        self.emit(delivery_mode="sync")
        outcomes = {item["subscription"]: (item["outcome"], item["code"]) for item in self.log()}
        self.assertEqual(outcomes, {"skips": ("skipped", None), "odd": ("failed", "PROTOCOL_STDOUT")})
        self.assertIsNone(self.cursors()["skips"]["pending"])

    def test_source_is_not_blocked_by_a_slow_subscriber(self):
        self.subscribe("slow", command("slow.py", "30"), timeout_seconds=1)
        started = time.monotonic()
        event = self.emit(delivery_mode="sync")
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 1 + process.GRACE_S + 1.5)
        self.assertIsNotNone(event)
        found, _ = events.read_events(self.project)
        self.assertEqual([item.id for item in found], [event.id])
        self.assertEqual(self.log()[-1]["code"], "PROCESS_TIMEOUT")


class TestCursors(DeliveryCase):
    def test_new_subscription_starts_at_the_trigger_or_the_end(self):
        self.emit()
        self.subscribe("mine", command("ok.py", str(self.out)))
        trigger = self.emit(delivery_mode="sync")
        self.assertEqual([item["id"] for item in self.got()], [trigger.id])
        self.subscribe("late", command("ok.py", str(self.tmp / "late.jsonl")))
        report = self.deliver()  # no trigger: the new subscription starts at the end
        self.assertEqual(report.attempts, [])
        self.assertEqual(self.cursors()["late"]["offset"], journal.size(self.journal))
        later = self.emit()
        self.deliver()
        self.assertEqual([item["id"] for item in self.got(self.tmp / "late.jsonl")], [later.id])

    def test_truncated_journal_resets_the_cursor(self):
        self.subscribe("mine", command("ok.py", str(self.out)))
        self.emit(delivery_mode="sync")
        self.emit(delivery_mode="sync")
        path = journal.journal_path(self.journal)
        path.write_bytes(path.read_bytes().splitlines(keepends=True)[0])  # cut by hand
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            report = self.deliver()
        self.assertEqual((report.resets, report.attempts), (1, []))
        self.assertIn("JOURNAL_RESET", stderr.getvalue())
        self.assertEqual(self.cursors()["mine"]["offset"], journal.size(self.journal))
        self.assertEqual(self.status()["resets"], 1)
        self.assertEqual([item["code"] for item in self.log()][-1], "JOURNAL_RESET")

    def test_replaced_journal_of_the_same_size_resets_the_cursor(self):
        self.subscribe("mine", command("ok.py", str(self.out)))
        self.emit(delivery_mode="sync")
        path = journal.journal_path(self.journal)
        size = path.stat().st_size
        path.unlink()
        self.emit()
        self.assertEqual(journal.size(self.journal), size)
        with redirect_stderr(io.StringIO()):
            report = self.deliver()
        self.assertEqual((report.resets, len(self.got())), (1, 1))

    def test_replay_from_start_and_from_event(self):
        self.subscribe("mine", command("ok.py", str(self.out)))
        sent = [self.emit(delivery_mode="sync"), self.emit(delivery_mode="sync"), self.emit(delivery_mode="sync")]
        self.replay("mine", from_start=True)
        self.assertEqual([item["id"] for item in self.got()][3:], [event.id for event in sent])
        self.replay("mine", from_event=sent[1].id)
        self.assertEqual([item["id"] for item in self.got()][6:], [event.id for event in sent[1:]])

    def test_replay_refusals(self):
        self.subscribe("mine", command("ok.py", str(self.out)), enabled=False)
        self.emit()
        for kwargs, code in (({"from_start": True}, "SUBSCRIPTION_INACTIVE"),
                             ({"event_id": "0" * 32}, "SUBSCRIPTION_INACTIVE")):
            with self.assertRaises(ExtError) as caught:
                self.replay("mine", **kwargs)
            self.assertEqual(caught.exception.code, code)
        with self.assertRaises(ExtError) as caught:
            self.replay("unknown", from_start=True)
        self.assertEqual(caught.exception.code, "SUBSCRIPTION_UNKNOWN")
        self.config = ""
        self.subscribe("mine", command("ok.py", str(self.out)))
        with self.assertRaises(ExtError) as caught:
            self.replay("mine", from_event="0" * 32)
        self.assertEqual(caught.exception.code, "EVENT_NOT_FOUND")
        with self.assertRaises(ValueError):
            self.replay("mine")
        with self.assertRaises(ValueError):
            self.replay("mine", from_start=True, event_id="0" * 32)

    def test_broken_lines_are_skipped_and_counted(self):
        self.subscribe("mine", command("ok.py", str(self.out)))
        self.emit(delivery_mode="sync")
        with open(journal.journal_path(self.journal), "ab") as handle:
            handle.write(b"not json\n")
        later = self.emit()
        with redirect_stderr(io.StringIO()) as stderr:
            self.deliver()
        self.assertEqual(self.got()[-1]["id"], later.id)
        self.assertIn("EVENT_MALFORMED", stderr.getvalue())
        self.assertEqual(self.status()["malformed"], 1)

    def test_too_long_line_is_skipped(self):
        self.subscribe("mine", command("ok.py", str(self.out)))
        self.emit(delivery_mode="sync")
        with open(journal.journal_path(self.journal), "ab") as handle:
            handle.write(b"x" * (journal.MAX_LINE + 10) + b"\n")
        later = self.emit()
        with redirect_stderr(io.StringIO()):
            self.deliver()
        self.assertEqual(self.got()[-1]["id"], later.id)
        self.assertEqual(self.cursors()["mine"]["offset"], journal.size(self.journal))

    def test_damaged_cursor_file_starts_again(self):
        self.subscribe("mine", command("ok.py", str(self.out)))
        self.emit(delivery_mode="sync")
        delivery.cursors_path(self.journal).write_text("{broken", encoding="utf-8")
        with redirect_stderr(io.StringIO()) as stderr:
            trigger = self.emit(delivery_mode="sync")
        self.assertIn("DELIVERY_CURSORS_INVALID", stderr.getvalue())
        self.assertEqual(self.got()[-1]["id"], trigger.id)
        self.assertEqual(len(self.got()), 2)

    def test_cursor_writers_need_the_held_lock(self):
        with self.assertRaises(RuntimeError):
            delivery.save_cursors(None, {})
        with self.assertRaises(RuntimeError):
            delivery.append_dead_letter("lock", {})
        with delivery._deliver_lock(self.journal, wait=False) as lock:
            delivery.save_cursors(lock, {})
        with self.assertRaises(RuntimeError):
            delivery.save_cursors(lock, {})  # released
        self.assertEqual(oct(delivery.cursors_path(self.journal).stat().st_mode & 0o777), "0o600")


class TestOneDeliverer(DeliveryCase):
    def test_second_deliverer_gives_way(self):
        self.subscribe("mine", command("ok.py", str(self.out)))
        self.emit(delivery_mode="sync")
        self.emit()
        with delivery._deliver_lock(self.journal, wait=False) as lock:
            self.assertIsNotNone(lock)
            report = self.deliver()
            self.assertEqual((report.busy, report.attempts), (True, []))
            with self.assertRaises(ExtError) as caught:
                self.deliver(wait=0.2)
            self.assertEqual(caught.exception.code, "DELIVERY_LOCKED")
        self.assertEqual(delivery.WAIT_S, 30.0)
        report = self.deliver()
        self.assertEqual((report.busy, report.delivered), (False, 1))

    def test_growth_during_a_pass_is_picked_up(self):
        self.subscribe("mine", command("chain.py", str(self.out)))
        first = self.emit(delivery_mode="sync")
        subjects = [item["subject"] for item in self.got()]
        self.assertEqual(subjects, [None, "chained"])
        self.assertEqual(self.got()[0]["id"], first.id)
        self.assertEqual(self.cursors()["mine"]["offset"], journal.size(self.journal))


class TestEmitModes(DeliveryCase):
    def test_off_only_journals(self):
        self.subscribe("mine", command("ok.py", str(self.out)))
        self.emit()
        self.assertEqual(self.got(), [])
        self.assertFalse(delivery.cursors_path(self.journal).exists())

    def test_mode_from_the_configuration(self):
        self.env.pop("SKM_AICORE_EVENTS__DELIVERY")
        self.machine('[aicore.events]\ndelivery = "sync"\n')
        self.subscribe("mine", command("ok.py", str(self.out)))
        self.emit(delivery_mode=None)
        self.assertEqual(len(self.got()), 1)

    def test_invalid_configuration_keeps_the_event(self):
        self.env.pop("SKM_AICORE_EVENTS__DELIVERY")
        self.project_file('[aicore.subscriptions.evil]\nrun = ["/bin/sh"]\n')
        with redirect_stderr(io.StringIO()) as stderr:
            event = self.emit(delivery_mode=None)
        self.assertIsNotNone(event)
        self.assertIn("CONFIG_INVALID", stderr.getvalue())
        self.assertEqual(self.log()[-1]["code"], "CONFIG_INVALID")
        with self.assertRaises(ExtError) as caught:
            self.emit(delivery_mode=None, strict=True)
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")
        found, _ = events.read_events(self.project)
        self.assertEqual(len(found), 2)

    def test_failing_spawn_is_a_warning(self):
        real = delivery.subprocess.Popen

        def refuse(*args, **kwargs):
            raise OSError(2, "No such file or directory")

        delivery.subprocess.Popen = refuse
        self.addCleanup(setattr, delivery.subprocess, "Popen", real)
        with redirect_stderr(io.StringIO()) as stderr:
            self.assertIsNotNone(self.emit(delivery_mode="background"))
        self.assertIn("DELIVERY_SPAWN", stderr.getvalue())
        with self.assertRaises(ExtError) as caught:
            self.emit(delivery_mode="background", strict=True)
        self.assertEqual(caught.exception.code, "DELIVERY_SPAWN")

    def test_background_deliverer_runs_in_its_own_session(self):
        self.subscribe("mine", command("ok.py", str(self.out)))
        event = self.emit(delivery_mode="background")
        proc = delivery._SPAWNED[-1]
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            path = delivery.cursors_path(self.journal)
            if path.exists() and self.cursors().get("mine", {}).get("offset") == journal.size(self.journal):
                break
            time.sleep(0.05)
        self.assertEqual(proc.wait(10), 0)
        self.assertEqual(self.cursors()["mine"]["offset"], journal.size(self.journal))
        seen = self.got()
        self.assertEqual([item["id"] for item in seen], [event.id])
        self.assertEqual(seen[0]["parent"], proc.pid)
        self.assertEqual(seen[0]["parent_sid"], proc.pid)  # the deliverer leads its own session
        self.assertNotEqual(seen[0]["parent_sid"], os.getsid(0))


class TestCli(DeliveryCase):
    def events_cli(self, *argv):
        return run_cli("events", *argv, env=self.env, cwd=self.tmp)

    def test_deliver_status_replay(self):
        self.subscribe("mine", command("ok.py", str(self.out)))
        self.emit(delivery_mode="sync")
        event = self.emit()
        code, out, err = self.events_cli("status", "--project", str(self.project))
        self.assertEqual((code, err), (0, ""))
        self.assertIn("mine config on lag 1 dead-letters 0", out)
        code, out, err = self.events_cli("deliver", "--project", str(self.project), "--json")
        self.assertEqual((code, json.loads(out)["delivered"]), (0, 1))
        code, out, _ = self.events_cli("status", "--project", str(self.project), "--json")
        self.assertEqual(json.loads(out)["subscriptions"][0]["lag"], 0)
        code, out, _ = self.events_cli("replay", "mine", "--event", event.id, "--project", str(self.project))
        self.assertEqual((code, out.strip()), (0, "delivered 1, failed 0, dead-lettered 0"))
        code, _, err = self.events_cli("replay", "nope", "--from-start", "--project", str(self.project))
        self.assertEqual(code, 1)
        self.assertIn("SUBSCRIPTION_UNKNOWN", err)
        code, _, _ = self.events_cli("replay", "mine", "--project", str(self.project))
        self.assertEqual(code, 2)

    def test_deliver_exit_code_on_failure(self):
        self.subscribe("mine", command("always_fail.py"))
        self.emit(delivery_mode="sync")
        self.emit()
        code, _, err = self.events_cli("deliver", "--project", str(self.project))
        self.assertEqual(code, 1)
        self.assertIn("PROCESS_EXIT", err)

    def test_hidden_journal_option_does_not_guess_the_project(self):
        self.subscribe("mine", command("ok.py", str(self.out)), projects=[str(self.project)])
        self.emit(delivery_mode="sync")
        self.emit()
        cwd = self.project  # a project around the cwd must not be taken for the journal's project
        code, out, _ = run_cli("events", "deliver", "--journal", str(self.journal), "--json", env=self.env, cwd=cwd)
        self.assertEqual((code, json.loads(out)["delivered"]), (0, 0))
        code, out, _ = run_cli("events", "deliver", "--journal", str(self.journal), "--project", str(self.project),
                               "--trigger-offset", "0", "--json", env=self.env, cwd=cwd)
        self.assertEqual((code, json.loads(out)["delivered"]), (0, 1))


if __name__ == "__main__":
    unittest.main()
