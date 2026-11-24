import { clockInTz, formatDuration, formatTime, localToUtcMs, todayInTz } from "./time";

describe("time helpers", () => {
  test("UTC is shown in Jamaica time, five hours behind (SR-03-02)", () => {
    expect(formatTime("2026-11-18T14:00:00Z")).toBe("9:00:00 AM");
    expect(formatTime("2026-11-18T14:00:00Z", undefined, false)).toBe("9:00 AM");
    expect(formatTime("2026-11-18T03:30:00Z")).toBe("10:30:00 PM"); // previous evening locally
  });

  test("a store-local date and time converts back to UTC", () => {
    expect(localToUtcMs("2026-11-18", "09:00")).toBe(Date.parse("2026-11-18T14:00:00Z"));
    expect(localToUtcMs("2026-11-18", "23:30")).toBe(Date.parse("2026-11-19T04:30:00Z"));
  });

  test("today and the clock are read in the store's zone, not the browser's", () => {
    const now = new Date("2026-11-19T03:15:00Z"); // still 18 Nov, 10:15 PM in Jamaica
    expect(todayInTz(undefined, now)).toBe("2026-11-18");
    expect(clockInTz(undefined, now)).toBe("22:15");
  });

  test("durations read naturally", () => {
    expect(formatDuration(30)).toBe("30 s");
    expect(formatDuration(120)).toBe("2 min");
    expect(formatDuration(150)).toBe("2 min 30 s");
    expect(formatDuration(3900)).toBe("1 h 05 min");
  });
});
