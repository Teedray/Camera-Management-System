import React from 'react';
import { isIOS } from 'react-device-detect';
import { Alert, Box, Button, LinearProgress, Paper, Typography } from '@mui/material';
import VideoPlayer from '../components/VideoPlayer';
import Layout from '../components/Layout';
import useAuth from '../hooks/useAuth';
import useMe from '../hooks/useMe';
import { listLegacyFiles } from '../api/managementApi';
import { canManageFootage } from '../utils/permissions';
export default function VideoList(){
 const {token,ready}=useAuth(),me=useMe(ready?token:null);
 const [files,setFiles]=React.useState([]),[selected,setSelected]=React.useState(null),[busy,setBusy]=React.useState(false),[error,setError]=React.useState('');
 const refresh=React.useCallback(async()=>{setBusy(true);setError('');try{const data=await listLegacyFiles(token,isIOS?'mp4':'webm');setFiles(data);setSelected(old=>data.includes(old)?old:data[0]||null);}catch(e){setFiles([]);setSelected(null);setError(e.message);}finally{setBusy(false);}},[token]);
 React.useEffect(()=>{if(ready)refresh();},[ready,refresh,me?.role]);
 if(!ready)return null;
 return <Layout token={token}><Typography variant="h5" component="h1">Recorded videos</Typography><Button onClick={refresh} disabled={busy}>Refresh recordings</Button>{busy&&<LinearProgress/>}{error&&<Alert severity="error">{error}</Alert>}{!busy&&!files.length&&!error&&<Alert severity="info">No accessible recordings found.</Alert>}<Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',md:'minmax(240px, 1fr) 3fr'},gap:2}}><Paper sx={{p:2,maxHeight:600,overflow:'auto'}}>{files.map(f=><Button key={f} fullWidth variant={selected===f?'contained':'text'} sx={{overflowWrap:'anywhere',justifyContent:'flex-start'}} onClick={()=>setSelected(f)}>{f}</Button>)}</Paper><Paper sx={{p:2}}><VideoPlayer key={selected} videoFileName={selected} token={token} canExport={canManageFootage(me?.role)}/></Paper></Box></Layout>;
}
