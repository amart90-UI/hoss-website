#!/usr/bin/env python3
"""Generate static event pages and sitemap entries for upcoming shows."""

import argparse
import html
import json
import re
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

from process_schedule import check_url, slugify

BAND_NAME = "Hoss and the Hangmen"
BAND_URL = "https://hossandthehangmen.com/"
BASE_URL = "https://hossandthehangmen.com"
EVENT_IMAGE_PATH = "img/og-image.jpg"
TIMEZONE = "America/Denver"

STATE_RE = re.compile(r"^[A-Za-z]{2}$")
POSTAL_RE = re.compile(r"^\d{5}(?:-\d{4})?$")


class EventPageError(Exception):
    pass


def event_slug(venue):
    return slugify(venue)


def assign_event_paths(events):
    """Assign deterministic page paths to shows with complete venue addresses."""
    assigned = []
    used = {}
    for event in sorted(events, key=lambda item: (item["date"], item["start"], item["id"])):
        if not event.get("address") or not event.get("zip_code"):
            copy = dict(event)
            copy.pop("page_path", None)
            copy.pop("page_url", None)
            assigned.append(copy)
            continue
        base = f"{event['date']}-{event_slug(event['venue'])}"
        suffix = used.get(base, 0)
        used[base] = suffix + 1
        path_slug = base if suffix == 0 else f"{base}-{suffix + 1}"
        copy = dict(event)
        copy["page_path"] = f"/events/{path_slug}/"
        copy["page_url"] = BASE_URL + copy["page_path"]
        assigned.append(copy)
    return assigned


def validate_event(event, row_number=None):
    prefix = f"row {row_number}: " if row_number is not None else ""
    problems = []
    for column in ("venue", "address", "city", "state", "zip_code"):
        if not event.get(column):
            problems.append(f"missing required value '{column}'")
    if event.get("state") and not STATE_RE.match(event["state"]):
        problems.append(f"state '{event['state']}' must be a two-letter code such as CO")
    if event.get("zip_code") and not POSTAL_RE.match(event["zip_code"]):
        problems.append(f"zip_code '{event['zip_code']}' must be a 5-digit US ZIP code")
    if event.get("country") and event["country"].upper() != "US":
        problems.append(f"country '{event['country']}' must be US")
    if event.get("timezone") and event["timezone"] != TIMEZONE:
        problems.append(f"timezone '{event['timezone']}' must be {TIMEZONE}")
    for column in ("venue_url", "event_url"):
        if event.get(column):
            try:
                check_url(event[column], column)
            except ValueError as error:
                problems.append(str(error))
    if problems:
        raise EventPageError(prefix + "; ".join(problems))
    return event


def build_json_ld(event):
    data = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": f"{BAND_NAME} at {event['venue']}",
        "url": event["page_url"],
        "startDate": event["start"],
        "eventStatus": "https://schema.org/EventScheduled",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "image": BASE_URL + "/" + EVENT_IMAGE_PATH,
        "isAccessibleForFree": True,
        "performer": {
            "@type": "PerformingGroup",
            "name": BAND_NAME,
            "url": BAND_URL,
        },
        "organizer": {
            "@type": "Organization",
            "name": BAND_NAME,
            "url": BAND_URL,
        },
        "location": {
            "@type": "Place",
            "name": event["venue"],
            "address": {
                "@type": "PostalAddress",
                "streetAddress": event["address"],
                "addressLocality": event["city"],
                "addressRegion": event["state"],
                "postalCode": event["zip_code"],
                "addressCountry": "US",
            },
        },
    }
    if event.get("end"):
        data["endDate"] = event["end"]
    if event.get("description"):
        data["description"] = event["description"]
    if event.get("event_url"):
        data["sameAs"] = [event["event_url"]]
    if event.get("venue_url"):
        data["location"]["url"] = event["venue_url"]
    return data


def format_date(iso_date):
    value = date.fromisoformat(iso_date)
    weekdays = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    months = ("January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December")
    return f"{weekdays[value.weekday()]}, {months[value.month - 1]} {value.day}, {value.year}"


def format_time(time24):
    hour, minute = (int(part) for part in time24.split(":"))
    suffix = "AM" if hour < 12 else "PM"
    hour = hour % 12 or 12
    return f"{hour}:{minute:02d} {suffix}"


def google_calendar_url(event):
    if not event.get("start") or not event.get("end"):
        return None
    start = datetime.fromisoformat(event["start"]).astimezone(timezone.utc)
    end = datetime.fromisoformat(event["end"]).astimezone(timezone.utc)
    address = ", ".join(filter(None, (
        event.get("venue"),
        event.get("address"),
        event.get("city"),
        event.get("state"),
        event.get("zip_code"),
    )))
    params = {
        "action": "TEMPLATE",
        "text": f"{BAND_NAME} at {event['venue']}",
        "dates": start.strftime("%Y%m%dT%H%M%SZ") + "/" + end.strftime("%Y%m%dT%H%M%SZ"),
        "ctz": event.get("timezone") or TIMEZONE,
        "location": address,
        "details": event.get("description") or "",
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(params)


def render_event_page(event):
    title = f"{BAND_NAME} at {event['venue']}"
    description = event.get("description") or f"{title} in {event['city']}, {event['state']}."
    venue_link = (
        f'<a href="{html.escape(event["venue_url"], quote=True)}" target="_blank" rel="noopener">'
        f'{html.escape(event["venue"], quote=True)}</a>'
        if event.get("venue_url") else html.escape(event["venue"])
    )
    event_link = (
        '<p><a class="event-announcement" href="'
        + html.escape(event["event_url"], quote=True)
        + '" target="_blank" rel="noopener">Event Announcement</a></p>'
        if event.get("event_url") else ""
    )
    performers = (
        f'<p><strong>Performers:</strong> {html.escape(event["performers"])}</p>'
        if event.get("performers") else ""
    )
    description_html = (
        f'<p class="event-description">{html.escape(description)}</p>'
    )
    time_range = format_time(event["start_time"])
    if event.get("end_time"):
        time_range += " &ndash; " + format_time(event["end_time"])
    json_ld = json.dumps(build_json_ld(event), ensure_ascii=False, indent=2)
    map_query = ", ".join(filter(None, (
        event.get("venue"),
        event.get("address"),
        event.get("city"),
        event.get("state"),
        event.get("zip_code"),
    )))
    maps_url = "https://www.google.com/maps/search/?" + urlencode({"api": "1", "query": map_query})
    calendar_url = google_calendar_url(event)
    event_actions = (
        '<div class="event-actions">'
        f'<a class="show-action-link" href="{html.escape(maps_url, quote=True)}" target="_blank" rel="noopener">Directions</a>'
        + (
            f'<a class="show-action-link" href="{html.escape(calendar_url, quote=True)}" target="_blank" rel="noopener">Add to calendar</a>'
            if calendar_url else ""
        )
        + '</div>'
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description, quote=True)}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{html.escape(event["page_url"], quote=True)}">
<link href="https://fonts.googleapis.com/css2?family=Faculty+Glyphic:wght@400&amp;display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Amatic+SC:wght@400;700&amp;display=swap" rel="stylesheet">
<link rel="stylesheet" href="../../css/style.css">
<link rel="icon" type="image/svg+xml" href="../../img/favicon.svg">
<script type="application/ld+json">
{json_ld}
</script>
</head>
<body class="event-page">
<header class="event-header">
  <a class="event-brand" href="../../" aria-label="Hoss and the Hangmen home">
    <img src="../../img/hoss_logo_white.svg" alt="Hoss and the Hangmen" width="244" height="147">
  </a>
</header>
<main>
<article class="event-content">
  <h1>{html.escape(title)}</h1>
  <img class="event-image" src="../../{EVENT_IMAGE_PATH}" alt="Hoss and the Hangmen promotional image" width="1200" height="630">
  <p class="event-date"><strong>{format_date(event["date"])}</strong></p>
  <p class="event-time"><strong>{time_range}</strong></p>
  <p><strong>Venue:</strong> {venue_link}</p>
  <p>{html.escape(event["address"])}<br>{html.escape(event["city"])}, {html.escape(event["state"])} {html.escape(event["zip_code"])}</p>
  {event_actions}
  {performers}
  {description_html}
  {event_link}
  <p class="more-link"><a href="../../#shows">&larr; Back to all shows</a></p>
</article>
</main>
<footer>
  <p>&copy; 2026 Hoss and the Hangmen</p>
</footer>
</body>
</html>
"""


def generate_event_pages(events, site_root):
    site_root = Path(site_root)
    assigned = [event for event in assign_event_paths(events) if event.get("page_path")]
    errors = []
    for event in assigned:
        try:
            validate_event(event)
        except EventPageError as error:
            errors.append(str(error))
    if errors:
        raise EventPageError("The schedule has invalid event page rows:\n  " + "\n  ".join(errors))

    events_root = site_root / "events"
    if events_root.exists():
        shutil.rmtree(events_root)
    if assigned:
        events_root.mkdir(parents=True)

    for event in assigned:
        page_dir = site_root / event["page_path"].lstrip("/")
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(render_event_page(event), encoding="utf-8")
    return assigned


def update_sitemap(site_root, events):
    site_root = Path(site_root)
    sitemap_path = site_root / "sitemap.xml"
    ns = "http://www.sitemaps.org/schemas/sitemap/0.9"
    ET.register_namespace("", ns)

    static_urls = [BASE_URL + "/"]
    if sitemap_path.exists():
        try:
            root = ET.fromstring(sitemap_path.read_text(encoding="utf-8"))
            for loc in root.findall(f".//{{{ns}}}loc"):
                url = loc.text or ""
                if url == BASE_URL + "/" or "/events/" not in url:
                    if url and url not in static_urls:
                        static_urls.append(url)
        except ET.ParseError:
            pass

    urls = static_urls + [event["page_url"] for event in events]
    urls = list(dict.fromkeys(urls))
    root = ET.Element(f"{{{ns}}}urlset")
    for url in urls:
        node = ET.SubElement(root, f"{{{ns}}}url")
        loc = ET.SubElement(node, f"{{{ns}}}loc")
        loc.text = url
    sitemap_path.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shows-file", default="data/shows.json", help="upcoming shows JSON from process_schedule.py")
    parser.add_argument("--site-root", default=".", help="directory where the site and event pages are served from")
    args = parser.parse_args(argv)

    shows_file = Path(args.shows_file)
    try:
        events = json.loads(shows_file.read_text(encoding="utf-8"))
        if not isinstance(events, list):
            raise EventPageError(f"{shows_file} must contain a JSON list of upcoming events")
        generated = generate_event_pages(events, args.site_root)
        update_sitemap(args.site_root, generated)
    except (OSError, json.JSONDecodeError, EventPageError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"Generated {len(generated)} individual event page(s) in {Path(args.site_root) / 'events'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
