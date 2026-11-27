#!/usr/bin/env python3
"""Build a ranked venue summary from the generated past-shows JSON."""

import argparse
import json
import os
import sys
from pathlib import Path

MAX_VENUES = 6


def build_venue_history(shows, limit=MAX_VENUES):
    """Count past performances by venue and return the most-played venues first."""
    if not isinstance(shows, list):
        raise ValueError("past shows must be a JSON array")

    venues = {}
    for show in shows:
        if not isinstance(show, dict) or not isinstance(show.get("venue"), str) or not show["venue"].strip():
            raise ValueError("every past show must have a venue name")
        name = show["venue"].strip()
        key = name.casefold()
        venue = venues.setdefault(key, {"names": set(), "shows": []})
        venue["names"].add(name)
        venue["shows"].append(show)

    ranked = []
    for venue in venues.values():
        name = min(venue["names"], key=lambda value: (value.casefold(), value))
        ordered_shows = sorted(
            venue["shows"],
            key=lambda show: (str(show.get("date", "")), str(show.get("id", ""))),
            reverse=True,
        )
        logo_url = next(
            (show.get("venue_logo_url") for show in ordered_shows if show.get("venue_logo_url")),
            None,
        )
        video_url = next(
            (show.get("venue_video_url") for show in ordered_shows if show.get("venue_video_url")),
            None,
        )
        ranked.append({
            "venue": name,
            "count": len(venue["shows"]),
            "logo_url": logo_url,
            "video_url": video_url,
        })

    ranked.sort(key=lambda venue: (-venue["count"], venue["venue"].casefold(), venue["venue"]))
    return ranked[:limit]


def write_venue_history(shows_file, output_file, limit=MAX_VENUES):
    shows = json.loads(Path(shows_file).read_text(encoding="utf-8"))
    venues = build_venue_history(shows, limit)
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = output_file.with_name(output_file.name + ".tmp")
    try:
        temporary_file.write_text(json.dumps(venues, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(temporary_file, output_file)
    finally:
        if temporary_file.exists():
            temporary_file.unlink()
    return len(venues)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shows-file", default="data/past-shows.json", help="generated past-shows JSON file")
    parser.add_argument("--output", default="data/venue-history.json", help="venue summary JSON output path")
    parser.add_argument("--limit", type=int, default=MAX_VENUES, help="maximum number of venues to include")
    args = parser.parse_args(argv)

    if args.limit < 1:
        parser.error("--limit must be at least 1")
    try:
        count = write_venue_history(args.shows_file, args.output, args.limit)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"error: could not generate venue history: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {count} venue(s) to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
