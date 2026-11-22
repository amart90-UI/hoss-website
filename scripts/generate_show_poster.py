#!/usr/bin/env python3
"""Generate a JPEG poster and a simple /showposter/ page from upcoming shows."""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

WIDTH = 1080
HEIGHT = 1350
INK = "#323536"
PAPER = "#efe1c6"
ACCENT = "#BDB199"
BACKGROUND = Path("img/next-show-bg.png")
FONT_DIRECTORY = Path(__file__).resolve().parent.parent / "fonts"


class PosterError(Exception):
    """Invalid poster input that should stop the build."""


def _time_label(value):
    try:
        hour, minute = (int(part) for part in value.split(":"))
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError
    except (AttributeError, ValueError):
        raise PosterError(f"invalid show time '{value}'") from None
    suffix = "AM" if hour < 12 else "PM"
    return f"{hour % 12 or 12}:{minute:02d}", suffix


def format_time_range(start, end):
    start_time, start_suffix = _time_label(start)
    if not end:
        return f"{start_time} {start_suffix}"
    end_time, end_suffix = _time_label(end)
    if start_suffix == end_suffix:
        return f"{start_time} - {end_time} {end_suffix}"
    return f"{start_time} {start_suffix} - {end_time} {end_suffix}"


def format_groups(shows):
    grouped = defaultdict(list)
    for show in shows:
        try:
            date.fromisoformat(show["date"])
            venue = show["venue"]
            city = show["city"]
            state = show["state"]
            start = show["start_time"]
            end = show.get("end_time")
        except (KeyError, TypeError, ValueError):
            raise PosterError("each show must have a date, venue, city, state, and start_time") from None
        if not all(isinstance(value, str) and value for value in (venue, city, state, start)):
            raise PosterError("each show must have a date, venue, city, state, and start_time")
        grouped[show["date"]].append((start, venue, f"{city}, {state} {format_time_range(start, end)}"))

    result = []
    for show_date in sorted(grouped):
        day = date.fromisoformat(show_date)
        events = sorted(grouped[show_date])
        result.append((f"{day.strftime('%b')} {day.day}", [(venue, location) for _, venue, location in events]))
    return result


def _font_path(bold, family):
    if family == "faculty":
        return str(FONT_DIRECTORY / "FacultyGlyphic-Regular.ttf")
    if family == "amatic":
        return str(FONT_DIRECTORY / "AmaticSC-Bold.ttf")
    candidates = (
        [
            "C:/Windows/Fonts/arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ]
        if bold
        else [
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]
    )
    return next((candidate for candidate in candidates if Path(candidate).is_file()), None)


def _load_font(size, bold=False, family="sans"):
    font_path = _font_path(bold, family)
    if font_path:
        return ImageFont.truetype(font_path, size=size)
    return ImageFont.load_default(size=size)


def _fit_font(draw, text, size, max_width, bold=False, family="sans"):
    font = _load_font(size, bold, family)
    while draw.textbbox((0, 0), text, font=font)[2] > max_width and size > 12:
        size -= 1
        font = _load_font(size, bold, family)
    return font


def _background_image(background):
    if background.is_file():
        try:
            image = ImageOps.fit(Image.open(background).convert("RGB"), (WIDTH, HEIGHT))
        except (OSError, ValueError) as error:
            raise PosterError(f"could not read background image {background}: {error}") from error
    else:
        print(f"warning: {background} not found; using a solid background", file=sys.stderr)
        image = Image.new("RGB", (WIDTH, HEIGHT), INK)

    image = image.convert("RGBA")
    image.alpha_composite(Image.new("RGBA", image.size, (50, 53, 54, 95)))
    return image


def render_poster(groups, background, output):
    image = _background_image(Path(background))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((36, 36, WIDTH - 36, HEIGHT - 36), radius=28, fill=(50, 53, 54, 218), outline=ACCENT, width=3)

    title_font = _load_font(82, bold=True)
    title = "Upcoming shows"
    title_bounds = draw.textbbox((0, 0), title, font=title_font)
    title_width = title_bounds[2] - title_bounds[0]
    draw.text(((WIDTH - title_width) / 2, 88), title, fill=PAPER, font=title_font)
    draw.rounded_rectangle((150, 210, WIDTH - 150, 216), radius=3, fill=ACCENT)

    event_count = sum(len(events) for _, events in groups)
    required_height = len(groups) * 62 + event_count * 88
    scale = min(1.0, (HEIGHT - 330) / max(required_height, 1))
    date_size = max(24, int(48 * scale))
    venue_size = max(20, int(36 * scale))
    location_size = max(16, int(29 * scale))
    y = 266
    max_width = WIDTH - 200
    if not groups:
        message = "No upcoming shows scheduled"
        message_font = _fit_font(draw, message, 34, max_width, family="faculty")
        message_width = draw.textbbox((0, 0), message, font=message_font)[2]
        draw.text(((WIDTH - message_width) / 2, y), message, fill=PAPER, font=message_font)
    for date_label, events in groups:
        date_font = _fit_font(draw, date_label, date_size, max_width, family="amatic")
        draw.text((100, y), date_label, fill=ACCENT, font=date_font)
        y += date_size + 9
        for venue, location in events:
            venue_font = _fit_font(draw, venue, venue_size, max_width, family="faculty")
            location_font = _fit_font(draw, location, location_size, max_width, family="faculty")
            draw.text((100, y), venue, fill=PAPER, font=venue_font)
            y += venue_size + 3
            draw.text((100, y), location, fill=PAPER, font=location_font)
            y += location_size + 17
        y += 12

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    image.convert("RGB").save(temporary, format="JPEG", quality=92, optimize=True)
    os.replace(temporary, output)


def write_poster_page(image_path, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    image_url = "/" + str(image_path).replace("\\", "/").lstrip("/")
    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Upcoming shows for Hoss and the Hangmen.">
  <meta property="og:title" content="Upcoming shows - Hoss and the Hangmen">
  <meta property="og:image" content="https://hossandthehangmen.com{image_url}">
  <title>Upcoming shows - Hoss and the Hangmen</title>
  <style>
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: {INK}; }}
    img {{ display: block; width: min(100%, 810px); height: auto; }}
  </style>
</head>
<body><img src="{image_url}" alt="Upcoming shows for Hoss and the Hangmen"></body>
</html>
"""
    page_path = output / "index.html"
    temporary = page_path.with_name(page_path.name + ".tmp")
    temporary.write_text(page, encoding="utf-8")
    os.replace(temporary, page_path)


def generate_poster(shows_file, background, output, page_output):
    try:
        shows = json.loads(Path(shows_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PosterError(f"could not read shows from {shows_file}: {error}") from error
    if not isinstance(shows, list):
        raise PosterError(f"{shows_file} must contain a JSON list of upcoming shows")
    groups = format_groups(shows)
    render_poster(groups, background, output)
    write_poster_page(output, page_output)
    return sum(len(events) for _, events in groups)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shows-file", default="data/shows.json")
    parser.add_argument("--background", default=str(BACKGROUND))
    parser.add_argument("--output", default="img/upcomingshow.jpg")
    parser.add_argument("--page-output", default="showposter")
    args = parser.parse_args(argv)
    try:
        count = generate_poster(args.shows_file, args.background, args.output, args.page_output)
    except PosterError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Generated upcoming show poster with {count} show(s) at {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
