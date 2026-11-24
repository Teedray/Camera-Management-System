// Fake backend for working on the screens without the server (REACT_APP_USE_MOCK=1).
// It follows the same response shape as the real /api/recordings endpoint.
import { DEFAULT_TZ, localToUtcMs } from "../utils/time";

const RETENTION_MS = 30 * 24 * 3600 * 1000;
const SEGMENT_MS = 30 * 1000;
const iso = (ms) => new Date(ms).toISOString();

export const MOCK_CAMERAS = ["CAM_ENTRANCE", "CAM_CASHIER", "CAM_AISLES", "CAM_DISPENSARY"].map((name) => ({
  name, recordings: 2880, last_recording: iso(Date.now() - 60 * 1000),
}));

export function mockSearch({ camera, date, start, end }, now = Date.now()) {
  const startMs = localToUtcMs(date, start, DEFAULT_TZ);
  const endMs = Math.min(localToUtcMs(date, end, DEFAULT_TZ), now);
  const cutoff = now - RETENTION_MS;
  const segments = [];
  const gaps = [];

  if (endMs <= cutoff) {
    gaps.push({ start: iso(startMs), end: iso(endMs), type: "expired" });
  } else {
    // 30-second clips, with a two-minute outage about a third of the way in.
    const total = Math.floor((endMs - startMs) / SEGMENT_MS);
    const outageFrom = Math.floor(total / 3);
    for (let i = 0; i < total; i += 1) {
      if (i >= outageFrom && i < outageFrom + 4) continue;
      const s = startMs + i * SEGMENT_MS;
      segments.push({ id: i + 1, start: iso(s), end: iso(s + SEGMENT_MS), duration: 30,
                      formats: ["webm", "mp4"], estimated: false });
    }
    if (total > 8) {
      const g0 = startMs + outageFrom * SEGMENT_MS;
      gaps.push({ start: iso(g0), end: iso(g0 + 4 * SEGMENT_MS), type: "missing" });
    }
  }
  const sum = (type) => gaps.filter((g) => g.type === type)
    .reduce((t, g) => t + (Date.parse(g.end) - Date.parse(g.start)) / 1000, 0);
  return {
    status: "OK", camera, timezone: DEFAULT_TZ, segments, gaps,
    range: { start: iso(startMs), end: iso(endMs) },
    summary: { segments: segments.length, available_seconds: segments.length * 30,
               missing_seconds: sum("missing"), expired_seconds: sum("expired") },
  };
}
