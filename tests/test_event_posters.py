"""Tests for scripts/generate_event_posters.py and scripts/qr_code.py."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import generate_event_posters as posters  # noqa: E402
import qr_code  # noqa: E402

SHOW = {
    "id": "2026-07-12-1100-horsetooth-tavern",
    "date": "2026-07-12",
    "start_time": "11:00",
    "end_time": "14:00",
    "venue": "Horsetooth Tavern",
    "city": "Fort Collins",
    "state": "CO",
    "event_url": "https://example.com/event",
    "page_path": "/events/2026-07-12-horsetooth-tavern/",
}


class QRTests(unittest.TestCase):
    def test_size_grows_with_text_and_finder_patterns_present(self):
        small = qr_code.make_qr("hi")
        large = qr_code.make_qr("https://example.com/" + "a" * 150)
        self.assertEqual(len(small), 21)
        self.assertGreater(len(large), 21)
        for grid in (small, large):
            n = len(grid)
            for left, top in ((0, 0), (n - 7, 0), (0, n - 7)):
                self.assertTrue(all(grid[top][left + i] for i in range(7)))  # outer ring top edge
                self.assertTrue(grid[top + 3][left + 3])                      # center dot
                self.assertFalse(grid[top + 1][left + 1])                     # light ring

    def test_deterministic(self):
        self.assertEqual(qr_code.make_qr("https://example.com/x"), qr_code.make_qr("https://example.com/x"))

    def test_too_long_text_is_rejected(self):
        with self.assertRaises(qr_code.QRError):
            qr_code.make_qr("x" * 300)


class PosterTests(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(posters.format_date("2026-07-12"), "JUL 12, 2026")
        self.assertEqual(posters.format_time_range("11:00", "14:00"), "11 am - 2 pm")
        self.assertEqual(posters.format_time_range("21:00", "23:00"), "9 - 11 pm")
        self.assertEqual(posters.format_time_range("18:30", None), "6:30 pm")
        self.assertEqual(posters.format_time_range("00:00", "01:15"), "12 - 1:15 am")

    def test_generates_poster_beside_event_page_and_skips_pageless_shows(self):
        pageless = dict(SHOW, id="x", page_path=None)
        no_url = dict(SHOW, id="y", page_path="/events/2026-08-01-no-url/", event_url=None)
        with tempfile.TemporaryDirectory() as folder:
            shows = Path(folder) / "shows.json"
            shows.write_text(json.dumps([SHOW, pageless, no_url]), encoding="utf-8")
            site = Path(folder) / "site"
            written = posters.generate_posters(shows, site)
            self.assertEqual(len(written), 2)
            first = site / "events" / "2026-07-12-horsetooth-tavern" / "poster.jpg"
            self.assertTrue(first.is_file())
            with Image.open(first) as image:
                self.assertEqual(image.size, (3000, 3996))
            self.assertTrue((site / "events" / "2026-08-01-no-url" / "poster.jpg").is_file())

    def test_only_filter(self):
        with tempfile.TemporaryDirectory() as folder:
            shows = Path(folder) / "shows.json"
            shows.write_text(json.dumps([SHOW]), encoding="utf-8")
            self.assertEqual(posters.generate_posters(shows, folder, only="nomatch"), [])

    def test_bad_input_raises(self):
        with tempfile.TemporaryDirectory() as folder:
            shows = Path(folder) / "shows.json"
            shows.write_text(json.dumps([dict(SHOW, city="")]), encoding="utf-8")
            with self.assertRaises(posters.PosterError):
                posters.generate_posters(shows, folder)
            with self.assertRaises(posters.PosterError):
                posters.generate_posters(Path(folder) / "missing.json", folder)


if __name__ == "__main__":
    unittest.main()
