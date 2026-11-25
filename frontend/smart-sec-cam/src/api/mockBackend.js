// An in-memory stand-in for the server, used when REACT_APP_USE_MOCK=1 and in tests.
// It follows docs/FRONTEND_API_CONTRACT.md, including the "in progress" states, so the screens can be
// built and checked before the real endpoints exist.
import { ROLES, FLAGS } from "../utils/flags";
import { ApiError } from "./client";

const HOUR = 3600 * 1000;
const iso = (ms) => new Date(ms).toISOString();
const strip = ({ polls, ...rest }) => ({ ...rest });
const fail = (message, field, status = 400) => new ApiError(message, { status, field });
const CAMERA_NAME = /^[A-Za-z0-9_-]{2,40}$/;

let state;

export function resetMock(now = Date.now()) {
  const day = (hoursAgo, minutes = 4) => ({ start: iso(now - hoursAgo * HOUR), end: iso(now - hoursAgo * HOUR + minutes * 60000), duration: minutes * 60 });
  state = {
    nextId: 100,
    incidents: [
      { id: 2, title: "Shelf stock taken", description: "Two boxes removed from aisle 3.", flag: "theft", camera: "CAM_AISLES",
        ...day(30, 3), status: "saved", error: null, created_at: iso(now - 29 * HOUR), created_by: "manager1", backed_up: false },
      { id: 1, title: "Till discrepancy", description: "Cash count did not match the receipts.", flag: "dispute", camera: "CAM_CASHIER",
        ...day(52, 6), status: "saved", error: null, created_at: iso(now - 50 * HOUR), created_by: "owner", backed_up: true },
    ],
    exports: [
      { id: 1, camera: "CAM_ENTRANCE", ...day(5, 10), status: "ready", error: null, filename: "CAM_ENTRANCE_clip.mp4",
        size_bytes: 14200000, created_at: iso(now - 4 * HOUR), expires_at: iso(now + 20 * HOUR), polls: 9 },
    ],
    cameras: [
      { id: 1, name: "CAM_ENTRANCE", address: "http://192.168.1.21:8080/video", type: "ip", enabled: true, connection: "connected" },
      { id: 2, name: "CAM_CASHIER", address: "http://192.168.1.22:8080/video", type: "ip", enabled: true, connection: "connected" },
      { id: 3, name: "CAM_AISLES", address: "0", type: "usb", enabled: true, connection: "connected" },
      { id: 4, name: "CAM_DISPENSARY", address: "http://192.168.1.24:8080/video", type: "ip", enabled: true, connection: "disconnected" },
    ],
    users: [
      { id: "u1", username: "owner", role: "admin", cameras: [] },
      { id: "u2", username: "manager1", role: "manager", cameras: ["CAM_ENTRANCE", "CAM_CASHIER"] },
      { id: "u3", username: "viewer1", role: "viewer", cameras: ["CAM_AISLES"] },
    ],
  };
}
resetMock();

function checkInterval(body) {
  if (!body.camera) throw fail("Select a camera.", "camera");
  const start = Date.parse(body.start);
  const end = Date.parse(body.end);
  if (Number.isNaN(start)) throw fail("Enter the start time.", "start");
  if (Number.isNaN(end)) throw fail("Enter the end time.", "end");
  if (end <= start) throw fail("The end time must be after the start time.", "end");
  return { start, end };
}

// Each time an export is looked at it moves one step along, like time passing on a real server.
function advanceExport(exp) {
  exp.polls += 1;
  if (exp.status === "queued" && exp.polls >= 1) exp.status = "processing";
  else if (exp.status === "processing" && exp.polls >= 2) {
    if (exp.camera === "CAM_DISPENSARY") {
      exp.status = "failed";
      exp.error = "The source recordings could not be read.";
    } else {
      exp.status = "ready";
      exp.size_bytes = 12600000;
    }
  }
  return exp;
}

export const mock = {
  // The token made by mockLogin is "mock-token:<username>"; anything else counts as the owner.
  me(token = "") {
    const name = String(token).startsWith("mock-token:") ? String(token).slice(11) : "owner";
    const user = state.users.find((u) => u.username === name) || state.users[0];
    return {
      user: { id: user.id, username: user.username, role: user.role },
      cameras: user.role === "admin" ? state.cameras.map((c) => c.name) : [...user.cameras],
    };
  },

  // ---- incidents (F04)
  listIncidents: () => state.incidents.map(strip),
  createIncident(body) {
    const { start, end } = checkInterval(body);
    if (!(body.title || "").trim()) throw fail("Enter a title.", "title");
    if (!FLAGS.some((f) => f.value === body.flag)) throw fail("Choose a flag.", "flag");
    const incident = {
      id: state.nextId++, title: body.title.trim(), description: body.description || "", flag: body.flag, camera: body.camera,
      start: iso(start), end: iso(end), duration: (end - start) / 1000, status: "saving", error: null,
      created_at: iso(Date.now()), created_by: "owner", backed_up: false, polls: 0,
    };
    state.incidents.unshift(incident);
    return strip(incident);
  },
  getIncident(id) {
    const incident = state.incidents.find((i) => i.id === Number(id));
    if (!incident) throw fail("Incident not found.", undefined, 404);
    incident.polls += 1;
    if (incident.status === "saving" && incident.polls >= 1) incident.status = "saved";
    return strip(incident);
  },
  deleteIncident(id) {
    const before = state.incidents.length;
    state.incidents = state.incidents.filter((i) => i.id !== Number(id));
    if (state.incidents.length === before) throw fail("Incident not found.", undefined, 404);
  },

  // ---- exports (F05)
  listExports: () => state.exports.map((e) => strip(advanceExport(e))),
  createExport(body) {
    const { start, end } = checkInterval(body);
    if (end - start > HOUR) throw fail("Exports are limited to 60 minutes. Choose a shorter range.", "end");
    const exp = {
      id: state.nextId++, camera: body.camera, start: iso(start), end: iso(end), status: "queued", error: null,
      filename: `${body.camera}_${iso(start).slice(0, 19).replace(/[:T]/g, "-")}.mp4`, size_bytes: null,
      created_at: iso(Date.now()), expires_at: iso(Date.now() + 24 * HOUR), polls: 0,
    };
    state.exports.unshift(exp);
    return strip(exp);
  },
  getExport(id) {
    const exp = state.exports.find((e) => e.id === Number(id));
    if (!exp) throw fail("Export not found.", undefined, 404);
    return strip(advanceExport(exp));
  },

  // ---- system status
  systemStatus() {
    const now = Date.now();
    const total = 2e12;
    const used = 1.72e12;
    return {
      checked_at: iso(now),
      cameras: state.cameras.map((c) => ({
        name: c.name, connection: c.connection, recording: c.connection === "connected",
        last_frame: c.connection === "connected" ? iso(now - 2000) : iso(now - 95 * 60000),
        last_recording: c.connection === "connected" ? iso(now - 30000) : iso(now - 95 * 60000),
        gaps_today: c.connection === "connected" ? 0 : 3,
      })),
      storage: { total_bytes: total, used_bytes: used, retention_days: 30, threshold_percent: 85, low: used / total >= 0.85 },
      cloud: { connected: true, pending_uploads: 4, last_upload: iso(now - 20000), last_error: null },
      backup: { last_success: iso(now - 6 * HOUR), last_error: null },
      warnings: [
        { level: "error", code: "CAMERA_DISCONNECTED", message: "CAM_DISPENSARY has been disconnected for 95 minutes.", since: iso(now - 95 * 60000) },
        { level: "warning", code: "LOW_STORAGE", message: "Storage is 86% full. Free up disk space or reduce video quality.", since: iso(now - 2 * HOUR) },
      ],
    };
  },

  // ---- administration
  listAdminCameras: () => state.cameras.map((c) => ({ ...c })),
  createCamera(body) {
    const name = (body.name || "").trim();
    if (!CAMERA_NAME.test(name)) throw fail("Use 2 to 40 letters, numbers, underscores or hyphens.", "name");
    if (state.cameras.some((c) => c.name === name)) throw fail("A camera with this name already exists.", "name");
    if (!(body.address || "").trim()) throw fail("Enter the camera address.", "address");
    const camera = { id: state.nextId++, name, address: body.address.trim(), type: body.type || "ip", enabled: body.enabled !== false, connection: "disconnected" };
    state.cameras.push(camera);
    return { ...camera };
  },
  updateCamera(id, body) {
    const camera = state.cameras.find((c) => c.id === Number(id));
    if (!camera) throw fail("Camera not found.", undefined, 404);
    const name = (body.name ?? camera.name).trim();
    if (!CAMERA_NAME.test(name)) throw fail("Use 2 to 40 letters, numbers, underscores or hyphens.", "name");
    if (state.cameras.some((c) => c.name === name && c.id !== camera.id)) throw fail("A camera with this name already exists.", "name");
    if (!(body.address ?? camera.address).trim()) throw fail("Enter the camera address.", "address");
    Object.assign(camera, { name, address: (body.address ?? camera.address).trim(), type: body.type ?? camera.type, enabled: body.enabled ?? camera.enabled });
    return { ...camera };
  },
  deleteCamera(id) {
    state.cameras = state.cameras.filter((c) => c.id !== Number(id));
  },
  listUsers: () => state.users.map((u) => ({ ...u, cameras: [...u.cameras] })),
  updateUser(id, body) {
    const user = state.users.find((u) => u.id === id);
    if (!user) throw fail("User not found.", undefined, 404);
    if (!ROLES.includes(body.role)) throw fail("Choose a role.", "role");
    user.role = body.role;
    user.cameras = body.role === "admin" ? [] : [...(body.cameras || [])];
    return { ...user, cameras: [...user.cameras] };
  },
};
