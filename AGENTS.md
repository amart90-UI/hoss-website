## Project overview

This repository contains the official website for Hoss and the Hangmen, a modern Colorado country band.

The website is based on:
https://github.com/gtcore902/free-rock-band-website-template

The goal is to maintain the template's visual identity while adapting it into a polished, responsive, low-maintenance band website.

## Core architectural decisions

### Hosting

- GitHub Pages is the hosting platform.
- The website must be entirely static.
- The site is served at https://hossandthehangmen.com (registered through Porkbun, set in Settings > Pages, and repeated in the root CNAME file so replacing the gh-pages branch keeps it).
- The deploy workflow publishes by force-pushing the built site as a single fresh commit to the generated "gh-pages" branch, and Pages serves that branch. Do not switch back to actions/deploy-pages: redeploying an already-deployed commit (manual and scheduled runs) silently keeps serving old files (actions/deploy-pages#383). The push uses the "PAGES_DEPLOY_TOKEN" secret because Pages ignores pushes made with GITHUB_TOKEN.
- HTTPS will be provided through GitHub Pages.
- Do not introduce server-side dependencies such as PHP, Node.js hosting, or a database.

### Technology

- Prefer the template's existing HTML, CSS, and JavaScript.
- Python may be used for build-time data processing and GitHub Actions scripts.
- Use GitHub Actions for scheduled automation and deployment.
- Avoid unnecessary frameworks, dependencies, and build systems.

### Cost

The intended recurring cost is limited primarily to domain registration. Prefer free services and existing tools. Do not introduce paid APIs, hosting, or third-party services without explicit approval.

## Website functionality

### Contact

- No contact form or newsletter signup.
- Use a simple "mailto:" link for booking and general inquiries.
- Remove obsolete PHP handlers and related functionality.

### Videos

- Videos are hosted on YouTube.
- Display videos in a horizontally scrolling gallery.
- Use YouTube thumbnails and click-to-load embedded players.
- Store video metadata separately from presentation logic.
- The video list lives in a Google Sheet (columns: title, url, id) published to the web as CSV. Its URL is the repository secret "VIDEO_CSV_URL". scripts/process_videos.py builds data/videos.json from it at build time (inside the deploy workflow, like the schedule). The committed data/videos.json is the local-development copy and the source of "channel_url".
- Do not host video files in the GitHub repository.

### Images

- Store optimized website images in the repository.
- Original media is archived separately in Google Drive.
- Prefer WebP for photographic assets when practical.
- Use descriptive filenames and meaningful alt attributes.
- Avoid committing unnecessarily large original photographs.

## Gig schedule architecture

### Source of truth

Google Sheets is the authoritative record of all performances.

Use one master sheet/tab containing both upcoming and historical shows. Never physically move or delete records as part of automated processing.

The spreadsheet tab (named "schedule") is published to the web as CSV for retrieval by GitHub Actions. The full published-CSV URL is stored in the repository secret "SCHEDULE_CSV_URL". It contains public performance information only. Every show listed is confirmed; canceled shows are simply removed from the sheet.

### Data processing

A Python script processes the CSV and generates two datasets:

- "data/shows.json" — upcoming performances, soonest first.
- "data/past-shows.json" — historical performances, most recent first.

These files are generated inside the deployment workflow and are not committed (they are git-ignored). Locally, run scripts/process_schedule.py with --csv pointing at a downloaded copy of the sheet.

Classification rules:

- Use "America/Denver" for date classification.
- Shows dated today remain upcoming throughout that calendar day.
- Shows dated before today are historical.
- Preserve historical records and their original information.
- Do not discard malformed or unrecognized records silently.

Use unique, stable show IDs. Use ISO 8601 dates ("YYYY-MM-DD") and unambiguous time representations.

Sheet columns: date (M/D/YYYY, as exported by Google Sheets), start_time (H:MM:SS AM/PM), end_time (optional, same format), venue, venue_url (optional), city, state, event_url (optional), notes (optional). The id is derived from date, start time and venue. Output fields: id, date, start_time, end_time, start, end (ISO 8601 with Denver offset), venue, venue_url, city, state, event_url, notes.

### Validation and reliability

- Validate required fields, dates, times, and URLs.
- Report invalid rows with useful error messages.
- Never replace valid deployed data with empty or incomplete data because retrieval or processing failed.
- Generate deterministic JSON.
- Only deploy when generated website output changes.
- Do not automatically delete or alter source spreadsheet records.

### GitHub Actions

- Run the schedule pipeline daily.
- Include "workflow_dispatch" for manual runs.
- Use GitHub Actions to retrieve the published CSV, execute processing, and deploy updated static content.
- Do not assume a commit made with "GITHUB_TOKEN" will trigger another workflow.
- Prefer generating the deployment artifact and deploying it within the same workflow.
- Document all required configuration values and secrets.

### Website integration

The website reads the generated JSON datasets.

Upcoming and past show sections must use the same data source and consistent presentation.

Generate Event JSON-LD from the upcoming show data. Do not maintain a separate manually edited event dataset.

### Event posters

- scripts/generate_event_posters.py builds events/<page>/poster.jpg for every upcoming show with an event page, from data/shows.json and img/blank-poster.webp (design reference: img/example_poster.png). It runs in the deploy workflow; posters are generated and git-ignored.
- Text placement is the LAYOUT section at the top of the script. The QR code (scripts/qr_code.py, pure Python) encodes a short /e/<code>/ URL, where the code is a hash of the event page path (event_pages.short_code). event_pages.py writes the redirect pages to the event page; 404.html sends unknown /e/ paths to /#shows.

## Booking and press kit

- /booking/ (booking/index.html) is a static, hand-written page: lineups, booking details, past venues, a prefilled "mailto:" inquiry (date, venue, event type, lineup, budget) and press kit downloads. Do not invent testimonials, rates, technical specifications or band details; use only what the band has provided.
- scripts/generate_press_kit.py runs in the deploy workflow and writes booking/press/ (PDF and JPG photos; generated and git-ignored). Past venues come from data/past-shows.json. The booking page's "Where we've played" cards come from data/venue-history.json (scripts/generate_venue_history.py: top six venues by show count; logos are committed in img/venues/<venue-slug>.<svg|webp|png|jpg>; the logo links to the venue's venue_url; a link goes to /#past-shows on the home page). Logos are committed in img/ (hoss_logo_white/dark .svg/.png).
- All photographs are by Darrin Williams (LICENSE-MEDIA.md). Keep the credit, linked to https://darrinwilliamsmedia.com, on the page and in the PDF. Rates are not published; direct bookers to inquire.

## SEO requirements

Implement SEO features appropriate for a small static website:

- "robots.txt" allowing normal crawling.
- "sitemap.xml" referencing the canonical custom domain.
- Descriptive title and meta description.
- Canonical URL.
- Open Graph metadata.
- Semantic heading hierarchy.
- Descriptive image alt attributes.
- "MusicGroup" JSON-LD.
- Dynamically generated "Event" JSON-LD for upcoming performances.

The canonical domain is https://hossandthehangmen.com (no www). It appears in index.html, sitemap.xml and robots.txt.

Do not block images, CSS, or JavaScript from crawlers. Avoid keyword stuffing and misleading structured data.

## Design and development principles

- Preserve the existing template's design unless a requested feature requires modification.
- Maintain responsive desktop and mobile layouts.
- Prioritize accessibility and performance.
- The home page and the booking page are one design: they share section gutters, headings, quote, member cards, buttons, menu, footer, skip link/main landmark and scroll fade-ins. Reuse those components for new sections; tests/test_site_consistency.py enforces it.
- Keep data, presentation, and automation logic separate.
- Prefer simple, readable implementations over abstractions that add unnecessary complexity.
- Keep configuration centralized where practical.
- Do not invent band details, dates, email addresses, or social media URLs.
- Use clearly labeled placeholders for information that requires input.

- The footer is identical on the home page, the booking page and event pages. scripts/event_pages.py render_footer() is the source of truth; tests/test_footer.py enforces it. The deploy workflow stamps the build time into every index.html.

## Working with the project

Before modifying unfamiliar code:

1. Inspect the existing implementation.
2. Understand how the relevant components interact.
3. Identify dependencies and compatibility concerns.
4. Make the smallest reasonable change that accomplishes the task.

When implementing features:

- Avoid unnecessary rewrites.
- Preserve working functionality.
- Validate changes locally.
- Test data-processing scripts with synthetic examples, including edge cases.
- Document setup and maintenance procedures.

When a decision requires external information or credentials, ask rather than guessing.

Keep this file updated when fundamental architectural decisions change.
