// YouTube video gallery.
// Video list: data/videos.json (order in the file = order on the page).
// The YouTube player is only created when a visitor clicks a video.
(function () {
	const DATA_URL = 'data/videos.json';
	const VIDEO_ID = /^[A-Za-z0-9_-]{11}$/;
	const container = document.getElementById('video-gallery');
	if (!container) {
		return;
	}

	let playing = null; // {frame, button} of the video currently loaded in a player

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

	function showMessage(text) {
		container.replaceChildren(el('p', 'hardLight', text));
	}

	// Put the thumbnail button back in place of a player that was loaded earlier.
	function resetPlaying() {
		if (playing) {
			playing.frame.replaceChildren(playing.button);
			playing = null;
		}
	}

	function loadPlayer(frame, button, video) {
		resetPlaying();
		const iframe = document.createElement('iframe');
		iframe.src = 'https://www.youtube-nocookie.com/embed/' + video.id + '?autoplay=1&rel=0';
		iframe.title = video.title;
		iframe.allow = 'autoplay; encrypted-media; picture-in-picture; fullscreen';
		iframe.allowFullscreen = true;
		iframe.referrerPolicy = 'strict-origin-when-cross-origin';
		frame.replaceChildren(iframe);
		playing = {frame, button};
	}

	function buildItem(video) {
		const item = el('li', 'video-item');
		const frame = el('div', 'video-frame');
		const button = el('button', 'video-play');
		button.type = 'button';
		button.setAttribute('aria-label', 'Play video: ' + video.title);
		const img = document.createElement('img');
		img.src = 'https://i.ytimg.com/vi/' + video.id + '/hqdefault.jpg';
		img.alt = '';
		img.width = 480;
		img.height = 360;
		img.loading = 'lazy';
		button.append(img, el('span', 'video-playicon'));
		button.addEventListener('click', () => loadPlayer(frame, button, video));
		frame.append(button);
		item.append(frame, el('p', 'video-title', video.title));
		return item;
	}

	function buildArrow(direction, scroller) {
		const arrow = el('button', 'video-arrow video-arrow-' + direction, direction === 'prev' ? '\u2039' : '\u203A');
		arrow.type = 'button';
		arrow.setAttribute('aria-label', direction === 'prev' ? 'Previous videos' : 'Next videos');
		arrow.addEventListener('click', () => {
			const step = scroller.clientWidth * 0.8 * (direction === 'prev' ? -1 : 1);
			scroller.scrollBy({left: step, behavior: 'smooth'});
		});
		return arrow;
	}

	function render(data) {
		const videos = (data.videos || []).filter(video => {
			const valid = video && VIDEO_ID.test(video.id) && typeof video.title === 'string' && video.title;
			if (!valid) {
				console.warn('Skipping invalid entry in ' + DATA_URL + ':', video);
			}
			return valid;
		});
		if (videos.length === 0) {
			showMessage('Videos coming soon.');
			return;
		}
		const list = el('ul', 'video-list');
		videos.forEach(video => list.append(buildItem(video)));

		const scroller = el('div', 'video-scroller');
		scroller.tabIndex = 0;
		scroller.setAttribute('role', 'region');
		scroller.setAttribute('aria-label', 'Video gallery (scroll horizontally)');
		scroller.append(list);

		const wrapper = el('div', 'video-gallery-inner');
		wrapper.append(buildArrow('prev', scroller), scroller, buildArrow('next', scroller));
		container.replaceChildren(wrapper);

		if (typeof data.channel_url === 'string' && /^https:\/\//.test(data.channel_url)) {
			const more = el('p', 'pink');
			const link = el('a', '', 'Watch more on YouTube \u279E');
			link.href = data.channel_url;
			link.target = '_blank';
			link.rel = 'noopener';
			more.append(link);
			container.append(more);
		}
	}

	fetch(DATA_URL)
		.then(response => {
			if (!response.ok) {
				throw new Error('HTTP ' + response.status);
			}
			return response.json();
		})
		.then(render)
		.catch(error => {
			console.error('Could not load ' + DATA_URL + ':', error);
			showMessage('Videos are unavailable right now.');
		});
})();
