'use strict';
const CACHE='aladin-benov-v9';
const APP_FILES=['./','./index.html','./style.css','./app.js','./manifest.webmanifest','./icon.svg','./data/forecast.json'];
self.addEventListener('install',event=>event.waitUntil((async()=>{const cache=await caches.open(CACHE);await cache.addAll(APP_FILES);await self.skipWaiting();})()));
self.addEventListener('activate',event=>event.waitUntil((async()=>{const keys=await caches.keys();await Promise.all(keys.filter(key=>key.startsWith('aladin-benov-')&&key!==CACHE).map(key=>caches.delete(key)));await self.clients.claim();})()));
self.addEventListener('fetch',event=>{
  const url=new URL(event.request.url);
  if(url.origin!==self.location.origin||event.request.method!=='GET')return;
  const isAppShell=/\/(?:index\.html|app\.js|style\.css)$/.test(url.pathname)||url.pathname.endsWith('/')||url.pathname.endsWith('/data/forecast.json');
  if(isAppShell){
    event.respondWith((async()=>{try{const response=await fetch(event.request,{cache:'no-store'});if(response.ok){const cache=await caches.open(CACHE);await cache.put(event.request,response.clone());}return response;}catch(error){const cached=await caches.match(event.request);if(cached)return cached;throw error;}})());
  }else{
    event.respondWith((async()=>{const cached=await caches.match(event.request);if(cached)return cached;const response=await fetch(event.request);if(response.ok){const cache=await caches.open(CACHE);await cache.put(event.request,response.clone());}return response;})());
  }
});
