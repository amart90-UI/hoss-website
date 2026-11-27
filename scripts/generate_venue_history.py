#!/usr/bin/env python3
"""Rank the venues the band has played most often, for the booking page's venue cards.

Reads data/past-shows.json (written by process_schedule.py) and writes data/venue-history.json:
the top venues by number of past shows, most-played first. Ties go to the most recent show.

Each entry has: venue, city, state, count, last_date, url (the venue's website from the
sheet's venue_url column, or null), logo (path of the logo file in img/venues/, or null) and
logo_background ("black", "white" or null for the default tile; set in LOGO_BACKGROUNDS below).

A venue's logo is a committed image named after the venue: img/venues/<slug>.<svg|webp|png|jpg>,
where the slug is the venue name in lowercase with every run of other characters turned into
a hyphen ("The Fox Theatre" -> "the-fox-theatre"). Venues without a logo file still get a card.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

MAX_VENUES = 6
LOGO_DIR = "img/venues"
LOGO_EXTENSIONS = (".svg", ".webp", ".png", ".jpg", ".jpeg")

# Background of the tile behind each venue's logo, so the logo is readable. Keyed by the venue's slug
# (see venue_slug); the value is "black" or "white". Venues not listed get the default cream tile.
LOGO_BACKGROUNDS = {
    "velvet-lounge": "black",
    "the-slab": "white",
    "the-old-mine": "white",
    "city-star": "white",
    "abbott-and-wallace": "black",
    "horsetooth-tavern": "white",
}
BACKGROUND_CHOICES = ("black", "white")


def venue_slug(name):
    """Logo file name for a venue, without the extension."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def find_logo(name, logo_dir=LOGO_DIR):
    """Path of the venue's logo (relative to the site root), or None if no file exists."""
    slug = venue_slug(name)
    if not slug:
        return None
    directory = Path(logo_dir)
    for extension in LOGO_EXTENSIONS:
        if (directory / (slug + extension)).is_file():
            return f"{directory.as_posix()}/{slug}{extension}"
    return None


def build_venue_history(shows, limit=MAX_VENUES, logo_dir=LOGO_DIR):
    """Count past shows per venue and return the `limit` most-played venues, best first."""
    if not isinstance(shows, list):
        raise ValueError("past shows must be a JSON array")

    venues = {}
    for show in shows:
        if not isinstance(show, dict) or not isinstance(show.get("venue"), str) or not show["venue"].strip():
            raise ValueError("every past show must have a venue name")
        name = show["venue"].strip()
        city = str(show.get("city") or "").strip()
        venues.setdefault((name.casefold(), city.casefold()), []).append(show)

    ranked = []
    for entries in venues.values():
        # Newest first, so the first non-empty value below is the most recent one.
        entries.sort(key=lambda show: (str(show.get("date", "")), str(show.get("id", ""))), reverse=True)
        latest = entries[0]
        name = latest["venue"].strip()
        ranked.append({
            "venue": name,
            "city": str(latest.get("city") or "").strip(),
            "state": str(latest.get("state") or "").strip(),
            "count": len(entries),
            "last_date": str(latest.get("date") or ""),
            "url": next((show["venue_url"] for show in entries if show.get("venue_url")), None),
            "logo": find_logo(name, logo_dir),
            "logo_background": LOGO_BACKGROUNDS.get(venue_slug(name)),
        })

    ranked.sort(key=lambda venue: (venue["venue"].casefold(), venue["city"].casefold()))
    ranked.sort(key=lambda venue: venue["last_date"], reverse=True)
    ranked.sort(key=lambda venue: venue["count"], reverse=True)
    return ranked[:limit]


def write_venue_history(shows_file, output_file, limit=MAX_VENUES, logo_dir=LOGO_DIR):
    shows = json.loads(Path(shows_file).read_text(encoding="utf-8"))
    venues = build_venue_history(shows, limit, logo_dir)
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = output_file.with_name(output_file.name + ".tmp")
    try:
        temporary_file.write_text(json.dumps(venues, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(temporary_file, output_file)
    finally:
        if temporary_file.exists():
            temporary_file.unlink()
    return venues


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--shows-file", default="data/past-shows.json", help="generated past-shows JSON file")
    parser.add_argument("--output", default="data/venue-history.json", help="venue summary JSON output path")
    parser.add_argument("--logo-dir", default=LOGO_DIR, help="folder holding the venue logo files")
    parser.add_argument("--limit", type=int, default=MAX_VENUES, help="maximum number of venues to include")
    args = parser.parse_args(argv)

    if args.limit < 1:
        parser.error("--limit must be at least 1")
    try:
        venues = write_venue_history(args.shows_file, args.output, args.limit, args.logo_dir)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"error: could not generate venue history: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {len(venues)} venue(s) to {args.output}")
    for venue in venues:
        note = "" if venue["logo"] else f"  (no logo: add {LOGO_DIR}/{venue_slug(venue['venue'])}.<svg|webp|png|jpg>)"
        print(f"  {venue['count']:>3}  {venue['venue']}{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
