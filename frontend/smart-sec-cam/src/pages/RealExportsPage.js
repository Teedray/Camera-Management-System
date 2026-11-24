import React from 'react';
import { Alert, Box, Button, Chip, LinearProgress, Paper, Typography } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';import { FeaturePanel, NotConnected, RetryError } from '../components/FeaturePanel';
import useAuth from '../hooks/useAuth';import useMe from '../hooks/useMe';
import { loadExportJobs } from '../api/managementApi';import { readExportHistory } from '../utils/exportHistory';
import { canManageFootage } from '../utils/permissions';import { formatDateTime, formatBytes,DEFAULT_TZ } from '../utils/time';
export default function RealExportsPage(){
 const {token,ready}=useAuth(),me=useMe(ready?token:null),allowed=canManageFootage(me?.role),navigate=useNavigate();
 const [jobs,setJobs]=React.useState(null),[local,setLocal]=React.useState([]),[error,setError]=React.useState(''),[busy,setBusy]=React.useState(false);
 const refresh=React.useCallback(async()=>{setBusy(true);setError('');try{setJobs(await loadExportJobs(token));}catch(e){setError(e.message);}finally{setLocal(readExportHistory());setBusy(false);}},[token]);
 React.useEffect(()=>{if(ready&&allowed)refresh();},[ready,allowed,refresh]);
 if(!ready)return null;
 const serverJobs=jobs?.data?.items||[];
 return <Layout token={token}><Box sx={{display:'flex',justifyContent:'space-between',gap:1,mb:2,alignItems:'center',flexWrap:'wrap'}}><Typography variant="h5" component="h1">MP4 exports and downloads</Typography><Button onClick={refresh} disabled={busy||!allowed}>Refresh jobs</Button></Box>
 {!me?<LinearProgress/>:!allowed?<Alert severity="warning">Viewers cannot trim, merge, export or download footage. Manager or administrator role required.</Alert>:<>
  <RetryError error={error} onRetry={refresh}/>{busy&&<LinearProgress sx={{mb:2}}/>}
  <FeaturePanel title="Prepare a new export"><Typography variant="body2" color="text.secondary" sx={{mb:2}}>Choose one permitted recording, mark a nonzero clip interval and request an MP4 without editing the original file.</Typography><Button variant="contained" onClick={()=>navigate('/search')}>Open search & trim</Button></FeaturePanel>
  <FeaturePanel title="Export queue / server job history" detail="Queued, processing, ready, failed, expiry and download availability">
   {!jobs?.supported&&<NotConnected name="Server export queue" detail="This backend returns the MP4 directly in response to a POST. It cannot provide job expiry or persistent re-download without a jobs API."/>}
   {jobs?.supported&&serverJobs.length===0&&<Alert severity="info">No server export jobs.</Alert>}
   {serverJobs.map(j=><Paper key={j.id} variant="outlined" sx={{p:2,mb:1}}><Box sx={{display:'flex',gap:1,justifyContent:'space-between',flexWrap:'wrap'}}><Typography fontWeight={700}>{j.filename||j.id}</Typography><Chip color={j.status==='failed'?'error':j.status==='ready'?'success':'default'} label={j.status||'unknown'}/></Box><Typography variant="body2" color="text.secondary">Created: {j.created_at?formatDateTime(j.created_at,DEFAULT_TZ):'Unknown'} · Expires: {j.expires_at?formatDateTime(j.expires_at,DEFAULT_TZ):'Not reported'}</Typography>{['queued','processing'].includes(j.status)&&<LinearProgress sx={{mt:1}}/>}{j.error&&<Alert severity="error" sx={{mt:1}}>{j.error}</Alert>}{j.status==='ready'&&j.download_url&&<Button component="a" href={j.download_url} size="small" variant="outlined" sx={{mt:1}}>Download</Button>}</Paper>)}
  </FeaturePanel>
  <FeaturePanel title="This browser session's direct exports" detail="Local history only; no MP4s are stored here, and server download expiry is unknown">
   {!local.length&&<Alert severity="info">No exports have been requested from this browser session.</Alert>}
   {local.map(entry=><Paper key={entry.id} variant="outlined" sx={{p:2,mb:1}}><Box sx={{display:'flex',justifyContent:'space-between',gap:2,flexWrap:'wrap'}}><Typography fontWeight={600}>{entry.file||entry.filename||'Export request'}</Typography><Chip size="small" color={entry.status==='failed'?'error':entry.status==='downloaded'?'success':'default'} label={entry.status==='downloaded'?'Downloaded to device':entry.status}/></Box><Typography variant="body2" color="text.secondary">{formatDateTime(entry.created_at,DEFAULT_TZ)} · {entry.size_bytes!=null?formatBytes(entry.size_bytes):'Size unknown'} · Server expiry: not provided</Typography>{entry.error&&<Alert severity="error">{entry.error}</Alert>}</Paper>)}
  </FeaturePanel>
 </>}
 </Layout>;
}
