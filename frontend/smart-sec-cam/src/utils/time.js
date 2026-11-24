// All times travel as UTC. They are only converted for display, and always into
// the store's time zone (SRS 2.1.3, SR-03-02).
export const DEFAULT_TZ = "America/Jamaica";

export function formatTime(value, tz = DEFAULT_TZ, withSeconds = true) {
  const opts = { timeZone: tz, hour: "numeric", minute: "2-digit", hour12: true };
  if (withSeconds) opts.second = "2-digit";
  return new Intl.DateTimeFormat("en-US", opts).format(new Date(value));
}

export function formatDate(value, tz = DEFAULT_TZ) {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: tz, weekday: "short", year: "numeric", month: "short", day: "numeric",
  }).format(new Date(value));
}

export function formatDuration(totalSeconds) {
  const s = Math.max(0, Math.round(totalSeconds));
  if (s < 60) return `${s} s`;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const rest = s % 60;
  if (h > 0) return `${h} h ${String(m).padStart(2, "0")} min`;
  return rest ? `${m} min ${rest} s` : `${m} min`;
}

// "YYYY-MM-DD" for the current day in the given zone.
export function todayInTz(tz = DEFAULT_TZ, now = new Date()) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit",
  }).format(now);
}

// "HH:MM" (24 hour) for the current time in the given zone.
export function clockInTz(tz = DEFAULT_TZ, now = new Date()) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: tz, hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).format(now);
}

// Convert a store-local date ("YYYY-MM-DD") and time ("HH:MM" or "HH:MM:SS") to a UTC epoch in ms.
// Works for any zone by comparing what the zone's clock shows at a guessed instant.
export function localToUtcMs(date, time, tz = DEFAULT_TZ) {
  const [y, mo, d] = date.split("-").map(Number);
  const [h, mi, sec = 0] = time.split(":").map(Number);
  const guess = Date.UTC(y, mo - 1, d, h, mi, sec);
  const shown = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
  }).formatToParts(new Date(guess)).reduce((acc, p) => ({ ...acc, [p.type]: p.value }), {});
  const asUtc = Date.UTC(shown.year, shown.month - 1, shown.day, shown.hour, shown.minute, shown.second);
  return guess - (asUtc - guess);
}

// "YYYY-MM-DD" of an instant in the given zone.
export function dateInTz(ms, tz = DEFAULT_TZ) {
  return todayInTz(tz, new Date(ms));
}

// "HH:MM:SS" (24 hour) of an instant in the given zone, the format <input type="time" step="1"> uses.
export function clockSecondsInTz(ms, tz = DEFAULT_TZ) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: tz, hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
  }).format(new Date(ms));
}

export function formatDateTime(value, tz = DEFAULT_TZ) {
  return `${formatDate(value, tz)}, ${formatTime(value, tz)}`;
}

export function formatBytes(bytes) {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let n = Number(bytes) || 0;
  let i = 0;
  while (n >= 1000 && i < units.length - 1) {
    n /= 1000;
    i += 1;
  }
  return `${n >= 100 || i === 0 ? Math.round(n) : n.toFixed(1)} ${units[i]}`;
}

export function timeAgo(value, tz = DEFAULT_TZ, now = Date.now()) {
  if (!value) return "never";
  const seconds = Math.round((now - Date.parse(value)) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  return formatDateTime(value, tz);
}
