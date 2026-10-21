// Network-first for everything (LAN is fast, updates land immediately); cache fallback for offline.
// Images are cache-first: they never change for a given filename.
const CACHE = "recipes-v2";
const ASSETS = ["/", "/app.js", "/style.css", "/manifest.json", "/icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(
    ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  const store = (r) => { if (r.ok) caches.open(CACHE).then((c) => c.put(e.request, r.clone())); return r; };
  if (url.pathname.startsWith("/images/")) {
    e.respondWith(caches.match(e.request).then((hit) => hit || fetch(e.request).then(store)));
  } else {
    e.respondWith(fetch(e.request).then(store).catch(() => caches.match(e.request)));
  }
});
