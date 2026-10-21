// Shell and images cache-first, API network-first with cache fallback.
const SHELL = "shell-v1";
const DATA = "data-v1";
const ASSETS = ["/", "/app.js", "/style.css", "/manifest.json", "/icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(
    ks.filter((k) => ![SHELL, DATA].includes(k)).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/")) {
    e.respondWith(fetch(e.request).then((r) => {
      caches.open(DATA).then((c) => c.put(e.request, r.clone()));
      return r;
    }).catch(() => caches.match(e.request)));
    return;
  }
  e.respondWith(caches.match(e.request).then((hit) => hit || fetch(e.request).then((r) => {
    caches.open(url.pathname.startsWith("/images/") ? DATA : SHELL).then((c) => c.put(e.request, r.clone()));
    return r;
  })));
});
