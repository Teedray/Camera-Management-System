// Build a timeline from the catalogue without inventing missing/expired states.
export function recordingSegments(recordings, fromMs, toMs) {
  return (recordings||[]).filter(r => r && r.filename && Number(r.duration_seconds)>0)
    .map(r => ({id:r.filename, startMs:Date.parse(r.start), endMs:Date.parse(r.end), recording:r}))
    .filter(s=>Number.isFinite(s.startMs) && Number.isFinite(s.endMs) && s.endMs>s.startMs && s.startMs<toMs && s.endMs>fromMs)
    .sort((a,b)=>a.startMs-b.startMs);
}
// Each 30-second segment starts at its first frame, a few milliseconds after the
// previous one ends, so only breaks longer than this count as gaps. It matches
// GAP_TOLERANCE_SECONDS in backend/smart_sec_cam/video/catalogue.py.
export const GAP_TOLERANCE_MS = 2000;
export function catalogueGaps(segments, fromMs, toMs, toleranceMs = GAP_TOLERANCE_MS) {
  const gaps=[];let position=fromMs;
  const add=(startMs,endMs)=>{if(endMs-startMs>toleranceMs)gaps.push({startMs,endMs,type:'missing'});};
  for(const segment of segments){const start=Math.max(fromMs,segment.startMs);const end=Math.min(toMs,segment.endMs);if(start>position)add(position,start);position=Math.max(position,end);}
  if(position<toMs)add(position,toMs);
  return gaps;
}
export function recordingAt(segments, ms) {return segments.find(s=>ms>=s.startMs&&ms<s.endMs)||null;}
