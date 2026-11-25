import { SERVER_URL, USE_MOCK } from "../config";
import { ApiError, request } from "./client";
import { mock } from "./mockBackend";
import { MOCK_CAMERAS, mockSearch } from "./mockRecordings";

export { ApiError };
export async function fetchCameras(token) {
  if (USE_MOCK) {
    const allowed = mock.me(token).cameras;
    return MOCK_CAMERAS.filter((c) => allowed.includes(c.name));
  }
  const response = await request("GET", "/api/v1/cameras", token);
  return response.data.items;
}
export async function listRecordings(token) {
  if (USE_MOCK) return [];
  const response = await request("GET", "/api/v1/recordings", token);
  return response.data.items;
}
// Retains existing demo-only search behavior. Real search uses timestamped catalogue items.
export async function searchRecordings(params, token) {
  if (USE_MOCK) return mockSearch(params);
  throw new ApiError("Use the catalogue-based recording search for real footage.");
}
export function streamUrl(filename, token, format = "webm") {
  if (USE_MOCK) return `${process.env.PUBLIC_URL || ""}/mock/sample.webm`;
  return `${SERVER_URL}/api/video/${encodeURIComponent(filename)}?token=${encodeURIComponent(token)}`;
}
