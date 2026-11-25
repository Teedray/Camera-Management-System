import { USE_MOCK } from "../config";
import { request } from "./client";
import { loadOverview } from "./managementApi";
import { mock } from "./mockBackend";

// { user: { id, username, role }, cameras: [names this user may see] }
export async function fetchMe(token) {
  if (USE_MOCK) return mock.me(token);
  const response = await request("GET", "/api/v1/auth/me", token);
  return { user: response.data, cameras: response.data.cameras || [] };
}

// Health of cameras, storage, cloud upload and backup, plus a list of warnings to show management.
export async function fetchSystemStatus(token) {
  if (USE_MOCK) return mock.systemStatus();
  const result = await loadOverview(token);
  return result.supported ? result.data : {warnings:[], supported:false};
}
