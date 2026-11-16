// Toggle class menu
document.addEventListener('DOMContentLoaded', function () {
	document.querySelector('.menu')?.addEventListener('click', function () {
		this.classList.toggle('active');
		const menus = [
			'.ss-menu1',
			'.ss-menu2',
			'.ss-menu3',
			'.ss-menu4',
			'.ss-menu5'
		];
		menus.forEach(menu => {
			document.querySelector(menu)?.classList.toggle('visible' + menu[8], this.classList.contains('active'));
		});
	});
	document.querySelectorAll('.ss-menu').forEach(ssMenu => {
		ssMenu.addEventListener('click', function () {
			document.querySelector('.menu')?.classList.remove('active');
			document.querySelectorAll('[class*="ss-menu"]').forEach(el => {
				el.classList.remove('visible' + el.className.match(/\d+/)[0]);
			});
		});
	});
	window.addEventListener('scroll', function () {
		if (document.querySelector('.menu')?.classList.contains('active')) {
			document.querySelector('.menu').classList.remove('active');
			document.querySelectorAll('[class*="ss-menu"]').forEach(el => {
				el.classList.remove('visible' + el.className.match(/\d+/)[0]);
			});
		}
	});
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
// Member cards: click opens the member's Instagram (set data-instagram-url on each card in index.html)
document.addEventListener('DOMContentLoaded', function () {
document.querySelectorAll('.card[data-instagram-url]').forEach(card => {
card.addEventListener('click', function () {
window.location.href = card.dataset.instagramUrl;
});
});
});
