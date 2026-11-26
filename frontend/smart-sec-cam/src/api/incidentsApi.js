import { USE_MOCK } from "../config";
import { mediaUrl, request } from "./client";
import { mock } from "./mockBackend";

export async function createIncident(token, body) {
  if (USE_MOCK) return mock.createIncident(body);
  const response = await request("POST", "/api/v1/incidents", token, { body });
  return response.data;
}
export async function getIncident(token, id) {
  if (USE_MOCK) return mock.getIncident(id);
  const response = await request("GET", `/api/v1/incidents/${encodeURIComponent(id)}`, token);
  return response.data;
}
export async function listIncidents(token) {
  if (USE_MOCK) return mock.listIncidents();
  const response = await request("GET", "/api/v1/incidents", token);
  return response.data.items;
}
export async function deleteIncident(token, id) {
  if (USE_MOCK) return mock.deleteIncident(id);
  return request("DELETE", `/api/v1/incidents/${encodeURIComponent(id)}`, token);
}
export function incidentStreamUrl(id, token, format = "mp4") {
  if (USE_MOCK) return `${process.env.PUBLIC_URL || ""}/mock/sample.webm`;
  return mediaUrl(`/api/v1/incidents/${encodeURIComponent(id)}/video`, token);
}
