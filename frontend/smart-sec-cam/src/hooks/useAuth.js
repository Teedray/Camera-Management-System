import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useCookies } from 'react-cookie';
import { SERVER_URL, USE_MOCK } from '../config';

// Inactivity logout is based on real user input, not polling or camera frames.
export const IDLE_LIMIT_MS = 15 * 60 * 1000;
const ACTIVITY_KEY = 'sentinel-last-activity';
export default function useAuth(){
 const [cookies,setCookie,removeCookie]=useCookies(['token']);const navigate=useNavigate();
 const token=cookies.token;const [valid,setValid]=React.useState(false);
 const signOut=React.useCallback((reason)=>{removeCookie('token',{path:'/'});setValid(false);navigate('/',reason?{state:{reason}}:undefined);},[removeCookie,navigate]);
 React.useEffect(()=>{
  if(!token){setValid(false);navigate('/');return undefined;}
  let active=true;let refreshTimer;
  if(USE_MOCK){setValid(true);return()=>{active=false;};}
  async function validate(){
   try{const response=await fetch(`${SERVER_URL}/api/token/validate`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token})});const data=await response.json();
    if(!active)return;if(!response.ok||data.status!=='OK'){signOut('expired');return;}setValid(true);
    const ttlResponse=await fetch(`${SERVER_URL}/api/token/ttl?token=${encodeURIComponent(token)}`);const ttl=await ttlResponse.json();
    if(!active)return;
    if(ttl.status==='OK'&&Number(ttl.ttl)>0){const wait=Math.max(1000,(Number(ttl.ttl)-60)*1000);refreshTimer=setTimeout(async()=>{
      try{const r=await fetch(`${SERVER_URL}/api/token/refresh`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token})});const d=await r.json();if(active&&d.status==='OK'&&d.token){setCookie('token',d.token,{path:'/',sameSite:'lax'});}else if(active)signOut('expired');}catch(e){if(active)signOut('expired');}
    },wait);}
   }catch(e){if(active){setValid(false);/* connection errors are shown by individual pages */}}
  }
  validate();return()=>{active=false;clearTimeout(refreshTimer);};
 },[token,navigate,setCookie,signOut]);
 React.useEffect(()=>{
  if(!token)return undefined;
  let last=Date.now();try{const prior=Number(window.sessionStorage.getItem(ACTIVITY_KEY));if(prior&&prior<=Date.now())last=prior;}catch(e){}
  let tooLate=false;
  const check=()=>{if(!tooLate&&Date.now()-last>=IDLE_LIMIT_MS){tooLate=true;signOut('idle');}};
  const activity=()=>{check();if(tooLate)return;last=Date.now();try{window.sessionStorage.setItem(ACTIVITY_KEY,String(last));}catch(e){}};
  const expiry=()=>signOut('expired');
  for(const event of ['pointerdown','keydown','touchstart'])window.addEventListener(event,activity,{passive:true});
  window.addEventListener('focus',check);window.addEventListener('camera-session-expired',expiry);
  const interval=setInterval(check,30000);check();
  return()=>{clearInterval(interval);for(const event of ['pointerdown','keydown','touchstart'])window.removeEventListener(event,activity);window.removeEventListener('focus',check);window.removeEventListener('camera-session-expired',expiry);};
 },[token,signOut]);
 return {token,ready:Boolean(token)&&valid,signOut};
}
