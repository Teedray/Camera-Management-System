import { USE_MOCK } from "../config";
import { ApiError } from "./client";

export const POLL_INTERVAL_MS = USE_MOCK ? 30 : 1500;

// Ask again until the answer says it is finished (used for saving an incident and for exports).
// Returns null if isCancelled() becomes true, for example because the dialog was closed.
export async function pollUntil(fetchOnce, isDone, { isCancelled = () => false, maxTries = 120, interval = POLL_INTERVAL_MS } = {}) {
  for (let i = 0; i < maxTries; i += 1) {
    if (isCancelled()) return null;
    const value = await fetchOnce();
    if (isDone(value)) return value;
    await new Promise((resolve) => setTimeout(resolve, interval));
  }
  throw new ApiError("This is taking longer than expected. Check back in a few minutes.");
}
