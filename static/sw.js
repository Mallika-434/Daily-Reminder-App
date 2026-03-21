// RoutineAI Service Worker
const CACHE = 'routineai-v2';

// App shell — pages and assets cached on install
const SHELL = [
  '/',
  '/static/manifest.json',
  '/static/icons/icon-192x192.png',
];

// ── Install: cache app shell ───────────────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(SHELL))
  );
  self.skipWaiting();
});

// ── Activate: remove old caches ───────────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// ── Fetch: network-first for API, cache-first for static ─────────────────────
self.addEventListener('fetch', event => {
  const url = event.request.url;

  // Skip non-GET and cross-origin requests
  if (event.request.method !== 'GET' || !url.startsWith(self.location.origin)) return;

  // API: network first, fall back to cached response
  if (url.includes('/api/')) {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE).then(cache => cache.put(event.request, clone));
          }
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Static assets: cache first, then network; cache new responses
  event.respondWith(
    caches.match(event.request).then(cached => {
      if (cached) return cached;
      return fetch(event.request).then(response => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE).then(cache => cache.put(event.request, clone));
        }
        return response;
      }).catch(() => {
        // Offline fallback for navigation requests
        if (event.request.mode === 'navigate') {
          return caches.match('/');
        }
      });
    })
  );
});

// ── Message: receive alarm trigger from page JS ───────────────────────────────
self.addEventListener('message', event => {
  if (!event.data) return;

  if (event.data.type === 'alarm') {
    event.waitUntil(
      self.registration.showNotification('RoutineAI ⏰', {
        body:             `Time for: ${event.data.name}`,
        icon:             '/static/icons/icon-192x192.png',
        badge:            '/static/icons/icon-192x192.png',
        vibrate:          [200, 100, 200, 100, 200],
        tag:              'routineai-alarm',
        requireInteraction: true,
        actions: [
          { action: 'snooze',  title: '💤 Snooze' },
          { action: 'dismiss', title: '✓ Got it' },
        ],
        data: { logId: event.data.logId },
      })
    );
  }
});

// ── Notification click: handle actions ────────────────────────────────────────
self.addEventListener('notificationclick', event => {
  event.notification.close();

  if (event.action === 'snooze') {
    // Tell the open client to snooze
    event.waitUntil(
      clients.matchAll({ type: 'window', includeUncontrolled: true }).then(cs => {
        if (cs.length > 0) {
          cs[0].postMessage({ type: 'snooze-alarm' });
          return cs[0].focus();
        }
        return clients.openWindow('/');
      })
    );
  } else {
    // Open or focus the app
    event.waitUntil(
      clients.matchAll({ type: 'window', includeUncontrolled: true }).then(cs => {
        if (cs.length > 0) return cs[0].focus();
        return clients.openWindow('/');
      })
    );
  }
});

// ── Background sync: refresh API data when connection restores ────────────────
self.addEventListener('sync', event => {
  if (event.tag === 'sync-routineai') {
    event.waitUntil(
      Promise.allSettled([
        fetch('/api/today?schedule=home_workout').then(r => {
          if (r.ok) caches.open(CACHE).then(c => c.put('/api/today?schedule=home_workout', r));
        }),
        fetch('/api/today?schedule=gym_day').then(r => {
          if (r.ok) caches.open(CACHE).then(c => c.put('/api/today?schedule=gym_day', r));
        }),
      ])
    );
  }
});
