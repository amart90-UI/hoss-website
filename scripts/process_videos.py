#!/usr/bin/env python3
"""Turn the published Google Sheets video list into the website's data/videos.json.

Sheet columns: title, id (required); url (optional, not used; the id is what the site needs).
Row order in the sheet is the order on the page.

Writes videos.json into the output directory. The "channel_url" value is carried over from the
videos.json already in that directory (the one committed in the repo), so it is still edited there.
Nothing is written unless every row is valid, so a failed run never replaces good data.

Input, in order of precedence:
  --csv FILE           read a local CSV file (for local testing)
  env VIDEO_CSV_URL    the full published-CSV link ("File > Share > Publish to web")

Standard library only. Reuses the download and error-reporting code in process_schedule.py.
"""

import argparse
import csv
import io
import json
import os
import re
import sys
from pathlib import Path

from process_schedule import ScheduleError, read_csv_text, report_error

URL_ENV_VAR = "VIDEO_CSV_URL"
OUTPUT_NAME = "videos.json"
REQUIRED_COLUMNS = ["title", "id"]
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def parse_csv(text):
    """Return a list of {"id", "title"} records, or raise ScheduleError listing every bad row."""
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise ScheduleError("The video CSV is empty.") from None
    columns = [name.strip().lower() for name in header]
    missing = [name for name in REQUIRED_COLUMNS if name not in columns]
    if missing:
        raise ScheduleError(f"The video CSV is missing required column(s): {', '.join(missing)}. Found: {columns}")

    videos, errors, seen = [], [], {}
    for row_number, cells in enumerate(reader, start=2):  # row 1 is the header
        if not any(cell.strip() for cell in cells):
            continue  # completely blank row
        row = {name: cell.strip() for name, cell in zip(columns, cells)}
        title, video_id = row.get("title", ""), row.get("id", "")
        problems = []
        if not title:
            problems.append("missing required value 'title'")
        if not video_id:
            problems.append("missing required value 'id'")
        elif not VIDEO_ID_RE.match(video_id):
            problems.append(f"id '{video_id}' is not a valid YouTube video ID (11 letters, digits, '-' or '_')")
        elif video_id in seen:
            problems.append(f"duplicate of row {seen[video_id]} (same id {video_id})")
        if problems:
            errors.append(f"row {row_number}: " + "; ".join(problems))
            continue
        seen[video_id] = row_number
        videos.append({"id": video_id, "title": title})

    if errors:
        raise ScheduleError("The video list has invalid rows:\n  " + "\n  ".join(errors))
    if not videos:
        raise ScheduleError(
            "The video CSV has a header but no videos. Refusing to publish an empty gallery; "
            "this usually means the wrong tab or a failed export."
        )
    return videos


def existing_channel_url(output_dir):
    """Keep channel_url from the videos.json already in the output directory, if there is one."""
    path = Path(output_dir) / OUTPUT_NAME
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("channel_url")
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, str) and value.startswith("https://") else None


def build_document(videos, channel_url):
    """The videos.json structure: {"channel_url": ..., "videos": [...]}."""
    document = {}
    if channel_url:
        document["channel_url"] = channel_url
    document["videos"] = videos
    return document


def to_json(document):
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def write_output(output_dir, document):
    """Write the file via a temporary file so a crash never leaves a half-written videos.json."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    temp = output_dir / (OUTPUT_NAME + ".tmp")
    try:
        temp.write_bytes(to_json(document).encode("utf-8"))
        os.replace(temp, output_dir / OUTPUT_NAME)
    finally:
        if temp.exists():
            temp.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", help="read this local CSV file instead of downloading the sheet")
    parser.add_argument("--output-dir", default="data", help="where to write videos.json")
    args = parser.parse_args(argv)

    try:
        videos = parse_csv(read_csv_text(args.csv, URL_ENV_VAR))
        write_output(args.output_dir, build_document(videos, existing_channel_url(args.output_dir)))
    except ScheduleError as error:
        report_error("Video processing failed", error)
        return 1

    print(f"Wrote {len(videos)} video(s) to {args.output_dir}/{OUTPUT_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
