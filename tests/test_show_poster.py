"""Tests for scripts/generate_show_poster.py."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import generate_show_poster as poster  # noqa: E402


class ShowPosterTests(unittest.TestCase):
    def test_groups_shows_and_formats_dates_and_time_ranges(self):
        groups = poster.format_groups([
            {
                "date": "2026-11-25",
                "start_time": "12:00",
                "end_time": "14:00",
                "venue": "The Slab",
                "city": "Estes Park",
                "state": "CO",
            },
            {
                "date": "2026-11-25",
                "start_time": "18:00",
                "end_time": "20:00",
                "venue": "Abbott and Wallace Distilling",
                "city": "Longmont",
                "state": "CO",
            },
            {
                "date": "2026-12-04",
                "start_time": "19:00",
                "end_time": "21:00",
                "venue": "Horsetooth Tavern",
                "city": "Fort Collins",
                "state": "CO",
            },
        ])

        self.assertEqual(groups, [
            ("Nov 25", [
                ("The Slab", "Estes Park, CO 12:00 - 2:00 PM"),
                ("Abbott and Wallace Distilling", "Longmont, CO 6:00 - 8:00 PM"),
            ]),
            ("Dec 4", [("Horsetooth Tavern", "Fort Collins, CO 7:00 - 9:00 PM")]),
        ])
        self.assertEqual(poster.format_time_range("11:00", "13:00"), "11:00 AM - 1:00 PM")

    def test_generates_jpeg_and_showposter_page_with_supplied_background(self):
        shows = [{
            "date": "2026-11-25",
            "start_time": "18:00",
            "end_time": "20:00",
            "venue": "The Slab",
            "city": "Estes Park",
            "state": "CO",
        }]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shows_file = root / "shows.json"
            background = root / "background.png"
            output = root / "img" / "upcomingshow.jpg"
            page_output = root / "showposter"
            shows_file.write_text(json.dumps(shows), encoding="utf-8")
            Image.new("RGB", (400, 600), "#BDB199").save(background)

            count = poster.generate_poster(shows_file, background, output, page_output)

            self.assertEqual(count, 1)
            with Image.open(output) as image:
                self.assertEqual(image.format, "JPEG")
                self.assertEqual(image.size, (poster.WIDTH, poster.HEIGHT))
            self.assertIn("/img/upcomingshow.jpg", (page_output / "index.html").read_text(encoding="utf-8"))

    def test_missing_background_uses_fallback_and_empty_schedule_is_rendered(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shows_file = root / "shows.json"
            output = root / "upcomingshow.jpg"
            shows_file.write_text("[]", encoding="utf-8")

            count = poster.generate_poster(shows_file, root / "missing.png", output, root / "showposter")

            self.assertEqual(count, 0)
            with Image.open(output) as image:
                self.assertEqual(image.format, "JPEG")


if __name__ == "__main__":
    unittest.main()
