import React from 'react';
import { Alert, Box, Button, Chip, LinearProgress, MenuItem, Paper, TextField, Typography } from '@mui/material';
import { fetchCameras, listRecordings } from '../api/recordingsApi';
import { listLegacyFiles } from '../api/managementApi';
import { createIncident } from '../api/incidentsApi';
import { downloadClip } from '../api/exportsApi';
import Layout from '../components/Layout';import SegmentPlayer from '../components/SegmentPlayer';import TimelineBar from '../components/TimelineBar';
import useAuth from '../hooks/useAuth';import useMe from '../hooks/useMe';
import { defaultValues, validateSearch } from '../components/SearchForm';
import { localToUtcMs, formatDateTime, formatDuration, DEFAULT_TZ } from '../utils/time';
import { catalogueGaps, recordingSegments, recordingAt } from '../utils/recordingTimeline';
import { canManageFootage } from '../utils/permissions';import { writeExportHistory } from '../utils/exportHistory';

function filenameFor(recording,start,end){return `${String(recording).replace(/\.(mp4|webm)$/i,'').replace(/[^a-zA-Z0-9_-]/g,'_')}_${Math.round(start)}-${Math.round(end)}.mp4`;}
export default function RealSearchPage(){
 const {token,ready}=useAuth(),me=useMe(ready?token:null),allowed=canManageFootage(me?.role);
 const [cameras,setCameras]=React.useState([]),[values,setValues]=React.useState(defaultValues),[results,setResults]=React.useState([]);
 const [legacy,setLegacy]=React.useState([]),[searched,setSearched]=React.useState(false),[searching,setSearching]=React.useState(false);
 const [fromMs,setFromMs]=React.useState(null),[toMs,setToMs]=React.useState(null),[selected,setSelected]=React.useState(null),[playhead,setPlayhead]=React.useState(null);
 const [seek,setSeek]=React.useState(null),[startSec,setStartSec]=React.useState('0'),[endSec,setEndSec]=React.useState('0');
 const [title,setTitle]=React.useState(''),[notes,setNotes]=React.useState(''),[busy,setBusy]=React.useState(''),[error,setError]=React.useState(''),[notice,setNotice]=React.useState('');
 const nonce=React.useRef(0);
 React.useEffect(()=>{if(!ready)return;let active=true;fetchCameras(token).then(cs=>{if(active)setCameras(cs);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[ready,token]);
 const segments=React.useMemo(()=>fromMs!=null?recordingSegments(results,fromMs,toMs):[],[results,fromMs,toMs]);
 const gaps=React.useMemo(()=>fromMs!=null?catalogueGaps(segments,fromMs,toMs):[],[segments,fromMs,toMs]);
 function choose(s,play=true){if(!s)return;setSelected(s);setStartSec('0');setEndSec(String(Math.min(Number(s.recording.duration_seconds),30)));setTitle('');setNotes('');setSeek({ms:s.startMs,play,nonce:++nonce.current});}
 async function submit(e){e.preventDefault();const found=validateSearch(values);if(Object.keys(found).length){setError(Object.values(found).join(' '));return;}
  setSearching(true);setError('');setNotice('');setResults([]);setLegacy([]);setSelected(null);setSearched(false);
  try{const from=localToUtcMs(values.date,values.start,DEFAULT_TZ),to=localToUtcMs(values.date,values.end,DEFAULT_TZ);
   if(!(to>from))throw new Error('End time must be after start time.');const camera=cameras.find(c=>c.id===values.camera);if(!camera)throw new Error('Select an assigned camera.');
   const [all,files]=await Promise.all([listRecordings(token),listLegacyFiles(token)]);
   const filtered=all.filter(r=>r.camera_id===camera.id);const list=recordingSegments(filtered,from,to);
   setResults(filtered);setLegacy(files.filter(f=>f.startsWith(`${camera.channel_name}__`) && !all.some(r=>r.filename===f)));
   setFromMs(from);setToMs(to);setSearched(true);if(list.length)choose(list[0],false);
  }catch(e){setError(e.message);}finally{setSearching(false);}}
 const currentRange=()=>{if(!selected)throw new Error('Select one available catalogue recording.');const start=Number(startSec),end=Number(endSec),duration=Number(selected.recording.duration_seconds);
   if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end<=start||end>duration+0.001)throw new Error(`Enter a valid interval between 0 and ${duration.toFixed(1)} seconds. A clip must stay inside one recording.`);
   return {filename:selected.id,start_time:start,end_time:end};};
 function setAtPlayhead(which){if(!selected||playhead==null)return;const s=recordingAt(segments,playhead);if(!s||s.id!==selected.id){setError('Select the recording containing the current playhead first.');return;}const offset=Math.max(0,Math.min(Number(selected.recording.duration_seconds),(playhead-s.startMs)/1000)).toFixed(1);(which==='start'?setStartSec:setEndSec)(offset);}
 async function save(){if(!allowed)return;setBusy('saving');setError('');setNotice('');try{const clip=currentRange();if(!title.trim())throw new Error('Enter an incident title.');await createIncident(token,{...clip,title:title.trim(),notes:notes.trim()});setNotice('Incident saved. Open the incident archive to view the protected clip.');}catch(e){setError(e.message);}finally{setBusy('');}}
 async function exportMp4(){if(!allowed)return;setBusy('exporting');setError('');setNotice('');const id=`${Date.now()}-${Math.random().toString(36).slice(2)}`;
   try{const clip=currentRange();writeExportHistory({id,filename:clip.filename,start_time:clip.start_time,end_time:clip.end_time,status:'processing',created_at:new Date().toISOString()});const blob=await downloadClip(token,clip);const file=filenameFor(clip.filename,clip.start_time,clip.end_time);const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=file;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);writeExportHistory({id,filename:clip.filename,file,start_time:clip.start_time,end_time:clip.end_time,status:'downloaded',created_at:new Date().toISOString(),size_bytes:blob.size});setNotice('MP4 downloaded. A copy was not retained on the server for re-download.');}
   catch(e){writeExportHistory({id,filename:selected?.id||'',status:'failed',created_at:new Date().toISOString(),error:e.message});setError(e.message);}finally{setBusy('');}}
 function seekTo(ms,play=true){setSeek({ms,play,nonce:++nonce.current});const s=recordingAt(segments,ms);if(s&&s.id!==selected?.id)choose(s,play);}
 const rangeValid=Number(endSec)>Number(startSec)&&Number(startSec)>=0&&Number(endSec)<=Number(selected?.recording?.duration_seconds||0)+0.001;
 if(!ready)return null;
 return <Layout token={token}><Typography variant="h5" component="h1" sx={{mb:1}}>Search & review footage</Typography>
  <Typography variant="body2" color="text.secondary" sx={{mb:2}}>Manual timeline scanning · Camera access checked by backend · Store timezone: {DEFAULT_TZ}</Typography>
  {error&&<Alert severity="error" sx={{mb:2}} onClose={()=>setError('')}>{error}</Alert>}{notice&&<Alert severity="success" sx={{mb:2}} onClose={()=>setNotice('')}>{notice}</Alert>}
  <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',lg:'minmax(310px,380px) 1fr'},gap:2,alignItems:'start'}}>
   <Paper component="form" onSubmit={submit} sx={{p:2,display:'grid',gap:1.5}}>
    <Typography variant="h6">Find recordings</Typography><TextField select label="Assigned camera" required value={values.camera} onChange={e=>setValues(v=>({...v,camera:e.target.value}))}><MenuItem value="">Choose camera</MenuItem>{cameras.map(c=><MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>)}</TextField>
    <TextField type="date" label="Date" InputLabelProps={{shrink:true}} value={values.date} onChange={e=>setValues(v=>({...v,date:e.target.value}))}/><Box sx={{display:'flex',gap:1}}><TextField fullWidth type="time" label="Start time" InputLabelProps={{shrink:true}} value={values.start} onChange={e=>setValues(v=>({...v,start:e.target.value}))}/><TextField fullWidth type="time" label="End time" InputLabelProps={{shrink:true}} value={values.end} onChange={e=>setValues(v=>({...v,end:e.target.value}))}/></Box>
    <Button type="submit" variant="contained" disabled={searching||!cameras.length}>Search</Button>{searching&&<LinearProgress/>}
    {searched&&<><Typography fontWeight={600}>{segments.length} playable recording(s)</Typography><Typography variant="body2" color="text.secondary">{gaps.length} catalogue gap(s). Gaps may indicate missing, expired or legacy footage; the backend does not identify which.</Typography>
      {segments.map(s=><Button key={s.id} size="small" variant={selected?.id===s.id?'contained':'outlined'} onClick={()=>choose(s)} sx={{justifyContent:'flex-start',textAlign:'left'}}>{formatDateTime(s.startMs,DEFAULT_TZ)} · {formatDuration(s.recording.duration_seconds)}</Button>)}
      {!segments.length&&<Alert severity="info">No timestamped catalogue clips in this time window.</Alert>}
      {legacy.length>0&&<Alert severity="warning">{legacy.length} accessible legacy filename(s) exist for this camera but have no verified duration. View them under Videos; they cannot be precisely placed or trimmed without server metadata.</Alert>}
    </>}
   </Paper>
   <Paper sx={{p:2}}>
    <Typography variant="h6" sx={{mb:1}}>Recording player</Typography>
    <SegmentPlayer segments={segments} token={token} tz={DEFAULT_TZ} seekRequest={seek} onPosition={ms=>setPlayhead(ms)}/>
    {fromMs!=null&&toMs!=null&&<Box sx={{mt:1}}><TimelineBar rangeStartMs={fromMs} rangeEndMs={toMs} segments={segments} gaps={gaps} posMs={playhead} onSeek={ms=>seekTo(ms)} tz={DEFAULT_TZ}/><Alert severity="info" sx={{mt:1}}>Red portions are unverified catalogue gaps, not proof that footage was never recorded. Retention/expiry classification requires backend metadata.</Alert></Box>}
    {selected&&<Box sx={{mt:2}}><Typography fontWeight={600}>{selected.recording.camera_name} · {formatDateTime(selected.startMs,DEFAULT_TZ)}</Typography><Typography variant="body2" color="text.secondary">Recording duration: {formatDuration(selected.recording.duration_seconds)}. Select a clip interval inside this one recording.</Typography>
      <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',sm:'1fr 1fr'},gap:1,mt:2}}><TextField label="Clip start (seconds)" size="small" type="number" inputProps={{min:0,step:0.1,max:selected.recording.duration_seconds}} value={startSec} onChange={e=>setStartSec(e.target.value)}/><TextField label="Clip end (seconds)" size="small" type="number" inputProps={{min:0,step:0.1,max:selected.recording.duration_seconds}} value={endSec} onChange={e=>setEndSec(e.target.value)}/><Button variant="outlined" disabled={playhead==null||!!busy} onClick={()=>setAtPlayhead('start')}>Start at playhead</Button><Button variant="outlined" disabled={playhead==null||!!busy} onClick={()=>setAtPlayhead('end')}>End at playhead</Button></Box>
      <Chip sx={{my:2}} color={rangeValid?'success':'warning'} label={rangeValid?`Selected: ${formatDuration(Number(endSec)-Number(startSec))}`:'Choose a valid nonzero interval'}/>
      {allowed?<><Box sx={{display:'grid',gap:1.5}}><TextField label="Incident title" size="small" value={title} onChange={e=>setTitle(e.target.value)}/><TextField label="Notes (optional)" size="small" multiline minRows={2} value={notes} onChange={e=>setNotes(e.target.value)}/><Box sx={{display:'flex',gap:1,flexWrap:'wrap'}}><Button variant="outlined" disabled={!!busy||!rangeValid||!title.trim()} onClick={save}>{busy==='saving'?'Saving…':'Save incident'}</Button><Button variant="contained" disabled={!!busy||!rangeValid} onClick={exportMp4}>{busy==='exporting'?'Preparing MP4…':'Trim & download MP4'}</Button></Box></Box>{busy&&<LinearProgress sx={{mt:1}}/>}</>:<Alert severity="info">Viewer permission: playback only. Incident saving, trimming and MP4 downloads are restricted to managers and administrators.</Alert>}
    </Box>}
   </Paper>
  </Box>
 </Layout>;
}
