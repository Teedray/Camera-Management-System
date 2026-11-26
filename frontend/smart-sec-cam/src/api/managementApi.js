import { ApiError, request } from './client';
import { USE_MOCK } from '../config';
import { mock } from './mockBackend';

// Optional feature contract. The frontend never invents success when the server
// does not implement a feature. See FRONTEND-BACKEND-CONTRACT.md in the patch.
function absent(error) {
  return [404, 405, 501].includes(error?.status);
}
export async function optionalFeature(method, path, token, options) {
  if (USE_MOCK) return { supported: false, data: null, reason: 'Demo mode has no persistent management service.' };
  try {
    const response = await request(method, path, token, options);
    return { supported: true, data: response.data ?? response };
  } catch (error) {
    if (absent(error)) return { supported: false, data: null, reason: 'This backend endpoint is not installed.' };
    throw error;
  }
}
export async function loadOverview(token) {
  if (USE_MOCK) {
    const s = mock.systemStatus();
    return { supported: true, data: s };
  }
  return optionalFeature('GET', '/api/v1/system/status', token);
}
export const loadCloud = token => optionalFeature('GET', '/api/v1/cloud/status', token);
export const connectCloud = (token, body) => request('POST', '/api/v1/cloud/connect', token, { body });
export const disconnectCloud = token => request('DELETE', '/api/v1/cloud/connection', token);
export const retryCloudUpload = (token, jobId) => request('POST', `/api/v1/cloud/jobs/${encodeURIComponent(jobId)}/retry`, token);
export const loadStorage = token => optionalFeature('GET', '/api/v1/storage', token);
export const saveRetention = (token, body) => request('PATCH', '/api/v1/storage/retention', token, { body });
export const loadAudit = (token, params) => optionalFeature('GET', '/api/v1/audit', token, { params });
export const loadMerges = token => optionalFeature('GET', '/api/v1/merges', token);
export const createMerge = (token, body) => request('POST', '/api/v1/merges', token, { body });
export const loadExportJobs = token => optionalFeature('GET', '/api/v1/exports', token);
export const extendIncident = (token, id, body) => request('POST', `/api/v1/incidents/${encodeURIComponent(id)}/preservation`, token, { body });
export const patchCamera = (token, id, body) => request('PATCH', `/api/v1/cameras/${encodeURIComponent(id)}`, token, { body });
export async function listLegacyFiles(token, format = 'webm') {
  if (USE_MOCK) return [];
  const response = await request('GET', '/api/video/video-list', token, { params: { 'video-format': format } });
  return Array.isArray(response.videos) ? response.videos : [];
}
export function explainUnsupported(e, label = 'This action') {
  if (absent(e)) return `${label} requires a corresponding backend endpoint; no change was saved.`;
  if (e instanceof ApiError) return e.message;
  return e?.message || 'Unexpected service error.';
}
