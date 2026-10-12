/* Offline-first app shell. Bump CACHE whenever a shell file changes. */
const CACHE = 'headcount-v12';
const SHELL = [
  './', './index.html', './styles.css', './app.js', './manifest.webmanifest',
  './icons/icon-192.png', './icons/apple-touch-180.png', './icons/icon-512.png', './icons/maskable-512.png'
];

// The whole shell goes into a fresh cache in one step, fetched past the HTTP
// cache. Without `reload` a host's caching headers can bake a stale app.js in
// beside a new index.html, and a page built from mismatched files may not boot.
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(SHELL.map(u => new Request(u, { cache: 'reload' }))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// Strictly cache-first, and the cache is never written after install, so every
// file a page loads comes from one version. Changes arrive only as a new CACHE,
// which installs complete or not at all. A dead network never blocks a tap.
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== location.origin) return;
  e.respondWith(
    caches.open(CACHE)
      .then(c => c.match(req, { ignoreSearch: true }))
      .then(hit => hit || fetch(req).catch(() =>
        req.mode === 'navigate' ? caches.open(CACHE).then(c => c.match('./')) : Response.error()))
  );
});
