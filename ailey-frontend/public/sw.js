// Ailey Service Worker — aggressive MP3 + cover caching
// Cache-first for all /api/songs/*/mp3, /api/songs/*/cover, /api/albums/*/cover
const CACHE = 'ailey-media-v1';
const AUDIO_CACHE = 'ailey-audio-v1';

const isMediaUrl = (url) => {
  return /\/api\/songs\/[^/]+\/mp3/.test(url) ||
         /\/api\/songs\/[^/]+\/cover/.test(url) ||
         /\/api\/albums\/[^/]+\/cover/.test(url);
};

self.addEventListener('install', (e) => {
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(clients.claim());
});

self.addEventListener('fetch', (e) => {
  const url = e.request.url;
  if (!isMediaUrl(url)) return; // Let non-media requests pass through normally

  // Cache-first strategy for media files
  e.respondWith(
    (async () => {
      // Choose the right cache bucket
      const cacheName = /\/mp3/.test(url) ? AUDIO_CACHE : CACHE;
      const cache = await caches.open(cacheName);
      const cached = await cache.match(e.request);
      if (cached) return cached;

      // Not in cache → fetch and store
      try {
        const response = await fetch(e.request);
        if (response.ok) {
          // Clone before consuming
          cache.put(e.request, response.clone());
        }
        return response;
      } catch (err) {
        // Offline + no cache → 503
        return new Response('Offline — media not cached', { status: 503 });
      }
    })()
  );
});
