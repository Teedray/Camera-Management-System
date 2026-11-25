import { ApiError, fetchCameras, listRecordings, searchRecordings, streamUrl } from "./recordingsApi";

jest.mock("../config", () => ({ SERVER_URL: "https://localhost:8443", USE_MOCK: false }));

function reply(status, body) {
  return Promise.resolve({ status, ok: status >= 200 && status < 300, json: () => Promise.resolve(body) });
}

beforeEach(() => { global.fetch = jest.fn(); });

// Real mode: the search page loads the caller's catalogue from GET /api/v1/recordings
// (the server returns only cameras assigned to that user) and filters it by camera
// and time in the page; videos play from /api/video/<encoded filename>.
describe("recordings API", () => {
  const item = {
    filename: "CAM_FRONT_DESK__2026-11-25_03:48:00-4a5f5c38ee844324854c28f3da2d87f1.mp4",
    camera_id: "CAM_FRONT_DESK", start: "2026-11-25T03:48:00+00:00", end: "2026-11-25T03:48:30+00:00",
    duration_seconds: 30, format: "mp4",
  };

  test("the catalogue is fetched with the login token and returned as items", async () => {
    fetch.mockReturnValue(reply(200, { success: true, data: { items: [item] } }));
    await expect(listRecordings("tok")).resolves.toEqual([item]);
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe("https://localhost:8443/api/v1/recordings");
    expect(options.method).toBe("GET");
    expect(options.headers["x-access-token"]).toBe("tok");
  });

  test("a server error keeps the server's message, status and field", async () => {
    fetch.mockReturnValue(reply(400, { success: false, error: "start must be before end", field: "end" }));
    await expect(listRecordings("tok")).rejects.toMatchObject({
      name: "ApiError", message: "start must be before end", field: "end", status: 400 });
  });

  test("TS-03-06: an unauthorised request surfaces as a 403 with the server's message", async () => {
    fetch.mockReturnValue(reply(403, { success: false, error: "Manager or administrator role required" }));
    await expect(listRecordings("tok")).rejects.toMatchObject({
      status: 403, message: "Manager or administrator role required" });
  });

  test("real mode does not fall back to the demo search", async () => {
    await expect(searchRecordings({ camera: "CAM_A" }, "tok")).rejects.toBeInstanceOf(ApiError);
    expect(fetch).not.toHaveBeenCalled();
  });

  test("an expired login asks the user to sign in again", async () => {
    fetch.mockReturnValue(reply(401, { status: "ERROR", error: "Invalid token" }));
    await expect(fetchCameras("old")).rejects.toMatchObject({ status: 401, message: expect.stringMatching(/sign in again/i) });
  });

  test("a network failure gives a friendly message, not a stack trace", async () => {
    fetch.mockRejectedValue(new TypeError("Failed to fetch"));
    const error = await fetchCameras("tok").catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.message).toMatch(/could not reach the server/i);
  });

  test("a non-JSON server error is still handled", async () => {
    fetch.mockReturnValue(Promise.resolve({ status: 500, ok: false, json: () => Promise.reject(new Error("bad json")) }));
    await expect(fetchCameras("tok")).rejects.toMatchObject({ status: 500 });
  });

  test("video URLs encode the recording filename and carry the token", () => {
    expect(streamUrl(item.filename, "a b")).toBe(
      "https://localhost:8443/api/video/CAM_FRONT_DESK__2026-11-25_03%3A48%3A00-4a5f5c38ee844324854c28f3da2d87f1.mp4?token=a%20b");
  });
});
