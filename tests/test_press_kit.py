"""Tests for scripts/generate_press_kit.py and the /booking/ page that links to its files."""
import html
import io
import re
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import event_pages  # noqa: E402
import generate_press_kit as pk  # noqa: E402

BOOKING_HTML = (ROOT / "booking" / "index.html").read_text(encoding="utf-8")
INDEX_HTML = (ROOT / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "css" / "style.css").read_text(encoding="utf-8")


class PageParser(HTMLParser):
    """Collects links, sources, ids, image alt text and visible text of an HTML page."""

    def __init__(self):
        super().__init__()
        self.hrefs, self.srcs, self.ids, self.images, self.text = [], [], [], [], []
        self.h1_count = 0
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "h1":
            self.h1_count += 1
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "a" and "href" in attrs:
            self.hrefs.append(attrs["href"])
        if tag in ("img", "script") and "src" in attrs:
            self.srcs.append(attrs["src"])
        if tag == "img":
            self.images.append(attrs)

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.text.append(data)


def parse(source):
    parser = PageParser()
    parser.feed(source)
    return parser


def sample_shows(count):
    return [{"venue": f"Venue {number}", "city": f"City {number}"} for number in range(count)]


class VenueHighlightTests(unittest.TestCase):
    def test_ranks_by_count_then_most_recent_and_ignores_bad_rows(self):
        shows = [
            {"venue": "B", "city": "X"},          # most recent
            {"venue": "A", "city": "X"},
            {"venue": "a ", "city": "x"},          # same venue as A, different case and spacing
            {"venue": "C", "city": ""},
            {"venue": "", "city": "X"},
            {"city": "X"},
            "not a show",
        ]
        result = pk.highlight_venues(shows)
        self.assertEqual([(v["name"], v["count"]) for v in result], [("A", 2), ("B", 1), ("C", 1)])

    def test_same_name_in_two_cities_is_two_venues(self):
        result = pk.highlight_venues([{"venue": "Tap", "city": "Denver"}, {"venue": "Tap", "city": "Boulder"}])
        self.assertEqual(len(result), 2)

    def test_limit_and_empty(self):
        self.assertEqual(len(pk.highlight_venues(sample_shows(30), 5)), 5)
        self.assertEqual(pk.highlight_venues([]), [])

    def test_missing_file_means_no_venues_and_bad_json_is_an_error(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(pk.load_past_shows(Path(folder) / "none.json"), [])
            bad = Path(folder) / "bad.json"
            bad.write_text("{not json", encoding="utf-8")
            with self.assertRaises(pk.PressKitError):
                pk.load_past_shows(bad)
            bad.write_text('{"a": 1}', encoding="utf-8")
            with self.assertRaises(pk.PressKitError):
                pk.load_past_shows(bad)


class PdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        cls.shows = sample_shows(3)
        cls.page = pk.write_pdf(cls.out / "kit.pdf", cls.shows)
        cls.pdf = (cls.out / "kit.pdf").read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_is_a_single_letter_page_with_a_valid_cross_reference_table(self):
        pdf = self.pdf
        self.assertTrue(pdf.startswith(b"%PDF-1.4"))
        self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))
        self.assertIn(b"/MediaBox [0 0 612 792]", pdf)
        self.assertIn(b"/Count 1", pdf)
        start = int(re.search(rb"startxref\n(\d+)\n", pdf).group(1))
        self.assertTrue(pdf[start:].startswith(b"xref\n"))
        header = re.match(rb"xref\n0 (\d+)\n", pdf[start:])
        count = int(header.group(1))
        entries = pdf[start + header.end():].split(b"\n")[:count]
        self.assertEqual(entries[0], b"0000000000 65535 f ")
        for number, entry in enumerate(entries[1:], start=1):
            offset = int(entry[:10])
            self.assertTrue(pdf[offset:].startswith(f"{number} 0 obj".encode()), f"object {number}")

    def test_links_and_invisible_text_layer(self):
        pdf = self.pdf
        self.assertTrue(b"/URI (mailto:hossandthehangmen@gmail.com?subject=Booking%20inquiry%20for%20Hoss%20and%20the%20Hangmen)" in pdf)
        for url in (pk.WEBSITE_URL, pk.INSTAGRAM_URL, pk.YOUTUBE_URL, pk.FACEBOOK_URL, pk.PHOTOGRAPHER_URL):
            self.assertTrue(b"/URI (" + url.encode() + b")" in pdf, url)
        self.assertEqual(pdf.count(b"/Subtype /Link"), 6)
        self.assertTrue(b"3 Tr" in pdf)  # invisible text
        # Long text wraps over several runs, so look at the runs joined together.
        layer = " ".join(run[2] for run in self.page.runs)
        for phrase in (pk.EMAIL, "up to 3 hours of music", "Venue 0 (City 0)", "30 minutes for load-in and setup",
                       "Please inquire for rates", "Ben (Hoss), guitar and vocals", "Anthony, upright bass",
                       "Alex, drums", pk.EXPECT[0][1], "darrinwilliamsmedia.com"):
            self.assertTrue(phrase in layer, phrase)

    def test_members_ben_on_his_own_line_then_the_others_together(self):
        lines = {run[2]: run[1] for run in self.page.runs}
        ben, others = "Ben (Hoss), guitar and vocals", "Anthony, upright bass \u00b7 Alex, drums"  # wrapping collapses spaces
        self.assertIn(ben, lines)
        self.assertIn(others, lines)
        self.assertLess(lines[ben], lines[others])
        self.assertFalse(any("Ben" in text and "Anthony" in text for text in lines), "Ben shares a line")

    def test_second_bio_paragraph_is_drawn(self):
        layer = " ".join(run[2] for run in self.page.runs)
        for word in pk.BIO_EXTRA.split()[:6]:
            self.assertIn(word, layer)
        self.assertIn("Johnny Cash", pk.BIO_EXTRA)

    def test_embedded_page_picture_is_a_letter_size_jpeg(self):
        match = re.search(rb"/Filter /DCTDecode /Length (\d+) >>\nstream\n", self.pdf)
        data = self.pdf[match.end():match.end() + int(match.group(1))]
        image = Image.open(io.BytesIO(data))
        self.assertEqual(image.format, "JPEG")
        self.assertEqual(image.size, (2550, 3300))
        self.assertLess(len(self.pdf), 2 * 1024 * 1024)

    def test_links_sit_inside_the_page(self):
        for left, top, right, bottom, url in self.page.links:
            self.assertTrue(0 <= left < right <= self.page.image.width, url)
            self.assertTrue(0 <= top < bottom <= self.page.image.height, url)

    def test_output_is_deterministic(self):
        pk.write_pdf(self.out / "again.pdf", self.shows)
        self.assertEqual((self.out / "again.pdf").read_bytes(), self.pdf)

    def test_layout_fits_with_no_venues_few_and_very_many(self):
        def drawn(page):
            return sum(1 for run in page.runs if run[2].startswith("Venue "))

        for shows in ([], sample_shows(3), sample_shows(200)):
            page = pk.render_fitting_page(shows)
            self.assertEqual(page.image.size, (2550, 3300))
        self.assertEqual(drawn(pk.render_fitting_page([])), 0)
        self.assertTrue(drawn(pk.render_fitting_page(sample_shows(3))) >= 1)
        # No more than MAX_VENUES are listed, however many shows there are (fewer if they would not fit).
        text = " ".join(run[2] for run in pk.render_fitting_page(sample_shows(200)).runs)
        self.assertTrue(0 < text.count("Venue ") <= pk.MAX_VENUES)

    def test_a_long_venue_list_is_trimmed_until_it_fits(self):
        shows = [{"venue": f"Venue {n} " + "Brewing and Distilling Company " * 3, "city": "Fort Collins"} for n in range(30)]
        photo = pk._hero_photo()
        _, full_bottom = pk.render_page(pk.highlight_venues(shows), photo)
        self.assertGreater(full_bottom, pk.px(pk.CONTENT_BOTTOM))  # all ten would overflow
        page = pk.render_fitting_page(shows)
        text = " ".join(run[2] for run in page.runs)
        listed = text.count("Brewing and Distilling Company")
        self.assertTrue(0 < listed < pk.MAX_VENUES)
        _, fitted_bottom = pk.render_page(pk.highlight_venues(shows, listed // 3), photo)
        self.assertLessEqual(fitted_bottom, pk.px(pk.CONTENT_BOTTOM))

    def test_text_that_cannot_fit_is_an_error(self):
        original = pk.BIO
        pk.BIO = original * 6
        try:
            with self.assertRaises(pk.PressKitError):
                pk.render_fitting_page([])
        finally:
            pk.BIO = original

    def test_long_venue_names_do_not_break_the_layout(self):
        shows = [{"venue": "The Extraordinarily Long Brewing and Distilling Company Taproom " * 3, "city": "Fort Collins"}]
        page = pk.render_fitting_page(shows)
        self.assertEqual(page.image.size, (2550, 3300))


class ShippedTextFitsTests(unittest.TestCase):
    def test_shipped_text_leaves_room_for_a_typical_venue_list(self):
        venues = pk.highlight_venues([
            {"venue": "Abbott and Wallace Distilling", "city": "Longmont"},
            {"venue": "Horsetooth Tavern", "city": "Fort Collins"},
            {"venue": "The Slab", "city": "Estes Park"},
            {"venue": "Tavern at the Legion", "city": "Fort Collins"},
            {"venue": "Velvet Lounge", "city": "Estes Park"},
        ])
        _, bottom = pk.render_page(venues, pk._hero_photo())
        over = (bottom - pk.px(pk.CONTENT_BOTTOM)) / pk.DPI
        self.assertLessEqual(over, 0, f"press kit text with five venues runs {over:.2f} in past the footer")


class GenerateTests(unittest.TestCase):
    def test_generate_writes_pdf_and_every_photo(self):
        with tempfile.TemporaryDirectory() as folder:
            site = Path(folder)
            (site / "data").mkdir()
            (site / "data" / "past-shows.json").write_text('[{"venue": "Test Tavern", "city": "Denver"}]', encoding="utf-8")
            out = pk.generate(site)
            self.assertEqual(out, site / "booking" / "press")
            self.assertTrue((out / pk.PDF_NAME).stat().st_size > 10000)
            self.assertTrue(b"Test Tavern" in (out / pk.PDF_NAME).read_bytes())
            for name in pk.PHOTOS:
                with Image.open(out / name) as image:
                    self.assertEqual(image.format, "JPEG")

    def test_main_reports_a_bad_past_shows_file(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = Path(folder) / "past.json"
            bad.write_text("nope", encoding="utf-8")
            self.assertEqual(pk.main(["--site-root", folder, "--past-shows-file", str(bad)]), 1)


class BookingPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = parse(BOOKING_HTML)

    def test_local_files_and_anchors_exist(self):
        generated = {f"press/{pk.PDF_NAME}"} | {f"press/{name}" for name in pk.PHOTOS}
        for ref in self.page.hrefs + self.page.srcs:
            if re.match(r"^(https?:|mailto:)", ref):
                continue
            path, _, fragment = ref.partition("#")
            if path in generated:
                continue
            if path:
                self.assertTrue((ROOT / "booking" / path).resolve().exists(), ref)
            if fragment and not path:
                self.assertIn(fragment, self.page.ids, ref)

    def test_every_generated_download_is_linked_and_nothing_else_is_expected(self):
        linked = {ref for ref in self.page.hrefs if ref.startswith("press/")}
        self.assertEqual(linked, {f"press/{pk.PDF_NAME}"} | {f"press/{name}" for name in pk.PHOTOS})

    def test_menu_has_two_page_links_and_four_section_links_and_icons_exist(self):
        for source in (BOOKING_HTML, INDEX_HTML):
            self.assertEqual(len(re.findall(r'class="ss-menu ss-page"', source)), 2)
            self.assertEqual(len(re.findall(r'class="ss-menu ss-section"', source)), 4)
            for icon in re.findall(r'<span class="ss-icon"><img src="(?:\.\./)?(img/[^"]+)"', source):
                self.assertTrue((ROOT / icon).exists(), icon)
        for selector in (".ss-page", ".ss-section", ".ss-label", ".ss-icon", "#menu-items.open"):
            self.assertIn(selector, CSS)
        self.assertIn('href="booking/"', INDEX_HTML)
        self.assertTrue((ROOT / "img" / "menu/book.svg").exists())
    def test_homepage_hero_footer_and_contact_link_to_booking(self):
        self.assertIn('<div class="hero-cta">', INDEX_HTML)
        self.assertIn('<a href="booking/">Booking &amp; press kit</a>', INDEX_HTML)
        self.assertGreaterEqual(INDEX_HTML.count('href="booking/"'), 4)  # menu, hero, contact, footer

    def test_one_h1_unique_ids_and_alt_text(self):
        self.assertEqual(self.page.h1_count, 1)
        self.assertEqual(len(self.page.ids), len(set(self.page.ids)))
        for image in self.page.images:
            if "/menu-" in image.get("src", ""):
                # Menu icons are decorative: the visible label next to each one names the link.
                self.assertEqual(image.get("alt"), "", image)
            else:
                self.assertTrue(image.get("alt"), image)

    def test_seo_metadata(self):
        self.assertIn('<link rel="canonical" href="https://hossandthehangmen.com/booking/" />', BOOKING_HTML)
        for tag in ('property="og:url" content="https://hossandthehangmen.com/booking/"',
                    'property="og:image" content="https://hossandthehangmen.com/img/og-image.jpg"',
                    'name="twitter:card" content="summary_large_image"', 'name="description"'):
            self.assertIn(tag, BOOKING_HTML)
        self.assertIn('"contactType": "booking"', BOOKING_HTML)

    def test_sitemap_lists_the_page_and_event_generation_keeps_it(self):
        sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn("<loc>https://hossandthehangmen.com/booking/</loc>", sitemap)
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "sitemap.xml").write_text(sitemap, encoding="utf-8")
            event_pages.update_sitemap(folder, [])
            rewritten = (Path(folder) / "sitemap.xml").read_text(encoding="utf-8")
            self.assertIn("https://hossandthehangmen.com/booking/", rewritten)

    def test_inquiry_email_has_a_prefilled_template(self):
        links = [ref for ref in self.page.hrefs if ref.startswith("mailto:") and "?" in ref]
        self.assertEqual(len(links), 1)
        query = parse_qs(urlparse(links[0]).query, keep_blank_values=True)
        self.assertEqual(unquote(urlparse(links[0]).path), pk.EMAIL)
        self.assertEqual(query["subject"], [pk.EMAIL_SUBJECT])
        body = query["body"][0]
        for field in ("Date:", "Venue or location:", "Event type:", "Desired lineup", "Budget:"):
            self.assertIn(field, body)
        gmail = [ref for ref in self.page.hrefs if ref.startswith("https://mail.google.com/")][0]
        gmail_query = parse_qs(urlparse(gmail).query, keep_blank_values=True)
        self.assertEqual(gmail_query["to"], [pk.EMAIL])
        self.assertEqual(gmail_query["body"], query["body"])

    def test_booking_facts_on_the_page_match_the_pdf(self):
        text = re.sub(r"\s+", " ", html.unescape(" ".join(self.page.text)))
        for _, value in pk.FACTS:
            self.assertIn(value, text)
        for _, label, detail in pk.LINEUPS:
            self.assertIn(label, text)
            self.assertIn(detail, text)
        self.assertIn("mostly covers", text.lower())
        self.assertIn("Photos by Darrin Williams", text)

    def test_bio_and_header_lines_match_the_pdf(self):
        text = re.sub(r"\s+", " ", html.unescape(" ".join(self.page.text)))
        for source in (pk.BIO, pk.BIO_EXTRA, pk.TAGLINE, pk.SUBTAGLINE):
            self.assertIn(re.sub(r"\s+", " ", source), text)
        for name, role in pk.MEMBERS:
            self.assertIn(name, text)

    def test_what_to_expect_and_the_new_booking_details_are_on_the_page(self):
        text = re.sub(r"\s+", " ", html.unescape(" ".join(self.page.text)))
        self.assertEqual(len(pk.EXPECT), 3)
        for title, description in pk.EXPECT:
            self.assertIn(title, text)
            self.assertIn(description, text)
        self.assertIn("expect", self.page.ids)
        facts = dict(pk.FACTS)
        self.assertIn("30 minutes", facts["Load-in"])
        self.assertIn("very small venues", facts["Power"])
        self.assertIn("inquire", facts["Rates"].lower())
        # No rates or prices are published anywhere on the page.
        self.assertNotRegex(text, r"\$\s?\d")
        self.assertIn("We don't post our rates publicly", text)

    def test_page_and_pdf_link_to_the_photographer(self):
        self.assertEqual(pk.PHOTOGRAPHER_URL, "https://darrinwilliamsmedia.com")
        self.assertIn(pk.PHOTOGRAPHER_URL, self.page.hrefs)
        self.assertIn("https://darrinwilliamsmedia.com", (ROOT / "LICENSE-MEDIA.md").read_text(encoding="utf-8"))

    def test_photo_credit_is_in_the_pdf_and_logo_files_exist(self):
        self.assertEqual(pk.PHOTO_CREDIT, "Photo: Darrin Williams")
        for name in ("hoss-logo-light.svg", "hoss-logo-light.png", "hoss-logo-dark.svg", "hoss-logo-dark.png"):
            self.assertTrue((ROOT / "img" / name).exists(), name)
        for name in ("hoss-logo-light.png", "hoss-logo-dark.png"):
            with Image.open(ROOT / "img" / name) as logo:
                self.assertEqual(logo.mode, "RGBA")
                self.assertEqual(logo.getchannel("A").getextrema()[0], 0)


if __name__ == "__main__":
    unittest.main()
