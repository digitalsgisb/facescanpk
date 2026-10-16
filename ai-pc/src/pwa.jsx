import React,{useEffect,useRef,useState} from 'react';
import {Smartphone,Download,RefreshCw,CheckCircle2} from 'lucide-react';
import './pwa.css';

export function usePwa(){
  const [prompt,setPrompt]=useState(null),[installed,setInstalled]=useState(()=>window.matchMedia('(display-mode: standalone)').matches||!!navigator.standalone),[registration,setRegistration]=useState(null),[update,setUpdate]=useState(false),[error,setError]=useState('');
  const reloadRequested=useRef(false);
  useEffect(()=>{
    let active=true;
    const beforeInstall=event=>{event.preventDefault();setPrompt(event)};
    const didInstall=()=>{setInstalled(true);setPrompt(null)};
    const controllerChanged=()=>{if(reloadRequested.current)window.location.reload()};
    window.addEventListener('beforeinstallprompt',beforeInstall);
    window.addEventListener('appinstalled',didInstall);
    if(import.meta.env.PROD&&window.isSecureContext&&'serviceWorker' in navigator){
      navigator.serviceWorker.addEventListener('controllerchange',controllerChanged);
      navigator.serviceWorker.register('/sw.js',{scope:'/',updateViaCache:'none'}).then(reg=>{
        if(!active)return;
        setRegistration(reg);setUpdate(!!reg.waiting);
        reg.addEventListener('updatefound',()=>{
          const worker=reg.installing;
          worker?.addEventListener('statechange',()=>{if(active&&worker.state==='installed'&&navigator.serviceWorker.controller)setUpdate(true)});
        });
      }).catch(()=>{if(active)setError('The app is available online; offline support could not start.')});
    }
    return()=>{active=false;window.removeEventListener('beforeinstallprompt',beforeInstall);window.removeEventListener('appinstalled',didInstall);navigator.serviceWorker?.removeEventListener('controllerchange',controllerChanged)};
  },[]);
  async function install(){
    if(!prompt)return;
    try{await prompt.prompt();await prompt.userChoice;setPrompt(null)}catch{setError('Use your browser’s Install app or Add to Home Screen option.')}
  }
  function applyUpdate(){if(registration?.waiting){reloadRequested.current=true;registration.waiting.postMessage({type:'ACTIVATE_UPDATE'})}}
  return {installed,canInstall:!!prompt,install,update,applyUpdate,error,secure:window.isSecureContext};
}
export function PwaPanel({pwa}){
  return <section className="card pwa-panel"><div className="section-heading"><div><h2><Smartphone size={21}/>Use attendance on your phone</h2><p>Open this app’s address on your phone, sign in as administrator, then open an employee profile to choose or take a photo.</p></div></div><div className="pwa-panel-body">{pwa.installed?<p className="pwa-installed"><CheckCircle2 size={17}/>Installed on this device</p>:pwa.canInstall?<button className="primary" onClick={pwa.install}><Download size={16}/>Install attendance app</button>:<p>{pwa.secure?'Android: browser menu → Install app. iPhone: Safari → Share → Add to Home Screen.':'Photo uploads work in the browser. Open the trusted HTTPS address to install the app on your phone.'}</p>}<small>Use the same workplace network, or the company’s configured HTTPS address. Photo uploads need a connection.</small>{pwa.update&&<div className="pwa-update"><p>An app update is ready. Save your edits before refreshing.</p><button className="secondary" onClick={pwa.applyUpdate}><RefreshCw size={15}/>Update app</button></div>}{pwa.error&&<p role="status">{pwa.error}</p>}</div></section>;
}
