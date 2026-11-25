// Build a timeline from the catalogue without inventing missing/expired states.
export function recordingSegments(recordings, fromMs, toMs) {
  return (recordings||[]).filter(r => r && r.filename && Number(r.duration_seconds)>0)
    .map(r => ({id:r.filename, startMs:Date.parse(r.start), endMs:Date.parse(r.end), recording:r}))
    .filter(s=>Number.isFinite(s.startMs) && Number.isFinite(s.endMs) && s.endMs>s.startMs && s.startMs<toMs && s.endMs>fromMs)
    .sort((a,b)=>a.startMs-b.startMs);
}
export function catalogueGaps(segments, fromMs, toMs) {
  const gaps=[];let position=fromMs;
  for(const segment of segments){const start=Math.max(fromMs,segment.startMs);const end=Math.min(toMs,segment.endMs);if(start>position)gaps.push({startMs:position,endMs:start,type:'missing'});position=Math.max(position,end);}
  if(position<toMs)gaps.push({startMs:position,endMs:toMs,type:'missing'});
  return gaps;
}
export function recordingAt(segments, ms) {return segments.find(s=>ms>=s.startMs&&ms<s.endMs)||null;}
