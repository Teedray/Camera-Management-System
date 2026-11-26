import React from 'react';
import io from 'socket.io-client';
import { SERVER_URL } from '../config';
import { base64ToBlob } from '../utils/base64ToBlob';
import './ImageViewer.css';

// The visual stream uses authenticated Socket.IO joins. An actual received frame
// (not a guessed camera flag) is required before the UI says the camera is live.
export default function ImageViewer({room, token, isPreview=false, onStatus}){
 const [url,setUrl]=React.useState(null),[state,setState]=React.useState('connecting');
 const lastFrame=React.useRef(0),blobUrl=React.useRef(null),statusCallback=React.useRef(onStatus);
 statusCallback.current=onStatus;
 React.useEffect(()=>{
  if(!room||!token){setState('unavailable');return undefined;}
  let mounted=true;let s;
  const report=(value)=>{if(mounted){setState(value);statusCallback.current?.(value);}};
  const image=(payload)=>{if(payload?.room!==room||!payload?.data)return;try{
    const next=URL.createObjectURL(base64ToBlob(payload.data));
    if(blobUrl.current)URL.revokeObjectURL(blobUrl.current);blobUrl.current=next;
    if(mounted){setUrl(next);lastFrame.current=Date.now();report('live');}
  }catch(e){report('unavailable');}};
  const join=()=>{report('connecting');s.emit('join',{room,token},ack=>{if(ack?.status==='ERROR')report('denied');});};
  s=io(SERVER_URL,{transports:['websocket','polling'],reconnection:true,reconnectionAttempts:Infinity});
  s.on('connect',join);s.on('image',image);s.on('connect_error',()=>report('reconnecting'));s.on('disconnect',()=>report('reconnecting'));
  const watchdog=setInterval(()=>{if(mounted&&lastFrame.current&&Date.now()-lastFrame.current>15000)report('reconnecting');},5000);
  return()=>{mounted=false;clearInterval(watchdog);s.emit('leave',{room});s.off('image',image);s.disconnect();if(blobUrl.current)URL.revokeObjectURL(blobUrl.current);blobUrl.current=null;};
 },[room,token]);
 return <div className={`imageviewer ${isPreview?'preview':'main'}`} style={{position:'relative',background:'#070d16'}}>
   {url&&<img src={url} alt={`${room} live camera feed`} style={{width:'100%',height:'100%',objectFit:'contain'}}/>}
   {(!url||state!=='live')&&<div role="status" style={{position:'absolute',inset:0,display:'grid',placeItems:'center',color:'#c9d5e7',fontSize:isPreview?11:15,background:'rgba(7,13,22,.70)',textAlign:'center',padding:10}}>
     {state==='denied'?'Camera access denied':state==='reconnecting'?'Feed interrupted — reconnecting…':state==='unavailable'?'Feed unavailable':'Connecting to stream…'}
   </div>}
 </div>;
}
