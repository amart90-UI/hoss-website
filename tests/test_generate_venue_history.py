"""Tests for scripts/generate_venue_history.py."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import generate_venue_history as venue_history  # noqa: E402


class VenueHistoryTests(unittest.TestCase):
    def test_counts_ranks_caps_and_uses_latest_metadata(self):
        shows = [
            {"venue": "The Fox", "date": "2025-01-01"},
            {"venue": "the fox", "date": "2025-02-01", "venue_video_url": "https://youtube.com/watch?v=fox"},
            {"venue": "The Fox", "date": "2025-03-01", "venue_logo_url": "https://example.com/fox.png"},
            *[{"venue": f"Venue {number}", "date": "2025-04-01"} for number in range(2, 9)],
        ]

        result = venue_history.build_venue_history(shows)

        self.assertEqual(len(result), 6)
        self.assertEqual(result[0], {
            "venue": "The Fox",
            "count": 3,
            "logo_url": "https://example.com/fox.png",
            "video_url": "https://youtube.com/watch?v=fox",
        })
        self.assertEqual([item["venue"] for item in result[1:]], [
            "Venue 2", "Venue 3", "Venue 4", "Venue 5", "Venue 6",
        ])

    def test_ties_sort_by_venue_name_and_empty_input_is_valid(self):
        result = venue_history.build_venue_history([
            {"venue": "Zulu"}, {"venue": "Alpha"}, {"venue": "alpha"},
        ])
        self.assertEqual([(item["venue"], item["count"]) for item in result], [
            ("Alpha", 2), ("Zulu", 1),
        ])
        self.assertEqual(venue_history.build_venue_history([]), [])

    def test_invalid_show_fails_instead_of_emitting_incomplete_data(self):
        with self.assertRaisesRegex(ValueError, "venue name"):
            venue_history.build_venue_history([{"date": "2025-01-01"}])

    def test_writes_json_to_requested_path(self):
        with tempfile.TemporaryDirectory() as folder:
            shows_file = Path(folder) / "past-shows.json"
            output_file = Path(folder) / "nested" / "venue-history.json"
            shows_file.write_text(json.dumps([{"venue": "The Fox"}]), encoding="utf-8")

            count = venue_history.write_venue_history(shows_file, output_file)

            self.assertEqual(count, 1)
            self.assertEqual(json.loads(output_file.read_text(encoding="utf-8"))[0]["venue"], "The Fox")
            self.assertFalse(output_file.with_name(output_file.name + ".tmp").exists())


if __name__ == "__main__":
    unittest.main()
