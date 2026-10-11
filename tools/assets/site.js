(function () {
  // reading progress
  var bar = document.getElementById('progress');
  function onScroll() {
    var h = document.documentElement, max = h.scrollHeight - h.clientHeight;
    if (bar) bar.style.width = (max > 0 ? (h.scrollTop / max) * 100 : 0) + '%';
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // remember the last chapter opened, and offer it on the home page
  var KEY = '8ba-last-chapter';
  var main = document.querySelector('main.read[data-chapter]');
  try {
    if (main) localStorage.setItem(KEY, JSON.stringify({ slug: main.dataset.chapter, label: main.dataset.label }));
    var last = JSON.parse(localStorage.getItem(KEY) || 'null');
    var start = document.getElementById('startBtn');
    if (start && last && last.slug && last.slug !== 'prologue') {
      start.textContent = 'Continue: ' + last.label;
      start.setAttribute('href', last.slug + '/');
      var li = document.querySelector('.contents a[href="' + last.slug + '/"]');
      if (li) li.classList.add('last');
    }
  } catch (e) {}

  // giscus comment threads: one per section, Praise or Suggestions, loaded on demand
  var fb = document.querySelector('.fb');
  if (!fb) return;
  var host = fb.querySelector('.giscus-host');
  var tabs = fb.querySelectorAll('.tab');
  function load(kind) {
    var d = fb.dataset;
    var praise = kind === 'praise';
    host.innerHTML = '<div class="giscus"></div>';
    var s = document.createElement('script');
    s.src = 'https://giscus.app/client.js';
    s.async = true;
    s.crossOrigin = 'anonymous';
    var attrs = {
      'data-repo': d.repo,
      'data-repo-id': d.repoId,
      'data-category': praise ? d.praiseCat : d.suggCat,
      'data-category-id': praise ? d.praiseCatId : d.suggCatId,
      'data-mapping': 'specific',
      'data-term': d.term + (praise ? ' · Praise' : ' · Suggestions'),
      'data-strict': '1',
      'data-reactions-enabled': '1',
      'data-emit-metadata': '0',
      'data-input-position': 'top',
      'data-theme': 'preferred_color_scheme',
      'data-lang': 'en',
      'data-loading': 'lazy'
    };
    Object.keys(attrs).forEach(function (k) { s.setAttribute(k, attrs[k]); });
    host.appendChild(s);
    Array.prototype.forEach.call(tabs, function (t) { t.setAttribute('aria-selected', String(t.dataset.kind === kind)); });
  }
  Array.prototype.forEach.call(tabs, function (t) {
    t.addEventListener('click', function () { load(t.dataset.kind); });
  });
  if (location.hash === '#reader-notes' && tabs.length) load('praise');
})();
