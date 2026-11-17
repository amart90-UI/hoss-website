// Hamburger menu: a toggle button that reveals the section links.
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

	function setOpen(open) {
		toggle.classList.toggle('active', open);
		toggle.setAttribute('aria-expanded', String(open));
		if (list) {
			list.inert = !open;
		}
		items.forEach((item, index) => item.classList.toggle('visible' + (index + 1), open));
	}

	toggle.addEventListener('click', () => setOpen(!isOpen()));
	items.forEach(item => item.addEventListener('click', () => setOpen(false)));

	// Escape closes the menu and returns focus to the toggle button.
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
// Parallax effect
document.addEventListener('DOMContentLoaded', function () {
	document.querySelectorAll('.rellax').forEach(el => {
		el.style.transform = 'translateX(-50%)';
	});
	if (typeof Rellax === 'function') {
		new Rellax('.rellax');
	}
});
// Lazy loading: swap the blurred image (src) for the full image (data-src) when it nears the viewport
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
// Handle animations on scroll
function revealOnScroll() {
	const sizePage = window.innerHeight;
	const trigger = 100;
	document.querySelectorAll('.animatableY, .animatableX, .animatableOpacity').forEach(el => {
		if (el.getBoundingClientRect().top + trigger <= sizePage) {
			el.classList.add('showed');
		}
	});
}
window.addEventListener('scroll', revealOnScroll);
window.addEventListener('load', revealOnScroll);
// Scroll Up Button
document.addEventListener('DOMContentLoaded', function () {
	const upArrow = document.getElementById('upArrow');
	if (upArrow) {
		let lastScrollTop = 0;
		window.addEventListener('scroll', function () {
			const currentScroll = window.scrollY;
			if (currentScroll > 600 && currentScroll < lastScrollTop) {
				upArrow.style.display = 'block';
			} else {
				upArrow.style.display = 'none';
			}
			lastScrollTop = currentScroll;
		});
		upArrow.addEventListener('click', function () {
			window.scrollTo({top: 0, behavior: 'smooth'});
		});
	}
});
