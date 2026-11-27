// Booking page: the "Where we've played" list.
// Built from data/past-shows.json (the same data as the Past shows list on the home page).
// Venues are ranked by how many times the band has played them, then by most recent show.
// scripts/generate_press_kit.py uses the same rule for the PDF, so keep the two in step.
(function () {
	const MAX_VENUES = 12;
	const section = document.getElementById('played');
	const list = document.getElementById('booking-venues');
	if (!section || !list) {
		return;
	}

	// Only http(s) links are used.
	function safeUrl(url) {
		return typeof url === 'string' && /^https?:\/\//i.test(url) ? url : null;
	}

	// Past shows arrive most recent first, so the first time a venue appears is its latest show.
	function highlightVenues(shows) {
		const venues = new Map();
		shows.forEach((show, index) => {
			if (!show || typeof show.venue !== 'string' || !show.venue.trim()) {
				return;
			}
			const city = typeof show.city === 'string' ? show.city.trim() : '';
			const key = show.venue.trim().toLowerCase() + '|' + city.toLowerCase();
			const entry = venues.get(key);
			if (entry) {
				entry.count += 1;
				if (!entry.url) {
					entry.url = safeUrl(show.venue_url);
				}
			} else {
				venues.set(key, {name: show.venue.trim(), city, url: safeUrl(show.venue_url), count: 1, first: index});
			}
		});
		return Array.from(venues.values())
			.sort((a, b) => b.count - a.count || a.first - b.first)
			.slice(0, MAX_VENUES);
	}

	function render(shows) {
		const venues = highlightVenues(Array.isArray(shows) ? shows : []);
		if (venues.length === 0) {
			return;
		}
		venues.forEach(venue => {
			const item = document.createElement('li');
			let name;
			if (venue.url) {
				name = document.createElement('a');
				name.href = venue.url;
				name.target = '_blank';
				name.rel = 'noopener';
			} else {
				name = document.createElement('span');
			}
			name.className = 'booking-venue-name';
			name.textContent = venue.name;
			item.append(name);
			if (venue.city) {
				const place = document.createElement('span');
				place.className = 'booking-venue-city';
				place.textContent = venue.city;
				item.append(place);
			}
			list.append(item);
		});
		section.hidden = false;
	}

	fetch('../data/past-shows.json')
		.then(response => {
			if (!response.ok) {
				throw new Error('HTTP ' + response.status);
			}
			return response.json();
		})
		.then(render)
		.catch(error => console.warn('Could not load past shows:', error));
})();
