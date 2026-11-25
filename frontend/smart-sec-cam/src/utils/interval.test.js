import { defaultInterval, validateInterval } from "./interval";
import { formatBytes, localToUtcMs, timeAgo } from "./time";

const start = Date.parse("2026-11-18T14:00:00Z");
const end = Date.parse("2026-11-18T15:00:00Z");
const TZ = "America/Jamaica";

describe("interval helpers", () => {
  test("starts at the playback position and runs five minutes, in store time", () => {
    expect(defaultInterval(start, end, Date.parse("2026-11-18T14:10:00Z"), TZ))
      .toEqual({ date: "2026-11-18", start: "09:10:00", end: "09:15:00" });
  });

  test("never runs past the end of the searched range", () => {
    expect(defaultInterval(start, end, Date.parse("2026-11-18T14:58:00Z"), TZ).end).toBe("10:00:00");
  });

  test("a valid choice returns UTC times", () => {
    const r = validateInterval({ date: "2026-11-18", start: "09:10:00", end: "09:15:30" }, start, end, TZ);
    expect(r.errors).toEqual({});
    expect(r.startMs).toBe(Date.parse("2026-11-18T14:10:00Z"));
    expect(r.endMs).toBe(Date.parse("2026-11-18T14:15:30Z"));
  });

  test.each([
    [{ start: "", end: "09:15" }, "start", "Enter the start time."],
    [{ start: "09:15", end: "09:10" }, "end", "The end time must be after the start time."],
    [{ start: "09:15", end: "09:15" }, "end", "The end time must be after the start time."],
    [{ start: "08:30", end: "09:15" }, "start", /Choose times between 9:00 AM and 10:00 AM/],
    [{ start: "09:30", end: "10:30" }, "start", /Choose times between/],
  ])("rejects %j", (change, field, message) => {
    const { errors } = validateInterval({ date: "2026-11-18", ...change }, start, end, TZ);
    expect(errors[field]).toEqual(typeof message === "string" ? message : expect.stringMatching(message));
  });

  test("times with seconds convert exactly", () => {
    expect(localToUtcMs("2026-11-18", "09:10:30", TZ)).toBe(Date.parse("2026-11-18T14:10:30Z"));
  });

  test("sizes and ages read naturally", () => {
    expect(formatBytes(1.72e12)).toBe("1.7 TB");
    expect(formatBytes(14200000)).toBe("14.2 MB");
    const now = Date.parse("2026-11-18T20:00:00Z");
    expect(timeAgo("2026-11-18T19:59:40Z", TZ, now)).toBe("just now");
    expect(timeAgo("2026-11-18T19:30:00Z", TZ, now)).toBe("30 min ago");
    expect(timeAgo("2026-11-18T15:00:00Z", TZ, now)).toBe("5 h ago");
    expect(timeAgo(null)).toBe("never");
  });
});
