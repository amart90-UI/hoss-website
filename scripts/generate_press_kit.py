#!/usr/bin/env python3
"""Generate the downloads on the /booking/ page: the one-page press kit PDF and the JPG photos.

Writes into <site-root>/booking/press/:
  hoss-and-the-hangmen-press-kit.pdf   one US Letter page (picture of the page, plus link
                                       annotations and an invisible text layer so the text
                                       can be searched, selected and read aloud)
  hoss-and-the-hangmen-*.jpg           band photo and member photos, converted from the WebP files in img/

The PDF's "Where we've played" list comes from <site-root>/data/past-shows.json when that file
exists (the deploy workflow creates it); without it the section is left out. No dependencies
beyond Pillow, which the poster scripts already use.
"""
import argparse
import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent
FONT_DIRECTORY = REPO_ROOT / "fonts"
IMAGE_DIRECTORY = REPO_ROOT / "img"

OUTPUT_SUBDIRECTORY = Path("booking") / "press"
PDF_NAME = "hoss-and-the-hangmen-press-kit.pdf"

# Files the booking page links to (booking/index.html). A test checks that these match the page.
PHOTOS = {
    "hoss-and-the-hangmen-band-photo.jpg": "hero-band.webp",
    "hoss-and-the-hangmen-ben.jpg": "ben.webp",
    "hoss-and-the-hangmen-anthony.jpg": "anthony.webp",
    "hoss-and-the-hangmen-alex.jpg": "alex.webp",
}
PHOTO_QUALITY = 90

BAND_NAME = "Hoss and the Hangmen"
TAGLINE = "Northern Colorado country, folk & Americana"
SUBTAGLINE = "Covers and original songs for breweries, venues, festivals, & private events."
EMAIL = "hossandthehangmen@gmail.com"
EMAIL_SUBJECT = "Booking inquiry for Hoss and the Hangmen"
WEBSITE_LABEL = "hossandthehangmen.com/booking"
WEBSITE_URL = "https://hossandthehangmen.com/booking/"
INSTAGRAM_URL = "https://www.instagram.com/hossandthehangmen"
YOUTUBE_URL = "https://youtube.com/@hossandthehangmen"
FACEBOOK_URL = "https://www.facebook.com/people/Hoss-and-the-Hangmen/61590706506140/"
PHOTO_CREDIT = "Photo: Darrin Williams"
PHOTOGRAPHER_URL = "https://darrinwilliamsmedia.com"
PHOTOGRAPHER_LABEL = "darrinwilliamsmedia.com"

BIO = (
    "Hoss and the Hangmen bring a distinctly Colorado spirit to the Northern Colorado music scene, blending "
    "traditional country, outlaw influences, and modern Americana. Fronted by Hoss, a guitar-slinging singing "
    "cowboy, the group pairs storytelling, rugged melodies, and an unpretentious approach to live performances. "
    "The Hangmen join Hoss for a duo or a full 3-man lineup allowing the band to move comfortably between "
    "small, intimate solo performances to energetic shows that fill the room. But in any case, the mission is "
    "the same: good songs, engaging performances, and plenty of grit and personality."
)
# A second short paragraph under the bio, and the link line under it.
BIO_EXTRA = (
    "The set list is mostly covers, with a handful of original songs mixed in, drawing from artists like "
    "Johnny Cash, Garth Brooks, Colter Wall, Zach Bryan, and Trampled by Turtles."
)

# Band members, as shown on the booking page (which writes "guitar + vocals", like the home page).
MEMBERS = [("Ben (Hoss)", "guitar and vocals"), ("Anthony", "upright bass"), ("Alex", "drums")]
# (name, short label, detail); the booking page shows the label and the detail separately.
LINEUPS = [
    ("Trio", "The full band", "Acoustic guitar & vocals, upright bass, and drums."),
    ("Duo", "Acoustic duo", "A stripped-down version of the band. Guitar & vocals with either bass or drums."),
    ("Solo", "Solo act", "Guitar & vocals. The most intimate setup."),
]
# Booking details shown in the PDF. The booking page shows all of these (plus a few more), worded the same.
FACTS = [
    ("Set length", "Configurable sets, up to 3 hours of music"),
    ("Load-in", "30 minutes for load-in and setup"),
    ("Service area", "Northern Colorado and the Front Range"),
    ("Sound", "PA provided for typical gigs"),
    ("Power", "Required, except at very small venues where amplification isn't needed"),
    (
        "Content",
        "Generally family-friendly, with some adult-oriented material: dark subject matter and the "
        "occasional swear, nothing worse than you'd hear on the radio.",
    ),
    ("Rates", "Please inquire for rates"),
]
# What to expect when booking the band: (title, text). Shown on the booking page and in the PDF.
EXPECT = [
    ("Responsive", "We communicate clearly and promptly throughout the booking process, making it easy to coordinate details and stay on the same page."),
    ("Professional and punctual", "We show up prepared, on time, and ready to deliver, respecting your schedule, your staff, and your customers."),
    ("Built around your venue", "We adapt to your space, audience, and needs to make a great experience for your customers and your night a success."),
]
INQUIRY_HINT = "Please include the date, venue, event type, desired lineup and budget."

# ------------------------------------------------------------------ LAYOUT (inches unless noted)

PAGE_WIDTH_IN = 8.5
PAGE_HEIGHT_IN = 11.0
DPI = 300

BACKGROUND = "#323536"
FOOTER_BACKGROUND = "#3A3E3F"
TEXT = "#efe1c6"
MUTED = "#BDB199"
ACCENT = "#ff9760"

MARGIN = 0.6
PHOTO_HEIGHT = 2.1          # the band photo across the top
PHOTO_FADE = 0.6            # how much of the photo's bottom fades into the background
PHOTO_TOP_OFFSET = 60       # pixels (at 300 dpi) cut from the top of the scaled photo
LOGO_TOP = 1.6
LOGO_WIDTH = 2.6
HEADER_TEXT_X = 3.7         # tagline column, right of the logo
CONTENT_TOP = 3.4          # where the two columns start
LEFT_X = MARGIN
LEFT_WIDTH = 3.5
RIGHT_X = 4.3
RIGHT_WIDTH = PAGE_WIDTH_IN - MARGIN - RIGHT_X
FACT_LABEL_WIDTH = 0.95
FOOTER_TOP = 9.75
CONTENT_BOTTOM = 9.6        # the columns must end above this
MAX_VENUES = 10

BODY_PT = 9.5
BODY_LEADING = 1.42
SMALL_PT = 7.5
HEADING_PT = 24


class PressKitError(Exception):
    """Invalid input or a layout that does not fit; stops the build."""


def px(inches):
    return round(inches * DPI)


def points_to_px(points):
    return round(points * DPI / 72)


# ------------------------------------------------------------------ past venues

def highlight_venues(shows, limit=MAX_VENUES):
    """Venues ranked by number of shows, then by most recent show (scripts/generate_venue_history.py uses the same rule).

    `shows` is the contents of past-shows.json, most recent first."""
    venues = {}
    for index, show in enumerate(shows):
        if not isinstance(show, dict):
            continue
        name = show.get("venue")
        if not isinstance(name, str) or not name.strip():
            continue
        city = show.get("city")
        city = city.strip() if isinstance(city, str) else ""
        key = (name.strip().lower(), city.lower())
        if key in venues:
            venues[key]["count"] += 1
        else:
            venues[key] = {"name": name.strip(), "city": city, "count": 1, "first": index}
    ranked = sorted(venues.values(), key=lambda v: (-v["count"], v["first"]))
    return ranked[:limit]


def load_past_shows(path):
    path = Path(path)
    if not path.exists():
        return []
    try:
        shows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PressKitError(f"could not read {path}: {error}") from None
    if not isinstance(shows, list):
        raise PressKitError(f"{path} must contain a JSON list")
    return shows


# ------------------------------------------------------------------ drawing

def _font(name, points):
    return ImageFont.truetype(str(FONT_DIRECTORY / name), points_to_px(points))


def body_font(points=BODY_PT):
    return _font("FacultyGlyphic-Regular.ttf", points)


def heading_font(points=HEADING_PT):
    return _font("AmaticSC-Bold.ttf", points)


class Page:
    """A page image plus what the PDF needs on top of it: text runs and link rectangles."""

    def __init__(self):
        self.image = Image.new("RGB", (px(PAGE_WIDTH_IN), px(PAGE_HEIGHT_IN)), BACKGROUND)
        self.draw = ImageDraw.Draw(self.image)
        self.runs = []    # (x, baseline y, text, size in points), pixels
        self.links = []   # (left, top, right, bottom, url), pixels

    def text(self, x, baseline, text, font, points, fill, link=None):
        """Draw one line with its left end at x. Returns its width in pixels."""
        self.draw.text((x, baseline), text, font=font, fill=fill, anchor="ls")
        width = round(font.getlength(text))
        self.runs.append((x, baseline, text, points))
        if link:
            ascent = points_to_px(points)
            self.links.append((x, baseline - ascent, x + width, baseline + round(ascent * 0.3), link))
        return width

    def wrapped(self, x, top, width, text, font, points, fill, leading=BODY_LEADING):
        """Draw word-wrapped text. `top` is the top of the first line; returns the bottom of the last."""
        line_height = round(points_to_px(points) * leading)
        baseline = top + points_to_px(points)
        line = ""
        for word in text.split():
            trial = f"{line} {word}".strip()
            if line and font.getlength(trial) > width:
                self.text(x, baseline, line, font, points, fill)
                baseline += line_height
                line = word
            else:
                line = trial
        if line:
            self.text(x, baseline, line, font, points, fill)
        return baseline - points_to_px(points) + line_height

    def heading(self, x, top, label):
        """Section heading with a short rule under it. Returns the top for what follows."""
        font = heading_font()
        baseline = top + points_to_px(HEADING_PT) * 0.8
        self.text(x, round(baseline), label, font, HEADING_PT, MUTED)
        rule_y = round(baseline) + px(0.07)
        self.draw.rectangle((x, rule_y, x + px(0.7), rule_y + 4), fill=MUTED)
        return rule_y + px(0.14)


def _hero_photo():
    photo = Image.open(IMAGE_DIRECTORY / "hero-band.webp").convert("RGB")
    width = px(PAGE_WIDTH_IN)
    photo = photo.resize((width, round(photo.height * width / photo.width)), Image.LANCZOS)
    height = px(PHOTO_HEIGHT)
    top = PHOTO_TOP_OFFSET
    if top + height > photo.height:
        raise PressKitError("band photo is too short for the press kit layout")
    photo = photo.crop((0, top, width, top + height))
    fade = px(PHOTO_FADE)
    mask = Image.linear_gradient("L").resize((width, fade))
    photo.paste(Image.new("RGB", (width, fade), BACKGROUND), (0, height - fade), mask)
    return photo


def render_page(venues, photo):
    """Draw the page. Returns (Page, bottom of the columns in pixels)."""
    page = Page()
    page.image.paste(photo, (0, 0))

    logo = Image.open(IMAGE_DIRECTORY / "hoss-logo-light.png").convert("RGBA")
    logo_width = px(LOGO_WIDTH)
    logo = logo.resize((logo_width, round(logo.height * logo_width / logo.width)), Image.LANCZOS)
    page.image.paste(logo, (px(MARGIN), px(LOGO_TOP)), logo)
    page.runs.append((px(MARGIN), px(LOGO_TOP) + logo.height, BAND_NAME, 36))
    page.draw = ImageDraw.Draw(page.image)

    # Tagline beside the logo
    header_width = px(PAGE_WIDTH_IN - MARGIN - HEADER_TEXT_X)
    y = page.wrapped(px(HEADER_TEXT_X), px(LOGO_TOP + 0.3), header_width, TAGLINE, heading_font(32), 32, TEXT, 1.0)
    page.wrapped(px(HEADER_TEXT_X), y + px(0.1), header_width, SUBTAGLINE, body_font(10), 10, MUTED)

    # Left column: about, members, past venues
    y = page.heading(px(LEFT_X), px(CONTENT_TOP), "The band")
    y = page.wrapped(px(LEFT_X), y, px(LEFT_WIDTH), BIO, body_font(), BODY_PT, TEXT)
    y = page.wrapped(px(LEFT_X), y + px(0.08), px(LEFT_WIDTH), BIO_EXTRA, body_font(), BODY_PT, TEXT)
    # Members: the first one (Ben) on a line of his own, the others together on the next line
    lead, *others = (f"{name}, {role}" for name, role in MEMBERS)
    for line in (lead, "  \u00b7  ".join(others)):
        if line:
            y = page.wrapped(px(LEFT_X), y + px(0.03), px(LEFT_WIDTH), line, body_font(8.5), 8.5, MUTED, 1.3)
    y += px(0.08)
    y += round(points_to_px(BODY_PT) * BODY_LEADING)
    if venues:
        # A small label instead of a full heading, to save room
        y += px(0.06)
        page.text(px(LEFT_X), y + points_to_px(SMALL_PT), "WHERE WE'VE PLAYED", body_font(SMALL_PT), SMALL_PT, MUTED)
        names = [f"{v['name']} ({v['city']})" if v["city"] else v["name"] for v in venues]
        y = page.wrapped(px(LEFT_X), y + px(0.17), px(LEFT_WIDTH), "  \u00b7  ".join(names), body_font(9), 9, TEXT, 1.35)
    left_bottom = y

    # Right column: booking details, lineups
    y = page.heading(px(RIGHT_X), px(CONTENT_TOP), "Booking details")
    label_font = body_font(SMALL_PT)
    value_x = px(RIGHT_X + FACT_LABEL_WIDTH)
    value_width = px(RIGHT_WIDTH - FACT_LABEL_WIDTH)
    for label, value in FACTS:
        page.text(px(RIGHT_X), y + points_to_px(BODY_PT) - 2, label.upper(), label_font, SMALL_PT, MUTED)
        y = page.wrapped(value_x, y, value_width, value, body_font(), BODY_PT, TEXT) + px(0.05)
    y = page.heading(px(RIGHT_X), y + px(0.1), "Lineups")
    for name, label, detail in LINEUPS:
        description = f"{label}. {detail}"
        page.text(px(RIGHT_X), y + points_to_px(15), name, heading_font(17), 17, TEXT)
        y = page.wrapped(px(RIGHT_X + 0.55), y, px(RIGHT_WIDTH - 0.55), description, body_font(), BODY_PT, TEXT)
        y += px(0.06)
    columns_bottom = max(left_bottom, y)

    # What to expect: three short columns across the page, under a thin rule
    y = columns_bottom + px(0.1)
    page.draw.rectangle((px(MARGIN), y, px(PAGE_WIDTH_IN - MARGIN), y + 3), fill=MUTED)
    y += px(0.12)
    gap = px(0.25)
    column_width = (px(PAGE_WIDTH_IN - 2 * MARGIN) - 2 * gap) // 3
    expect_bottom = y
    for index, (title, text) in enumerate(EXPECT):
        x = px(MARGIN) + index * (column_width + gap)
        page.text(x, y + points_to_px(15), title, heading_font(17), 17, TEXT)
        column_bottom = page.wrapped(x, y + points_to_px(17) + px(0.02), column_width, text, body_font(9), 9, MUTED)
        expect_bottom = max(expect_bottom, column_bottom)

    bottom = expect_bottom

    # Footer: how to book
    page.draw.rectangle((0, px(FOOTER_TOP), page.image.width, page.image.height), fill=FOOTER_BACKGROUND)
    top = px(FOOTER_TOP + 0.12)
    page.text(px(MARGIN), top + points_to_px(30) * 0.8, "Book the band", heading_font(30), 30, TEXT)
    email_baseline = top + points_to_px(30) + points_to_px(15)
    page.text(px(MARGIN), email_baseline, EMAIL, body_font(15), 15, ACCENT,
              link=f"mailto:{EMAIL}?subject={EMAIL_SUBJECT.replace(' ', '%20')}")
    page.wrapped(px(MARGIN), email_baseline + px(0.1), px(4.0), INQUIRY_HINT, body_font(8.5), 8.5, MUTED)

    # Right side of the footer: website and social links, right-aligned
    right_edge = px(PAGE_WIDTH_IN - MARGIN)
    rows = [
        (WEBSITE_LABEL, WEBSITE_URL, TEXT, 11),
        ("Instagram @hossandthehangmen", INSTAGRAM_URL, MUTED, 8.5),
        ("YouTube @hossandthehangmen", YOUTUBE_URL, MUTED, 8.5),
        ("Facebook: Hoss and the Hangmen", FACEBOOK_URL, MUTED, 8.5),
    ]
    y = top + points_to_px(12)
    for label, url, color, size in rows:
        font = body_font(size)
        page.text(right_edge - round(font.getlength(label)), y, label, font, size, color, link=url)
        y += round(points_to_px(size) * 1.75) if size > 10 else round(points_to_px(size) * 1.6)
    credit_font = body_font(6.5)
    credit = f"{PHOTO_CREDIT}, {PHOTOGRAPHER_LABEL}"
    page.text(right_edge - round(credit_font.getlength(credit)), px(PAGE_HEIGHT_IN - 0.12),
              credit, credit_font, 6.5, MUTED, link=PHOTOGRAPHER_URL)

    return page, bottom


def render_fitting_page(past_shows):
    """Draw the page with as many past venues as fit above the footer."""
    photo = _hero_photo()
    venues = highlight_venues(past_shows, MAX_VENUES)
    while True:
        page, bottom = render_page(venues, photo)
        if bottom <= px(CONTENT_BOTTOM):
            return page
        if not venues:
            over = (bottom - px(CONTENT_BOTTOM)) / DPI
            raise PressKitError(
                f"the press kit text does not fit on one page: it runs {over:.2f} inches past the footer even "
                "without the list of past venues. Shorten the bio, booking details or other text in "
                "scripts/generate_press_kit.py, or adjust the LAYOUT values"
            )
        venues = venues[:-1]


# ------------------------------------------------------------------ PDF

def _pdf_string(value):
    data = value.encode("cp1252", "replace")
    return b"(" + data.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def build_pdf(page, jpeg_bytes, title, author, subject):
    """A one-page PDF: the page picture, an invisible text layer and URI link annotations."""
    width_pt = PAGE_WIDTH_IN * 72
    height_pt = PAGE_HEIGHT_IN * 72
    scale = 72 / DPI

    ops = [b"q", f"{width_pt:g} 0 0 {height_pt:g} 0 0 cm".encode(), b"/Im0 Do", b"Q", b"BT", b"3 Tr"]
    for x, baseline, text, points in page.runs:
        ops.append(f"/F1 {points:g} Tf 1 0 0 1 {x * scale:.2f} {height_pt - baseline * scale:.2f} Tm".encode())
        ops.append(_pdf_string(text) + b" Tj")
    ops.append(b"ET")
    content = b"\n".join(ops)

    annotation_ids = []
    objects = {}
    first_annotation = 8
    for offset, (left, top, right, bottom, url) in enumerate(page.links):
        rect = [left * scale, height_pt - bottom * scale, right * scale, height_pt - top * scale]
        annotation_ids.append(first_annotation + offset)
        objects[first_annotation + offset] = (
            b"<< /Type /Annot /Subtype /Link /Rect ["
            + " ".join(f"{value:.2f}" for value in rect).encode()
            + b"] /Border [0 0 0] /A << /S /URI /URI " + _pdf_string(url) + b" >> >>"
        )
    annots = " ".join(f"{number} 0 R" for number in annotation_ids).encode()

    objects[1] = b"<< /Type /Catalog /Pages 2 0 R /Lang (en-US) /ViewerPreferences << /DisplayDocTitle true >> >>"
    objects[2] = b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"
    objects[3] = (
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width_pt:g} {height_pt:g}] ".encode()
        + b"/Resources << /XObject << /Im0 5 0 R >> /Font << /F1 6 0 R >> >> /Contents 4 0 R "
        + b"/Annots [" + annots + b"] >>"
    )
    objects[4] = b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"
    objects[5] = (
        f"<< /Type /XObject /Subtype /Image /Width {page.image.width} /Height {page.image.height} ".encode()
        + b"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length "
        + str(len(jpeg_bytes)).encode() + b" >>\nstream\n" + jpeg_bytes + b"\nendstream"
    )
    objects[6] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    objects[7] = (
        b"<< /Title " + _pdf_string(title) + b" /Author " + _pdf_string(author)
        + b" /Subject " + _pdf_string(subject) + b" /Creator (scripts/generate_press_kit.py) >>"
    )

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for number in sorted(objects):
        offsets[number] = len(output)
        output += f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n"
    xref_at = len(output)
    count = max(objects) + 1
    output += f"xref\n0 {count}\n".encode() + b"0000000000 65535 f \n"
    for number in range(1, count):
        output += f"{offsets[number]:010d} 00000 n \n".encode()
    output += f"trailer\n<< /Size {count} /Root 1 0 R /Info 7 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    return bytes(output)


def write_pdf(path, past_shows):
    page = render_fitting_page(past_shows)
    from io import BytesIO
    buffer = BytesIO()
    page.image.save(buffer, "JPEG", quality=88, optimize=True, dpi=(DPI, DPI))
    pdf = build_pdf(
        page,
        buffer.getvalue(),
        title=f"{BAND_NAME} press kit",
        author=BAND_NAME,
        subject="One-page press kit and booking information",
    )
    Path(path).write_bytes(pdf)
    return page


# ------------------------------------------------------------------ photos and CLI

def write_photos(output_dir):
    for name, source in PHOTOS.items():
        source_path = IMAGE_DIRECTORY / source
        if not source_path.exists():
            raise PressKitError(f"missing source image {source_path}")
        Image.open(source_path).convert("RGB").save(Path(output_dir) / name, "JPEG", quality=PHOTO_QUALITY, optimize=True)


def generate(site_root, past_shows_file=None):
    site_root = Path(site_root)
    output_dir = site_root / OUTPUT_SUBDIRECTORY
    output_dir.mkdir(parents=True, exist_ok=True)
    past_shows = load_past_shows(past_shows_file or site_root / "data" / "past-shows.json")
    write_pdf(output_dir / PDF_NAME, past_shows)
    write_photos(output_dir)
    return output_dir


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-root", default=".", help="directory the site is served from (default: repository root)")
    parser.add_argument("--past-shows-file", help="past shows JSON (default: <site-root>/data/past-shows.json)")
    args = parser.parse_args(argv)
    try:
        output_dir = generate(args.site_root, args.past_shows_file)
    except PressKitError as error:
        print(f"Press kit error: {error}", file=sys.stderr)
        return 1
    print(f"Wrote the press kit and photos to {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
