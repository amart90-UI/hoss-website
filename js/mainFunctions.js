// Page behavior: hamburger menu, parallax logo, lazy-loaded member photos, fade-in on scroll,
// and the back-to-top arrow.

// Hamburger menu. The button opens and closes the page and section links.
// While closed, the links are "inert": they can't be focused or clicked and screen readers skip them.
document.addEventListener('DOMContentLoaded', function () {
	const nav = document.querySelector('.menu-nav');
	const toggle = document.querySelector('.menu');
	if (!nav || !toggle) {
		return;
	}
	const list = document.getElementById('menu-items');
	const items = nav.querySelectorAll('.ss-menu');
	const isOpen = () => toggle.classList.contains('active');

	// The "open" class slides the links into place (see css/style.css).
	function setOpen(open) {
		toggle.classList.toggle('active', open);
		toggle.setAttribute('aria-expanded', String(open));
		if (list) {
			list.inert = !open;
		}
		if (list) {
			list.classList.toggle('open', open);
		}
	}

	toggle.addEventListener('click', () => setOpen(!isOpen()));
	items.forEach(item => item.addEventListener('click', () => setOpen(false)));

	// Escape closes the menu and returns focus to the menu button.
	nav.addEventListener('keydown', function (event) {
		if (event.key === 'Escape' && isOpen()) {
			setOpen(false);
			toggle.focus();
		}
	});

	// Tabbing out of the menu closes it.
	nav.addEventListener('focusout', function (event) {
		if (event.relatedTarget && !nav.contains(event.relatedTarget)) {
			setOpen(false);
		}
	});

	// Scrolling closes the menu, except while someone is moving through it with the keyboard.
	window.addEventListener('scroll', function () {
		if (!isOpen()) {
			return;
		}
		const focused = document.activeElement;
		if (focused && nav.contains(focused) && focused.matches(':focus-visible')) {
			return;
		}
		setOpen(false);
	}, {passive: true});
});

// Parallax: the hero logo scrolls at a different speed than the page (js/vendor/rellax.min.js).
document.addEventListener('DOMContentLoaded', function () {
	document.querySelectorAll('.rellax').forEach(el => {
		el.style.transform = 'translateX(-50%)';
	});
	if (typeof Rellax === 'function') {
		new Rellax('.rellax');
	}
});

// Member photos: show the small blurred image (src) first, then swap in the full image (data-src)
// shortly before it scrolls into view.
document.addEventListener('DOMContentLoaded', function () {
	const images = document.querySelectorAll('img.lazyload[data-src]');
	const load = img => {
		img.src = img.dataset.src;
		img.removeAttribute('data-src');
	};
	if (!('IntersectionObserver' in window)) {
		images.forEach(load);
		return;
	}
	const observer = new IntersectionObserver((entries, obs) => {
		entries.forEach(entry => {
			if (entry.isIntersecting) {
				load(entry.target);
				obs.unobserve(entry.target);
			}
		});
	}, {rootMargin: '200px'});
	images.forEach(img => observer.observe(img));
});

// Fade-in on scroll: elements with an "animatable" class get "showed" once they are 100px into the window.
// js/shows.js calls this again after it adds the show rows.
function revealOnScroll() {
	const windowHeight = window.innerHeight;
	const offset = 100;
	document.querySelectorAll('.animatableY, .animatableX, .animatableOpacity').forEach(el => {
		if (el.getBoundingClientRect().top + offset <= windowHeight) {
			el.classList.add('showed');
		}
	});
}

window.addEventListener('scroll', revealOnScroll);
window.addEventListener('load', revealOnScroll);

// Back-to-top arrow: appears when scrolling up after the first 600px. It's a plain link to #top,
// so it works with a mouse or the keyboard; it also appears whenever it has keyboard focus (see CSS).
document.addEventListener('DOMContentLoaded', function () {
	const upArrow = document.getElementById('upArrow');
	if (!upArrow) {
		return;
	}
	let lastScrollTop = 0;
	window.addEventListener('scroll', function () {
		const currentScroll = window.scrollY;
		upArrow.classList.toggle('shown', currentScroll > 600 && currentScroll < lastScrollTop);
		lastScrollTop = currentScroll;
	});
});

// Build timestamp. The deploy workflow writes the UTC build time into the <time> element's datetime
// attribute; show it in the visitor's own date, time and time zone. Hidden if there is no valid time
// (for example when running locally, where the placeholder is never replaced) or if the build is more
// than 3 days old, so a stale date never makes the site look abandoned.
document.addEventListener('DOMContentLoaded', function () {
	const el = document.getElementById('buildTime');
	if (!el) {
		return;
	}
	const MAX_AGE_MS = 3 * 24 * 60 * 60 * 1000;
	const date = new Date(el.getAttribute('datetime'));
	if (isNaN(date) || Date.now() - date.getTime() > MAX_AGE_MS) {
		el.parentElement.hidden = true;
		return;
	}
	el.textContent = date.toLocaleString(undefined, {
		year: 'numeric',
		month: 'short',
		day: 'numeric',
		hour: 'numeric',
		minute: '2-digit',
		timeZoneName: 'short'
	});
	el.title = date.toISOString();
});
