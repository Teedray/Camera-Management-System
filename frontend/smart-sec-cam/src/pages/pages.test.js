import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CookiesProvider } from "react-cookie";

import AdminPage from "./AdminPage";
import ExportsPage from "./ExportsPage";
import IncidentsPage from "./IncidentsPage";
import StatusPage from "./StatusPage";
import { mock, resetMock } from "../api/mockBackend";
import useMe from "../hooks/useMe";

jest.mock("../config", () => ({ SERVER_URL: "https://localhost:8443", USE_MOCK: true }));
const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
  useLocation: () => ({ pathname: "/page" }),
}), { virtual: true });
jest.mock("../hooks/useMe", () => ({ __esModule: true, default: jest.fn() }));

const show = (page) => render(<CookiesProvider>{page}</CookiesProvider>);
beforeEach(() => {
  resetMock();
  mockNavigate.mockClear();
  useMe.mockReturnValue({ id: "u1", username: "owner", role: "admin" });
});

describe("IncidentsPage (F04)", () => {
  test("lists saved incidents with flag, camera, status and cloud backup state", async () => {
    show(<IncidentsPage />);
    const till = await screen.findByRole("article", { name: "Till discrepancy" });
    expect(till).toHaveTextContent("Dispute or complaint");
    expect(till).toHaveTextContent("CAM_CASHIER");
    expect(till).toHaveTextContent("Saved");
    expect(till).toHaveTextContent("Backed up to cloud");
    expect(screen.getByRole("article", { name: "Shelf stock taken" })).toHaveTextContent("Cloud backup pending");
  });

  test("filtering by flag hides the others, and says so when nothing matches", async () => {
    show(<IncidentsPage />);
    await screen.findByRole("article", { name: "Till discrepancy" });
    await userEvent.click(screen.getByRole("combobox", { name: /flag/i }));
    await userEvent.click(await screen.findByRole("option", { name: "Theft" }));
    expect(screen.queryByRole("article", { name: "Till discrepancy" })).not.toBeInTheDocument();
    expect(screen.getByRole("article", { name: "Shelf stock taken" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("combobox", { name: /flag/i }));
    await userEvent.click(await screen.findByRole("option", { name: "Safety incident" }));
    expect(screen.getByText("No incident clips found")).toBeInTheDocument();
  });

  test("an administrator can delete a clip after confirming", async () => {
    show(<IncidentsPage />);
    const till = await screen.findByRole("article", { name: "Till discrepancy" });
    await userEvent.click(within(till).getByRole("button", { name: "Delete" }));
    await userEvent.click(await screen.findByRole("button", { name: "Delete clip" }));
    await screen.findByRole("article", { name: "Shelf stock taken" });
    expect(screen.queryByRole("article", { name: "Till discrepancy" })).not.toBeInTheDocument();
  });

  test("other roles can play but not delete", async () => {
    useMe.mockReturnValue({ id: "u3", username: "viewer1", role: "viewer" });
    show(<IncidentsPage />);
    const till = await screen.findByRole("article", { name: "Till discrepancy" });
    expect(within(till).queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
    await userEvent.click(within(till).getByRole("button", { name: "Play" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });
});

describe("ExportsPage (F05)", () => {
  test("shows a ready export with its size, expiry and a download link", async () => {
    show(<ExportsPage />);
    const item = await screen.findByRole("article", { name: "Export 1" });
    expect(item).toHaveTextContent("Ready");
    expect(item).toHaveTextContent("14.2 MB");
    expect(item).toHaveTextContent("available until");
    expect(within(item).getByRole("link", { name: "Download MP4" })).toHaveAttribute("download");
  });

  test("a queued export refreshes itself until it is ready", async () => {
    const queued = mock.createExport({ camera: "CAM_ENTRANCE", start: "2026-11-18T14:00:00Z", end: "2026-11-18T14:05:00Z" });
    show(<ExportsPage />);
    const item = await screen.findByRole("article", { name: `Export ${queued.id}` });
    expect(item).toHaveTextContent(/Processing|Queued/);
    expect(await within(await screen.findByRole("article", { name: `Export ${queued.id}` })).findByRole("link", { name: "Download MP4" }, { timeout: 3000 })).toBeInTheDocument();
  });

  test("a failed export shows why and no download", async () => {
    const failing = mock.createExport({ camera: "CAM_DISPENSARY", start: "2026-11-18T14:00:00Z", end: "2026-11-18T14:05:00Z" });
    show(<ExportsPage />);
    const item = await screen.findByRole("article", { name: `Export ${failing.id}` });
    expect(await within(item).findByText("The source recordings could not be read.", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(within(item).queryByRole("link", { name: "Download MP4" })).not.toBeInTheDocument();
  });
});

describe("StatusPage", () => {
  test("shows camera health, storage, cloud and backup, with the warnings first", async () => {
    show(<StatusPage />);
    // (the warning banner repeats these on other pages, so allow more than one match)
    expect((await screen.findAllByText(/CAM_DISPENSARY has been disconnected/)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Storage is 86% full/).length).toBeGreaterThan(0);
    expect(within(screen.getByLabelText("CAM_DISPENSARY")).getByText("Disconnected")).toBeInTheDocument();
    expect(within(screen.getByLabelText("CAM_ENTRANCE")).getByText("Connected")).toBeInTheDocument();
    expect(screen.getByText(/1\.7 TB of 2\.0 TB used \(86%\)/)).toBeInTheDocument();
    expect(screen.getByText(/Waiting to upload: 4 clips/)).toBeInTheDocument();
    expect(screen.getByText(/Last successful backup: 6 h ago/)).toBeInTheDocument();
  });
});

// Long click-through flows over MUI dialogs and chips: give them room on slow CI machines.
const ADMIN_FLOW_TIMEOUT = 20000;

describe("AdminPage", () => {
  test("is closed to anyone who is not an administrator", async () => {
    useMe.mockReturnValue({ id: "u3", username: "viewer1", role: "viewer" });
    show(<AdminPage />);
    expect(await screen.findByText("Only administrators can open this page.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add camera" })).not.toBeInTheDocument();
  });

  test("lists cameras, and validates a new one before sending it", async () => {
    show(<AdminPage />);
    expect(await screen.findByRole("article", { name: "CAM_ENTRANCE" })).toHaveTextContent("Connected");
    await userEvent.click(screen.getByRole("button", { name: "Add camera" }));
    await userEvent.type(screen.getByLabelText(/^Name/), "x");
    await userEvent.click(screen.getByRole("button", { name: "Save camera" }));
    expect(screen.getByText("Use 2 to 40 letters, numbers, underscores or hyphens.")).toBeInTheDocument();
    expect(screen.getByText("Enter the camera address.")).toBeInTheDocument();
  });

  test("adds a camera, and the server's 'already exists' answer appears on the name", async () => {
    show(<AdminPage />);
    await screen.findByRole("article", { name: "CAM_ENTRANCE" });
    await userEvent.click(screen.getByRole("button", { name: "Add camera" }));
    await userEvent.type(screen.getByLabelText(/^Name/), "CAM_ENTRANCE");
    await userEvent.type(screen.getByLabelText(/^Stream address/), "http://192.168.1.30:8080/video");
    await userEvent.click(screen.getByRole("button", { name: "Save camera" }));
    expect(await screen.findByText("A camera with this name already exists.")).toBeInTheDocument();

    await userEvent.clear(screen.getByLabelText(/^Name/));
    await userEvent.type(screen.getByLabelText(/^Name/), "CAM_STOREROOM");
    await userEvent.click(screen.getByRole("button", { name: "Save camera" }));
    expect(await screen.findByRole("article", { name: "CAM_STOREROOM" })).toBeInTheDocument();
  }, ADMIN_FLOW_TIMEOUT);

  test("changes which cameras a user can see", async () => {
    show(<AdminPage />);
    await screen.findByRole("article", { name: "CAM_ENTRANCE" });
    await userEvent.click(screen.getByRole("tab", { name: "Users" }));
    const row = await screen.findByRole("article", { name: "viewer1" });
    expect(within(row).getByRole("button", { name: "Save changes" })).toBeDisabled();
    await userEvent.click(within(row).getByRole("button", { name: "CAM_CASHIER" }));
    await userEvent.click(within(row).getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Saved viewer1.")).toBeInTheDocument();
    expect(mock.listUsers().find((u) => u.username === "viewer1").cameras).toEqual(["CAM_AISLES", "CAM_CASHIER"]);

    // After the reload both cameras are still selected; removing one keeps the other.
    const reloaded = await screen.findByRole("article", { name: "viewer1" });
    expect(within(reloaded).getByRole("button", { name: "CAM_CASHIER" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(within(reloaded).getByRole("button", { name: "CAM_AISLES" }));
    await userEvent.click(within(reloaded).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(mock.listUsers().find((u) => u.username === "viewer1").cameras).toEqual(["CAM_CASHIER"]));
  }, ADMIN_FLOW_TIMEOUT);

  test("a failed save shows the error, not success", async () => {
    const spy = jest.spyOn(mock, "updateUser").mockImplementation(() => { throw new Error("Server unavailable"); });
    try {
      show(<AdminPage />);
      await screen.findByRole("article", { name: "CAM_ENTRANCE" });
      await userEvent.click(screen.getByRole("tab", { name: "Users" }));
      const row = await screen.findByRole("article", { name: "viewer1" });
      await userEvent.click(within(row).getByRole("button", { name: "CAM_CASHIER" }));
      await userEvent.click(within(row).getByRole("button", { name: "Save changes" }));
      expect(await screen.findByText("Server unavailable")).toBeInTheDocument();
      expect(screen.queryByText("Saved viewer1.")).not.toBeInTheDocument();
      expect(mock.listUsers().find((u) => u.username === "viewer1").cameras).not.toContain("CAM_CASHIER");
    } finally {
      spy.mockRestore();
    }
  }, ADMIN_FLOW_TIMEOUT);
});

describe("signed-out visitors", () => {
  test("every page sends them to the login page and shows nothing", async () => {
    document.cookie = "token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
    show(<IncidentsPage />);
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/"));
    expect(screen.queryByRole("heading", { name: "Incident clips" })).not.toBeInTheDocument();
  });
});
