"""Tests for scripts/event_pages.py."""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

import sys
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import event_pages as ep  # noqa: E402
from process_schedule import parse_csv


HEADER = "date,start_time,end_time,address,zip_code,venue,city,state,country,timezone,venue_url,performers,event_url,description\n"


def row(extra=""):
    return "7/18/2026,7:00 PM,10:00 PM,4791 W County Rd 38 E,80526,Horsetooth Tavern,Fort Collins,CO,US,America/Denver,https://example.com/venue,Ben + Anthony,https://example.com/event,\"Hoss & friends, \"\"live\"\"\"" + extra + "\n"


class EventPageTests(unittest.TestCase):
    def valid_event(self):
        event = parse_csv(HEADER + row())[0]
        event.update({
            "start": "2026-07-18T19:00:00-06:00",
            "end": "2026-07-18T22:00:00-06:00",
        })
        return ep.assign_event_paths([event])[0]

    def test_valid_page_data_and_timezone_offsets(self):
        event = self.valid_event()
        ep.validate_event(event)
        ld = ep.build_json_ld(event)
        self.assertEqual(ld["@type"], "Event")
        self.assertEqual(ld["name"], "Hoss and the Hangmen at Horsetooth Tavern")
        self.assertEqual(ld["url"], event["page_url"])
        self.assertEqual(ld["startDate"], "2026-07-18T19:00:00-06:00")
        self.assertTrue(ld["isAccessibleForFree"])
        self.assertEqual(ld["performer"]["@type"], "PerformingGroup")
        self.assertEqual(ld["organizer"], {
            "@type": "Organization",
            "name": "Hoss and the Hangmen",
            "url": "https://hossandthehangmen.com/",
        })
        self.assertEqual(ld["sameAs"], ["https://example.com/event"])
        self.assertEqual(ld["location"]["address"]["postalCode"], "80526")
        json.dumps(ld)

    def test_missing_optional_fields(self):
        event = self.valid_event()
        event["description"] = None
        event["event_url"] = None
        event["venue_url"] = None
        ld = ep.build_json_ld(event)
        self.assertNotIn("description", ld)
        self.assertNotIn("sameAs", ld)
        self.assertEqual(ld["url"], event["page_url"])
        self.assertNotIn("url", ld["location"])

    def test_missing_required_fields_and_bad_values(self):
        event = self.valid_event()
        event["address"] = ""
        event["zip_code"] = "bad"
        event["state"] = "Colorado"
        with self.assertRaises(ep.EventPageError) as ctx:
            ep.validate_event(event)
        message = str(ctx.exception)
        self.assertIn("address", message)
        self.assertIn("zip_code", message)
        self.assertIn("two-letter", message)

    def test_deterministic_unique_paths_and_collision_suffixes(self):
        event = self.valid_event()
        collision = dict(event)
        collision["id"] = "2026-07-18-2100-horsetooth-tavern"
        collision["start"] = "2026-07-18T21:00:00-06:00"
        assigned = ep.assign_event_paths([collision, event])
        paths = [item["page_path"] for item in assigned]
        self.assertEqual(len(set(paths)), 2)
        self.assertEqual(paths, ["/events/2026-07-18-horsetooth-tavern/", "/events/2026-07-18-horsetooth-tavern-2/"])

    def test_event_page_requires_address_and_postal_code(self):
        event = self.valid_event()
        event["address"] = None
        event["zip_code"] = None
        with tempfile.TemporaryDirectory() as folder:
            generated = ep.generate_event_pages([event], folder)
            self.assertEqual(generated, [])
            self.assertFalse((Path(folder) / "events").exists())

    def test_description_special_characters_are_json_safe(self):
        event = self.valid_event()
        event["description"] = 'A "great" show & café\nBring friends'
        ld = ep.build_json_ld(event)
        parsed = json.loads(json.dumps(ld))
        self.assertEqual(parsed["description"], event["description"])

    def test_calendar_link_uses_event_timezone_and_details(self):
        event = self.valid_event()
        url = ep.google_calendar_url(event)
        params = parse_qs(urlparse(url).query)
        self.assertEqual(params["dates"], ["20260719T010000Z/20260719T040000Z"])
        self.assertEqual(params["ctz"], ["America/Denver"])
        self.assertEqual(params["location"], ["Horsetooth Tavern, 4791 W County Rd 38 E, Fort Collins, CO, 80526"])

    def test_calendar_link_omitted_when_end_time_is_unknown(self):
        event = self.valid_event()
        event["end"] = None
        self.assertIsNone(ep.google_calendar_url(event))

    def test_generated_page_is_static_and_sitemap_is_valid(self):
        event = self.valid_event()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            generated = ep.generate_event_pages([event], root)
            page = root / generated[0]["page_path"].lstrip("/") / "index.html"
            text = page.read_text(encoding="utf-8")
            self.assertIn("Horsetooth Tavern", text)
            self.assertIn("Ben + Anthony", text)
            self.assertIn("application/ld+json", text)
            self.assertIn('<a class="skip-link" href="#main-content">Skip to main content</a>', text)
            self.assertIn('<main id="main-content" tabindex="-1">', text)
            self.assertIn("Directions", text)
            self.assertIn("Add to calendar", text)
            self.assertIn("google.com/maps/search/?api=1&amp;query=", text)
            ep.update_sitemap(root, generated)
            tree = ET.parse(root / "sitemap.xml")
            locs = [node.text for node in tree.getroot().iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
            self.assertIn(generated[0]["page_url"], locs)

    def test_stale_event_pages_removed(self):
        event = self.valid_event()
        with tempfile.TemporaryDirectory() as folder:
            stale = Path(folder) / "events" / "old-show"
            stale.mkdir(parents=True)
            (stale / "index.html").write_text("old", encoding="utf-8")
            ep.generate_event_pages([event], folder)
            self.assertFalse((Path(folder) / "events" / "old-show").exists())

    def test_script_generates_pages_from_schedule_json(self):
        event = self.valid_event()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "shows.json").write_text(json.dumps([event]), encoding="utf-8")
            self.assertEqual(ep.main(["--shows-file", str(data_dir / "shows.json"), "--site-root", folder]), 0)
            page = root / "events" / "2026-07-18-horsetooth-tavern" / "index.html"
            self.assertTrue(page.exists())
            ET.parse(root / "sitemap.xml")

    def test_past_events_excluded(self):
        event = self.valid_event()
        from process_schedule import split_shows, parse_csv
        shows = parse_csv(HEADER + row())
        upcoming, past = split_shows(shows, date(2026, 7, 19))
        self.assertEqual(upcoming, [])
        self.assertEqual(len(past), 1)


if __name__ == "__main__":
    unittest.main()
