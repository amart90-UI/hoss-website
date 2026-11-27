"""The footer is the same on the home page, the booking page and every event page."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import event_pages as ep  # noqa: E402
from process_schedule import parse_csv  # noqa: E402

HEADER = "date,start_time,end_time,address,zip_code,venue,city,state,country,timezone,venue_url,performers,event_url,description\n"
ROW = "7/18/2026,7:00 PM,10:00 PM,4791 W County Rd 38 E,80526,Horsetooth Tavern,Fort Collins,CO,US,America/Denver,,Ben + Anthony,,\n"


def footer_of(source):
    match = re.search(r"<footer>.*?</footer>", source, re.S)
    assert match, "no <footer> found"
    return match.group(0)


def normalized(markup):
    return re.sub(r"\s+", " ", markup).strip()


def event_page_html():
    event = parse_csv(HEADER + ROW)[0]
    event.update({"start": "2026-07-18T19:00:00-06:00", "end": "2026-07-18T22:00:00-06:00"})
    return ep.render_event_page(ep.assign_event_paths([event])[0])


class FooterTests(unittest.TestCase):
    PAGES = (("index.html", ""), ("booking/index.html", "../"))

    def test_each_page_uses_the_shared_footer_markup(self):
        for path, prefix in self.PAGES:
            source = (ROOT / path).read_text(encoding="utf-8")
            self.assertEqual(normalized(footer_of(source)), normalized(ep.render_footer(prefix)), path)
        self.assertEqual(
            normalized(footer_of(event_page_html())), normalized(ep.render_footer("../../")), "event page"
        )

    def test_footers_are_identical_apart_from_the_path_to_the_site_root(self):
        def without_prefix(markup, prefix):
            markup = re.sub(r'((?:src|href)=")' + re.escape(prefix), r"\1", markup) if prefix else markup
            return markup.replace('href="./"', 'href=""')

        pages = {
            "home": (footer_of((ROOT / "index.html").read_text(encoding="utf-8")), ""),
            "booking": (footer_of((ROOT / "booking" / "index.html").read_text(encoding="utf-8")), "../"),
            "event": (footer_of(event_page_html()), "../../"),
        }
        results = {name: normalized(without_prefix(markup, prefix)) for name, (markup, prefix) in pages.items()}
        self.assertEqual(len(set(results.values())), 1, results)

    def test_footer_content(self):
        footer = ep.render_footer("../")
        for expected in (
            'src="../img/hoss-logo-light.svg"',
            'href="../">Home</a>',
            'href="../#shows">Shows</a>',
            'href="../booking/">Booking &amp; press kit</a>',
            f'href="mailto:{ep.CONTACT_EMAIL}"',
            ep.FACEBOOK_URL,
            ep.INSTAGRAM_URL,
            "&copy; 2026 Hoss and the Hangmen",
            '<time id="buildTime" datetime="__BUILD_TIME__"></time>',
        ):
            self.assertIn(expected, footer)
        self.assertIn('href="./">Home</a>', ep.render_footer(""))

    def test_every_local_link_in_the_footer_exists(self):
        for path, prefix in self.PAGES:
            base = (ROOT / path).parent
            for ref in re.findall(r'(?:src|href)="([^"]+)"', footer_of((ROOT / path).read_text(encoding="utf-8"))):
                if re.match(r"^(https?:|mailto:)", ref):
                    continue
                target = ref.split("#")[0]
                self.assertTrue((base / target).resolve().exists(), f"{path}: {ref}")

    def test_event_pages_load_the_script_that_shows_the_build_time(self):
        self.assertIn('<script defer src="../../js/mainFunctions.js"></script>', event_page_html())
        self.assertTrue((ROOT / "js" / "mainFunctions.js").exists())

    def test_deploy_workflow_stamps_every_page_after_the_event_pages_are_generated(self):
        workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
        generate = workflow.index("name: Generate schedule data from Google Sheets")
        stamp = workflow.index("name: Stamp build time")
        self.assertGreater(stamp, generate)
        self.assertIn('find _site -name index.html -exec sed -i "s/__BUILD_TIME__/$stamp/" {} +', workflow)
        self.assertNotIn("_site/index.html", workflow.split("name: Stamp build time")[1].split("name:")[0])


if __name__ == "__main__":
    unittest.main()
