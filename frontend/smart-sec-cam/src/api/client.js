import { SERVER_URL } from "../config";

// An error with a message that is safe to show to the user.
// `field` names the form input a validation error belongs to (from the server).
export class ApiError extends Error {
  constructor(message, { status, field } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.field = field;
  }
}

// One place that talks to the server. Every endpoint answers JSON of the form
// { status: "OK", ... } or { status: "ERROR", error: "...", field?: "..." } (see docs/FRONTEND_API_CONTRACT.md).
export async function request(method, path, token, { params, body } = {}) {
  const entries = Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null && v !== "");
  const query = entries.length ? "?" + new URLSearchParams(entries).toString() : "";
  const headers = { "x-access-token": token };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let response;
  try {
    response = await fetch(SERVER_URL + path + query, {
      method, headers, body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (err) {
    throw new ApiError("Could not reach the server. Check the connection and try again.");
  }
  let data = null;
  try {
    data = await response.json();
  } catch (err) {
    // not JSON; handled below
  }
  if (response.status === 401) {
    if (typeof window !== "undefined") window.dispatchEvent(new Event("camera-session-expired"));
    throw new ApiError("Your session has expired. Please sign in again.", { status: 401 });
  }
  if (!response.ok || !data || data.status === "ERROR" || data.success === false) {
    throw new ApiError((data && data.error) || "The server could not complete the request.",
                       { status: response.status, field: data && data.field });
  }
  return data;
}

// <video> and download links cannot send headers, so the token goes in the query string.
export function mediaUrl(path, token, extra = {}) {
  const parts = Object.entries({ ...extra, token }).map(([k, v]) => `${k}=${encodeURIComponent(v)}`);
  return `${SERVER_URL}${path}?${parts.join("&")}`;
}
