import { SERVER_URL, USE_MOCK } from "../config";
import { ApiError, mediaUrl } from "./client";
import { mock } from "./mockBackend";

// The real backend streams a completed MP4 in a single POST; there is no export queue/history.
export async function downloadClip(token, body) {
  if (USE_MOCK) throw new ApiError("Direct download is only available with the real backend.");
  let response;
  try {
    response = await fetch(`${SERVER_URL}/api/v1/exports`, {
      method: "POST",
      headers: { "x-access-token": token, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    throw new ApiError("Could not reach the export service.");
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(data.error || "Export failed.", { status: response.status });
  }
  return response.blob();
}
// Demo support is preserved; real clients use downloadClip() directly.
export async function createExport(token, body) {
  if (USE_MOCK) return mock.createExport(body);
  throw new ApiError("Use direct MP4 downloads with the real backend.");
}
export async function getExport(token, id) {
  if (USE_MOCK) return mock.getExport(id);
  throw new ApiError("The backend does not have an export queue.");
}
export async function listExports(token) {
  if (USE_MOCK) return mock.listExports();
  throw new ApiError("The backend does not store an export history.");
}
export function exportDownloadUrl(id, token) {
  if (USE_MOCK) return `${process.env.PUBLIC_URL || ""}/mock/sample.webm`;
  return mediaUrl(`/api/v1/exports/${encodeURIComponent(id)}/download`, token);
}
