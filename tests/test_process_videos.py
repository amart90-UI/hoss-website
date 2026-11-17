"""Tests for scripts/process_videos.py. Run from the repo root: python -m unittest discover tests -v"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import process_videos as pv  # noqa: E402
from process_schedule import ScheduleError  # noqa: E402

HEADER = "title,url,id\n"
GOOD = "House Fire,https://www.youtube.com/watch?v=WvEge0fWXK0,WvEge0fWXK0"


def csv_text(*rows):
    return HEADER + "".join(row + "\n" for row in rows)


class ParsingTests(unittest.TestCase):
    def test_valid_rows_keep_sheet_order(self):
        videos = pv.parse_csv(csv_text(GOOD, "Big River,u,lrVk6F1Y7vA", "Folsom Prison Blues,u,H-lEsXnYICU"))
        self.assertEqual(
            videos,
            [
                {"id": "WvEge0fWXK0", "title": "House Fire"},
                {"id": "lrVk6F1Y7vA", "title": "Big River"},
                {"id": "H-lEsXnYICU", "title": "Folsom Prison Blues"},
            ],
        )

    def test_url_column_is_optional_and_ignored(self):
        videos = pv.parse_csv("id,title\nWvEge0fWXK0,House Fire\n")
        self.assertEqual(videos, [{"id": "WvEge0fWXK0", "title": "House Fire"}])

    def test_whitespace_bom_blank_rows_and_case(self):
        text = "\ufeffTitle,URL,ID\n  House Fire , x , WvEge0fWXK0 \n,,\n\n"
        videos = pv.parse_csv(pv.decode_csv_bytes(text.encode("utf-8")))
        self.assertEqual(videos, [{"id": "WvEge0fWXK0", "title": "House Fire"}])

    def test_quoted_commas_and_unicode(self):
        videos = pv.parse_csv(csv_text('"Smith, Jones & Caf\u00e9",u,WvEge0fWXK0'))
        self.assertEqual(videos[0]["title"], "Smith, Jones & Caf\u00e9")

    def assertRowError(self, row, *fragments):
        with self.assertRaises(ScheduleError) as ctx:
            pv.parse_csv(csv_text(row))
        for fragment in fragments:
            self.assertIn(fragment, str(ctx.exception))

    def test_missing_values(self):
        self.assertRowError(",u,WvEge0fWXK0", "row 2", "'title'")
        self.assertRowError("House Fire,u,", "row 2", "'id'")

    def test_invalid_ids(self):
        self.assertRowError("A,u,short", "not a valid YouTube video ID")
        self.assertRowError("A,u,WvEge0fWXK0X", "not a valid YouTube video ID")
        self.assertRowError("A,u,WvEge0fWX!0", "not a valid YouTube video ID")
        self.assertRowError("A,u,https://youtu.be/WvEge0fWXK0", "not a valid YouTube video ID")

    def test_duplicate_ids(self):
        with self.assertRaises(ScheduleError) as ctx:
            pv.parse_csv(csv_text(GOOD, GOOD))
        self.assertIn("duplicate of row 2", str(ctx.exception))

    def test_all_bad_rows_reported_together(self):
        with self.assertRaises(ScheduleError) as ctx:
            pv.parse_csv(csv_text(GOOD, "bad,u,x", ",u,lrVk6F1Y7vA"))
        message = str(ctx.exception)
        self.assertIn("row 3", message)
        self.assertIn("row 4", message)
        self.assertNotIn("row 2", message)

    def test_header_only_empty_and_missing_columns(self):
        for text in (HEADER, ""):
            with self.assertRaises(ScheduleError):
                pv.parse_csv(text)
        with self.assertRaises(ScheduleError) as ctx:
            pv.parse_csv("title,url\nA,u\n")
        self.assertIn("id", str(ctx.exception))

    def test_html_response_detected_and_names_the_right_secret(self):
        with self.assertRaises(ScheduleError) as ctx:
            pv.decode_csv_bytes(b"<!DOCTYPE html><html>sign in</html>", pv.URL_ENV_VAR)
        self.assertIn("VIDEO_CSV_URL", str(ctx.exception))


class OutputTests(unittest.TestCase):
    def run_main(self, csv_content, output_dir):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "videos.csv"
            source.write_text(csv_content, encoding="utf-8")
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                code = pv.main(["--csv", str(source), "--output-dir", str(output_dir)])
        return code, err.getvalue()

    def test_output_shape_and_channel_url_preserved(self):
        with tempfile.TemporaryDirectory() as out:
            (Path(out) / "videos.json").write_text(
                json.dumps({"channel_url": "https://youtube.com/@x", "videos": [{"id": "AAAAAAAAAAA", "title": "Old"}]}),
                encoding="utf-8",
            )
            self.assertEqual(self.run_main(csv_text(GOOD), out)[0], 0)
            data = json.loads((Path(out) / "videos.json").read_text(encoding="utf-8"))
            self.assertEqual(data["channel_url"], "https://youtube.com/@x")
            self.assertEqual(data["videos"], [{"id": "WvEge0fWXK0", "title": "House Fire"}])
            self.assertEqual(list(data), ["channel_url", "videos"])

    def test_no_existing_file_omits_channel_url(self):
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(self.run_main(csv_text(GOOD), out)[0], 0)
            self.assertEqual(list((json.loads((Path(out) / "videos.json").read_text()))), ["videos"])

    def test_bad_existing_channel_url_is_dropped(self):
        for bad in ('{"channel_url": "javascript:alert(1)"}', "not json", "[]"):
            with tempfile.TemporaryDirectory() as out:
                (Path(out) / "videos.json").write_text(bad, encoding="utf-8")
                self.assertEqual(self.run_main(csv_text(GOOD), out)[0], 0)
                self.assertNotIn("channel_url", json.loads((Path(out) / "videos.json").read_text()))

    def test_deterministic_output(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self.run_main(csv_text(GOOD, "Big River,u,lrVk6F1Y7vA"), a)
            self.run_main(csv_text(GOOD, "Big River,u,lrVk6F1Y7vA"), b)
            self.assertEqual((Path(a) / "videos.json").read_bytes(), (Path(b) / "videos.json").read_bytes())

    def test_invalid_data_leaves_existing_file_untouched(self):
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(self.run_main(csv_text(GOOD), out)[0], 0)
            before = (Path(out) / "videos.json").read_bytes()
            code, err = self.run_main(csv_text(GOOD, "bad,u,x"), out)
            self.assertEqual(code, 1)
            self.assertIn("row 3", err)
            self.assertEqual(self.run_main(HEADER, out)[0], 1)
            self.assertEqual(self.run_main("<html>login</html>", out)[0], 1)
            self.assertEqual((Path(out) / "videos.json").read_bytes(), before)
            self.assertEqual(list(Path(out).glob("*.tmp")), [])

    def test_missing_and_non_https_env_url(self):
        with tempfile.TemporaryDirectory() as out:
            for env, expected in (({}, "VIDEO_CSV_URL"), ({"VIDEO_CSV_URL": "http://example.com/x"}, "https://")):
                err = io.StringIO()
                with mock.patch.dict(os.environ, env, clear=False), contextlib.redirect_stderr(err):
                    os.environ.pop("VIDEO_CSV_URL", None) if not env else None
                    self.assertEqual(pv.main(["--output-dir", out]), 1)
                self.assertIn(expected, err.getvalue())


if __name__ == "__main__":
    unittest.main()
