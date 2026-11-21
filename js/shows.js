// Show schedule: the "Next show" line, the upcoming and past show tables, and Event structured data.
// Reads data/shows.json (upcoming, soonest first) and data/past-shows.json (past, most recent first).
// Both files are generated from the Google Sheet by scripts/process_schedule.py, already sorted.
(function () {
	const BAND_NAME = 'Hoss and the Hangmen';
	const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
	const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

	const nextShowEl = document.getElementById('next-show');
	const upcomingEl = document.getElementById('shows-upcoming');
	const pastEl = document.getElementById('shows-past');
	if (!nextShowEl || !upcomingEl || !pastEl) {
		return;
	}

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

	// Only http(s) links are used. The build already checks this; this is a second check.
	function safeUrl(url) {
		return typeof url === 'string' && /^https?:\/\//i.test(url) ? url : null;
	}

	// A link that opens in a new tab.
	function externalLink(text, href, className) {
		const link = el('a', className, text);
		link.href = href;
		link.target = '_blank';
		link.rel = 'noopener';
		return link;
	}

	// "2026-07-18" -> "Sat, Jul 18, 2026". Calculated without time zones, so the date can't shift by a day.
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

	// One table row: date | venue, city and notes | time
	function buildRow(show) {
		const row = el('tr', 'animatableY');
		row.append(el('td', '', formatDate(show.date, true)));

		const details = el('td');
		const venue = el('span');
		const venueUrl = safeUrl(show.venue_url);
		if (show.page_url) {
			venue.append(el('a', '', show.venue));
			venue.firstElementChild.href = show.page_url.replace(/^https:\/\/hossandthehangmen\.com/, '');
		} else if (venueUrl) {
			venue.append(externalLink(show.venue, venueUrl));
		} else {
			venue.textContent = show.venue;
		}
		details.append(venue, el('br'), document.createTextNode(show.city + ', ' + show.state));
		if (show.notes) {
			details.append(el('br'), el('small', 'show-extra', show.notes));
		}
		const eventUrl = safeUrl(show.event_url);
		if (eventUrl) {
			details.append(el('br'), externalLink('Event details', eventUrl, 'show-extra show-event-link'));
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

	// Past shows go in a <details> element, which stays collapsed until the visitor opens it.
	function renderPast(shows) {
		if (shows.length === 0) {
			pastEl.replaceChildren();
			return;
		}
		const details = el('details', 'past-shows');
		details.append(el('summary', '', 'Past shows (' + shows.length + ')'), buildTable(shows, 'Past shows'));
		pastEl.replaceChildren(details);
	}

	// Event structured data (JSON-LD) for search engines, one MusicEvent per upcoming show.
	function renderJsonLd(shows) {
		document.getElementById('events-jsonld')?.remove();
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
			if (show.address) location.address.streetAddress = show.address;
			if (show.zip_code) location.address.postalCode = show.zip_code;
			if (safeUrl(show.venue_url)) {
				location.url = show.venue_url;
			}
			const event = {
				'@type': 'Event',
				name: BAND_NAME + ' at ' + show.venue,
				startDate: show.start,
				eventStatus: 'https://schema.org/EventScheduled',
				eventAttendanceMode: 'https://schema.org/OfflineEventAttendanceMode',
				location: location,
				performer: {'@type': 'PerformingGroup', name: BAND_NAME, url: 'https://hossandthehangmen.com/'},
				isAccessibleForFree: true,
				image: 'https://hossandthehangmen.com/img/og-image.jpg'
			};
			if (show.end) {
				event.endDate = show.end;
			}
			if (show.page_url) {
				event.url = show.page_url;
			}
			if (show.description) {
				event.description = show.description;
			}
			return event;
		});
		const script = el('script');
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

	// New rows start hidden (animatableY), so run the fade-in check from js/mainFunctions.js.
	function afterRender() {
		if (typeof revealOnScroll === 'function') {
			revealOnScroll();
		}
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
