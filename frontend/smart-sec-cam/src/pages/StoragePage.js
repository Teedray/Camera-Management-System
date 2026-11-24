import React from 'react';
import { Alert, Box, Button, LinearProgress, Paper, TextField, Typography } from '@mui/material';
import Layout from '../components/Layout';
import { FeaturePanel, InfoGrid, NotConnected, RetryError } from '../components/FeaturePanel';
import useAuth from '../hooks/useAuth';import useMe from '../hooks/useMe';
import { loadStorage, saveRetention, explainUnsupported } from '../api/managementApi';
import { canManageSystem } from '../utils/permissions';import { formatBytes } from '../utils/time';
export default function StoragePage(){
  const {token,ready}=useAuth(),me=useMe(ready?token:null),admin=canManageSystem(me?.role);
  const [snapshot,setSnapshot]=React.useState(null),[days,setDays]=React.useState('30'),[busy,setBusy]=React.useState(false),[error,setError]=React.useState(''),[notice,setNotice]=React.useState('');
  const load=React.useCallback(async()=>{setBusy(true);setError('');try{const s=await loadStorage(token);setSnapshot(s);if(s?.data?.retention_days!=null)setDays(String(s.data.retention_days));}catch(e){setError(e.message);}finally{setBusy(false);}},[token]);
  React.useEffect(()=>{if(ready&&admin)load();},[ready,admin,load]);
  const d=snapshot?.data||{};const percent=d.total_bytes>0?Math.min(100,100*Number(d.used_bytes||0)/d.total_bytes):null;
  async function save(e){e.preventDefault();if(!/^\d+$/.test(days)||Number(days)<1||Number(days)>3650){setError('Retention must be a whole number between 1 and 3650 days.');return;}setBusy(true);setNotice('');setError('');try{await saveRetention(token,{retention_days:Number(days)});setNotice('Retention policy saved by backend.');await load();}catch(e){setError(explainUnsupported(e,'Retention update'));}finally{setBusy(false);}}
  if(!ready)return null;
  return <Layout token={token}><Typography variant="h5" component="h1" sx={{mb:1}}>Storage & retention</Typography><Typography color="text.secondary" variant="body2" sx={{mb:2}}>Manage expiration while protecting incident clips and active jobs</Typography>
    {!me?<LinearProgress/>:!admin?<Alert severity="warning">Storage settings require administrator access.</Alert>:<>
      <RetryError error={error} onRetry={load}/>{notice&&<Alert severity="success" sx={{mb:2}}>{notice}</Alert>}{busy&&<LinearProgress sx={{mb:2}}/>}
      <InfoGrid items={[{label:'Capacity',value:d.total_bytes!=null?formatBytes(d.total_bytes):null},{label:'Used',value:d.used_bytes!=null?formatBytes(d.used_bytes):null},{label:'Free',value:d.free_bytes!=null?formatBytes(d.free_bytes):null},{label:'Protected incidents',value:d.protected_incidents}]}/>
      <FeaturePanel title="Disk capacity and health">
        {percent!=null?<><Box sx={{height:12,borderRadius:2,bgcolor:'action.hover',overflow:'hidden'}}><Box sx={{height:'100%',bgcolor:percent>=90?'error.main':'primary.main',width:`${percent}%`}}/></Box><Typography variant="body2" sx={{mt:1}}>{percent.toFixed(1)}% used</Typography></>:<NotConnected name="Disk telemetry"/>}
        {d.warnings?.map((w,i)=><Alert key={i} severity="warning" sx={{mt:1}}>{w.message||w}</Alert>)}
      </FeaturePanel>
      <FeaturePanel title="Approved retention period" detail="Changes take effect only after the server confirms the new policy.">
        <Box component="form" onSubmit={save} sx={{display:'flex',gap:2,alignItems:'start',flexWrap:'wrap'}}><TextField label="Retain ordinary footage (days)" size="small" type="number" inputProps={{min:1,max:3650,step:1}} value={days} onChange={e=>setDays(e.target.value)} sx={{minWidth:230}}/><Button type="submit" variant="contained" disabled={busy||!snapshot?.supported}>Save retention policy</Button></Box>
        {!snapshot?.supported&&<NotConnected name="Retention controls"/>}
      </FeaturePanel>
      <FeaturePanel title="Expiry, legal hold and active jobs">
        <Typography variant="body2">Saved incidents and recordings used by active exports or merges must be protected from routine deletion. The server—not the browser—must enforce retention and holds.</Typography>
        {(d.items||[]).map(item=><Paper key={item.id} variant="outlined" sx={{p:1.5,mt:1}}><Typography>{item.filename||item.id}</Typography><Typography color="text.secondary" variant="caption">Expires: {item.expires_at||'Not reported'} · Protected: {item.protected?'Yes':'No'} · Active jobs: {item.active_jobs??'Unknown'}</Typography></Paper>)}
        {!snapshot?.supported&&<NotConnected name="Expiry/protection inventory"/>}
      </FeaturePanel>
    </>}
  </Layout>;
}
