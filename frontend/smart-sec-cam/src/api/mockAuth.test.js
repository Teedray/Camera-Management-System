import { fetchCameras } from "./recordingsApi";
import { mock, resetMock } from "./mockBackend";
import { fetchMe } from "./systemApi";
import { mockLogin } from "./mockAuth";

jest.mock("../config", () => ({ SERVER_URL: "https://localhost:8443", USE_MOCK: true }));
beforeEach(() => resetMock());

describe("mock sign-in", () => {
  test("only the demo accounts with the demo password get a token", () => {
    expect(mockLogin("owner", "password")).toEqual({ status: "OK", token: "mock-token:owner" });
    expect(mockLogin("owner", "wrong").status).toBe("ERROR");
    expect(mockLogin("nobody", "password").status).toBe("ERROR");
  });

  test("the token decides who you are and what you may see", async () => {
    expect((await fetchMe("mock-token:owner")).user.role).toBe("admin");
    const viewer = await fetchMe("mock-token:viewer1");
    expect(viewer.user).toMatchObject({ username: "viewer1", role: "viewer" });
    expect(viewer.cameras).toEqual(["CAM_AISLES"]);
    expect((await fetchCameras("mock-token:viewer1")).map((c) => c.name)).toEqual(["CAM_AISLES"]);
    expect((await fetchCameras("mock-token:owner")).length).toBe(4);
  });

  test("changing a role on the Admin page changes that login", async () => {
    mock.updateUser("u3", { role: "admin", cameras: [] });
    expect((await fetchMe("mock-token:viewer1")).user.role).toBe("admin");
  });
});
