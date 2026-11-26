import React from 'react';
import { Alert, Box, Button, Chip, LinearProgress, Paper, Typography } from '@mui/material';
import Layout from '../components/Layout';import { FeaturePanel, InfoGrid, NotConnected, RetryError } from '../components/FeaturePanel';
import useAuth from '../hooks/useAuth';import useMe from '../hooks/useMe';
import { fetchCameras } from '../api/recordingsApi';import { loadOverview, loadCloud, loadStorage, loadCameraHealth, RECENT_RECORDING_MINUTES } from '../api/managementApi';
import { formatDateTime, DEFAULT_TZ, formatBytes } from '../utils/time';
const CONNECTION_LABELS={connected:'Connected',disconnected:'Disconnected',never_connected:'Never connected'};
export default function RealStatusPage(){
 const {token,ready}=useAuth(),me=useMe(ready?token:null);
 const [state,setState]=React.useState(null),[busy,setBusy]=React.useState(false),[error,setError]=React.useState('');
 const load=React.useCallback(async()=>{setBusy(true);setError('');try{const [cameras,overview,cloud,storage,health]=await Promise.all([fetchCameras(token),loadOverview(token),me?.role==="administrator"?loadCloud(token):null,me?.role==="administrator"?loadStorage(token):null,loadCameraHealth(token)]);setState({cameras,overview,cloud,storage,health});}catch(e){setError(e.message);}finally{setBusy(false);}},[token,me?.role]);
 React.useEffect(()=>{if(!ready)return undefined;load();const id=setInterval(load,30000);return()=>clearInterval(id);},[ready,load]);
 if(!ready)return null;
 const overall=state?.overview?.data||{},cloud=state?.cloud?.data||{},storage=state?.storage?.data||{};
 return <Layout token={token}><Box sx={{display:'flex',justifyContent:'space-between',gap:2,mb:2,flexWrap:'wrap'}}><Box><Typography variant="h5" component="h1">System health & alerts</Typography><Typography variant="body2" color="text.secondary">Actual backend measurements only · {DEFAULT_TZ}</Typography></Box><Button variant="outlined" disabled={busy} onClick={load}>Refresh status</Button></Box>
  {busy&&<LinearProgress sx={{mb:2}}/>}<RetryError error={error} onRetry={load}/>
  <InfoGrid items={[{label:'Backend',value:state?'Reachable':'Unknown'},{label:'Signed-in user',value:me?.username},{label:'Assigned cameras',value:state?.cameras?.length},{label:'Warnings',value:state?.overview?.supported?overall.warnings?.length??0:null}]}/>
  <Box sx={{mt:2}}>{(overall.warnings||[]).map((w,i)=><Alert key={w.code||i} severity={w.level==='error'?'error':'warning'} sx={{mb:1}}>{w.message}</Alert>)}</Box>
  <FeaturePanel title="Cameras and recording health">
   {!state?.overview?.supported&&!state?.health?.supported&&<NotConnected name="Live connectivity and recording telemetry"/>}
   {(state?.cameras||[]).map(c=>{const h=(overall.cameras||[]).find(x=>x.id===c.id||x.name===c.name);const live=(state?.health?.data?.items||[]).find(x=>x.id===c.id);
    const connection=h?.connection||CONNECTION_LABELS[live?.status]||'Connectivity unknown';const lastRecording=h?.last_recording||live?.last_recording;const lastFrame=h?.last_seen||live?.last_seen_utc;
    return <Paper variant="outlined" key={c.id} aria-label={c.name} sx={{p:1.5,mb:1,display:'flex',alignItems:'center',justifyContent:'space-between',gap:1,flexWrap:'wrap'}}><Box><Typography fontWeight={600}>{c.name}</Typography><Typography variant="caption" color="text.secondary">{c.location||c.channel_name}</Typography></Box><Box><Chip size="small" color={live?.status==='connected'?'success':live?.status?'error':'default'} label={connection}/>{h?.recording_state&&<Chip sx={{ml:1}} size="small" label={h.recording_state}/>}
     <Typography variant="caption" color="text.secondary" display="block">Last frame: {lastFrame?formatDateTime(lastFrame,DEFAULT_TZ):'Not reported'}</Typography>
     <Typography variant="caption" color="text.secondary" display="block">Last recording: {lastRecording?formatDateTime(lastRecording,DEFAULT_TZ):live?`None in the last ${RECENT_RECORDING_MINUTES} minutes`:'Not reported'}</Typography></Box></Paper>;})}
  </FeaturePanel>
  {me?.role==="administrator"&&<><FeaturePanel title="Cloud upload and backup health"><Typography>Connection: {cloud.connection_status||'Unknown'} · Pending uploads: {cloud.pending_uploads??'Unknown'} · Failed uploads: {cloud.failed_uploads??'Unknown'}</Typography><Typography>Last verified upload: {cloud.last_verified?formatDateTime(cloud.last_verified,DEFAULT_TZ):'Not reported'}</Typography>{cloud.last_error&&<Alert severity="error">{cloud.last_error}</Alert>}{!state?.cloud?.supported&&<NotConnected name="Cloud upload and backup telemetry"/>}</FeaturePanel>
  <FeaturePanel title="Storage and retention health"><Typography>Used: {storage.used_bytes!=null?formatBytes(storage.used_bytes):'Unknown'} · Free: {storage.free_bytes!=null?formatBytes(storage.free_bytes):'Unknown'}</Typography><Typography>Retention: {storage.retention_days??'Unknown'} days</Typography>{!state?.storage?.supported&&<NotConnected name="Storage telemetry"/>}</FeaturePanel></>}
 </Layout>;
}
