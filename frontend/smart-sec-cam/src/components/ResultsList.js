import React from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Typography from "@mui/material/Typography";
import PlayCircleOutlineIcon from "@mui/icons-material/PlayCircleOutline";
import ReportProblemOutlinedIcon from "@mui/icons-material/ReportProblemOutlined";
import HistoryToggleOffIcon from "@mui/icons-material/HistoryToggleOff";

import { buildBlocks } from "../utils/playbackPlan";
import { formatDuration, formatTime } from "../utils/time";

const GAP_LABEL = { missing: "Missing", expired: "Expired" };
const GAP_HELP = {
  missing: "No footage was recorded in this period.",
  expired: "Removed after the 30-day retention period.",
};

// Chronological list of what was found: recorded footage, and the gaps between it.
// Missing and expired periods are shown explicitly so nobody mistakes a gap for "nothing happened".
export default function ResultsList({ segments, gaps, tz, activeMs, onPlay, onGap }) {
  if (segments.length === 0) {
    return (
      <Box role="status" sx={{ p: 2, textAlign: "center", color: "text.secondary" }}>
        <Typography fontWeight={600}>No footage found</Typography>
        <Typography variant="body2">
          There is no recording for this camera and time range.
        </Typography>
        {gaps.length > 0 && (
          <Typography variant="body2" sx={{ mt: 1 }}>
            {gaps.some((g) => g.type === "expired")
              ? GAP_HELP.expired
              : GAP_HELP.missing}
          </Typography>
        )}
      </Box>
    );
  }

  const blocks = buildBlocks(segments, gaps);
  return (
    <List dense disablePadding aria-label="Search results">
      {blocks.map((b) => {
        const span = `${formatTime(b.startMs, tz)} – ${formatTime(b.endMs, tz)}`;
        const seconds = (b.endMs - b.startMs) / 1000;
        if (b.kind === "gap") {
          return (
            <ListItemButton key={`gap-${b.startMs}`} onClick={() => onGap(b)}
                            sx={{ bgcolor: b.type === "missing" ? "#fdecea" : "#f0f0f0", mb: 0.5, borderRadius: 1 }}>
              {b.type === "missing"
                ? <ReportProblemOutlinedIcon color="error" sx={{ mr: 1.5 }} />
                : <HistoryToggleOffIcon sx={{ mr: 1.5, color: "text.secondary" }} />}
              <ListItemText primary={span} secondary={`${formatDuration(seconds)} · ${GAP_HELP[b.type]}`} />
              <Chip size="small" label={GAP_LABEL[b.type]} color={b.type === "missing" ? "error" : "default"} />
            </ListItemButton>
          );
        }
        const playing = activeMs != null && activeMs >= b.startMs && activeMs < b.endMs;
        return (
          <ListItemButton key={`run-${b.startMs}`} selected={playing} onClick={() => onPlay(b)}
                          sx={{ mb: 0.5, borderRadius: 1, border: "1px solid #e0e0e0" }}>
            <PlayCircleOutlineIcon color="success" sx={{ mr: 1.5 }} />
            <ListItemText primary={span}
                          secondary={`${formatDuration(seconds)} continuous · ${b.count} ${b.count === 1 ? "clip" : "clips"}`} />
            {playing && <Chip size="small" color="primary" label="Playing" />}
          </ListItemButton>
        );
      })}
    </List>
  );
}
