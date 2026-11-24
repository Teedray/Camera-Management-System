import { USE_MOCK } from "../config";
import { ApiError, request } from "./client";
import { mock } from "./mockBackend";

// Admin-wide camera list is distinct from GET /api/v1/cameras (assigned only).
export async function listAdminCameras(token) {
  if (USE_MOCK) return mock.listAdminCameras();
  const response = await request("GET", "/api/v1/admin/cameras", token);
  return response.data.items;
}
export async function createCamera(token, body) {
  if (USE_MOCK) return mock.createCamera(body);
  const response = await request("POST", "/api/v1/cameras", token, { body });
  return response.data;
}
export async function updateCamera(token, id, body) {
  if (USE_MOCK) return mock.updateCamera(id, body);
  throw new ApiError("Editing a camera is not supported by this backend.");
}
export async function deleteCamera(token, id) {
  if (USE_MOCK) return mock.deleteCamera(id);
  throw new ApiError("Deleting a camera is not supported by this backend.");
}
export async function listUsers(token) {
  if (USE_MOCK) return mock.listUsers();
  const response = await request("GET", "/api/v1/users", token);
  return response.data.items;
}
export async function createUser(token, body) {
  if (USE_MOCK) throw new ApiError("User creation isn't available in mock mode.");
  const response = await request("POST", "/api/v1/users", token, { body });
  return response.data;
}
export async function updateUser(token, id, body) {
  if (USE_MOCK) return mock.updateUser(id, body);
  const response = await request("PATCH", `/api/v1/users/${encodeURIComponent(id)}`, token,
    { body: { role: body.role } });
  return response.data;
}
export async function listCameraAssignments(token) {
  if (USE_MOCK) throw new ApiError("Camera assignments aren't available in mock mode.");
  const response = await request("GET", "/api/v1/admin/assignments", token);
  return response.data.items;
}
export async function assignCamera(token, userId, cameraId) {
  const response = await request("PUT", `/api/v1/users/${encodeURIComponent(userId)}/cameras/${encodeURIComponent(cameraId)}`, token);
  return response.data;
}
export async function revokeCamera(token, userId, cameraId) {
  const response = await request("DELETE", `/api/v1/users/${encodeURIComponent(userId)}/cameras/${encodeURIComponent(cameraId)}`, token);
  return response.data;
}
