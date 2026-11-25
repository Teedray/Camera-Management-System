// Pure helpers that decide what to play and what to show. Kept free of React and
// the DOM so they can be tested directly.

// Breaks shorter than this between two segments are treated as continuous (matches the server).
export const CONTIGUOUS_TOLERANCE_MS = 2000;

export function toSegments(apiSegments = []) {
  return apiSegments
    .map((s) => ({
      id: s.id,
      startMs: Date.parse(s.start),
      endMs: Date.parse(s.end),
      formats: s.formats || [],
      estimated: Boolean(s.estimated),
    }))
    .sort((a, b) => a.startMs - b.startMs);
}

export function toGaps(apiGaps = []) {
  return apiGaps
    .map((g) => ({ startMs: Date.parse(g.start), endMs: Date.parse(g.end), type: g.type }))
    .sort((a, b) => a.startMs - b.startMs);
}

export function isContiguous(prev, next) {
  return next.startMs - prev.endMs <= CONTIGUOUS_TOLERANCE_MS;
}

// Where does a point in time land?
//   { type: "segment", index, offsetSec }  inside recorded footage
//   { type: "gap", nextIndex }             in a break; nextIndex is the next segment
//   { type: "end" }                        after the last segment
export function locate(segments, posMs) {
  for (let i = 0; i < segments.length; i += 1) {
    const s = segments[i];
    if (posMs >= s.startMs && posMs < s.endMs) {
      return { type: "segment", index: i, offsetSec: (posMs - s.startMs) / 1000 };
    }
    if (posMs < s.startMs) return { type: "gap", nextIndex: i };
  }
  return { type: "end" };
}

// Group back-to-back segments into runs so 120 half-minute clips read as one hour.
export function groupRuns(segments) {
  const runs = [];
  segments.forEach((seg, index) => {
    const last = runs[runs.length - 1];
    if (last && isContiguous(segments[last.lastIndex], seg)) {
      last.endMs = Math.max(last.endMs, seg.endMs);
      last.count += 1;
      last.lastIndex = index;
    } else {
      runs.push({ kind: "run", startMs: seg.startMs, endMs: seg.endMs, count: 1,
                  firstIndex: index, lastIndex: index });
    }
  });
  return runs;
}

// Runs and gaps in time order, for the results list.
export function buildBlocks(segments, gaps) {
  const gapBlocks = gaps.map((g) => ({ kind: "gap", startMs: g.startMs, endMs: g.endMs, type: g.type }));
  return [...groupRuns(segments), ...gapBlocks].sort((a, b) => a.startMs - b.startMs);
}
