# Hoss and the Hangmen website

The official website for Hoss and the Hangmen, a modern Colorado country band.

It is a static site hosted on GitHub Pages. The show schedule and the video gallery come from two Google Sheets. A GitHub Actions workflow reads the sheets every day and rebuilds the site's data, so updating the website normally means just editing a spreadsheet.

- Live site: <https://hossandthehangmen.com/>
- The default GitHub Pages address (<https://amart90-ui.github.io/hoss-website/>) redirects to the domain.

## Credits

This site is based on the [Free Rock Band Website Template](https://github.com/gtcore902/free-rock-band-website-template) by Gaëtan Tremois, used with the author's permission. The visual design (layout, scroll animations, hamburger menu, section styling) comes from that template. The contact form, newsletter signup, PHP backend and server configuration were removed, and the schedule, video gallery and deployment pipeline were added.

## How it works

```
Google Sheet "schedule"  ──┐                         ┌─> data/shows.json
(published as CSV)         ├─> GitHub Actions ──> Python scripts ─> data/past-shows.json ──> GitHub Pages
Google Sheet "videos"    ──┘   (daily / on push)     └─> data/videos.json
(published as CSV)
```

- **Plain HTML, CSS and JavaScript.** There is no framework and no build tool. `index.html` is the single page.
- **Show and video lists are not written in the HTML.** The browser loads `data/*.json` and `js/shows.js` and `js/videos.js` draw the lists.
- **Python (standard library only)** turns the spreadsheets into those JSON files while the workflow runs. The generated show files are not committed to the repo.
- **Cost:** GitHub Pages, GitHub Actions and Google Sheets are free. The only recurring cost is the domain name, once it is registered.

## Updating the website

### Add, change or remove a show

Open the schedule Google Sheet: **`https://docs.google.com/spreadsheets/d/1ih3MdZYOtfmeyatmTyqaz-d8hEW30kbOoiewOpgOoSY/edit?gid=0#gid=0`**

Use the tab named `schedule`. One row per show, with this header row (column order does not matter, and extra columns are ignored):

| Column | Required | Format and notes |
|---|---|---|
| `date` | yes | `M/D/YYYY`, such as `9/4/2026`. Month and day can be one or two digits. |
| `start_time` | yes | `H:MM:SS AM/PM`, such as `7:00:00 PM`. Seconds are optional. |
| `end_time` | no | Same format. An end time earlier than the start time means the show ends after midnight. |
| `venue` | yes | Venue name. |
| `venue_url` | no | Full link starting with `http://` or `https://`. The venue name on the site links here. |
| `city` | yes | City name. |
| `state` | yes | Two-letter code, such as `CO`. |
| `event_url` | no | Full link to an event page. Adds an "Event details" link. |
| `notes` | no | Short public note, such as "Ben and Anthony". |

Rules:

- **Every show in the sheet is treated as confirmed.** To cancel a show, delete its row.
- **Keep past shows in the sheet.** The pipeline moves them to the collapsed "Past shows" section by itself. A show dated today stays in "upcoming" until the day ends (Denver time).
- **Two shows can't share the same date, start time and venue.** That counts as a duplicate and stops the build.
- **Only put public information in the sheet.** Anyone who has the published CSV link can read the tab.

The change goes live the next time the workflow runs. That happens every night, or immediately if you [run it by hand](#run-the-pipeline-manually).

### Add, change, reorder or remove a video

Open the video Google Sheet: **`https://docs.google.com/spreadsheets/d/1ih3MdZYOtfmeyatmTyqaz-d8hEW30kbOoiewOpgOoSY/edit?gid=89406050#gid=89406050`**

| Column | Required | Notes |
|---|---|---|
| `title` | yes | Title shown under the thumbnail. |
| `id` | yes | The 11-character YouTube video ID. For `https://www.youtube.com/watch?v=WvEge0fWXK0` or `https://youtu.be/WvEge0fWXK0`, the ID is `WvEge0fWXK0`. |
| `url` | no | Not used by the site. Handy to keep as a reference. |

The row order in the sheet is the order in the gallery. The video must be public (or unlisted) and must allow embedding on other sites.

The "Watch more on YouTube" link comes from `channel_url` in `data/videos.json` in this repo, because the sheet has no column for it.

### Edit text, photos and links

These live in `index.html`. Search for `PLACEHOLDER` to find text that still needs real content.

- **Band bio and quote:** the `band` section.
- **Member names, roles and photos:** the three `card` blocks. Each photo has a small blurred version (`*-blur.webp`) that shows first and a full version that loads as the card scrolls into view. Add both files to `img/` and update the `src` and `data-src` paths.
- **Social links:** the Facebook and Instagram links appear twice (top-left buttons and the footer).
- **Booking email:** the `mailto:` link in the `contact` section.
- **Hero image:** `img/hero-band.webp`, set in the `.mainView` rule in `css/style.css`. The logo over it is `img/hoss_logo_white.svg`.
- **Colors and fonts:** `css/style.css`. The page uses Amatic SC for headings and Faculty Glyphic for body text from Google Fonts.

For images, use WebP, keep them small, and give each one a descriptive `alt` text. Keep the original large photos outside the repo (for example in Google Drive).

## The pipeline

The workflow is `.github/workflows/deploy.yml`.

**It runs when:**

- commits are pushed to the `deploy` branch,
- every day at 07:05 UTC, which is just after midnight in Denver (scheduled runs use the workflow file on the `main` branch, and GitHub pauses scheduled workflows in a repo that has had no activity for 60 days),
- someone starts it manually from the Actions tab.

**What it does, in order:**

1. Checks out the `deploy` branch, regardless of whichever branch started the run.
2. Runs the unit tests (`python3 -m unittest discover tests`). A failing test stops the run.
3. Copies the website files into a `_site` folder: `index.html`, `css/`, `js/`, `img/`, `data/`, `robots.txt`, `sitemap.xml`, and the favicon files and `site.webmanifest` from the repo root. Anything else in the repo (this README, scripts, tests, workflow files) is not published.
4. Runs `scripts/process_schedule.py`:
   - downloads the schedule CSV (URL from the `SCHEDULE_CSV_URL` secret),
   - checks every row (required values, `M/D/YYYY` dates, times, two-letter state, `http(s)` links, duplicates),
   - splits shows into upcoming and past using today's date in `America/Denver`,
   - writes `shows.json` (soonest first) and `past-shows.json` (most recent first).
5. Runs `scripts/process_videos.py`:
   - downloads the video CSV (URL from the `VIDEO_CSV_URL` secret),
   - checks every row (title present, valid 11-character YouTube ID, no duplicates),
   - writes `videos.json` in sheet order, keeping `channel_url` from the repo's copy.
6. On scheduled runs only, compares the new JSON files with the ones on the live site. If nothing changed, it skips the deployment. Pushes and manual runs always deploy.
7. Uploads `_site` and deploys it to GitHub Pages.

**Safety rules:**

- The generated JSON is deterministic. The same spreadsheet always produces byte-identical files, whatever the row order.
- If a download fails, a sheet is empty, or any row is invalid, the run fails and nothing deploys. The live site keeps its last good data. The error message lists each bad row by row number. It never prints the secret URLs.
- Nothing in the pipeline changes your spreadsheets.
- No generated data is committed back to the repo, so the pipeline needs no write access to it.

**What the page does with the data:**

- `js/shows.js` fills the "Next show" line, the upcoming table and the collapsed past-shows list. It also adds `MusicEvent` structured data (JSON-LD) for the upcoming shows, built from the same data.
- `js/videos.js` draws the horizontally scrolling gallery. It shows YouTube thumbnails only. The YouTube player (`youtube-nocookie.com`) loads when a visitor clicks a video, and the video starts playing right away.

## One-time setup

### 1. Publish each Google Sheet tab as CSV

Do this once for the `schedule` tab and once for the video tab.

1. Open the sheet and choose **File, Share, Publish to web**.
2. In the first dropdown, choose the specific tab (not "Entire document").
3. In the second dropdown, choose **Comma-separated values (.csv)**.
4. Click **Publish** and copy the link. It looks like `https://docs.google.com/spreadsheets/d/e/2PACX-…/pub?gid=…&single=true&output=csv`.

Keep the links private. Anyone with the link can read that tab. To revoke a link, use **Publish to web, Stop publishing**, then publish again to get a new one.

### 2. Add the repository secrets

In GitHub, go to **Settings, Secrets and variables, Actions, New repository secret**:

| Secret | Value |
|---|---|
| `SCHEDULE_CSV_URL` | The full published CSV link for the schedule tab. |
| `VIDEO_CSV_URL` | The full published CSV link for the video tab. |

### 3. Turn on GitHub Pages

1. **Settings, Pages:** set **Source** to **GitHub Actions**.
2. **Settings, Environments, `github-pages`:** under **Deployment branches and tags**, add a rule that allows the `deploy` branch. Without this, deployments fail with "Branch 'deploy' is not allowed to deploy to github-pages".

## Everyday workflow

Work happens on `main`. The `deploy` branch is what gets published.

```
# publish what is on main
git checkout main
git push origin main:deploy
```

That pushes `main` to the remote `deploy` branch, which starts the workflow. You can also open a pull request from `main` to `deploy` if you want a review step.

The workflow file must exist on both `main` and `deploy`. GitHub only lists the manual "Run workflow" button and only runs the daily schedule for a workflow on the default branch (`main`).

### Run the pipeline manually

1. Go to the **Actions** tab, choose **Build schedule and deploy site to GitHub Pages**, and click **Run workflow**.
2. Wait for the run to finish. The log shows how many shows and videos were processed.
3. Open the site. GitHub Pages can take a minute or two to show a new deployment, and your browser may need a hard refresh (Ctrl+F5).

## Local development

You need Python 3.9 or newer. The scripts use only the standard library. On Windows, if the scripts fail with a "No time zone found" error, run `pip install tzdata` once. The GitHub runner does not need this.

```
python -m http.server 8000
```

Open <http://localhost:8000>. Opening `index.html` straight from the file explorer will not work, because the page loads its data with `fetch`.

The show lists need `data/shows.json` and `data/past-shows.json`, which are git-ignored and only exist after you generate them. Download the schedule tab as CSV (in Google Sheets: **File, Download, Comma Separated Values**) and run:

```
python scripts/process_schedule.py --csv "path/to/schedule.csv"
```

You can also run the scripts against the real sheet by setting the secret as an environment variable first (`$env:SCHEDULE_CSV_URL = "..."` in PowerShell) and leaving off `--csv`. Do not save the link in a file in the repo.

To rebuild the video list from a downloaded copy of the video sheet:

```
python scripts/process_videos.py --csv "path/to/videos.csv"
```

That overwrites `data/videos.json`, which is committed. Check `git diff` before committing it.

### Tests

```
python -m unittest discover tests -v
```

The tests cover date and time parsing, the Denver "today" rules, sorting, validation errors, deterministic output, the download failure paths (with the network mocked), and the video list. They use inline sample data and need no network access or secrets.

## Repository layout

```
index.html                    the whole page, including SEO metadata and MusicGroup data
sitemap.xml, robots.txt       for search engines (contain the domain)
css/style.css                 styles (compiled from the template, edited directly)
js/mainFunctions.js           menu, parallax, scroll animations, lazy images, back-to-top
js/shows.js                   renders shows and Event JSON-LD from data/*.json
js/videos.js                  renders the video gallery, click-to-load player
js/vendor/rellax.min.js       parallax library (self-hosted)
img/                          optimized images and icons (og-image.jpg is the link-preview image)
data/videos.json              committed copy of the video list (see note below)
data/shows.json               generated, not committed
data/past-shows.json          generated, not committed
scripts/process_schedule.py   schedule sheet -> shows.json and past-shows.json
scripts/process_videos.py     video sheet -> videos.json
tests/                        unit tests for both scripts
.github/workflows/deploy.yml  tests, data build and deployment
AGENTS.md                     project decisions and rules for AI coding assistants
```

**About the committed `data/videos.json`:** the live site never uses it, because the workflow replaces it with the sheet's data. It exists for local previews and as the source of `channel_url`. Its video list can drift out of date without any effect on the site.

## Custom domain and SEO

The site is served at `https://hossandthehangmen.com`. The domain is registered through Porkbun, and its DNS points at GitHub Pages. The domain is set in **Settings, Pages, Custom domain**. A `CNAME` file isn't needed, because GitHub ignores that file for sites deployed by a workflow. `www.hossandthehangmen.com` redirects to the bare domain, which is the canonical address.

**What is in place:**

- Page title and meta description, and a canonical URL (`<link rel="canonical">`).
- Open Graph and Twitter card tags for link previews, using `img/og-image.jpg` (1200x630, cropped from the hero photo).
- `MusicGroup` structured data (JSON-LD) in `index.html`, with the band's Facebook, Instagram and YouTube links.
- `MusicEvent` structured data for upcoming shows, generated in the browser by `js/shows.js` from `data/shows.json`.
- A single `<h1>` (the logo, with the band name as its alt text) and `<h2>` section headings, and `alt` text on images.
- `robots.txt` (allows all crawling, including CSS, JavaScript and images) and `sitemap.xml`.

**Where the domain is written.** The full address `https://hossandthehangmen.com` appears in:

- `index.html` (canonical URL, Open Graph tags and the `MusicGroup` data, 6 places),
- `sitemap.xml`,
- `robots.txt`.

If the domain ever changes, update all three, then update **Settings, Pages, Custom domain** and the DNS records at Porkbun. The DNS records GitHub expects are listed in [GitHub's custom domain docs](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site).

Page assets use relative paths (`css/style.css`, not `/css/style.css`), so the site also works from a subfolder.

**Search engines.** Submit `https://hossandthehangmen.com/sitemap.xml` in [Google Search Console](https://search.google.com/search-console) after verifying the domain there (the DNS method works with Porkbun). This is optional, but it speeds up indexing and shows any crawl problems.

**Checking the result.** After the domain is live, test the page with Google's [Rich Results Test](https://search.google.com/test/rich-results) (Event and MusicGroup data) and the [Facebook Sharing Debugger](https://developers.facebook.com/tools/debug/) (link preview). The Event data only exists while at least one upcoming show is in the sheet.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Run fails: "Branch 'deploy' is not allowed to deploy to github-pages" | Add `deploy` to the allowed branches on the `github-pages` environment (setup step 3). |
| Run fails at the schedule or video step with "invalid rows" | The message lists each bad row number and the problem. Fix those rows in the sheet and re-run. |
| Run fails with "returned a web page, not CSV" | The secret is the normal sheet link, not the **Publish to web** CSV link. |
| Run fails with "Environment variable ... is not set" or an HTTP 404 | The secret is missing, misspelled or out of date, or the tab is no longer published. |
| Sheet changed but the site did not | Wait for the nightly run or run the workflow manually. Then hard refresh the page. |
| Style or color changes do not show locally | The browser cached the old file. Hard refresh with Ctrl+F5, or tick "Disable cache" in DevTools. |
| The daily run stopped | GitHub pauses scheduled workflows after 60 days without repo activity. Re-enable it in the Actions tab. |
