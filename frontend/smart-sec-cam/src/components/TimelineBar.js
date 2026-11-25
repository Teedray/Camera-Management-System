import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import { groupRuns } from "../utils/playbackPlan";
import { formatTime } from "../utils/time";

const COLORS = { available: "#2e7d32", missing: "#d32f2f", expired: "#9e9e9e" };

// A bar for the whole searched range: green where there is footage, red where it is
// missing, grey where it has expired. It doubles as the seek control for playback.
export default function TimelineBar({ rangeStartMs, rangeEndMs, segments, gaps, posMs, onSeek, tz }) {
  const [drag, setDrag] = React.useState(null);
  const total = Math.max(1, rangeEndMs - rangeStartMs);
  const left = (ms) => Math.min(100, Math.max(0, ((ms - rangeStartMs) / total) * 100));
  const block = (a, b) => ({ left: `${left(a)}%`, width: `${Math.max(0.3, left(b) - left(a))}%` });
  const value = Math.min(rangeEndMs, Math.max(rangeStartMs, drag ?? posMs ?? rangeStartMs));

  function commit() {
    if (drag != null) {
      onSeek(drag);
      setDrag(null);
    }
  }

  return (
    <Box>
      <Box sx={{ position: "relative", height: 40, borderRadius: 1, overflow: "hidden", bgcolor: "#e0e0e0" }}>
        {groupRuns(segments).map((r) => (
          <Box key={`a-${r.startMs}`} data-testid="timeline-available"
               sx={{ position: "absolute", top: 0, bottom: 0, bgcolor: COLORS.available, ...block(r.startMs, r.endMs) }} />
        ))}
        {gaps.map((g) => (
          <Box key={`g-${g.startMs}`} data-testid={`timeline-${g.type}`}
               sx={{ position: "absolute", top: 0, bottom: 0, bgcolor: COLORS[g.type], ...block(g.startMs, g.endMs) }} />
        ))}
        <Box sx={{ position: "absolute", top: 0, bottom: 0, width: "3px", bgcolor: "#111",
                   left: `${left(value)}%`, transform: "translateX(-1px)", pointerEvents: "none" }} />
        <Box component="input" type="range" min={rangeStartMs} max={rangeEndMs} step={1000}
             value={Math.round(value)} aria-label="Playback position" aria-valuetext={formatTime(value, tz)}
             onChange={(e) => setDrag(Number(e.target.value))}
             onPointerUp={commit} onKeyUp={commit} onBlur={commit}
             sx={{ position: "absolute", inset: 0, width: "100%", height: "100%", m: 0, opacity: 0,
                   cursor: "pointer", touchAction: "none" }} />
      </Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", mt: 0.5 }}>
        <Typography variant="caption">{formatTime(rangeStartMs, tz, false)}</Typography>
        <Typography variant="caption" fontWeight={600}>{formatTime(value, tz)}</Typography>
        <Typography variant="caption">{formatTime(rangeEndMs, tz, false)}</Typography>
      </Box>
      <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", mt: 0.5 }}>
        {[["available", "Footage"], ["missing", "Missing"], ["expired", "Expired"]].map(([k, label]) => (
          <Box key={k} sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            <Box sx={{ width: 12, height: 12, borderRadius: "2px", bgcolor: COLORS[k] }} />
            <Typography variant="caption">{label}</Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
