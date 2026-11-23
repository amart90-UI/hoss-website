#!/usr/bin/env python3
"""Generate a poster for each upcoming show and save it next to the show's event page.

Reads the upcoming shows from data/shows.json (the same file the website uses) and draws
the venue, city, state, date, time and a QR code onto img/blank-poster.webp.
Each poster is written to <site-root>/events/<page-slug>/poster.jpg.

To move something on the poster, edit the LAYOUT section below. Run with --guides to draw
colored outlines of every placement area, and --only <text> to redraw just one show:

    python3 scripts/generate_event_posters.py --site-root . --only horsetooth --guides
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFont

from event_pages import short_url
from qr_code import QRError, make_qr

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "img" / "blank-poster.webp"
FONT = ROOT / "fonts" / "AmaticSC-Bold.ttf"

# =====================================================================================
# LAYOUT: everything you may want to nudge lives in this section.
#
# All numbers are pixels on the 3000 x 3996 blank poster. (0, 0) is the top-left corner,
# so a larger x moves right and a larger y moves DOWN.
#
# Text:  x = horizontal center of the text, y = the baseline (the line the letters sit on).
#        size = largest font size. The text shrinks (never grows) to fit within max_width.
#        tracking = extra space between letters (0 = normal).
# =====================================================================================

TAN = "#BDB199"   # venue, city and state text
NAVY = "#2B323F"  # date and time text (they sit on the tan box)


class Text(NamedTuple):
    x: int
    y: int
    size: int
    max_width: int
    color: str
    tracking: int = 0  # extra space between letters, in pixels


# "LIVE MUSIC at <VENUE>" across the top.
HEADLINE = Text(x=1500, y=190, size=190, max_width=2510, color=TAN, tracking=20)

# Venue name above the underline, and "City, ST" below it.
VENUE = Text(x=1500, y=3645, size=300, max_width=1260, color=TAN)
CITY = Text(x=1500, y=3880, size=170, max_width=1260, color=TAN, tracking=8)

# The two lines inside the tan box at the bottom right.
DATE = Text(x=2583, y=3650, size=260, max_width=580, color=NAVY)
TIME = Text(x=2583, y=3880, size=260, max_width=580, color=NAVY)

# QR code (a short /e/<code>/ address that redirects to the show's event page).
# left/top/size are the outer edge of the light tile, which includes the quiet margin that
# scanners need around the code. The tile is rounded down to a whole number of pixels per module.
QR_LEFT = 144
QR_TOP = 3350
QR_SIZE = 560
QR_MARGIN_MODULES = 3         # width of the margin, measured in QR modules
QR_TILE_COLOR = TAN #"#EFE7D2"
QR_DARK_COLOR = NAVY #"#2B323F"

JPEG_QUALITY = 88

# ===================================== end of LAYOUT =================================


class PosterError(Exception):
    """Invalid input that should stop the build."""


def format_date(iso_date):
    day = date.fromisoformat(iso_date)
    return f"{day.strftime('%b').upper()} {day.day}, {day.year}"


def _clock(time24):
    hour, minute = (int(part) for part in time24.split(":"))
    # Amatic SC draws lowercase letters as small capitals, which is the look of "11 A.M.".
    suffix = "am" if hour < 12 else "pm"
    hour = hour % 12 or 12
    return f"{hour}" if minute == 0 else f"{hour}:{minute:02d}", suffix


def format_time_range(start, end):
    start_number, start_suffix = _clock(start)
    if not end:
        return f"{start_number} {start_suffix}"
    end_number, end_suffix = _clock(end)
    if start_suffix == end_suffix:
        return f"{start_number} - {end_number} {end_suffix}"  # "9 - 11 pm"
    return f"{start_number} {start_suffix} - {end_number} {end_suffix}"


def _fitted_font(draw, text, spot):
    """Return (font, tracking, width) with the text shrunk to fit spot.max_width."""
    scale = 1.0
    for _ in range(2):  # the second pass corrects for font sizes being whole numbers
        size = max(1, int(spot.size * scale))
        tracking = spot.tracking * size / spot.size
        font = ImageFont.truetype(str(FONT), size)
        width = sum(draw.textlength(char, font=font) for char in text) + tracking * (len(text) - 1)
        if width <= spot.max_width:
            break
        scale *= spot.max_width / width
    return font, tracking, width


def draw_text(draw, text, spot):
    font, tracking, width = _fitted_font(draw, text, spot)
    x = spot.x - width / 2
    for char in text:
        draw.text((x, spot.y), char, fill=spot.color, font=font, anchor="ls")
        x += draw.textlength(char, font=font) + tracking

def draw_qr(draw, url):
    try:
        modules = make_qr(url)
    except QRError as error:
        print(f"warning: no QR code ({error})", file=sys.stderr)
        return
    cells = len(modules) + 2 * QR_MARGIN_MODULES
    cell = QR_SIZE // cells
    drawn = cell * cells  # whole pixels per module keep the edges sharp
    draw.rounded_rectangle((QR_LEFT, QR_TOP, QR_LEFT + drawn, QR_TOP + drawn), radius=cell * 2, fill=QR_TILE_COLOR)
    for row, line in enumerate(modules):
        for column, dark in enumerate(line):
            if dark:
                x = QR_LEFT + (column + QR_MARGIN_MODULES) * cell
                y = QR_TOP + (row + QR_MARGIN_MODULES) * cell
                draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=QR_DARK_COLOR)


def draw_guides(draw):
    """Outline each placement area so it is clear what to nudge."""
    for spot, color in ((HEADLINE, "red"), (VENUE, "red"), (CITY, "red"), (DATE, "blue"), (TIME, "blue")):
        draw.line((spot.x - spot.max_width // 2, spot.y, spot.x + spot.max_width // 2, spot.y), fill=color, width=4)
        draw.line((spot.x, spot.y - spot.size // 2, spot.x, spot.y), fill=color, width=4)
    draw.rectangle((QR_LEFT, QR_TOP, QR_LEFT + QR_SIZE, QR_TOP + QR_SIZE), outline="magenta", width=4)


def render_poster(background, show, output, guides=False):
    poster = background.copy()
    draw = ImageDraw.Draw(poster)
    venue = show["venue"]
    draw_text(draw, f"LIVE MUSIC at {venue.upper()}", HEADLINE)
    draw_text(draw, venue.upper(), VENUE)
    draw_text(draw, f"{show['city']}, {show['state']}".upper(), CITY)
    draw_text(draw, format_date(show["date"]), DATE)
    draw_text(draw, format_time_range(show["start_time"], show.get("end_time")), TIME)
    draw_qr(draw, short_url(show["page_path"]))
    if guides:
        draw_guides(draw)

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    poster.save(temporary, format="JPEG", quality=JPEG_QUALITY, subsampling=0, optimize=True)
    os.replace(temporary, output)


def generate_posters(shows_file, site_root, template=TEMPLATE, only=None, guides=False):
    try:
        shows = json.loads(Path(shows_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PosterError(f"could not read shows from {shows_file}: {error}") from error
    if not isinstance(shows, list):
        raise PosterError(f"{shows_file} must contain a JSON list of upcoming shows")
    try:
        background = Image.open(template).convert("RGB")
    except OSError as error:
        raise PosterError(f"could not read poster template {template}: {error}") from error

    written = []
    for show in shows:
        page_path = show.get("page_path")
        if not page_path:
            continue  # shows without a full address get no event page, so no poster either
        if only and only.lower() not in show.get("id", "").lower():
            continue
        try:
            date.fromisoformat(show["date"])
            if not all(show.get(key) for key in ("venue", "city", "state", "start_time")):
                raise KeyError
            output = Path(site_root) / page_path.strip("/") / "poster.jpg"
            render_poster(background, show, output, guides)
        except (KeyError, ValueError, TypeError):
            raise PosterError(f"show {show.get('id', '?')} needs a date, venue, city, state and start_time") from None
        written.append(output)
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--shows-file", default="data/shows.json")
    parser.add_argument("--site-root", default=".", help="directory containing events/ (posters go in events/<slug>/)")
    parser.add_argument("--template", default=str(TEMPLATE), help="blank poster image (PNG, JPG or WebP)")
    parser.add_argument("--only", help="only make posters whose show id contains this text")
    parser.add_argument("--guides", action="store_true", help="draw outlines of the placement areas")
    args = parser.parse_args(argv)
    try:
        written = generate_posters(args.shows_file, args.site_root, args.template, args.only, args.guides)
    except PosterError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Generated {len(written)} event poster(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
