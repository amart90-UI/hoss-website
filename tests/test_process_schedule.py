"""Tests for scripts/process_schedule.py. Run from the repo root: python -m unittest discover tests -v"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import process_schedule as ps  # noqa: E402

HEADER = "date,start_time,end_time,venue,venue_url,city,state,event_url,notes,venue_logo_url,venue_video_url\n"


def csv_text(*rows):
    return HEADER + "".join(row + "\n" for row in rows)


GOOD = "7/18/2026,7:00 PM,10:00 PM,The Venue,https://example.com/v,Fort Collins,CO,https://example.com/e,Bring friends"


class ParsingTests(unittest.TestCase):
    def test_valid_row_fields(self):
        show = ps.parse_csv(csv_text(GOOD))[0]
        self.assertEqual(show["id"], "2026-07-18-1900-the-venue")
        self.assertEqual(show["date"], "2026-07-18")
        self.assertEqual(show["start_time"], "19:00")
        self.assertEqual(show["end_time"], "22:00")
        self.assertEqual(show["start"], "2026-07-18T19:00:00-06:00")  # MDT
        self.assertEqual(show["end"], "2026-07-18T22:00:00-06:00")
        self.assertEqual(show["state"], "CO")
        self.assertEqual(show["notes"], "Bring friends")
        self.assertIsNone(show["venue_logo_url"])
        self.assertIsNone(show["venue_video_url"])

    def test_optional_fields_become_null(self):
        show = ps.parse_csv(csv_text("1/10/2026,7:00 PM,,Venue,,Denver,co,,"))[0]
        self.assertIsNone(show["end_time"])
        self.assertIsNone(show["end"])
        self.assertIsNone(show["venue_url"])
        self.assertIsNone(show["event_url"])
        self.assertIsNone(show["notes"])
        self.assertIsNone(show["venue_logo_url"])
        self.assertIsNone(show["venue_video_url"])
        self.assertEqual(show["state"], "CO")
        self.assertEqual(show["start"], "2026-01-10T19:00:00-07:00")  # MST

    def test_end_before_start_means_after_midnight(self):
        show = ps.parse_csv(csv_text("7/18/2026,9:00 PM,1:00 AM,Venue,,Denver,CO,,"))[0]
        self.assertEqual(show["end"], "2026-07-19T01:00:00-06:00")

    def test_noon_and_midnight(self):
        shows = ps.parse_csv(csv_text(
            "7/18/2026,12:00 PM,,A,,Denver,CO,,",
            "7/18/2026,12:30 AM,,B,,Denver,CO,,",
        ))
        self.assertEqual({s["venue"]: s["start_time"] for s in shows}, {"A": "12:00", "B": "00:30"})

    def test_sheet_formats_with_seconds_and_short_dates(self):
        show = ps.parse_csv(csv_text("9/4/2026,7:00:00 PM,9:30:00 PM,V,,Denver,CO,,"))[0]
        self.assertEqual((show["date"], show["start_time"], show["end_time"]), ("2026-09-04", "19:00", "21:30"))
        self.assertEqual(show["id"], "2026-09-04-1900-v")
        show = ps.parse_csv(csv_text("11/7/2026,12:00:00 PM,3:00:00 PM,V,,Denver,CO,,"))[0]
        self.assertEqual((show["date"], show["start_time"]), ("2026-11-07", "12:00"))
        self.assertEqual(show["start"], "2026-11-07T12:00:00-07:00")  # MST after the November DST change

    def test_time_formats_accepted(self):
        for value in ("7:00 PM", "7:00PM", "7:00 pm", "07:00 PM", "7:00:00 PM", "7:00:59 pm"):
            show = ps.parse_csv(csv_text(f"7/18/2026,{value},,V,,Denver,CO,,"))[0]
            self.assertEqual(show["start_time"], "19:00", value)

    def test_whitespace_and_bom(self):
        text = "\ufeff" + csv_text("  7/18/2026 , 7:00 PM ,, The Venue ,, Denver , CO ,,")
        shows = ps.parse_csv(ps.decode_csv_bytes(text.encode("utf-8")))
        self.assertEqual(shows[0]["venue"], "The Venue")

    def test_header_case_and_order_flexible(self):
        text = "State,City,Venue,Start_Time,Date\nCO,Denver,V,7:00 PM,7/18/2026\n"
        self.assertEqual(ps.parse_csv(text)[0]["id"], "2026-07-18-1900-v")

    def test_blank_rows_ignored(self):
        shows = ps.parse_csv(csv_text(GOOD, ",,,,,,,,", "", GOOD.replace("7/18/2026", "7/19/2026")))
        self.assertEqual(len(shows), 2)

    def test_quoted_commas_and_unicode(self):
        show = ps.parse_csv(csv_text('7/18/2026,7:00 PM,,"Bar, Grill & Caf\u00e9",,Denver,CO,,"Hi, there"'))[0]
        self.assertEqual(show["venue"], "Bar, Grill & Caf\u00e9")
        self.assertEqual(show["notes"], "Hi, there")

    def assertRowError(self, row, *fragments):
        with self.assertRaises(ps.ScheduleError) as ctx:
            ps.parse_csv(csv_text(row))
        for fragment in fragments:
            self.assertIn(fragment, str(ctx.exception))

    def test_bad_dates(self):
        self.assertRowError("2026-07-18,7:00 PM,,V,,Denver,CO,,", "row 2", "M/D/YYYY")
        self.assertRowError("2/30/2026,7:00 PM,,V,,Denver,CO,,", "not a real calendar date")
        self.assertRowError("7-8-2026,7:00 PM,,V,,Denver,CO,,", "M/D/YYYY")
        self.assertRowError("13/1/2026,7:00 PM,,V,,Denver,CO,,", "not a real calendar date")
        self.assertRowError("7/18/26,7:00 PM,,V,,Denver,CO,,", "M/D/YYYY")

    def test_bad_times(self):
        self.assertRowError("7/18/2026,19:00,,V,,Denver,CO,,", "start_time")
        self.assertRowError("7/18/2026,13:00 PM,,V,,Denver,CO,,", "start_time")
        self.assertRowError("7/18/2026,7:00 PM,late,V,,Denver,CO,,", "end_time")
        self.assertRowError("7/18/2026,7:75 PM,,V,,Denver,CO,,", "start_time")

    def test_missing_required_values(self):
        self.assertRowError(",7:00 PM,,V,,Denver,CO,,", "missing required value 'date'")
        self.assertRowError("7/18/2026,,,V,,Denver,CO,,", "missing required value 'start_time'")
        self.assertRowError("7/18/2026,7:00 PM,,,,Denver,CO,,", "missing required value 'venue'")
        self.assertRowError("7/18/2026,7:00 PM,,V,,,CO,,", "missing required value 'city'")
        self.assertRowError("7/18/2026,7:00 PM,,V,,Denver,,,", "missing required value 'state'")

    def test_bad_state(self):
        self.assertRowError("7/18/2026,7:00 PM,,V,,Denver,Colorado,,", "two-letter")

    def test_bad_urls(self):
        self.assertRowError("7/18/2026,7:00 PM,,V,javascript:alert(1),Denver,CO,,", "venue_url")
        self.assertRowError("7/18/2026,7:00 PM,,V,,Denver,CO,example.com,", "event_url")
        self.assertRowError("7/18/2026,7:00 PM,,V,https://exa mple.com,Denver,CO,,", "venue_url")
        self.assertRowError("7/18/2026,7:00 PM,,V,ftp://example.com,Denver,CO,,", "venue_url")
        self.assertRowError("7/18/2026,7:00 PM,,V,,Denver,CO,,,javascript:alert(1),", "venue_logo_url")
        self.assertRowError("7/18/2026,7:00 PM,,V,,Denver,CO,,,,ftp://example.com", "venue_video_url")

    def test_venue_history_metadata(self):
        show = ps.parse_csv(csv_text(
            "7/18/2026,7:00 PM,,V,,Denver,CO,,,https://example.com/logo.png,https://youtube.com/watch?v=abc"
        ))[0]
        self.assertEqual(show["venue_logo_url"], "https://example.com/logo.png")
        self.assertEqual(show["venue_video_url"], "https://youtube.com/watch?v=abc")

    def test_all_bad_rows_reported_together(self):
        with self.assertRaises(ps.ScheduleError) as ctx:
            ps.parse_csv(csv_text(GOOD, "bad,7:00 PM,,V,,Denver,CO,,", "7/18/2026,nope,,V,,Denver,CO,,"))
        message = str(ctx.exception)
        self.assertIn("row 3", message)
        self.assertIn("row 4", message)
        self.assertNotIn("row 2", message)

    def test_duplicates_rejected(self):
        with self.assertRaises(ps.ScheduleError) as ctx:
            ps.parse_csv(csv_text(GOOD, GOOD))
        self.assertIn("duplicate of row 2", str(ctx.exception))

    def test_same_day_different_times_allowed(self):
        shows = ps.parse_csv(csv_text(GOOD, GOOD.replace("7:00 PM", "9:00 PM")))
        self.assertEqual(len(shows), 2)

    def test_header_only_is_error(self):
        with self.assertRaises(ps.ScheduleError):
            ps.parse_csv(HEADER)

    def test_empty_and_missing_columns(self):
        with self.assertRaises(ps.ScheduleError):
            ps.parse_csv("")
        with self.assertRaises(ps.ScheduleError) as ctx:
            ps.parse_csv("date,venue\n2026-07-18,V\n")
        self.assertIn("start_time", str(ctx.exception))

    def test_html_response_detected(self):
        for body in (b"<!DOCTYPE html><html>sign in</html>", b"  <html><body>x</body></html>"):
            with self.assertRaises(ps.ScheduleError) as ctx:
                ps.decode_csv_bytes(body)
            self.assertIn("web page", str(ctx.exception))

    def test_slug_edge_cases(self):
        self.assertEqual(ps.slugify("The Mishawaka & Grill!"), "the-mishawaka-grill")
        self.assertEqual(ps.slugify("!!!"), "show")


class ClassifyTests(unittest.TestCase):
    def shows(self):
        return ps.parse_csv(csv_text(
            "7/17/2026,7:00 PM,,Yesterday,,Denver,CO,,",
            "7/18/2026,11:30 PM,,Today,,Denver,CO,,",
            "7/19/2026,7:00 PM,,Tomorrow,,Denver,CO,,",
            "9/1/2026,7:00 PM,,Later,,Denver,CO,,",
            "1/1/2025,7:00 PM,,Ancient,,Denver,CO,,",
        ))

    def test_today_is_upcoming_and_yesterday_is_past(self):
        upcoming, past = ps.split_shows(self.shows(), date(2026, 7, 18))
        self.assertEqual([s["venue"] for s in upcoming], ["Today", "Tomorrow", "Later"])
        self.assertEqual([s["venue"] for s in past], ["Yesterday", "Ancient"])

    def test_day_after_moves_today_to_past(self):
        upcoming, past = ps.split_shows(self.shows(), date(2026, 7, 19))
        self.assertEqual([s["venue"] for s in upcoming], ["Tomorrow", "Later"])
        self.assertEqual([s["venue"] for s in past], ["Today", "Yesterday", "Ancient"])

    def test_same_day_sorted_by_time(self):
        shows = ps.parse_csv(csv_text(
            "7/20/2026,9:00 PM,,Late,,Denver,CO,,", "7/20/2026,1:00 PM,,Early,,Denver,CO,,"))
        upcoming, _ = ps.split_shows(shows, date(2026, 7, 18))
        self.assertEqual([s["venue"] for s in upcoming], ["Early", "Late"])
        _, past = ps.split_shows(shows, date(2026, 8, 1))
        self.assertEqual([s["venue"] for s in past], ["Late", "Early"])

    def test_denver_date_uses_local_midnight(self):
        # July: Denver is UTC-6, so local midnight is 06:00 UTC.
        before = datetime(2026, 7, 19, 5, 59, tzinfo=timezone.utc)
        after = datetime(2026, 7, 19, 6, 0, tzinfo=timezone.utc)
        self.assertEqual(ps.denver_today(before), date(2026, 7, 18))
        self.assertEqual(ps.denver_today(after), date(2026, 7, 19))
        # January: Denver is UTC-7.
        self.assertEqual(ps.denver_today(datetime(2026, 1, 10, 6, 59, tzinfo=timezone.utc)), date(2026, 1, 9))
        self.assertEqual(ps.denver_today(datetime(2026, 1, 10, 7, 0, tzinfo=timezone.utc)), date(2026, 1, 10))


class FetchTests(unittest.TestCase):
    """fetch_csv with the network mocked out."""

    def fake_response(self, body):
        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()
        return Response(body)

    def test_success_uses_url_as_given(self):
        seen = []

        def fake_urlopen(request, timeout):
            seen.append(request.full_url)
            return self.fake_response(csv_text(GOOD).encode("utf-8"))

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            text = ps.fetch_csv("https://docs.google.com/spreadsheets/d/e/SECRETLINK/pub?output=csv")
        self.assertEqual(seen, ["https://docs.google.com/spreadsheets/d/e/SECRETLINK/pub?output=csv"])
        self.assertEqual(len(ps.parse_csv(text)), 1)

    def test_http_404_fails_without_leaking_url(self):
        def fake_urlopen(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

        with mock.patch("urllib.request.urlopen", fake_urlopen), mock.patch("time.sleep"):
            with self.assertRaises(ps.ScheduleError) as ctx:
                ps.fetch_csv("https://docs.google.com/spreadsheets/d/e/SECRETSUFFIX/pub")
        self.assertIn("HTTP 404", str(ctx.exception))
        self.assertNotIn("SECRETSUFFIX", str(ctx.exception))

    def test_network_error_retries_then_fails(self):
        calls = []

        def fake_urlopen(request, timeout):
            calls.append(1)
            raise urllib.error.URLError("boom SECRETSUFFIX")

        with mock.patch("urllib.request.urlopen", fake_urlopen), mock.patch("time.sleep"):
            with self.assertRaises(ps.ScheduleError) as ctx:
                ps.fetch_csv("https://docs.google.com/spreadsheets/d/e/SECRETSUFFIX/pub")
        self.assertEqual(len(calls), ps.FETCH_ATTEMPTS)
        self.assertNotIn("SECRETSUFFIX", str(ctx.exception))

    def test_html_page_rejected(self):
        with mock.patch("urllib.request.urlopen", lambda request, timeout: self.fake_response(b"<!doctype html><html>")):
            with self.assertRaises(ps.ScheduleError):
                ps.fetch_csv("https://example.com/x")


class OutputTests(unittest.TestCase):
    def run_main(self, csv_content, output_dir, today="2026-07-18"):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "schedule.csv"
            source.write_text(csv_content, encoding="utf-8")
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                code = ps.main(["--csv", str(source), "--output-dir", str(output_dir), "--today", today])
        return code, err.getvalue()

    def test_output_is_deterministic_and_row_order_independent(self):
        rows = [GOOD, GOOD.replace("7/18/2026", "8/1/2026").replace("The Venue", "Other"),
                GOOD.replace("7/18/2026", "1/1/2025").replace("The Venue", "Old")]
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self.assertEqual(self.run_main(csv_text(*rows), a)[0], 0)
            self.assertEqual(self.run_main(csv_text(*reversed(rows)), b)[0], 0)
            for name in ("shows.json", "past-shows.json"):
                self.assertEqual((Path(a) / name).read_bytes(), (Path(b) / name).read_bytes())
            data = json.loads((Path(a) / "shows.json").read_text(encoding="utf-8"))
            self.assertEqual([s["venue"] for s in data], ["The Venue", "Other"])
            self.assertTrue((Path(a) / "shows.json").read_bytes().endswith(b"}\n]\n"))

    def test_invalid_data_leaves_existing_files_untouched(self):
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(self.run_main(csv_text(GOOD), out)[0], 0)
            before = {n: (Path(out) / n).read_bytes() for n in ("shows.json", "past-shows.json")}
            code, err = self.run_main(csv_text(GOOD, "bad,7:00 PM,,V,,Denver,CO,,"), out)
            self.assertEqual(code, 1)
            self.assertIn("row 3", err)
            code, _ = self.run_main(HEADER, out)  # header only
            self.assertEqual(code, 1)
            code, _ = self.run_main("<html>login</html>", out)
            self.assertEqual(code, 1)
            after = {n: (Path(out) / n).read_bytes() for n in ("shows.json", "past-shows.json")}
            self.assertEqual(before, after)
            self.assertEqual(list(Path(out).glob("*.tmp")), [])

    def test_no_upcoming_writes_empty_list(self):
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(self.run_main(csv_text(GOOD), out, today="2030-01-01")[0], 0)
            self.assertEqual(json.loads((Path(out) / "shows.json").read_text()), [])
            self.assertEqual(len(json.loads((Path(out) / "past-shows.json").read_text())), 1)

    def test_missing_env_and_bad_today(self):
        with tempfile.TemporaryDirectory() as out:
            err = io.StringIO()
            with mock.patch.dict(os.environ), contextlib.redirect_stderr(err):
                os.environ.pop("SCHEDULE_CSV_URL", None)
                code = ps.main(["--output-dir", out])
            self.assertEqual(code, 1)
            self.assertIn("SCHEDULE_CSV_URL", err.getvalue())
            code, _ = self.run_main(csv_text(GOOD), out, today="tomorrow")
            self.assertEqual(code, 1)

    def test_non_https_env_url_rejected(self):
        with tempfile.TemporaryDirectory() as out, mock.patch.dict(os.environ, {"SCHEDULE_CSV_URL": "http://example.com/x"}):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(ps.main(["--output-dir", out]), 1)
            self.assertIn("https://", err.getvalue())


if __name__ == "__main__":
    unittest.main()
