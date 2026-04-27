self.addEventListener('install', (e) => { console.log('SW instalado'); });
self.addEventListener('fetch', (e) => { e.respondWith(fetch(e.request)); });