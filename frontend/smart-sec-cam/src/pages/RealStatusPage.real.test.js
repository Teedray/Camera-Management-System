import { render, screen, within } from "@testing-library/react";

import RealStatusPage from "./RealStatusPage";

// Real mode against a server that has camera status but no system/cloud/storage telemetry.
jest.mock("../config", () => ({ SERVER_URL: "https://localhost:8443", USE_MOCK: false }));
jest.mock("../hooks/useAuth", () => ({ __esModule: true, default: () => ({ token: "abc", ready: true }) }));
jest.mock("../hooks/useMe", () => ({ __esModule: true, default: () => ({ username: "owner", role: "administrator" }) }));
jest.mock("../components/Layout", () => ({ __esModule: true, default: ({ children }) => <div>{children}</div> }));

const ok = (data) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, data }) });
const missing = () => Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ error: "Not found" }) });
const cameras = [
  { id: "CAM_ENTRANCE", name: "CAM_ENTRANCE", location: "Pharmacy entrance" },
  { id: "CAM_DISPENSARY", name: "CAM_DISPENSARY", location: "Dispensary" },
];

beforeEach(() => {
  global.fetch = jest.fn((url) => {
    if (url.includes("/api/v1/cameras/status")) return ok({ items: [
      { id: "CAM_ENTRANCE", status: "connected", last_seen_utc: "2026-11-26T01:35:18+00:00" },
      { id: "CAM_DISPENSARY", status: "never_connected", last_seen_utc: null },
    ] });
    if (url.includes("/api/v1/cameras/CAM_ENTRANCE/recordings")) return ok({ segments: [
      { end: "2026-11-26T01:34:30+00:00" }, { end: "2026-11-26T01:35:00+00:00" },
    ] });
    if (url.includes("/api/v1/cameras/CAM_DISPENSARY/recordings")) return ok({ segments: [] });
    if (url.match(/\/api\/v1\/cameras(\?|$)/)) return ok({ items: cameras });
    return missing();
  });
});

describe("RealStatusPage", () => {
  test("shows connection, last frame and last recording from the camera status API", async () => {
    render(<RealStatusPage />);
    const entrance = await screen.findByLabelText("CAM_ENTRANCE");
    expect(await within(entrance).findByText("Connected")).toBeInTheDocument();
    expect(within(entrance).getByText(/Last frame: .*8:35/)).toBeInTheDocument();
    expect(within(entrance).getByText(/Last recording: .*8:35/)).toBeInTheDocument();

    const dispensary = screen.getByLabelText("CAM_DISPENSARY");
    expect(within(dispensary).getByText("Never connected")).toBeInTheDocument();
    expect(within(dispensary).getByText("Last recording: None in the last 15 minutes")).toBeInTheDocument();
    expect(screen.queryByText(/Live connectivity and recording telemetry cannot be verified/)).not.toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledWith(expect.stringMatching(/CAM_ENTRANCE\/recordings\?start=/), expect.anything());
  });

  test("still warns when the server has no camera status API", async () => {
    global.fetch = jest.fn((url) => (url.match(/\/api\/v1\/cameras(\?|$)/) ? ok({ items: cameras }) : missing()));
    render(<RealStatusPage />);
    const entrance = await screen.findByLabelText("CAM_ENTRANCE");
    expect(within(entrance).getByText("Connectivity unknown")).toBeInTheDocument();
    expect(screen.getByText(/Live connectivity and recording telemetry cannot be verified/)).toBeInTheDocument();
  });
});
