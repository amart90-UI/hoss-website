// Calendar view of the upcoming shows, with a List / Calendar toggle above the show list.
// Reads data/shows.json (the same file js/shows.js and the event pages use). Without JavaScript, or if the
// file can't be loaded, nothing is added and the page shows what js/shows.js draws.
//
// Time zones: every date and time on the calendar is the band's America/Denver date and time, taken from
// the "date" and "start_time" fields. "Today" and the first month shown are also worked out in Denver.
// If the visitor's own time zone shows a different time, the local time is added next to the Denver time.
(function () {
	const BAND_TIME_ZONE = 'America/Denver';
	const MONTHS_AHEAD = 3; // The calendar runs at least this many months past the current month.
	const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
		'October', 'November', 'December'];
	const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

	const listEl = document.getElementById('shows-upcoming');
	if (!listEl || !window.fetch || !window.Intl) {
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

	// ---------------------------------------------------------------- dates
	// A month is stored as one number, year * 12 + month (0-11), so adding and comparing months is simple.
	function monthOf(isoDateString) {
		const [year, month] = isoDateString.split('-').map(Number);
		return year * 12 + month - 1;
	}

	// Today's date in Denver, "YYYY-MM-DD", whatever time zone the visitor is in.
	function denverToday() {
		return new Intl.DateTimeFormat('en-CA', {
			timeZone: BAND_TIME_ZONE, year: 'numeric', month: '2-digit', day: '2-digit'
		}).format(new Date());
	}

	function isoDate(month, day) {
		return Math.floor(month / 12) + '-' + String(month % 12 + 1).padStart(2, '0') + '-' + String(day).padStart(2, '0');
	}

	function weekdayOf(year, monthIndex, day) {
		return new Date(Date.UTC(year, monthIndex, day)).getUTCDay();
	}

	// "2026-12-04" -> "Fri, Dec 4, 2026". Calculated without time zones, so the date can't shift by a day.
	function formatLongDate(isoDateString) {
		const [year, month, day] = isoDateString.split('-').map(Number);
		return WEEKDAYS[weekdayOf(year, month - 1, day)].slice(0, 3) + ', ' + MONTH_NAMES[month - 1].slice(0, 3)
			+ ' ' + day + ', ' + year;
	}

	// "19:00" -> "7:00 PM"
	function formatTime(time24) {
		const [hour, minute] = time24.split(':').map(Number);
		const hour12 = hour % 12 === 0 ? 12 : hour % 12;
		return hour12 + ':' + String(minute).padStart(2, '0') + ' ' + (hour < 12 ? 'AM' : 'PM');
	}

	// The show start in the visitor's own time zone, or null when it reads the same as Denver's.
	function localTimeNote(show) {
		const start = new Date(show.start);
		if (Number.isNaN(start.getTime())) {
			return null;
		}
		const timeFormat = {hour: 'numeric', minute: '2-digit'};
		const localTime = new Intl.DateTimeFormat(undefined, timeFormat).format(start);
		const denverTime = new Intl.DateTimeFormat(undefined, {...timeFormat, timeZone: BAND_TIME_ZONE}).format(start);
		const localDate = new Intl.DateTimeFormat('en-CA', {year: 'numeric', month: '2-digit', day: '2-digit'}).format(start);
		if (localDate === show.date && localTime === denverTime) {
			return null;
		}
		const dayPrefix = localDate === show.date
			? ''
			: new Intl.DateTimeFormat(undefined, {weekday: 'short', month: 'short', day: 'numeric'}).format(start) + ', ';
		return dayPrefix + localTime + ' your time';
	}

	// ---------------------------------------------------------------- show details under the calendar
	function buildCard(show) {
		const card = el('article', 'cal-card');
		const times = el('p', 'cal-card-time', formatTime(show.start_time)
			+ (show.end_time ? ' \u2013 ' + formatTime(show.end_time) : '') + ' MT');
		const local = localTimeNote(show);
		if (local) {
			times.append(el('span', 'cal-card-local', local));
		}
		const venue = el('h4', 'cal-card-venue');
		// Only same-site event pages are linked, matching js/shows.js.
		const pagePath = typeof show.page_path === 'string' && /^\/events\/[^/]+\/$/.test(show.page_path)
			? show.page_path
			: null;
		if (pagePath) {
			const link = el('a', '', show.venue);
			link.href = pagePath;
			venue.append(link);
		} else {
			venue.textContent = show.venue;
		}
		card.append(times, venue, el('p', 'cal-card-place', show.city + ', ' + show.state));
		if (show.notes) {
			card.append(el('p', 'cal-card-place', show.notes));
		}
		if (pagePath) {
			const more = el('a', 'show-action-link', 'Event details');
			more.href = pagePath;
			card.append(more);
		}
		return card;
	}

	// ---------------------------------------------------------------- the date picker
	// A month grid where only days with a show are buttons. Selecting one lists that day's shows below.
	function buildCalendar(shows, today) {
		const byDate = new Map();
		shows.forEach(show => {
			if (!byDate.has(show.date)) {
				byDate.set(show.date, []);
			}
			byDate.get(show.date).push(show);
		});

		const firstMonth = monthOf(today);
		const lastMonth = Math.max(firstMonth + MONTHS_AHEAD, ...shows.map(show => monthOf(show.date)));
		let current = firstMonth;
		let selected = null;

		const root = el('div', 'cal');
		const widget = el('div', 'cal-widget');
		const prev = el('button', 'cal-arrow cal-arrow-prev');
		const next = el('button', 'cal-arrow cal-arrow-next');
		const title = el('h3', 'cal-title');
		title.setAttribute('aria-live', 'polite');
		for (const [button, label] of [[prev, 'Previous month'], [next, 'Next month']]) {
			button.type = 'button';
			button.setAttribute('aria-label', label);
		}
		const header = el('div', 'cal-header');
		header.append(prev, title, next);

		const weekdays = el('div', 'cal-weekdays');
		weekdays.setAttribute('aria-hidden', 'true');
		WEEKDAYS.forEach(name => weekdays.append(el('div', '', name.slice(0, 3))));

		const grid = el('div', 'cal-grid');
		widget.append(header, weekdays, grid);

		const details = el('div', 'cal-details');
		details.setAttribute('aria-live', 'polite');
		details.append(el('p', 'cal-hint', 'Select a highlighted date to see the show details.'));
		root.append(widget, details, el('p', 'cal-note', 'All dates and times are Mountain Time (Denver).'));

		function showDetails(date) {
			selected = date;
			details.replaceChildren(el('h3', 'cal-details-date', formatLongDate(date)), ...byDate.get(date).map(buildCard));
			grid.querySelectorAll('button.cal-day').forEach(button => {
				button.setAttribute('aria-pressed', String(button.dataset.date === selected));
			});
		}

		function render() {
			const year = Math.floor(current / 12);
			const monthIndex = current % 12;
			title.textContent = MONTH_NAMES[monthIndex] + ' ' + year;
			prev.disabled = current <= firstMonth;
			next.disabled = current >= lastMonth;

			const cells = [];
			for (let i = weekdayOf(year, monthIndex, 1); i > 0; i--) {
				const pad = el('span', 'cal-pad');
				pad.setAttribute('aria-hidden', 'true');
				cells.push(pad);
			}
			const daysInMonth = new Date(Date.UTC(year, monthIndex + 1, 0)).getUTCDate();
			for (let day = 1; day <= daysInMonth; day++) {
				const date = isoDate(current, day);
				const count = (byDate.get(date) || []).length;
				const cell = count ? el('button', 'cal-day', String(day)) : el('span', 'cal-day', String(day));
				if (date === today) {
					cell.classList.add('is-today');
				}
				if (count) {
					cell.type = 'button';
					cell.dataset.date = date;
					cell.setAttribute('aria-pressed', String(date === selected));
					cell.setAttribute('aria-label', formatLongDate(date) + ', ' + count + (count > 1 ? ' shows' : ' show'));
					cell.addEventListener('click', () => showDetails(date));
				}
				cells.push(cell);
			}
			grid.replaceChildren(...cells);
		}

		function go(step) {
			current = Math.min(Math.max(current + step, firstMonth), lastMonth);
			render();
			// A disabled button can't keep focus, so move it to the arrow that still works.
			if (prev.disabled && document.activeElement !== next && step < 0) {
				next.focus();
			} else if (next.disabled && document.activeElement !== prev && step > 0) {
				prev.focus();
			}
		}
		prev.addEventListener('click', () => go(-1));
		next.addEventListener('click', () => go(1));
		render();
		return root;
	}

	// ---------------------------------------------------------------- List / Calendar toggle
	function addTabs(calendar) {
		const tabs = el('div', 'view-tabs');
		tabs.setAttribute('role', 'tablist');
		tabs.setAttribute('aria-label', 'Show view');

		const calendarPanel = el('div');
		calendarPanel.id = 'shows-calendar';
		calendarPanel.setAttribute('role', 'tabpanel');
		calendarPanel.setAttribute('aria-labelledby', 'tab-calendar');
		calendarPanel.hidden = true;
		calendarPanel.append(calendar);

		listEl.setAttribute('role', 'tabpanel');
		listEl.setAttribute('aria-labelledby', 'tab-list');

		const views = [
			{id: 'tab-list', label: 'List', panel: listEl},
			{id: 'tab-calendar', label: 'Calendar', panel: calendarPanel}
		];
		const buttons = views.map(view => {
			const button = el('button', 'view-tab', view.label);
			button.type = 'button';
			button.id = view.id;
			button.setAttribute('role', 'tab');
			button.setAttribute('aria-controls', view.panel.id);
			return button;
		});

		function select(index, focus) {
			views.forEach((view, i) => {
				const selected = i === index;
				buttons[i].setAttribute('aria-selected', String(selected));
				buttons[i].tabIndex = selected ? 0 : -1;
				view.panel.hidden = !selected;
			});
			if (focus) {
				buttons[index].focus();
			}
		}
		buttons.forEach((button, index) => {
			button.addEventListener('click', () => select(index, false));
			button.addEventListener('keydown', event => {
				const keys = {ArrowLeft: -1, ArrowRight: 1};
				if (event.key in keys) {
					event.preventDefault();
					select((index + keys[event.key] + views.length) % views.length, true);
				} else if (event.key === 'Home' || event.key === 'End') {
					event.preventDefault();
					select(event.key === 'Home' ? 0 : views.length - 1, true);
				}
			});
		});

		tabs.append(...buttons);
		listEl.before(tabs);
		listEl.after(calendarPanel);
		select(0, false);
	}

	fetch('data/shows.json')
		.then(response => {
			if (!response.ok) {
				throw new Error('HTTP ' + response.status);
			}
			return response.json();
		})
		.then(data => {
			const shows = (Array.isArray(data) ? data : []).filter(show => {
				const valid = show && /^\d{4}-\d{2}-\d{2}$/.test(show.date) && /^\d{2}:\d{2}$/.test(show.start_time)
					&& typeof show.venue === 'string';
				if (!valid) {
					console.warn('Calendar skipped a show with missing or invalid fields:', show);
				}
				return valid;
			});
			if (shows.length > 0) {
				addTabs(buildCalendar(shows, denverToday()));
			}
		})
		.catch(error => console.error('Could not build the show calendar:', error));
})();
