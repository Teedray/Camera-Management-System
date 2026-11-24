import React from 'react';
import { Alert, Box, Button, Chip, LinearProgress, MenuItem, Paper, TextField, Typography } from '@mui/material';
import Layout from '../components/Layout';
import { FeaturePanel, InfoGrid, NotConnected, RetryError } from '../components/FeaturePanel';
import useAuth from '../hooks/useAuth';
import useMe from '../hooks/useMe';
import { connectCloud, disconnectCloud, loadCloud, retryCloudUpload, explainUnsupported } from '../api/managementApi';
import { canManageSystem } from '../utils/permissions';
import { formatDateTime, DEFAULT_TZ } from '../utils/time';

export default function CloudPage(){
  const {token,ready}=useAuth(); const me=useMe(ready?token:null);
  const [snapshot,setSnapshot]=React.useState(null),[loading,setLoading]=React.useState(false),[saving,setSaving]=React.useState(false),[error,setError]=React.useState(''),[message,setMessage]=React.useState('');
  const [provider,setProvider]=React.useState('google_drive'); const [folder,setFolder]=React.useState('');
  const admin=canManageSystem(me?.role);
  const refresh=React.useCallback(async()=>{setLoading(true);setError('');try{setSnapshot(await loadCloud(token));}catch(e){setError(e.message);}finally{setLoading(false);}},[token]);
  React.useEffect(()=>{if(ready&&admin)refresh();},[ready,admin,refresh]);
  const run=async(fn)=>{setSaving(true);setError('');setMessage('');try{await fn();setMessage('Request completed by backend.');await refresh();}catch(e){setError(explainUnsupported(e,'Cloud management'));}finally{setSaving(false);}};
  if(!ready)return null;
  const info=snapshot?.data||{}; const jobs=Array.isArray(info.jobs)?info.jobs:[];
  return <Layout token={token}>
    <Typography variant="h5" component="h1" sx={{mb:1}}>Cloud storage & syncing</Typography>
    <Typography variant="body2" color="text.secondary" sx={{mb:2}}>Connection setup, upload queues, offline buffering and verification</Typography>
    {!me ? <LinearProgress/> : !admin ? <Alert severity="warning">Only administrators can manage cloud connections and uploads.</Alert> : <>
      <RetryError error={error} onRetry={refresh}/>{message&&<Alert severity="success" sx={{mb:2}}>{message}</Alert>}
      {loading&&<LinearProgress sx={{mb:2}}/>}
      <InfoGrid items={[{label:'Connection',value:snapshot?.supported?info.connection_status||'Unknown':'Not connected to API'},
        {label:'Pending uploads',value:info.pending_uploads},{label:'Failed jobs',value:info.failed_uploads},{label:'Buffer usage',value:info.buffer_used_bytes != null?`${info.buffer_used_bytes} bytes`:null}]}/>
      <FeaturePanel title="Cloud connection" detail="OAuth credentials must be handled on the server. Never paste Google Drive tokens into this form." action={<Button disabled={loading} onClick={refresh}>Refresh</Button>}>
        {!snapshot?.supported && <NotConnected name="Cloud storage" detail="The connection controls are ready, but Google Drive OAuth and upload workers must be implemented on the backend."/>}
        <Box component="form" onSubmit={e=>{e.preventDefault();run(()=>connectCloud(token,{provider,folder}));}} sx={{display:'grid',gap:2,gridTemplateColumns:{xs:'1fr',sm:'1fr 1fr'},mt:2}}>
          <TextField label="Cloud provider" select value={provider} onChange={e=>setProvider(e.target.value)}><MenuItem value="google_drive">Google Drive</MenuItem><MenuItem value="other">Other configured provider</MenuItem></TextField>
          <TextField label="Destination folder identifier" value={folder} onChange={e=>setFolder(e.target.value)} helperText="Optional. Use a folder ID supplied by the service."/>
          <Box sx={{display:'flex',gap:1,flexWrap:'wrap',gridColumn:{sm:'span 2'}}}><Button type="submit" variant="contained" disabled={saving||!snapshot?.supported}>Connect account</Button><Button color="error" variant="outlined" disabled={saving||!snapshot?.supported} onClick={()=>run(()=>disconnectCloud(token))}>Disconnect</Button></Box>
        </Box>
      </FeaturePanel>
      <FeaturePanel title="Upload queue" detail="Pending, uploading, verified and failed files, including retry attempts">
        {jobs.length===0 ? <Alert severity="info">No upload jobs were reported by the server.</Alert> : jobs.map(job=><Paper key={job.id} variant="outlined" sx={{p:2,mb:1}}><Box sx={{display:'flex',justifyContent:'space-between',gap:1,flexWrap:'wrap'}}><Typography fontWeight={600}>{job.filename||job.id}</Typography><Chip size="small" color={job.status==='failed'?'error':job.status==='verified'?'success':'default'} label={job.status||'unknown'}/></Box><Typography variant="caption" color="text.secondary">Storage: {job.local_available?'Local ':''}{job.cloud_available?'Cloud':'Cloud unverified'} · Retries: {job.retries??'Unknown'} {job.updated_at&&`· ${formatDateTime(job.updated_at,DEFAULT_TZ)}`}</Typography>{job.error&&<Alert severity="error" sx={{mt:1}}>{job.error}</Alert>}{job.status==='failed'&&<Button size="small" sx={{mt:1}} disabled={saving} onClick={()=>run(()=>retryCloudUpload(token,job.id))}>Retry upload</Button>}</Paper>)}
      </FeaturePanel>
      <FeaturePanel title="Connectivity and buffering">
        <Typography>Internet connection: {info.internet_status||'Not reported'}</Typography><Typography>Upload buffer capacity: {info.buffer_total_bytes??'Unknown'} bytes</Typography><Typography>Last upload: {info.last_upload?formatDateTime(info.last_upload,DEFAULT_TZ):'Not reported'}</Typography>
        {info.last_error&&<Alert severity="error" sx={{mt:1}}>{info.last_error}</Alert>}
        {!snapshot?.supported&&<NotConnected name="Connectivity checks and offline buffering"/>}
      </FeaturePanel>
    </>}
  </Layout>;
}
