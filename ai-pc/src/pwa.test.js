import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {photoDimensions,preparePhoto} from './photo-upload.js';

const source=await readFile(new URL('../public/sw.js',import.meta.url),'utf8');
function worker(){
  const handlers={},buckets=new Map(),origin='https://attendance.example',calls=[];
  let offline=false,badAssets=false,activated=false;
  const key=request=>new URL(typeof request==='string'?request:request.url,origin).href;
  const caches={
    async open(name){if(!buckets.has(name))buckets.set(name,new Map());const bucket=buckets.get(name);return {match:async request=>bucket.get(key(request))?.clone(),put:async(request,response)=>{bucket.set(key(request),response.clone())}}},
    async match(request){for(const bucket of buckets.values())if(bucket.has(key(request)))return bucket.get(key(request)).clone()},
    async keys(){return [...buckets.keys()]},async delete(name){return buckets.delete(name)}
  };
  const self={location:{origin},clients:{claim:async()=>{}},skipWaiting:async()=>{activated=true},addEventListener:(name,handler)=>{handlers[name]=handler}};
  const fetch=async request=>{
    const url=key(request);calls.push(url);
    if(offline)throw new Error('Offline');
    const pathname=new URL(url).pathname,type=pathname==='/offline.html'||badAssets?'text/html':pathname.endsWith('.js')?'application/javascript':pathname.endsWith('.webmanifest')?'application/manifest+json':'image/png';
    return new Response(pathname==='/offline.html'?'Offline test page':'Public asset',{headers:{'content-type':type}});
  };
  vm.runInNewContext(source,{self,caches,fetch,URL});
  async function lifecycle(name){let work;handlers[name]({waitUntil:promise=>{work=promise}});await work}
  function request(path,{method='GET',mode='cors'}={}){let response;handlers.fetch({request:{url:new URL(path,origin).href,method,mode},respondWith:promise=>{response=promise}});return response}
  return {handlers,buckets,caches,calls,lifecycle,request,setOffline:value=>{offline=value},setBadAssets:value=>{badAssets=value},activated:()=>activated};
}
test('worker keeps API, authentication, uploaded photos, POSTs and external requests on the network',()=>{
  const app=worker();
  for(const path of ['/api/state','/api/auth/login','/api/events','/api/clock','/uploads/private.jpg','https://other.example/assets/app-abcd.js'])assert.equal(app.request(path),undefined);
  assert.equal(app.request('/api/photos',{method:'POST'}),undefined);
  assert.equal(app.request('/assets/app-abcd.js',{method:'POST'}),undefined);
  assert.equal(app.calls.length,0);
});
test('offline navigation gets the public connection page and never a cached dashboard',async()=>{
  const app=worker();await app.lifecycle('install');app.setOffline(true);
  const response=await app.request('/',{mode:'navigate'});
  assert.equal(await response.text(),'Offline test page');
  for(const bucket of app.buckets.values())assert.ok(!bucket.has('https://attendance.example/'));
});
test('only immutable hashed assets are reused and HTML is not cached as a script',async()=>{
  const app=worker();
  assert.equal(app.request('/unknown.js'),undefined);
  await app.request('/assets/index-abcd.js');await app.request('/assets/index-abcd.js');
  assert.equal(app.calls.length,1);
  app.setBadAssets(true);await app.request('/assets/index-new.js');await app.request('/assets/index-new.js');
  assert.equal(app.calls.length,3);
});
test('install rejects sign-in/error HTML returned in place of public assets',async()=>{
  const app=worker();app.setBadAssets(true);
  await assert.rejects(app.lifecycle('install'),/Public app asset unavailable/);
  assert.equal(app.buckets.size,0);
});
test('activation only cleans this app caches and applying updates is explicit',async()=>{
  const app=worker();await app.caches.open('another-app');await app.caches.open('attendance-public-old');
  await app.lifecycle('activate');
  assert.equal(app.buckets.has('another-app'),true);assert.equal(app.buckets.has('attendance-public-old'),false);
  assert.equal(app.activated(),false);
  app.handlers.message({data:{type:'ACTIVATE_UPDATE'}});assert.equal(app.activated(),true);
});
test('phone photo sizing preserves aspect ratio and never enlarges small photos',()=>{
  assert.deepEqual(photoDimensions(4000,3000),{width:1600,height:1200});
  assert.deepEqual(photoDimensions(3000,4000),{width:1200,height:1600});
  assert.deepEqual(photoDimensions(600,400),{width:600,height:400});
  assert.throws(()=>photoDimensions(0,400),/valid photo/);
});
test('oversized and non-photo uploads are rejected before decoding',async()=>{
  await assert.rejects(preparePhoto({size:25_000_001,type:'image/jpeg'}),/25 MB/);
  await assert.rejects(preparePhoto({size:100,type:'application/pdf'}),/photo/);
});
