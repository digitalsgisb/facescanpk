/* Public app assets only. Attendance, login responses and uploaded photos stay on the network. */
const CACHE='attendance-public-v1';
const OFFLINE='/offline.html';
const PUBLIC_FILES=[OFFLINE,'/manifest.webmanifest','/favicon.svg','/icons/icon-192.png','/icons/icon-512.png','/icons/icon-maskable-512.png','/icons/apple-touch-icon.png'];
self.addEventListener('install',event=>{
  event.waitUntil(Promise.all(PUBLIC_FILES.map(async path=>{
    const response=await fetch(path,{cache:'reload'}),type=response.headers.get('content-type')||'';
    if(!response.ok||response.redirected||(path===OFFLINE?!type.includes('text/html'):type.includes('text/html')))throw new Error('Public app asset unavailable');
    return [path,response];
  })).then(async files=>{const cache=await caches.open(CACHE);await Promise.all(files.map(([path,response])=>cache.put(path,response)))}));
});
self.addEventListener('activate',event=>{
  event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('attendance-public-')&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim()));
});
self.addEventListener('message',event=>{
  if(event.data?.type==='ACTIVATE_UPDATE')self.skipWaiting();
});
self.addEventListener('fetch',event=>{
  const request=event.request,url=new URL(request.url);
  if(request.method!=='GET'||url.origin!==self.location.origin||url.pathname==='/api'||url.pathname.startsWith('/api/')||url.pathname.startsWith('/uploads/'))return;
  if(request.mode==='navigate'){
    // Fresh HTML always wins; reconnecting never replays a saved dashboard or private data.
    event.respondWith(fetch(request).catch(()=>caches.match(OFFLINE)));
    return;
  }
  const hashedAsset=/^\/assets\/[^/]+-[A-Za-z0-9_-]+\.(?:js|css|woff2?)$/.test(url.pathname);
  if(!hashedAsset&&!PUBLIC_FILES.includes(url.pathname))return;
  event.respondWith(caches.open(CACHE).then(async cache=>{
    const cached=await cache.match(request);
    if(cached)return cached;
    const response=await fetch(request);
    if(response.ok&&response.type!=='opaque'&&!response.headers.get('content-type')?.includes('text/html'))await cache.put(request,response.clone());
    return response;
  }));
});
