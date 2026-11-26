import { ApiError, request } from './client';
import { SERVER_URL, USE_MOCK } from '../config';
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
// Connection status and last-frame time of the caller's cameras (GET /api/v1/cameras/status),
// plus the end of each camera's newest catalogued segment in the last 15 minutes.
export const RECENT_RECORDING_MINUTES = 15;
export async function loadCameraHealth(token, now = Date.now()) {
  const result = await optionalFeature('GET', '/api/v1/cameras/status', token);
  if (!result.supported) return result;
  const since = new Date(now - RECENT_RECORDING_MINUTES * 60000).toISOString();
  const items = await Promise.all((result.data.items || []).map(async camera => {
    let lastRecording = null;
    try {
      const response = await request('GET', `/api/v1/cameras/${encodeURIComponent(camera.id)}/recordings`, token, { params: { start: since } });
      const ends = (response.data?.segments || []).map(segment => segment.end);
      lastRecording = ends.length ? ends.reduce((a, b) => (new Date(a) > new Date(b) ? a : b)) : null;
    } catch (error) {
      // The connection status is still worth showing without the recording time.
    }
    return { ...camera, last_recording: lastRecording };
  }));
  return { supported: true, data: { items } };
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
export async function listLegacyFiles(token, format = 'mp4') {
  if (USE_MOCK) return [];
  const response = await request('GET', '/api/video/video-list', token, { params: { 'video-format': format } });
  return Array.isArray(response.videos) ? response.videos : [];
}
export function explainUnsupported(e, label = 'This action') {
  if (absent(e)) return `${label} requires a corresponding backend endpoint; no change was saved.`;
  if (e instanceof ApiError) return e.message;
  return e?.message || 'Unexpected service error.';
}

export async function downloadOutput(token, job) {
  const response = await fetch(SERVER_URL + job.download_url, {headers:{'x-access-token':token}});
  if (!response.ok) throw new Error('Download unavailable. Refresh jobs and check camera access.');
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = job.filename.endsWith('.mp4') ? job.filename : job.filename + '.mp4';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
