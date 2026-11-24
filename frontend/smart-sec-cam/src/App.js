import React from 'react';
import { Alert, Box, Button, Chip, LinearProgress, Paper, Typography } from '@mui/material';
import Layout from './components/Layout';import ImageViewer from './components/ImageViewer';
import useAuth from './hooks/useAuth';
import { fetchCameras } from './api/recordingsApi';import { request } from './api/client';
import { USE_MOCK } from './config';

export default function App(){
 const {token,ready}=useAuth();
 const [cameras,setCameras]=React.useState([]),[rooms,setRooms]=React.useState({}),[selected,setSelected]=React.useState(''),[state,setState]=React.useState('connecting'),[busy,setBusy]=React.useState(false),[error,setError]=React.useState('');
 const refresh=React.useCallback(async()=>{setBusy(true);setError('');try{
  const [list,response]=await Promise.all([fetchCameras(token),USE_MOCK?Promise.resolve({rooms:{}}):request('GET','/api/video/rooms',token)]);
  setCameras(list);setRooms(response.rooms||{});setSelected(prev=>list.some(c=>c.id===prev)?prev:(list[0]?.id||''));
 }catch(e){setError(e.message);}finally{setBusy(false);}},[token]);
 React.useEffect(()=>{if(!ready)return undefined;refresh();const timer=setInterval(refresh,30000);return()=>clearInterval(timer);},[ready,refresh]);
 if(!ready)return null;
 const camera=cameras.find(c=>c.id===selected);
 const streamRoom=c=>{if(!c)return '';return Object.keys(rooms).find(key=>key===c.channel_name||key===`b'${c.channel_name}'`)||c.channel_name||c.name;};
 return <Layout token={token}>
  <Box sx={{display:'flex',justifyContent:'space-between',gap:1,alignItems:'center',mb:2,flexWrap:'wrap'}}><Box><Typography variant="h5" component="h1">Live camera monitoring</Typography><Typography variant="body2" color="text.secondary">Your assigned cameras only · A camera is live after actual frames arrive</Typography></Box><Button variant="outlined" onClick={refresh} disabled={busy}>Retry / refresh feeds</Button></Box>
  {busy&&<LinearProgress sx={{mb:2}}/>}{error&&<Alert severity="error" sx={{mb:2}} onClose={()=>setError('')}>{error}</Alert>}
  <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',md:'minmax(240px,280px) 1fr'},gap:2}}>
   <Paper component="aside" sx={{p:1.5}}><Typography fontWeight={650} sx={{mb:1}}>Assigned cameras ({cameras.length})</Typography>
    {cameras.length===0&&<Alert severity="info">No cameras have been assigned to your account.</Alert>}
    {cameras.map(c=><Button key={c.id} variant={c.id===selected?'contained':'outlined'} onClick={()=>{setSelected(c.id);setState('connecting');}} sx={{width:'100%',mb:1,justifyContent:'flex-start',textAlign:'left',minHeight:55}}>{c.name}<Typography variant="caption" sx={{ml:1,opacity:.75}}>{c.location||''}</Typography></Button>)}
   </Paper>
   <Paper sx={{p:2}}>
    {camera?<><Box sx={{display:'flex',justifyContent:'space-between',gap:1,mb:1.5,alignItems:'center',flexWrap:'wrap'}}><Box><Typography variant="h6">{camera.name}</Typography><Typography variant="caption" color="text.secondary">{camera.location||camera.channel_name} · Channel: {camera.channel_name}</Typography></Box><Chip size="small" color={state==='live'?'success':state==='denied'?'error':'warning'} label={state==='live'?'Frames received':state==='denied'?'Access denied':state==='reconnecting'?'Reconnecting':state==='connecting'?'Connecting':'Unavailable'}/></Box>
      <ImageViewer key={camera.id} room={streamRoom(camera)} token={token} onStatus={setState}/><Typography variant="body2" color="text.secondary" sx={{mt:1}}>Recording state: not reported by the streaming service. A live feed does not prove footage is being recorded.</Typography></>:<Alert severity="info">Select an assigned camera to start live viewing.</Alert>}
   </Paper>
  </Box>
 </Layout>;
}
