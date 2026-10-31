/*
 * Libre Library service worker.
 *
 * Deliberately conservative: it only caches immutable static assets (icons, JS,
 * CSS) and Google Fonts with a stale-while-revalidate strategy so the installed
 * app shell loads instantly and survives flaky networks. It never caches HTML
 * pages, API responses, or book content — those stay authenticated and fresh.
 */
const CACHE = 'libre-static-v1';
const PRECACHE = [
  '/static/Libre-Library_icon.svg',
  '/static/Libre-Library_logo.svg',
  '/static/tars_icon.svg',
  '/manifest.webmanifest'
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE).catch(() => {}))
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  let url;
  try { url = new URL(req.url); } catch (e) { return; }

  const sameOrigin = url.origin === self.location.origin;
  const isStatic = sameOrigin && url.pathname.startsWith('/static/');
  const isFont = url.origin === 'https://fonts.googleapis.com' || url.origin === 'https://fonts.gstatic.com';

  // Only intercept cacheable static assets; everything else goes straight to the network.
  if (!isStatic && !isFont) return;

  event.respondWith(
    caches.open(CACHE).then((cache) =>
      cache.match(req).then((cached) => {
        const network = fetch(req).then((resp) => {
          if (resp && (resp.status === 200 || resp.type === 'opaque')) {
            cache.put(req, resp.clone()).catch(() => {});
          }
          return resp;
        }).catch(() => cached);
        return cached || network;
      })
    )
  );
});
