"""Tests for scripts/generate_venue_history.py."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import generate_venue_history as gvh  # noqa: E402


def show(venue, date, city="Fort Collins", url=None, state="CO"):
    return {"id": f"{date}-{venue}", "date": date, "venue": venue, "venue_url": url, "city": city, "state": state}


class VenueHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.logos = Path(self.tmp.name) / "img" / "venues"
        self.logos.mkdir(parents=True)

    def build(self, shows, **kwargs):
        return gvh.build_venue_history(shows, logo_dir=str(self.logos), **kwargs)

    def test_ranks_by_count_then_most_recent(self):
        shows = [
            show("Old Spot", "2024-01-01"),
            show("Fox", "2025-01-01"),
            show("Fox", "2025-02-01"),
            show("New Spot", "2025-06-01"),
            show("Fox", "2025-03-01"),
            show("Brew", "2025-04-01"),
            show("Brew", "2024-04-01"),
        ]
        result = self.build(shows)
        self.assertEqual([v["venue"] for v in result], ["Fox", "Brew", "New Spot", "Old Spot"])
        self.assertEqual([v["count"] for v in result], [3, 2, 1, 1])

    def test_limited_to_six_by_default(self):
        shows = [show(f"Venue {n}", f"2025-01-{n:02d}") for n in range(1, 10)]
        self.assertEqual(len(self.build(shows)), 6)
        self.assertEqual(len(self.build(shows, limit=3)), 3)

    def test_same_name_in_different_case_is_one_venue(self):
        result = self.build([show("The Fox", "2025-01-01"), show("the fox", "2025-02-01")])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["count"], 2)
        self.assertEqual(result[0]["venue"], "the fox")  # spelling of the newest show

    def test_url_is_newest_non_empty_venue_url(self):
        shows = [
            show("Fox", "2025-01-01", url="https://old.example.com"),
            show("Fox", "2025-02-01", url="https://new.example.com"),
            show("Fox", "2025-03-01"),
        ]
        self.assertEqual(self.build(shows)[0]["url"], "https://new.example.com")
        self.assertIsNone(self.build([show("Bare", "2025-01-01")])[0]["url"])

    def test_logo_found_by_slug_and_extension(self):
        (self.logos / "the-fox-theatre.webp").write_bytes(b"x")
        result = self.build([show("The Fox Theatre!", "2025-01-01"), show("No Logo", "2025-01-02")])
        by_name = {v["venue"]: v for v in result}
        self.assertTrue(by_name["The Fox Theatre!"]["logo"].endswith("/the-fox-theatre.webp"))
        self.assertIsNone(by_name["No Logo"]["logo"])

    def test_logo_background_comes_from_the_table(self):
        result = self.build([show("Velvet Lounge", "2025-01-01"), show("The Slab", "2025-01-02"), show("Other", "2025-01-03")])
        by_name = {v["venue"]: v["logo_background"] for v in result}
        self.assertEqual(by_name, {"Velvet Lounge": "black", "The Slab": "white", "Other": None})

    def test_background_table_only_uses_known_colors(self):
        for slug, color in gvh.LOGO_BACKGROUNDS.items():
            self.assertEqual(slug, gvh.venue_slug(slug))
            self.assertIn(color, gvh.BACKGROUND_CHOICES)

    def test_slug(self):
        self.assertEqual(gvh.venue_slug("  Odell Brewing Co. & Taproom "), "odell-brewing-co-taproom")
        self.assertEqual(gvh.venue_slug("!!!"), "")
        self.assertIsNone(gvh.find_logo("!!!", str(self.logos)))

    def test_empty_list_gives_empty_result(self):
        self.assertEqual(self.build([]), [])

    def test_bad_input_is_rejected(self):
        with self.assertRaises(ValueError):
            gvh.build_venue_history({"venue": "x"})
        with self.assertRaises(ValueError):
            gvh.build_venue_history([{"date": "2025-01-01"}])

    def test_writes_json_file(self):
        shows_file = Path(self.tmp.name) / "past-shows.json"
        shows_file.write_text(json.dumps([show("Fox", "2025-01-01")]), encoding="utf-8")
        output = Path(self.tmp.name) / "nested" / "venue-history.json"
        code = gvh.main(["--shows-file", str(shows_file), "--output", str(output), "--logo-dir", str(self.logos)])
        self.assertEqual(code, 0)
        data = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(data[0]["venue"], "Fox")
        self.assertEqual(data[0]["count"], 1)

    def test_bad_file_fails_without_touching_existing_output(self):
        output = Path(self.tmp.name) / "venue-history.json"
        output.write_text("[]\n", encoding="utf-8")
        missing = Path(self.tmp.name) / "missing.json"
        self.assertEqual(gvh.main(["--shows-file", str(missing), "--output", str(output)]), 1)
        self.assertEqual(output.read_text(encoding="utf-8"), "[]\n")


if __name__ == "__main__":
    unittest.main()
