"""The home page and the booking page share one design: same layout rules, components and structure."""
import re
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import generate_press_kit as pk  # noqa: E402

HOME = (ROOT / "index.html").read_text(encoding="utf-8")
BOOKING = (ROOT / "booking" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
PAGES = {"home": HOME, "booking": BOOKING}


class Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []  # (tag, attrs) in document order
        self.cards = []
        self._card_depth = 0
        self._in_card = False
        self._card_paragraphs = []
        self._capture = False
        self._text = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        classes = (attrs.get("class") or "").split()
        if tag == "div" and "card" in classes:
            self._in_card = True
            self._card_paragraphs = []
        if self._in_card and tag == "p":
            self._capture = True
            self._text = ""

    def handle_endtag(self, tag):
        if self._in_card and tag == "p" and self._capture:
            self._card_paragraphs.append(self._text.strip())
            self._capture = False
        if tag == "div" and self._in_card and len(self._card_paragraphs) >= 2:
            self.cards.append(tuple(self._card_paragraphs[:2]))
            self._in_card = False

    def handle_data(self, data):
        if self._capture:
            self._text += data


def parse(source):
    collector = Collector()
    collector.feed(source)
    return collector


def has_class(attrs, name):
    return name in (attrs.get("class") or "").split()


class SharedStructureTests(unittest.TestCase):
    def test_both_pages_have_a_skip_link_and_a_main_landmark(self):
        for name, source in PAGES.items():
            page = parse(source)
            skip = [a for t, a in page.tags if t == "a" and has_class(a, "skip-link")]
            self.assertEqual([a.get("href") for a in skip], ["#main-content"], name)
            main = [a for t, a in page.tags if t == "main"]
            self.assertEqual(len(main), 1, name)
            self.assertEqual(main[0].get("id"), "main-content", name)
            self.assertIn("tabindex", main[0], name)

    def test_the_menu_has_the_same_page_links_and_its_own_section_links_on_each_page(self):
        link = re.compile(
            r'<a class="ss-menu ss-(page|section)" href="([^"]*)"([^>]*)>\s*'
            r'<span class="ss-label">([^<]+)</span>\s*'
            r'<span class="ss-icon"><img src="([^"]*)" alt="" /></span>\s*</a>'
        )

        def menu(source):
            nav = re.search(r'<nav class="menu-nav" aria-label="([^"]*)">(.*?)</nav>', source, re.S)
            self.assertEqual(nav.group(1), "Site sections")
            links = link.findall(nav.group(2))
            self.assertEqual(len(links), nav.group(2).count('class="ss-menu '))
            return links

        pages = {name: menu(source) for name, source in PAGES.items()}
        shared = {}
        for name, links in pages.items():
            page_links = [l for l in links if l[0] == "page"]
            # The section links sit directly under the link for the page they belong to.
            expected = []
            for page in page_links:
                expected.append(page)
                if 'aria-current="page"' in page[2]:
                    expected.extend(l for l in links if l[0] == "section")
            self.assertEqual(links, expected, name)
            self.assertEqual([l[3] for l in page_links], ["Home", "Booking"], name)
            self.assertEqual([l[2] for l in page_links].count(' aria-current="page"'), 1, name)
            shared[name] = [(l[3], l[4].rsplit("/", 1)[-1]) for l in page_links]
            sections = [l for l in links if l[0] == "section"]
            self.assertEqual(len(sections), 4, name)
            ids = {attrs.get("id") for _, attrs in parse(PAGES[name]).tags}
            for _, href, attrs, label, icon in sections:
                self.assertRegex(href, r"^#[\w-]+$", f"{name}: {label}")
                self.assertIn(href[1:], ids, f"{name}: {label}")
                self.assertNotIn("aria-current", attrs, f"{name}: {label}")
        self.assertEqual(shared["home"], shared["booking"])
        self.assertEqual(
            [l[3] for l in pages["booking"] if l[0] == "section"], ["Lineups", "Details", "Book", "Press kit"]
        )
        # The current page is the one whose link stays on the page.
        self.assertIn(('page', '#top', ' aria-current="page"', 'Home'), [l[:4] for l in pages["home"]])
        self.assertIn(('page', '#top', ' aria-current="page"', 'Booking'), [l[:4] for l in pages["booking"]])

    def test_both_pages_load_the_same_stylesheet_fonts_and_main_script(self):
        for name, source in PAGES.items():
            self.assertEqual(len(re.findall(r'<link rel="stylesheet" href="(?:\.\./)?css/style\.css"', source)), 1, name)
            self.assertNotIn("fonts.googleapis.com", source, name)
            for font in ("FacultyGlyphic-Regular", "AmaticSC-Bold", "AmaticSC-Regular"):
                self.assertRegex(source, rf'<link rel="preload" href="(?:\.\./)?fonts/{font}-latin\.woff2" as="font"', name)
                self.assertTrue((ROOT / "fonts" / f"{font}-latin.woff2").exists(), font)
            self.assertIn('href="img/hero-band-mobile.webp"' if name == "home" else 'href="../img/hero-band-mobile.webp"', source, name)
            self.assertRegex(source, r'<script defer src="(?:\.\./)?js/mainFunctions\.js"></script>', name)
            self.assertIn('<meta name="theme-color" content="#323536" />', source, name)
            self.assertRegex(source, r'<html lang="en"', name)

    def test_every_section_heading_fades_in_the_same_way(self):
        for name, source in PAGES.items():
            main = source[source.index("<main"):source.index("</main>")]
            headings = re.findall(r"<h2\b[^>]*>", main)
            self.assertGreaterEqual(len(headings), 5, name)
            for tag in headings:
                self.assertIn("animatableX", tag, f"{name}: {tag}")
            separators = re.findall(r'<div class="(separator[^"]*)"', main)
            self.assertEqual(len(separators), len(headings), name)
            for cls in separators:
                self.assertIn("animatableOpacity", cls, name)

    def test_the_quote_and_the_member_cards_use_the_same_components(self):
        for name, source in PAGES.items():
            self.assertRegex(source, r'<p class="hardLight quote animatableY">', name)
            self.assertIn('class="imgContent', source, name)
        self.assertEqual(parse(HOME).cards, parse(BOOKING).cards)
        expected = [(n, role.replace(" and ", " + ")) for n, role in pk.MEMBERS]
        self.assertEqual([name for name, _ in parse(HOME).cards], [n for n, _ in expected])

    def test_the_footer_and_back_to_top_arrow_exist_on_both_pages(self):
        for name, source in PAGES.items():
            self.assertEqual(source.count("<footer>"), 1, name)
            self.assertIn('id="upArrow"', source, name)


class SharedStyleTests(unittest.TestCase):
    def rule(self, selector):
        match = re.search(r"(?m)^" + re.escape(selector) + r" \{\n(.*?)\n\}", CSS, re.S)
        self.assertTrue(match, f"no rule for {selector}")
        return match.group(1)

    def test_all_sections_share_one_set_of_gutters(self):
        self.assertIn("max(15%, calc((100% - 1000px) / 2))", self.rule("section"))
        # The booking sections must not set their own width or padding.
        booking = self.rule(".booking-section")
        self.assertNotIn("padding", booking)
        self.assertNotIn("width", booking)
        self.assertNotIn("margin", booking)
        mobile = re.search(r"@media screen and \(max-width: 767px\) \{.*?\n\tsection \{\n\t\tpadding: ([^;]*);", CSS, re.S)
        self.assertEqual(mobile.group(1), "50px 5% 50px 5%")

    def test_no_booking_only_copies_of_shared_components_remain(self):
        for leftover in (".booking-quote", ".booking-prose", ".booking-members", ".booking-member-name"):
            self.assertNotIn(leftover, CSS)
            self.assertNotIn(leftover[1:], BOOKING)

    def test_content_hidden_until_scrolled_into_view_is_shown_without_javascript(self):
        self.assertRegex(CSS, r"@media \(scripting: none\) \{[^}]*\.animatableY")

    def test_the_contact_email_address_cannot_overflow_a_phone_screen(self):
        rule = self.rule(".hardLight .email-link")
        self.assertIn("min(1em, 5.2vw)", rule)
        self.assertIn("overflow-wrap", rule)


if __name__ == "__main__":
    unittest.main()
