"""aicore.util.timefmt: UTC-aware parsing and formatting, independent of the process time zone."""
import os
import time
import unittest
from datetime import datetime, timedelta, timezone

from aicore.util import timefmt

EPOCH_2024 = 1704110400.0  # 2024-01-01T12:00:00Z


class TimefmtTests(unittest.TestCase):
    def test_a_date_without_a_time_is_not_a_moment(self):
        for text in ("2024-01-01Z", "2024-01-01", "2024-01-01+00:00"):
            with self.subTest(text=text):
                self.assertIsNone(timefmt.parse_rfc3339(text))
        self.assertIsNotNone(timefmt.parse_rfc3339("2024-01-01 12:00:00Z"))

    def test_a_time_without_a_utc_moment_is_unreadable_not_a_crash(self):
        for text in ("0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00"):
            with self.subTest(text=text):
                self.assertIsNone(timefmt.parse_rfc3339(text))

    def setUp(self):
        saved = os.environ.get("TZ")
        self.addCleanup(self._restore, saved)

    @staticmethod
    def _restore(saved):
        if saved is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = saved
        time.tzset()

    def in_zones(self):
        for zone in ("America/New_York", "Asia/Tokyo"):
            os.environ["TZ"] = zone
            time.tzset()
            yield zone

    def test_the_accepted_forms(self):
        cases = {
            "2024-01-01T12:00:00Z": EPOCH_2024,
            "2024-01-01T12:00:00z": EPOCH_2024,
            "2024-01-01T16:00:00+04:00": EPOCH_2024,
            "2024-01-01T07:00:00-05:00": EPOCH_2024,
            "2024-01-01T12:00:00.250Z": EPOCH_2024 + 0.25,
            "2024-01-01T12:00:00.1234567891Z": EPOCH_2024 + 0.123456,
            "2024-01-01T12:00:00": EPOCH_2024,  # naive is UTC
            " 2024-01-01T12:00:00Z ": EPOCH_2024,
        }
        for zone in self.in_zones():
            for text, expected in cases.items():
                with self.subTest(zone=zone, text=text):
                    parsed = timefmt.parse_rfc3339(text)
                    self.assertIsNotNone(parsed.tzinfo)
                    self.assertEqual(timedelta(0), parsed.utcoffset())
                    self.assertAlmostEqual(expected, parsed.timestamp(), places=5)
                    self.assertAlmostEqual(expected, timefmt.epoch(text), places=5)

    def test_garbage_is_none(self):
        for value in ("", "  ", "garbage", "2024-13-45T00:00:00Z", None, 5, b"2024-01-01T00:00:00Z", [], "Z"):
            with self.subTest(value=value):
                self.assertIsNone(timefmt.parse_rfc3339(value))
                self.assertIsNone(timefmt.epoch(value))

    def test_convert_false_keeps_the_offset(self):
        parsed = timefmt.parse_rfc3339("2024-01-01T16:00:00+04:00", convert=False)
        self.assertEqual(timedelta(hours=4), parsed.utcoffset())
        self.assertEqual(EPOCH_2024, parsed.timestamp())

    def test_the_epoch_is_the_same_in_every_zone(self):
        seen = set()
        for _ in self.in_zones():
            seen.add((timefmt.epoch("2024-01-01T12:00:00"), timefmt.epoch("2024-01-01T12:00:00Z"),
                      timefmt.parse_rfc3339("2024-01-01T12:00:00").timestamp()))
        self.assertEqual({(EPOCH_2024,) * 3}, seen)

    def test_utc_stamp_is_a_whole_second_in_utc(self):
        for _ in self.in_zones():
            self.assertEqual("2024-01-01T12:00:00Z", timefmt.utc_stamp(datetime(2024, 1, 1, 12, 0, 0, 999999)))
            self.assertEqual("2024-01-01T12:00:00Z", timefmt.utc_stamp(
                datetime(2024, 1, 1, 21, 0, 0, tzinfo=timezone(timedelta(hours=9)))))
            self.assertEqual("2024-01-01T12:00:00Z", timefmt.utc_stamp(EPOCH_2024))
            stamp = timefmt.utc_stamp()
            self.assertRegex(stamp, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
            self.assertLess(abs(timefmt.epoch(stamp) - time.time()), 5)

    def test_utc_now_is_aware_utc(self):
        for _ in self.in_zones():
            now = timefmt.utc_now()
            self.assertEqual(timedelta(0), now.utcoffset())
            self.assertLess(abs(now.timestamp() - time.time()), 5)

    def test_seconds_between(self):
        for _ in self.in_zones():
            self.assertEqual(90.0, timefmt.seconds_between("2024-01-01T12:00:00Z", "2024-01-01T12:01:30Z"))
            self.assertEqual(-3600.0, timefmt.seconds_between("2024-01-01T12:00:00Z", "2024-01-01T12:00:00+01:00"))
            self.assertEqual(1.5, timefmt.seconds_between(datetime(2024, 1, 1, 12), "2024-01-01T12:00:01.5Z"))
            self.assertIsNone(timefmt.seconds_between("nope", "2024-01-01T12:00:00Z"))
            self.assertIsNone(timefmt.seconds_between("2024-01-01T12:00:00Z", None))


if __name__ == "__main__":
    unittest.main()
