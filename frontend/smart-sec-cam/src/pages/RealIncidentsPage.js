import React from 'react';
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, LinearProgress, MenuItem, Paper, TextField, Typography } from '@mui/material';
import Layout from '../components/Layout';import { FeaturePanel, RetryError } from '../components/FeaturePanel';
import useAuth from '../hooks/useAuth';import useMe from '../hooks/useMe';
import { deleteIncident, incidentStreamUrl, listIncidents } from '../api/incidentsApi';
import { extendIncident, explainUnsupported } from '../api/managementApi';
import { canManageSystem } from '../utils/permissions';import { formatDateTime,DEFAULT_TZ } from '../utils/time';

export default function RealIncidentsPage(){
 const {token,ready}=useAuth(),me=useMe(ready?token:null),admin=canManageSystem(me?.role);
 const [items,setItems]=React.useState([]),[selected,setSelected]=React.useState(null),[deleteTarget,setDeleteTarget]=React.useState(null);
 const [preserveTarget,setPreserveTarget]=React.useState(null),[days,setDays]=React.useState('30'),[filter,setFilter]=React.useState('all');
 const [loading,setLoading]=React.useState(true),[busy,setBusy]=React.useState(false),[error,setError]=React.useState(''),[notice,setNotice]=React.useState(''),[videoError,setVideoError]=React.useState('');
 const load=React.useCallback(async()=>{setLoading(true);setError('');try{const result=await listIncidents(token);setItems(result);}catch(e){setError(e.message);}finally{setLoading(false);}},[token]);
 React.useEffect(()=>{if(ready)load();},[ready,load]);
 async function remove(){if(!deleteTarget)return;setBusy(true);setError('');try{await deleteIncident(token,deleteTarget.id);setNotice('Incident deleted.');setDeleteTarget(null);if(selected?.id===deleteTarget.id)setSelected(null);await load();}catch(e){setError(e.message);setDeleteTarget(null);}finally{setBusy(false);}}
 async function extend(){if(!preserveTarget)return;const n=Number(days);if(!Number.isInteger(n)||n<1||n>3650){setError('Choose a preservation extension between 1 and 3650 days.');return;}setBusy(true);setError('');try{await extendIncident(token,preserveTarget.id,{extend_days:n});setNotice('Preservation extended by backend.');setPreserveTarget(null);await load();}catch(e){setError(explainUnsupported(e,'Preservation extension'));setPreserveTarget(null);}finally{setBusy(false);}}
 if(!ready)return null;
 const shown=items.filter(i=>filter==='all'||(filter==='protected'?i.incident_flag||i.protected:!i.incident_flag&&!i.protected));
 return <Layout token={token}><Box sx={{display:'flex',gap:2,justifyContent:'space-between',mb:2,alignItems:'center',flexWrap:'wrap'}}><Box><Typography variant="h5" component="h1">Saved incident library</Typography><Typography variant="body2" color="text.secondary">Protected footage and preservation actions</Typography></Box><Button onClick={load} disabled={loading||busy}>Refresh archive</Button></Box>
  <RetryError error={error} onRetry={load}/>{notice&&<Alert severity="success" sx={{mb:2}} onClose={()=>setNotice('')}>{notice}</Alert>}{loading&&<LinearProgress sx={{mb:2}}/>}
  <FeaturePanel title={`Incident clips (${items.length})`} action={<TextField select label="Filter" size="small" value={filter} onChange={e=>setFilter(e.target.value)} sx={{minWidth:170}}><MenuItem value="all">All clips</MenuItem><MenuItem value="protected">Protected</MenuItem><MenuItem value="unprotected">Unprotected</MenuItem></TextField>}>
   {!loading&&shown.length===0&&<Alert severity="info">No matching incident clips are accessible to your account.</Alert>}
   <Box sx={{display:'grid',gap:1.5}}>{shown.map(i=><Paper component="article" key={i.id} variant="outlined" sx={{p:2}}>
    <Box sx={{display:'flex',gap:1,justifyContent:'space-between',alignItems:'center',flexWrap:'wrap'}}><Typography fontWeight={700}>{i.title||i.id}</Typography><Box sx={{display:'flex',gap:.5}}><Chip color="success" size="small" label={i.status||'Ready'}/><Chip size="small" color="primary" label={i.incident_flag||i.protected?'Protected archive':'Protection unknown'}/></Box></Box>
    <Typography variant="body2" color="text.secondary">Camera: {i.camera||'Unknown'} · Created: {i.created_at?formatDateTime(i.created_at,DEFAULT_TZ):'Unknown'}</Typography>
    <Typography variant="body2" color="text.secondary">Source range: {i.start_time}–{i.end_time} seconds · Saved by: {i.created_by||'Not reported'}</Typography>
    {i.preserved_until&&<Typography>Protected through {formatDateTime(i.preserved_until,DEFAULT_TZ)}</Typography>}{i.notes&&<Typography variant="body2" sx={{my:1}}>{i.notes}</Typography>}
    <Box sx={{display:'flex',gap:1,mt:1,flexWrap:'wrap'}}><Button size="small" variant="outlined" onClick={()=>{setSelected(i);setVideoError('');}}>Open clip</Button>{admin&&<><Button size="small" onClick={()=>setPreserveTarget(i)}>Extend preservation</Button><Button color="error" size="small" onClick={()=>setDeleteTarget(i)}>Delete…</Button></>}</Box>
   </Paper>)}</Box>
  </FeaturePanel>
  {selected&&<FeaturePanel title={`Playback — ${selected.title}`} action={<Button onClick={()=>setSelected(null)}>Close</Button>}>
    <Box component="video" key={selected.id} src={incidentStreamUrl(selected.id,token)} controls playsInline preload="metadata" onError={()=>setVideoError('The archived recording is unavailable or your camera access was revoked.')} sx={{width:'100%',maxWidth:1000,aspectRatio:'16/9',bgcolor:'#000',borderRadius:1}}/>
    {videoError&&<Alert severity="error" sx={{mt:1}}>{videoError}</Alert>}
  </FeaturePanel>}
  <Alert severity="info">Saved incident clips are kept in a separate protected archive. A preservation extension blocks manual deletion until the hold ends.</Alert>
  <Dialog open={Boolean(deleteTarget)} onClose={busy?undefined:()=>setDeleteTarget(null)}><DialogTitle>Delete protected incident?</DialogTitle><DialogContent><Typography>The clip “{deleteTarget?.title}” will be permanently removed from the archive. This cannot be undone.</Typography></DialogContent><DialogActions><Button disabled={busy} onClick={()=>setDeleteTarget(null)}>Cancel</Button><Button color="error" variant="contained" disabled={busy} onClick={remove}>Confirm delete</Button></DialogActions></Dialog>
  <Dialog open={Boolean(preserveTarget)} onClose={busy?undefined:()=>setPreserveTarget(null)}><DialogTitle>Extend clip preservation</DialogTitle><DialogContent><TextField fullWidth type="number" label="Extend by days" value={days} onChange={e=>setDays(e.target.value)} inputProps={{min:1,max:3650}} sx={{mt:1}}/></DialogContent><DialogActions><Button disabled={busy} onClick={()=>setPreserveTarget(null)}>Cancel</Button><Button variant="contained" disabled={busy} onClick={extend}>Confirm extension</Button></DialogActions></Dialog>
 </Layout>;
}
