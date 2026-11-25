import { catalogueGaps } from "./recordingTimeline";

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
