import { clockSecondsInTz, dateInTz, formatTime, localToUtcMs } from "./time";

const TIME = /^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$/;

// Check a start/end chosen inside the range the user searched (SR-04-01, SR-05-01).
// Returns { errors, startMs, endMs }; startMs and endMs are UTC epochs when there are no errors.
export function validateInterval({ date, start, end }, rangeStartMs, rangeEndMs, tz) {
  const errors = {};
  if (!TIME.test(start || "")) errors.start = "Enter the start time.";
  if (!TIME.test(end || "")) errors.end = "Enter the end time.";
  if (errors.start || errors.end) return { errors };
  const startMs = localToUtcMs(date, start, tz);
  const endMs = localToUtcMs(date, end, tz);
  if (endMs <= startMs) {
    errors.end = "The end time must be after the start time.";
  } else if (startMs < rangeStartMs || endMs > rangeEndMs) {
    errors.start = `Choose times between ${formatTime(rangeStartMs, tz, false)} and ${formatTime(rangeEndMs, tz, false)}, the range you searched.`;
  }
  return { errors, startMs, endMs };
}

// Start where the player is (or the start of the range) and run for five minutes.
export function defaultInterval(rangeStartMs, rangeEndMs, posMs, tz, lengthMs = 5 * 60 * 1000) {
  const start = Math.min(Math.max(posMs ?? rangeStartMs, rangeStartMs), rangeEndMs);
  const end = Math.min(start + lengthMs, rangeEndMs);
  return { date: dateInTz(start, tz), start: clockSecondsInTz(start, tz), end: clockSecondsInTz(end, tz) };
}
