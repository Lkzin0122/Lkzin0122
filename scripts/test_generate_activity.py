"""Checks for contribution counts, calendar boundaries, and API failures."""

from contextlib import redirect_stderr
from datetime import date, timedelta
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from xml.etree import ElementTree as ET

from generate_activity import fetch_calendar, main, metrics, parse_calendar, render_svg


def calendar(counts, start="2026-11-01"):
    first = date.fromisoformat(start)
    return {"weeks": [{"contributionDays": [
        {"date": (first + timedelta(days=index)).isoformat(),
         "contributionCount": count,
         "contributionLevel": "FIRST_QUARTILE" if count else "NONE"}
        for index, count in enumerate(counts)
    ]}]}


def response(payload):
    return io.BytesIO(json.dumps(payload).encode())


class ActivityTests(unittest.TestCase):
    def test_counts_and_streak_across_weeks(self):
        weeks = parse_calendar(calendar([1, 2, 0, 1, 1, 3], "2026-11-05"))
        self.assertEqual(len(weeks), 2)
        self.assertEqual(metrics(weeks), (8, 5, 3))

    def test_empty_activity_produces_valid_svg(self):
        weeks = parse_calendar(calendar([0] * 7))
        self.assertEqual(metrics(weeks), (0, 0, 0))
        svg = render_svg(weeks, "Lucas")
        root = ET.fromstring(svg)
        cells = root.findall('.//*[@class="day"]')
        self.assertEqual(len(cells), 7)
        self.assertIn("0 contribuições", svg)
        self.assertNotIn("nan", svg.lower())

    def test_leap_day_and_year_boundary(self):
        for start in ("2024-02-28", "2025-12-31"):
            with self.subTest(start=start):
                weeks = parse_calendar(calendar([1, 1, 1], start))
                self.assertEqual(metrics(weeks), (3, 3, 3))
                self.assertEqual(sum(map(len, weeks)), 3)

    def test_rejects_empty_duplicate_and_missing_days(self):
        duplicate = calendar([1, 1])
        duplicate["weeks"][0]["contributionDays"][1]["date"] = "2026-11-01"
        missing = calendar([1, 1, 1])
        missing["weeks"][0]["contributionDays"].pop(1)
        for payload in (calendar([]), duplicate, missing):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                parse_calendar(payload)

    def test_rejects_invalid_counts_and_levels(self):
        for key, value in (("contributionCount", -1), ("contributionCount", True),
                           ("contributionLevel", "UNKNOWN"), ("contributionLevel", "NONE")):
            payload = calendar([1])
            payload["weeks"][0]["contributionDays"][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                parse_calendar(payload)

    def test_full_calendar_fits_and_has_no_future_cells(self):
        # A leap-year window can occupy 54 calendar-week columns.
        weeks = parse_calendar(calendar([1] * 366, "2028-01-01"))
        self.assertEqual(len(weeks), 54)
        root = ET.fromstring(render_svg(weeks, "Lucas"))
        cells = root.findall('.//*[@class="day"]')
        self.assertEqual(len(cells), 366)
        self.assertLessEqual(max(float(cell.attrib["x"]) + 17 for cell in cells), 1232)

    def test_api_success(self):
        payload = {"data": {"user": {"contributionsCollection": {
            "contributionCalendar": calendar([1, 0, 2]),
        }}}}
        with patch("generate_activity.urlopen", return_value=response(payload)):
            self.assertEqual(metrics(parse_calendar(fetch_calendar("Lucas", "test-token"))), (3, 2, 1))

    def test_api_errors_are_not_treated_as_empty_activity(self):
        for payload in ({"errors": [{"message": "failure"}]}, {"data": {"user": None}}):
            with self.subTest(payload=payload):
                with patch("generate_activity.urlopen", return_value=response(payload)):
                    with self.assertRaises((RuntimeError, ValueError)):
                        fetch_calendar("Lucas", "test-token")

    def test_transient_http_failure_is_retried(self):
        payload = {"data": {"user": {"contributionsCollection": {
            "contributionCalendar": calendar([1]),
        }}}}
        unavailable = HTTPError("https://api.github.com/graphql", 503, "unavailable", {}, None)
        with patch("generate_activity.time.sleep"):
            with patch("generate_activity.urlopen", side_effect=[unavailable, response(payload)]) as request:
                self.assertEqual(metrics(parse_calendar(fetch_calendar("Lucas", "test-token"))), (1, 1, 1))
                self.assertEqual(request.call_count, 2)

    def test_invalid_input_preserves_existing_svg(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "activity.svg"
            source = Path(directory) / "calendar.json"
            output.write_text("last good panel", encoding="utf-8")
            source.write_text(json.dumps(calendar([])), encoding="utf-8")
            with patch("sys.argv", ["generate_activity.py", "--input", str(source), "--output", str(output)]):
                with redirect_stderr(io.StringIO()):
                    self.assertEqual(main(), 1)
            self.assertEqual(output.read_text(encoding="utf-8"), "last good panel")


if __name__ == "__main__":
    unittest.main()
