import { catalogueGaps, recordingSegments } from "./recordingTimeline";

const seg = (startMs, endMs) => ({ startMs, endMs });

test("back-to-back 30 s segments a few ms apart are not gaps", () => {
  // Segments start at their first frame, ~50 ms after the previous one ends.
  const segments = [seg(0, 30000), seg(30050, 60000), seg(60040, 90000)];
  expect(catalogueGaps(segments, 0, 90000)).toEqual([]);
});

test("a real outage is still reported", () => {
  const segments = [seg(0, 30000), seg(120000, 150000)];
  expect(catalogueGaps(segments, 0, 150000)).toEqual([{ startMs: 30000, endMs: 120000, type: "missing" }]);
});

test("time before the first and after the last segment counts", () => {
  expect(catalogueGaps([seg(10000, 20000)], 0, 30000)).toEqual([
    { startMs: 0, endMs: 10000, type: "missing" },
    { startMs: 20000, endMs: 30000, type: "missing" },
  ]);
});

test("only recordings overlapping the searched time range are kept, in time order", () => {
  const rec = (filename, start, end) => ({ filename, start, end, duration_seconds: 30 });
  const from = Date.parse("2026-11-25T03:48:00Z"), to = Date.parse("2026-11-25T03:49:00Z");
  const segments = recordingSegments([
    rec("late.mp4", "2026-11-25T03:48:30Z", "2026-11-25T03:49:00Z"),
    rec("before.mp4", "2026-11-25T03:47:00Z", "2026-11-25T03:47:30Z"),
    rec("early.mp4", "2026-11-25T03:48:00Z", "2026-11-25T03:48:30Z"),
    rec("after.mp4", "2026-11-25T03:49:00Z", "2026-11-25T03:49:30Z"),
    { filename: "broken.mp4", start: "not a date", end: "2026-11-25T03:48:10Z", duration_seconds: 10 },
  ], from, to);
  expect(segments.map((s) => s.id)).toEqual(["early.mp4", "late.mp4"]);
});
