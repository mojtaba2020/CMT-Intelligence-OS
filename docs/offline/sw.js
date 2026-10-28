// CMT Offline v3.8.1; cache only the application shell.
const CACHE='cmt-standalone-v3-8-2';
const FILES=['./','./index.html','./styles.css','./offline.css','./test_catalog.js','./offline_store.js','./offline_queue.js','./demo_seed.js','./offline.js','./register-sw.js','./manifest.webmanifest','./icons/icon-192.png','./icons/icon-512.png'];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(FILES)).then(()=>self.skipWaiting())));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('cmt-standalone-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{
 const req=e.request,u=new URL(req.url);
 if(req.method!=='GET'||u.origin!==self.location.origin||!u.pathname.startsWith(new URL('./',self.location.href).pathname))return;
 if(req.mode==='navigate'){e.respondWith(fetch(req).catch(()=>caches.match('./index.html')));return;}
 if(!FILES.some(f=>new URL(f,self.location.href).href===u.href))return;
 e.respondWith(caches.match(req).then(hit=>hit||fetch(req)));
});
