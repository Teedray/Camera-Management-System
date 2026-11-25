import React from 'react';
import { Alert, Box, Button, LinearProgress, MenuItem, Paper, TextField, Typography } from '@mui/material';
import Layout from '../components/Layout';
import { FeaturePanel, NotConnected, RetryError } from '../components/FeaturePanel';
import useAuth from '../hooks/useAuth';import useMe from '../hooks/useMe';
import { loadAudit } from '../api/managementApi';import { canViewAudit } from '../utils/permissions';
import { formatDateTime, DEFAULT_TZ } from '../utils/time';
const TYPES=['','permission_change','incident_saved','export','delete','error','login','camera_change'];
export default function AuditPage(){
 const {token,ready}=useAuth(),me=useMe(ready?token:null),admin=canViewAudit(me?.role);
 const [filters,setFilters]=React.useState({date:'',user:'',type:''}),[data,setData]=React.useState(null),[error,setError]=React.useState(''),[busy,setBusy]=React.useState(false);
 const search=React.useCallback(async()=>{setBusy(true);setError('');try{setData(await loadAudit(token,filters));}catch(e){setError(e.message);}finally{setBusy(false);}},[filters,token]);
 React.useEffect(()=>{if(ready&&admin)search();},[ready,admin,search]);
 const rows=data?.data?.items || data?.data?.events || [];
 if(!ready)return null;
 return <Layout token={token}>
  <Typography variant="h5" component="h1" sx={{mb:1}}>Activity & audit logs</Typography>
  <Typography variant="body2" color="text.secondary" sx={{mb:2}}>Read-only security events, permission changes, saves, exports, deletions and errors</Typography>
  {!me?<LinearProgress/>:!admin?<Alert severity="warning">Administrator access required for audit records.</Alert>:<>
   <RetryError error={error} onRetry={search}/>{busy&&<LinearProgress sx={{mb:2}}/>}
   <FeaturePanel title="Audit filters" action={<Button onClick={search} disabled={busy}>Refresh</Button>}>
    <Box sx={{display:'flex',gap:2,flexWrap:'wrap'}}>
     <TextField type="date" size="small" label="Date" InputLabelProps={{shrink:true}} value={filters.date} onChange={e=>setFilters(s=>({...s,date:e.target.value}))}/>
     <TextField size="small" label="Username / ID" value={filters.user} onChange={e=>setFilters(s=>({...s,user:e.target.value}))}/>
     <TextField select size="small" label="Event type" value={filters.type} onChange={e=>setFilters(s=>({...s,type:e.target.value}))} sx={{minWidth:190}}>{TYPES.map(t=><MenuItem key={t} value={t}>{t||'All events'}</MenuItem>)}</TextField>
    </Box>
   </FeaturePanel>
   {!data?.supported&&<NotConnected name="Audit log" detail="No audit entries will be invented. A backend read-only endpoint and immutable event storage are required."/>}
   {data?.supported&&rows.length===0&&<Alert severity="info">No events match these filters.</Alert>}
   <Box sx={{display:'grid',gap:1.5}}>{rows.map((a,i)=><Paper component="article" key={a.id||i} sx={{p:2}}>
    <Box sx={{display:'flex',justifyContent:'space-between',gap:1,flexWrap:'wrap'}}><Typography fontWeight={650}>{a.action||a.type||'System event'}</Typography><Typography color="text.secondary" variant="caption">{a.created_at||a.timestamp?formatDateTime(a.created_at||a.timestamp,DEFAULT_TZ):'Time unknown'}</Typography></Box>
    <Typography variant="body2">Actor: {a.username||a.actor||a.user_id||'Unknown'}</Typography><Typography variant="body2" color="text.secondary">{a.description||a.detail||a.message||'No detail provided'}</Typography>
   </Paper>)}</Box>
  </>}
 </Layout>;
}
