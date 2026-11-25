import React from 'react';
import { Alert, Box, Button, Checkbox, Chip, FormControlLabel, LinearProgress, MenuItem, Paper, TextField, Typography } from '@mui/material';
import Layout from '../components/Layout';import { FeaturePanel, NotConnected, RetryError } from '../components/FeaturePanel';
import useAuth from '../hooks/useAuth';import useMe from '../hooks/useMe';
import { fetchCameras, listRecordings } from '../api/recordingsApi';
import { loadMerges, createMerge, explainUnsupported } from '../api/managementApi';
import { canManageFootage } from '../utils/permissions';import { formatDateTime, DEFAULT_TZ } from '../utils/time';

export default function MergePage(){
 const {token,ready}=useAuth(),me=useMe(ready?token:null),allowed=canManageFootage(me?.role);
 const [cameras,setCameras]=React.useState([]),[recordings,setRecordings]=React.useState([]),[selected,setSelected]=React.useState([]),[cameraFilter,setCameraFilter]=React.useState(''),[title,setTitle]=React.useState('');
 const [jobs,setJobs]=React.useState(null),[loading,setLoading]=React.useState(false),[busy,setBusy]=React.useState(false),[error,setError]=React.useState(''),[notice,setNotice]=React.useState('');
 const load=React.useCallback(async()=>{setLoading(true);setError('');try{const [cs,rs,ms]=await Promise.all([fetchCameras(token),listRecordings(token),loadMerges(token)]);setCameras(cs);setRecordings(rs);setJobs(ms);}catch(e){setError(e.message);}finally{setLoading(false);}},[token]);
 React.useEffect(()=>{if(ready&&allowed)load();},[ready,allowed,load]);
 const checked=new Set(selected);const shown=recordings.filter(r=>!cameraFilter||r.camera_id===cameraFilter);
 function toggle(filename){setSelected(v=>v.includes(filename)?v.filter(n=>n!==filename):[...v,filename]);}
 async function submit(e){e.preventDefault();setError('');setNotice('');if(selected.length<2){setError('Select at least two available recordings.');return;}setBusy(true);try{await createMerge(token,{title:title.trim()||'Merged recording',filenames:selected});setNotice('Merge job accepted by backend.');setSelected([]);await load();}catch(e){setError(explainUnsupported(e,'Merge operation'));}finally{setBusy(false);}}
 if(!ready)return null;
 return <Layout token={token}><Typography variant="h5" component="h1" sx={{mb:1}}>Merge recordings</Typography><Typography variant="body2" color="text.secondary" sx={{mb:2}}>Select permitted recordings, submit a merge, and monitor the output</Typography>
 {!me?<LinearProgress/>:!allowed?<Alert severity="warning">Only managers and administrators may merge recordings.</Alert>:<>
  <RetryError error={error} onRetry={load}/>{notice&&<Alert severity="success" sx={{mb:2}}>{notice}</Alert>}{loading&&<LinearProgress sx={{mb:2}}/>}
  <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',md:'1.35fr 1fr'},gap:2}}>
  <FeaturePanel title="Source recordings" action={<Button onClick={load} disabled={loading||busy}>Refresh</Button>}>
   <TextField select size="small" fullWidth label="Filter by assigned camera" value={cameraFilter} onChange={e=>setCameraFilter(e.target.value)} sx={{mb:2}}><MenuItem value="">All assigned cameras</MenuItem>{cameras.map(c=><MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>)}</TextField>
   {shown.length===0&&<Alert severity="info">No completed catalogue recordings are available for this camera.</Alert>}
   <Box sx={{maxHeight:460,overflow:'auto'}}>{shown.map(r=><Paper key={r.filename} variant="outlined" sx={{p:1,mb:1}}><FormControlLabel sx={{m:0,alignItems:'start'}} control={<Checkbox checked={checked.has(r.filename)} onChange={()=>toggle(r.filename)} disabled={busy}/>} label={<Box><Typography fontWeight={600}>{r.camera_name}</Typography><Typography variant="body2" color="text.secondary">{r.start&&formatDateTime(r.start,DEFAULT_TZ)} · {Number(r.duration_seconds||0).toFixed(1)} s</Typography></Box>}/></Paper>)}</Box>
  </FeaturePanel>
  <FeaturePanel title="Create merge job" detail="Sources remain unchanged; server enforces camera permissions for every selected recording.">
   <Box component="form" onSubmit={submit} sx={{display:'grid',gap:2}}><TextField label="Merged output title" value={title} onChange={e=>setTitle(e.target.value)} inputProps={{maxLength:100}}/><Chip label={`${selected.length} source recordings selected`} sx={{width:'fit-content'}}/>
    <Alert severity="info">Recordings will be merged in capture-time order. The backend must validate compatible formats and intervals.</Alert>
    <Button type="submit" variant="contained" disabled={busy||selected.length<2||!jobs?.supported}>Merge selected recordings</Button>
   </Box>
   {!jobs?.supported&&<NotConnected name="Merge jobs" detail="The existing backend has clip trimming but no verified recording-merge endpoint. This frontend is ready to submit only when that endpoint exists."/>}
  </FeaturePanel>
  </Box>
  <FeaturePanel title="Merge jobs and completed outputs" detail="Queued, processing, completed and failed jobs; source camera and time metadata">
   {(jobs?.data?.items||[]).length===0?<Alert severity="info">No completed merge jobs available.</Alert>:(jobs.data.items).map(j=><Paper key={j.id} variant="outlined" sx={{p:2,mb:1}}><Box sx={{display:'flex',justifyContent:'space-between',gap:1}}><Typography fontWeight={600}>{j.title||j.id}</Typography><Chip color={j.status==='failed'?'error':j.status==='completed'?'success':'default'} label={j.status||'unknown'}/></Box><Typography variant="body2" color="text.secondary">Sources: {(j.source_cameras||[]).join(', ')||'Not reported'} · {j.start||'Time unknown'} – {j.end||'Time unknown'}</Typography>{j.status==='failed'&&<Alert severity="error">{j.error||'Merge failed.'}</Alert>}{j.download_url&&j.status==='completed'&&<Button component="a" href={j.download_url} size="small">Open output</Button>}</Paper>)}
  </FeaturePanel>
 </>}
 </Layout>;
}
