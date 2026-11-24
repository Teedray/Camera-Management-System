import { ApiError, fetchCameras, searchRecordings, streamUrl } from "./recordingsApi";

jest.mock("../config", () => ({ SERVER_URL: "https://localhost:8443", USE_MOCK: false }));

function reply(status, body) {
  return Promise.resolve({ status, ok: status >= 200 && status < 300, json: () => Promise.resolve(body) });
}

beforeEach(() => { global.fetch = jest.fn(); });

describe("recordings API", () => {
  test("search sends the token and the form values as the server expects", async () => {
    fetch.mockReturnValue(reply(200, { status: "OK", segments: [], gaps: [] }));
    await searchRecordings({ camera: "CAM_A", date: "2026-11-18", start: "09:00", end: "10:00" }, "tok");
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe("https://localhost:8443/api/recordings?camera=CAM_A&date=2026-11-18&start=09%3A00&end=10%3A00");
    expect(options.headers["x-access-token"]).toBe("tok");
  });

  test("a validation error keeps the server's message and the field it belongs to", async () => {
    fetch.mockReturnValue(reply(400, { status: "ERROR", error: "The end time must be after the start time.", field: "end" }));
    await expect(searchRecordings({}, "tok")).rejects.toMatchObject({
      name: "ApiError", message: "The end time must be after the start time.", field: "end", status: 400 });
  });

  test("TS-03-06: an unauthorised camera surfaces as a 403 with the server's message", async () => {
    fetch.mockReturnValue(reply(403, { status: "ERROR", error: "You do not have access to this camera.", field: "camera" }));
    await expect(searchRecordings({}, "tok")).rejects.toMatchObject({ status: 403, field: "camera" });
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

  test("stream URLs carry the token and format in the query string", () => {
    expect(streamUrl(7, "a b", "mp4")).toBe("https://localhost:8443/api/recordings/7/stream?format=mp4&token=a%20b");
  });
});
