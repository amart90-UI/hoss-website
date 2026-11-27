#!/usr/bin/env python3
"""Turn the published Google Sheets schedule CSV into the website's JSON data files.

Writes two files into the output directory:
  shows.json       upcoming shows (today and later), soonest first
  past-shows.json  past shows (before today), most recent first

Nothing is written unless every row is valid, so a failed run never replaces good data.

Input, in order of precedence:
  --csv FILE              read a local CSV file (for local testing)
  env SCHEDULE_CSV_URL    the full published-CSV link ("File > Share > Publish to web")

Standard library only. See README.md for the sheet layout. process_videos.py reuses the
download and error-reporting code in this file.
"""

import argparse
import csv
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("America/Denver")
URL_ENV_VAR = "SCHEDULE_CSV_URL"
FETCH_ATTEMPTS = 3
FETCH_TIMEOUT_SECONDS = 30

REQUIRED_COLUMNS = ["date", "start_time", "venue", "city", "state"]
OPTIONAL_COLUMNS = [
    "end_time", "venue_url", "event_url", "notes", "address", "zip_code", "zip",
    "performers", "description", "country", "timezone", "venue_logo_url", "venue_video_url",
]

DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")  # M/D/YYYY, day and month may be 1 or 2 digits
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AaPp][Mm])$")  # H:MM:SS AM/PM (seconds optional)
STATE_RE = re.compile(r"^[A-Za-z]{2}$")


class ScheduleError(Exception):
    """Any problem that must stop the run without writing output (also used by process_videos.py)."""


# --------------------------------------------------------------------------- reading the CSV

def fetch_csv(url, secret_name=URL_ENV_VAR):
    """Download the published CSV, retrying network errors.

    The URL is a secret, so error messages name the secret (secret_name) instead of showing the URL."""
    last_error = "unknown error"
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "hoss-website-schedule/1.0"})
            with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
                body = response.read()
            return decode_csv_bytes(body, secret_name)
        except urllib.error.HTTPError as error:
            last_error = f"HTTP {error.code}"
            if error.code in (400, 401, 403, 404):
                break  # retrying will not help
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = f"{type(error).__name__}"
        if attempt < FETCH_ATTEMPTS:
            time.sleep(2 * attempt)
    raise ScheduleError(
        f"Could not download the CSV ({last_error}). Check the {secret_name} secret and that the "
        "sheet tab is published to the web as CSV."
    )


def decode_csv_bytes(body, secret_name=URL_ENV_VAR):
    """Decode the downloaded bytes, and reject a web page (what Google returns for a wrong link)."""
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ScheduleError(f"The CSV is not valid UTF-8: {error}") from error
    head = text.lstrip()[:200].lower()
    if head.startswith("<!doctype") or head.startswith("<html") or "<html" in head:
        raise ScheduleError(
            f"The download returned a web page, not CSV. The {secret_name} secret probably points at the "
            "sheet itself instead of its 'Publish to web' CSV link, or the sheet is not shared/published."
        )
    return text


def read_csv_text(csv_path, env_var):
    """Read the CSV from a local file (--csv), or else download it from the URL in env_var."""
    if csv_path:
        return decode_csv_bytes(Path(csv_path).read_bytes(), env_var)
    url = os.environ.get(env_var, "").strip()
    if not url:
        raise ScheduleError(f"Environment variable {env_var} is not set (and no --csv given).")
    if not url.lower().startswith("https://"):
        raise ScheduleError(f"{env_var} must be a full https:// URL.")
    return fetch_csv(url, env_var)


def report_error(title, error):
    """Print an error. In GitHub Actions it becomes an annotation, shown on the run's summary page."""
    message = str(error)
    if os.environ.get("GITHUB_ACTIONS"):
        message = f"::error title={title}::" + message.replace("\n", "%0A")
    else:
        message = "error: " + message
    print(message, file=sys.stderr)


# --------------------------------------------------------------------------- parsing

def parse_date(value):
    """Parse a sheet date such as 9/4/2026 (M/D/YYYY)."""
    match = DATE_RE.match(value)
    if not match:
        raise ValueError(f"date '{value}' is not in M/D/YYYY format (for example 9/4/2026)")
    try:
        return date(int(match.group(3)), int(match.group(1)), int(match.group(2)))
    except ValueError:
        raise ValueError(f"date '{value}' is not a real calendar date") from None


def parse_time(value, column):
    """Parse '7:00:00 PM' (seconds optional) into (hour24, minute). Seconds are ignored."""
    match = TIME_RE.match(value)
    if not match:
        raise ValueError(f"{column} '{value}' is not in 'H:MM:SS AM/PM' format (for example 7:00:00 PM)")
    hour, minute, meridiem = int(match.group(1)), int(match.group(2)), match.group(4).upper()
    seconds = int(match.group(3) or 0)
    if not 1 <= hour <= 12 or minute > 59 or seconds > 59:
        raise ValueError(f"{column} '{value}' is not a valid time")
    if meridiem == "AM":
        hour = 0 if hour == 12 else hour
    else:
        hour = 12 if hour == 12 else hour + 12
    return hour, minute


def check_url(value, column):
    """Require a full http(s) link with no spaces."""
    if re.search(r"\s", value) or not re.match(r"^https?://[^/\s]+", value, re.IGNORECASE):
        raise ValueError(f"{column} '{value}' must be a full URL starting with http:// or https://")


def slugify(text):
    """"The Old Mine" -> "the-old-mine". Used in show IDs."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "show"


def local_iso(day, hour, minute):
    """ISO 8601 timestamp with the America/Denver UTC offset."""
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TIMEZONE).isoformat()


def build_show(row):
    """Check one row (a dict of stripped strings) and return its JSON record.

    Collects every problem in the row before failing, so one error message lists them all."""
    problems = []
    for column in REQUIRED_COLUMNS:
        if not row.get(column):
            problems.append(f"missing required value '{column}'")

    show_date = None
    start = end = None
    if row.get("date"):
        try:
            show_date = parse_date(row["date"])
        except ValueError as error:
            problems.append(str(error))
    if row.get("start_time"):
        try:
            start = parse_time(row["start_time"], "start_time")
        except ValueError as error:
            problems.append(str(error))
    if row.get("end_time"):
        try:
            end = parse_time(row["end_time"], "end_time")
        except ValueError as error:
            problems.append(str(error))
    if start and end and end == start:
        problems.append("end_time must occur after start_time")
    if row.get("state") and not STATE_RE.match(row["state"]):
        problems.append(f"state '{row['state']}' must be a two-letter code such as CO")
    for column in ("venue_url", "event_url", "venue_logo_url", "venue_video_url"):
        if row.get(column):
            try:
                check_url(row[column], column)
            except ValueError as error:
                problems.append(str(error))
    if problems:
        raise ValueError("; ".join(problems))

    start_iso = local_iso(show_date, *start)
    end_iso = None
    if end:
        end_day = show_date
        if end <= start:  # ends after midnight
            end_day = show_date + timedelta(days=1)
        end_iso = local_iso(end_day, *end)

    return {
        "id": f"{show_date.isoformat()}-{start[0]:02d}{start[1]:02d}-{slugify(row['venue'])}",
        "date": show_date.isoformat(),
        "start_time": f"{start[0]:02d}:{start[1]:02d}",
        "end_time": f"{end[0]:02d}:{end[1]:02d}" if end else None,
        "start": start_iso,
        "end": end_iso,
        "venue": row["venue"],
        "venue_url": row.get("venue_url") or None,
        "venue_logo_url": row.get("venue_logo_url") or None,
        "venue_video_url": row.get("venue_video_url") or None,
        "city": row["city"],
        "state": row["state"].upper(),
        "event_url": row.get("event_url") or None,
        "notes": row.get("notes") or None,
        "address": row.get("address") or None,
        "zip_code": row.get("zip_code") or row.get("zip") or None,
        "performers": row.get("performers") or None,
        "description": row.get("description") or None,
        "country": (row.get("country") or "US").upper(),
        "timezone": row.get("timezone") or "America/Denver",
    }


def parse_csv(text):
    """Return a list of show records, or raise ScheduleError listing every bad row."""
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise ScheduleError("The schedule CSV is empty.") from None
    columns = [name.strip().lower() for name in header]
    missing = [name for name in REQUIRED_COLUMNS if name not in columns]
    if missing:
        raise ScheduleError(f"The schedule CSV is missing required column(s): {', '.join(missing)}. Found: {columns}")
    known = set(REQUIRED_COLUMNS + OPTIONAL_COLUMNS)
    for name in columns:
        if name and name not in known:
            print(f"warning: ignoring unknown column '{name}'", file=sys.stderr)

    shows, errors, seen = [], [], {}
    for row_number, cells in enumerate(reader, start=2):  # row 1 is the header
        row = {}
        for name, cell in zip(columns, cells):
            if name in known:
                row[name] = cell.strip()
        if not any(cell.strip() for cell in cells):
            continue  # completely blank row
        try:
            show = build_show(row)
        except ValueError as error:
            errors.append(f"row {row_number}: {error}")
            continue
        if show["id"] in seen:
            errors.append(
                f"row {row_number}: duplicate of row {seen[show['id']]} (same date, start time and venue: {show['id']})"
            )
            continue
        seen[show["id"]] = row_number
        shows.append(show)

    if errors:
        raise ScheduleError("The schedule has invalid rows:\n  " + "\n  ".join(errors))
    if not shows:
        raise ScheduleError(
            "The schedule CSV has a header but no shows. Refusing to publish an empty schedule; "
            "this usually means the wrong tab or a failed export."
        )
    return shows


# --------------------------------------------------------------------------- classifying and writing

def denver_today(now=None):
    """Today's calendar date in America/Denver."""
    now = now or datetime.now(timezone.utc)
    return now.astimezone(TIMEZONE).date()


def split_shows(shows, today):
    """Upcoming = today or later (soonest first). Past = before today (most recent first)."""
    key = lambda show: (show["start"], show["id"])
    upcoming = sorted((s for s in shows if s["date"] >= today.isoformat()), key=key)
    past = sorted((s for s in shows if s["date"] < today.isoformat()), key=key, reverse=True)
    return upcoming, past


def to_json(records):
    return json.dumps(records, indent=2, ensure_ascii=False) + "\n"


def write_outputs(output_dir, upcoming, past):
    """Write both files, replacing existing ones only after both are fully written."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    targets = {"shows.json": to_json(upcoming), "past-shows.json": to_json(past)}
    temp_paths = {}
    try:
        for name, content in targets.items():
            temp = output_dir / (name + ".tmp")
            temp.write_bytes(content.encode("utf-8"))
            temp_paths[name] = temp
        for name, temp in temp_paths.items():
            os.replace(temp, output_dir / name)
    finally:
        for temp in temp_paths.values():
            if temp.exists():
                temp.unlink()


# --------------------------------------------------------------------------- command line

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", help="read this local CSV file instead of downloading the sheet")
    parser.add_argument("--output-dir", default="data", help="where to write shows.json and past-shows.json")
    parser.add_argument("--today", help="override today's date (YYYY-MM-DD); for testing")
    parser.add_argument("--generate-events", action="store_true", help="generate static event pages and update the sitemap")
    parser.add_argument("--site-root", default=".", help="website output root used with --generate-events")
    args = parser.parse_args(argv)

    try:
        shows = parse_csv(read_csv_text(args.csv, URL_ENV_VAR))
        try:
            today = date.fromisoformat(args.today) if args.today else denver_today()
        except ValueError as error:
            raise ScheduleError(f"--today must be YYYY-MM-DD: {error}") from error
        upcoming, past = split_shows(shows, today)
        try:
            from event_pages import assign_event_paths

            linked_upcoming = assign_event_paths(upcoming)
            upcoming_by_id = {show["id"]: show for show in linked_upcoming}
            upcoming = [upcoming_by_id[show["id"]] for show in upcoming]
        except ImportError:
            pass
        write_outputs(args.output_dir, upcoming, past)
        if args.generate_events:
            from event_pages import generate_event_pages, update_sitemap

            try:
                generated_events = generate_event_pages(upcoming, args.site_root)
                update_sitemap(args.site_root, generated_events)
                print(f"Generated {len(generated_events)} individual event page(s)")
            except Exception as error:
                raise ScheduleError(str(error)) from error
    except ScheduleError as error:
        report_error("Schedule processing failed", error)
        return 1

    print(f"Today (America/Denver): {today.isoformat()}")
    print(f"Wrote {len(upcoming)} upcoming and {len(past)} past show(s) to {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
