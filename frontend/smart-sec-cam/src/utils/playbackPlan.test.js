import { buildBlocks, groupRuns, isContiguous, locate, toGaps, toSegments } from "./playbackPlan";

const seg = (id, start, seconds = 30) => ({
  id, start: new Date(Date.parse(start)).toISOString(),
  end: new Date(Date.parse(start) + seconds * 1000).toISOString(), formats: ["webm"],
});
const T = "2026-11-18T14:";

describe("playback plan", () => {
  const segments = toSegments([seg(1, `${T}00:00Z`), seg(2, `${T}00:30Z`), seg(3, `${T}03:00Z`)]);

  test("segments are sorted and converted to milliseconds", () => {
    const sorted = toSegments([seg(2, `${T}00:30Z`), seg(1, `${T}00:00Z`)]);
    expect(sorted.map((s) => s.id)).toEqual([1, 2]);
    expect(sorted[0].endMs - sorted[0].startMs).toBe(30000);
  });

  test("back-to-back clips are contiguous, a two-minute break is not", () => {
    expect(isContiguous(segments[0], segments[1])).toBe(true);
    expect(isContiguous(segments[1], segments[2])).toBe(false);
  });

  test("locate finds the clip and the offset inside it", () => {
    expect(locate(segments, Date.parse(`${T}00:45Z`))).toEqual({ type: "segment", index: 1, offsetSec: 15 });
    expect(locate(segments, Date.parse(`${T}00:00Z`))).toEqual({ type: "segment", index: 0, offsetSec: 0 });
  });

  test("locate reports a gap and the next clip to resume from (TS-03-05)", () => {
    expect(locate(segments, Date.parse(`${T}01:30Z`))).toEqual({ type: "gap", nextIndex: 2 });
    expect(locate(segments, Date.parse(`${T}00:00Z`) - 5000)).toEqual({ type: "gap", nextIndex: 0 });
  });

  test("locate reports the end after the last clip", () => {
    expect(locate(segments, Date.parse(`${T}09:00Z`))).toEqual({ type: "end" });
  });

  test("a run covers consecutive clips and a break starts a new run", () => {
    const runs = groupRuns(segments);
    expect(runs).toHaveLength(2);
    expect(runs[0]).toMatchObject({ count: 2, firstIndex: 0, lastIndex: 1 });
    expect(runs[0].endMs - runs[0].startMs).toBe(60000);
    expect(runs[1]).toMatchObject({ count: 1, firstIndex: 2 });
  });

  test("120 half-minute clips collapse into one hour-long run", () => {
    const many = toSegments(Array.from({ length: 120 }, (_, i) => seg(i, new Date(Date.parse(`${T}00:00Z`) + i * 30000).toISOString())));
    const runs = groupRuns(many);
    expect(runs).toHaveLength(1);
    expect(runs[0].count).toBe(120);
  });

  test("blocks interleave footage and gaps in time order", () => {
    const gaps = toGaps([{ start: `${T}01:00Z`, end: `${T}03:00Z`, type: "missing" }]);
    expect(buildBlocks(segments, gaps).map((b) => b.kind)).toEqual(["run", "gap", "run"]);
  });
});
