// Show schedule.
// Reads data/shows.json (upcoming) and data/past-shows.json (past). Both files are generated from the Google Sheet
// by scripts/process_schedule.py; the order in each file is already correct (upcoming soonest first, past newest first).
// This script renders the next-show banner, both lists, and Event structured data (JSON-LD) for upcoming shows.
(function () {
	const BAND_NAME = 'Hoss and the Hangmen';
	const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
	const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

	const nextShowEl = document.getElementById('next-show');
	const upcomingEl = document.getElementById('shows-upcoming');
	const pastEl = document.getElementById('shows-past');

	function el(tag, className, text) {
		const node = document.createElement(tag);
		if (className) {
			node.className = className;
		}
		if (text !== undefined) {
			node.textContent = text;
		}
		return node;
	}

	// Only http(s) URLs become links. The data is validated at build time; this is a second check.
	function safeUrl(url) {
		return typeof url === 'string' && /^https?:\/\//i.test(url) ? url : null;
	}

	// "2026-07-18" -> "Sat, Jul 18, 2026" (no Date/timezone conversion, so it never shifts a day)
	function formatDate(isoDate, withYear) {
		const [year, month, day] = isoDate.split('-').map(Number);
		const weekday = WEEKDAYS[new Date(Date.UTC(year, month - 1, day)).getUTCDay()];
		return weekday + ', ' + MONTHS[month - 1] + ' ' + day + (withYear ? ', ' + year : '');
	}

	// "19:00" -> "7:00 PM"
	function formatTime(time24) {
		const [hour, minute] = time24.split(':').map(Number);
		const hour12 = hour % 12 === 0 ? 12 : hour % 12;
		return hour12 + ':' + String(minute).padStart(2, '0') + ' ' + (hour < 12 ? 'AM' : 'PM');
	}

	function formatTimeRange(show) {
		const start = formatTime(show.start_time);
		return show.end_time ? start + ' \u2013 ' + formatTime(show.end_time) : start;
	}

	function buildRow(show) {
		const row = el('tr', 'animatableY');
		row.append(el('td', '', formatDate(show.date, true)));

		const details = el('td');
		const venue = el('span', 'white');
		const venueUrl = safeUrl(show.venue_url);
		if (venueUrl) {
			const link = el('a', '', show.venue);
			link.href = venueUrl;
			link.target = '_blank';
			link.rel = 'noopener';
			venue.append(link);
		} else {
			venue.textContent = show.venue;
		}
		details.append(venue, document.createElement('br'), document.createTextNode(show.city + ', ' + show.state));
		if (show.notes) {
			details.append(document.createElement('br'), el('small', 'show-extra', show.notes));
		}
		const eventUrl = safeUrl(show.event_url);
		if (eventUrl) {
			const link = el('a', 'show-extra show-event-link', 'Event details');
			link.href = eventUrl;
			link.target = '_blank';
			link.rel = 'noopener';
			details.append(document.createElement('br'), link);
		}
		row.append(details, el('td', '', formatTimeRange(show)));
		return row;
	}

	function buildTable(shows, label) {
		const table = el('table');
		table.setAttribute('aria-label', label);
		const body = el('tbody');
		shows.forEach(show => body.append(buildRow(show)));
		table.append(body);
		return table;
	}

	function renderUpcoming(shows) {
		if (shows.length === 0) {
			nextShowEl.textContent = 'No shows scheduled right now. Check back soon!';
			upcomingEl.replaceChildren(el('p', 'hardLight', 'No upcoming shows right now. Check back soon!'));
			return;
		}
		const next = shows[0];
		nextShowEl.textContent = formatDate(next.date, false) + ' | ' + next.venue + ' - ' + next.city;
		upcomingEl.replaceChildren(buildTable(shows, 'Upcoming shows'));
	}

	// Past shows sit in a <details> element that is collapsed until the visitor opens it.
	function renderPast(shows) {
		if (shows.length === 0) {
			pastEl.replaceChildren();
			return;
		}
		const details = el('details', 'past-shows');
		details.append(el('summary', '', 'Past shows (' + shows.length + ')'), buildTable(shows, 'Past shows'));
		pastEl.replaceChildren(details);
	}

	// Event structured data for upcoming shows, built from the same JSON.
	function renderJsonLd(shows) {
		const old = document.getElementById('events-jsonld');
		if (old) {
			old.remove();
		}
		if (shows.length === 0) {
			return;
		}
		const events = shows.map(show => {
			const location = {
				'@type': 'Place',
				name: show.venue,
				address: {
					'@type': 'PostalAddress',
					addressLocality: show.city,
					addressRegion: show.state,
					addressCountry: 'US'
				}
			};
			if (safeUrl(show.venue_url)) {
				location.url = show.venue_url;
			}
			const event = {
				'@type': 'MusicEvent',
				name: BAND_NAME + ' at ' + show.venue,
				startDate: show.start,
				eventStatus: 'https://schema.org/EventScheduled',
				eventAttendanceMode: 'https://schema.org/OfflineEventAttendanceMode',
				location: location,
				performer: {'@type': 'MusicGroup', name: BAND_NAME}
			};
			if (show.end) {
				event.endDate = show.end;
			}
			if (safeUrl(show.event_url)) {
				event.url = show.event_url;
			}
			if (show.notes) {
				event.description = show.notes;
			}
			return event;
		});
		const script = document.createElement('script');
		script.type = 'application/ld+json';
		script.id = 'events-jsonld';
		script.textContent = JSON.stringify({'@context': 'https://schema.org', '@graph': events});
		document.head.append(script);
	}

	function load(url) {
		return fetch(url).then(response => {
			if (!response.ok) {
				throw new Error(url + ': HTTP ' + response.status);
			}
			return response.json();
		});
	}

	function afterRender() {
		if (typeof revealOnScroll === 'function') {
			revealOnScroll();
		}
	}

	if (!nextShowEl || !upcomingEl || !pastEl) {
		return;
	}

	load('data/shows.json')
		.then(shows => {
			renderUpcoming(shows);
			renderJsonLd(shows);
			afterRender();
		})
		.catch(error => {
			console.error('Could not load upcoming shows:', error);
			nextShowEl.textContent = 'Show schedule unavailable right now.';
			upcomingEl.replaceChildren(el('p', 'hardLight', 'The show schedule is unavailable right now.'));
		});

	load('data/past-shows.json')
		.then(shows => {
			renderPast(shows);
			afterRender();
		})
		.catch(error => console.error('Could not load past shows:', error));
})();
