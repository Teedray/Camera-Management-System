import React from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import PauseIcon from "@mui/icons-material/Pause";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";

import { streamUrl } from "../api/recordingsApi";
import { isContiguous, locate } from "../utils/playbackPlan";
import { formatTime } from "../utils/time";

function pickFormat() {
  try {
    return document.createElement("video").canPlayType("video/webm") ? "webm" : "mp4";
  } catch (err) {
    return "mp4";
  }
}

// Plays a list of short clips as if they were one continuous video.
//
// Two <video> elements take turns: while one plays, the other has already loaded the
// next clip. When the first ends they swap, so the gap between clips is a frame or
// two, well inside the one-second limit (PR-03). Breaks in the footage are skipped,
// with a notice saying what was skipped.
//
// segments:    [{ id, startMs, endMs }] in time order
// seekRequest: { ms, play, nonce }. A new nonce makes the player jump to `ms`.
// onPosition:  called with the current time (ms) as playback advances.
export default function SegmentPlayer({ segments, token, tz, seekRequest, onPosition }) {
  const videoA = React.useRef(null);
  const videoB = React.useRef(null);
  const active = React.useRef(0);          // element currently shown
  const loaded = React.useRef([-1, -1]);   // segment index held by each element
  const segRef = React.useRef(segments);
  const tokenRef = React.useRef(token);
  const latest = React.useRef({});
  const format = React.useMemo(pickFormat, []);

  const [shown, setShown] = React.useState(0);
  const [playing, setPlaying] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [notice, setNotice] = React.useState("");
  const [failed, setFailed] = React.useState(false);
  const [posMs, setPosMs] = React.useState(null);

  segRef.current = segments;
  tokenRef.current = token;

  const el = (slot) => (slot === 0 ? videoA.current : videoB.current);
  const urlFor = (idx) => streamUrl(segRef.current[idx].id, tokenRef.current, format);
  const play = (video) => {
    const p = video.play();
    if (p && p.catch) p.catch(() => setPlaying(false));
  };

  // Buffer the clip after `idx` in the hidden element, if it follows on without a break.
  function preloadNext(idx) {
    const spare = 1 - active.current;
    const list = segRef.current;
    const next = idx + 1;
    const video = el(spare);
    if (!video) return;
    video.onloadedmetadata = null;
    if (next < list.length && isContiguous(list[idx], list[next])) {
      loaded.current[spare] = next;
      video.preload = "auto";
      video.src = urlFor(next);
      video.load();
    } else {
      loaded.current[spare] = -1;
    }
  }

  // Load clip `idx` into the visible element, jump to offsetSec, and optionally play.
  function startAt(idx, offsetSec, autoplay) {
    const slot = active.current;
    const video = el(slot);
    if (!video || !segRef.current[idx]) return;
    setBusy(true);
    setFailed(false);
    const other = el(1 - slot);
    if (other) other.pause();
    loaded.current[slot] = idx;
    video.onloadedmetadata = () => {
      if (offsetSec > 0) video.currentTime = offsetSec;
      setBusy(false);
      if (autoplay) play(video);
      preloadNext(idx);
    };
    video.preload = "auto";
    video.src = urlFor(idx);
    video.load();
  }

  function seekTo(ms, autoplay) {
    const list = segRef.current;
    const where = locate(list, ms);
    setPosMs(ms);
    if (where.type === "end") {
      [videoA.current, videoB.current].forEach((v) => v && v.pause());
      setPlaying(false);
      setNotice("There is no footage after this point.");
      return;
    }
    if (where.type === "gap") {
      const resume = list[where.nextIndex].startMs;
      setNotice(`No footage from ${formatTime(ms, tz)} to ${formatTime(resume, tz)}. Skipped to the next recording.`);
      setPosMs(resume);
      startAt(where.nextIndex, 0, autoplay);
      return;
    }
    setNotice("");
    const video = el(active.current);
    if (video && loaded.current[active.current] === where.index && video.readyState >= 1) {
      video.currentTime = where.offsetSec; // same clip: just move within it
      if (autoplay) play(video);
    } else {
      startAt(where.index, where.offsetSec, autoplay);
    }
  }

  function handleEnded(slot) {
    if (slot !== active.current) return;
    const list = segRef.current;
    const idx = loaded.current[slot];
    const next = idx + 1;
    if (next >= list.length) {
      setPlaying(false);
      setNotice("End of the recorded footage.");
      return;
    }
    const spare = 1 - slot;
    if (isContiguous(list[idx], list[next]) && loaded.current[spare] === next) {
      active.current = spare;           // seamless: the next clip is already buffered
      setShown(spare);
      play(el(spare));
      preloadNext(next);
    } else {
      if (!isContiguous(list[idx], list[next])) {
        setNotice(`No footage from ${formatTime(list[idx].endMs, tz)} to ${formatTime(list[next].startMs, tz)}. Skipped to the next recording.`);
      }
      startAt(next, 0, true);
    }
  }

  function handleTimeUpdate(slot) {
    if (slot !== active.current) return;
    const seg = segRef.current[loaded.current[slot]];
    const video = el(slot);
    if (!seg || !video) return;
    const ms = seg.startMs + video.currentTime * 1000;
    setPosMs(ms);
    if (onPosition) onPosition(ms);
  }

  function togglePlay() {
    const video = el(active.current);
    if (!segRef.current.length || !video) return;
    if (playing) {
      video.pause();
    } else if (loaded.current[active.current] === -1) {
      seekTo(posMs ?? segRef.current[0].startMs, true);
    } else {
      play(video);
    }
  }

  latest.current = { seekTo };

  // New search results: stop everything and forget the old clips.
  React.useEffect(() => {
    [videoA.current, videoB.current].forEach((v) => {
      if (!v) return;
      v.pause();
      v.onloadedmetadata = null;
      v.removeAttribute("src");
      v.load();
    });
    loaded.current = [-1, -1];
    active.current = 0;
    setShown(0);
    setPlaying(false);
    setBusy(false);
    setFailed(false);
    setNotice("");
    setPosMs(null);
  }, [segments]);

  React.useEffect(() => {
    if (seekRequest) latest.current.seekTo(seekRequest.ms, Boolean(seekRequest.play));
  }, [seekRequest]);

  const slotProps = (slot) => ({
    ref: slot === 0 ? videoA : videoB,
    muted: true,            // recordings have no sound; muted also allows autoplay
    playsInline: true,
    preload: "auto",
    onEnded: () => handleEnded(slot),
    onTimeUpdate: () => handleTimeUpdate(slot),
    onPlay: () => slot === active.current && setPlaying(true),
    onPause: () => slot === active.current && setPlaying(false),
    onError: () => slot === active.current && loaded.current[slot] !== -1 && setFailed(true),
    style: { position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "contain",
             opacity: shown === slot ? 1 : 0, pointerEvents: shown === slot ? "auto" : "none" },
  });

  return (
    <Box>
      <Box sx={{ position: "relative", width: "100%", aspectRatio: "16 / 9", bgcolor: "#000", borderRadius: 1, overflow: "hidden" }}>
        <video data-testid="video-a" {...slotProps(0)} />
        <video data-testid="video-b" {...slotProps(1)} />
        {busy && (
          <Box sx={{ position: "absolute", inset: 0, display: "grid", placeItems: "center" }}>
            <CircularProgress aria-label="Loading video" />
          </Box>
        )}
        {segments.length === 0 && (
          <Box sx={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", color: "#bbb", p: 2, textAlign: "center" }}>
            <Typography variant="body2">Search for footage, then choose a recording to play it here.</Typography>
          </Box>
        )}
      </Box>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 1 }}>
        <IconButton onClick={togglePlay} disabled={segments.length === 0} color="primary"
                    aria-label={playing ? "Pause" : "Play"}>
          {playing ? <PauseIcon /> : <PlayArrowIcon />}
        </IconButton>
        <Typography variant="body2" color="text.secondary">
          {posMs != null ? formatTime(posMs, tz) : "—"}
        </Typography>
      </Box>
      {notice && <Alert severity="info" sx={{ mt: 1 }} onClose={() => setNotice("")}>{notice}</Alert>}
      {failed && (
        <Alert severity="error" sx={{ mt: 1 }}>
          This clip could not be played. It may have been removed or you may no longer have access.
        </Alert>
      )}
    </Box>
  );
}
