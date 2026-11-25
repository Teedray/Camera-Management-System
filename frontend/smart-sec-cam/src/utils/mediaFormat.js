// webm where the browser can play it, otherwise mp4 (recordings are saved in both).
export function videoFormat() {
  try {
    return document.createElement("video").canPlayType("video/webm") ? "webm" : "mp4";
  } catch (err) {
    return "mp4";
  }
}
