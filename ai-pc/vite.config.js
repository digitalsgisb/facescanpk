import { randomUUID } from 'node:crypto';
import { defineConfig } from 'vite';
const buildId = process.env.APP_BUILD_REVISION || randomUUID();
export default defineConfig({define:{__APP_BUILD_ID__:JSON.stringify(buildId)},plugins:[{name:'app-version',generateBundle(){this.emitFile({type:'asset',fileName:'app-version.json',source:JSON.stringify({version:buildId})})}}],server:{port:5173,proxy:{'/api':{target:'http://127.0.0.1:8765'},'/uploads':{target:'http://127.0.0.1:8765'}}},build:{outDir:'dist'}});
