import React from 'react';
import { Alert, Box, Button, Chip, LinearProgress, Paper, Typography } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';
import { FeaturePanel, InfoGrid, NotConnected, RetryError } from '../components/FeaturePanel';
import useAuth from '../hooks/useAuth';
import useMe from '../hooks/useMe';
import { fetchCameras, listRecordings } from '../api/recordingsApi';
import { listIncidents } from '../api/incidentsApi';
import { loadOverview, loadCloud, loadStorage } from '../api/managementApi';
import { request } from '../api/client';
import { USE_MOCK } from '../config';
import { formatDateTime, DEFAULT_TZ } from '../utils/time';

export default function DashboardPage() {
  const {token, ready} = useAuth();
  const me = useMe(ready ? token : null);
  const navigate = useNavigate();
  const [data,setData] = React.useState(null);
  const [busy,setBusy] = React.useState(false);
  const [error,setError] = React.useState('');
  const refresh = React.useCallback(async () => {
    if (!token) return;
    setBusy(true);setError('');
    const [cameras, recordings, incidents, health, cloud, storage, rooms] = await Promise.allSettled([
      fetchCameras(token), listRecordings(token), listIncidents(token), loadOverview(token), me?.role==="administrator"?loadCloud(token):null, me?.role==="administrator"?loadStorage(token):null,
      USE_MOCK ? Promise.resolve({rooms:{}}) : request('GET','/api/video/rooms',token)
    ]);
    const val = v => v.status === 'fulfilled' ? v.value : null;
    const failed = [cameras, recordings, incidents, rooms].filter(v=>v.status==='rejected');
    if (failed.length) setError(failed.map(v=>v.reason?.message || 'Service unavailable').join(' · '));
    setData({cameras:val(cameras)||[],recordings:val(recordings)||[],incidents:val(incidents)||[],
      health:val(health),cloud:val(cloud),storage:val(storage),rooms:val(rooms)?.rooms||{}});
    setBusy(false);
  },[token,me?.role]);
  React.useEffect(()=>{if(!ready)return undefined;refresh();const id=setInterval(refresh,45000);return()=>clearInterval(id);},[ready,refresh]);
  if (!ready) return null;
  const feedNames = Object.keys(data?.rooms||{});
  const streamVisible = c => feedNames.some(name=>name===c.channel_name || name===`b'${c.channel_name}'`);
  const cloud = data?.cloud?.data;
  const storage = data?.storage?.data;
  return <Layout token={token}>
    <Box sx={{display:'flex',justifyContent:'space-between',alignItems:'center',flexWrap:'wrap',gap:1,mb:2}}>
      <Box><Typography variant="h5" component="h1">Security dashboard</Typography><Typography color="text.secondary" variant="body2">Welcome {me?.username || 'back'} · All times in {DEFAULT_TZ}</Typography></Box>
      <Button variant="outlined" onClick={refresh} disabled={busy}>Refresh overview</Button>
    </Box>
    {busy && <LinearProgress sx={{mb:2}} aria-label="Updating dashboard"/>}
    <RetryError error={error} onRetry={refresh}/>
    <InfoGrid items={[
      {label:'Assigned cameras',value:data?.cameras?.length},
      {label:'Active stream announcements',value:data ? data.cameras.filter(streamVisible).length : null,detail:'Not a guarantee that frames are arriving'},
      {label:'Catalogue recordings',value:data?.recordings?.length},
      {label:'Protected incident clips',value:data?.incidents?.length}
    ]}/>
    <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',md:'1.5fr 1fr'},gap:2,mt:2}}>
      <FeaturePanel title="Assigned camera overview" action={<Button onClick={()=>navigate('/stream')}>Live view</Button>}>
        {!data?.cameras?.length ? <Alert severity="info">No assigned cameras were returned.</Alert> : data.cameras.map(c=><Paper key={c.id} variant="outlined" sx={{p:1.5,mb:1,display:'flex',justifyContent:'space-between',alignItems:'center',gap:2}}>
          <Box><Typography fontWeight={600}>{c.name}</Typography><Typography variant="caption" color="text.secondary">{c.location || c.channel_name}</Typography></Box>
          <Box sx={{textAlign:'right'}}><Chip size="small" color={streamVisible(c)?'success':'default'} label={streamVisible(c)?'Stream announced':'Stream unconfirmed'}/><Typography display="block" variant="caption" color="text.secondary">{data?.health?.data?.cameras?.find(h=>h.id===c.id)?.recording_state||"No recording status"}</Typography></Box>
        </Paper>)}
      </FeaturePanel>
      {me?.role==="administrator"&&<FeaturePanel title="Cloud and storage" action={<Button onClick={()=>navigate('/cloud')}>Cloud setup</Button>}>
        {cloud ? <Typography>Cloud: {cloud.connection_status || cloud.status || 'Unknown'} · Pending uploads: {cloud.pending_uploads ?? 'Unknown'} · Failed jobs: {cloud.failed_uploads ?? 'Unknown'}</Typography> : <NotConnected name="Cloud connection / upload jobs"/>}
        {storage ? <Typography sx={{mt:2}}>Storage: {storage.used_bytes != null ? `${storage.used_bytes} bytes used` : 'Unknown'} · Capacity: {storage.total_bytes ?? 'Unknown'} bytes</Typography> : <NotConnected name="Disk usage and retention"/>}
        <Button sx={{mt:2}} onClick={()=>navigate('/storage')}>Storage & retention settings</Button>
      </FeaturePanel>}
    </Box>
    <FeaturePanel title="Recent recordings" action={<Button onClick={()=>navigate('/search')}>Search all footage</Button>}>
      {data?.recordings?.length ? data.recordings.slice(0,5).map(r=><Paper key={r.filename} variant="outlined" sx={{mb:1,p:1.5}}><Typography fontWeight={600}>{r.camera_name}</Typography><Typography variant="body2" color="text.secondary">{r.start ? formatDateTime(r.start,DEFAULT_TZ) : 'Time unknown'} · {r.filename}</Typography></Paper>) : <Typography color="text.secondary">No timestamped recordings available yet.</Typography>}
    </FeaturePanel>
    {data?.health?.data?.warnings?.map((w,i)=><Alert key={w.code||i} severity={w.level==='error'?'error':'warning'} sx={{mb:1}}>{w.message}</Alert>)}
    {!data?.health?.supported && <Alert severity="info">Detailed camera health, automatic recording status, system faults, storage warnings and cloud failures require a server telemetry endpoint. Dashboard counts above use available live API responses only.</Alert>}
  </Layout>;
}
