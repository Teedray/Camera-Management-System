import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ExportDialog from "./ExportDialog";
import { resetMock } from "../api/mockBackend";

jest.mock("../config", () => ({ SERVER_URL: "https://localhost:8443", USE_MOCK: true }));

const props = (extra = {}) => ({
  open: true, onClose: jest.fn(), token: "tok", camera: "CAM_ENTRANCE", tz: "America/Jamaica",
  rangeStartMs: Date.parse("2026-11-18T14:00:00Z"), rangeEndMs: Date.parse("2026-11-18T16:00:00Z"),
  posMs: Date.parse("2026-11-18T14:10:00Z"), ...extra,
});
beforeEach(() => resetMock());

describe("ExportDialog (F05)", () => {
  test("SR-05-02: goes queued -> processing -> ready and offers the download", async () => {
    render(<ExportDialog {...props()} />);
    await userEvent.click(screen.getByRole("button", { name: "Start export" }));
    expect(await screen.findByText("Your video is ready. It stays available for 24 hours.")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "Download MP4" });
    expect(link).toHaveAttribute("href", expect.stringContaining("mock/sample.webm"));
    expect(link).toHaveAttribute("download");
  });

  test("a failed export says so and offers no download", async () => {
    render(<ExportDialog {...props({ camera: "CAM_DISPENSARY" })} />);
    await userEvent.click(screen.getByRole("button", { name: "Start export" }));
    expect(await screen.findByText("The source recordings could not be read.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Download MP4" })).not.toBeInTheDocument();
  });

  test("SR-05-01: reversed and zero-length selections are rejected before anything starts", async () => {
    render(<ExportDialog {...props()} />);
    fireEvent.change(screen.getByLabelText("End time"), { target: { value: "09:10:00" } });
    await userEvent.click(screen.getByRole("button", { name: "Start export" }));
    expect(screen.getByText("The end time must be after the start time.")).toBeInTheDocument();
    expect(screen.queryByText(/Export status/)).not.toBeInTheDocument();
  });

  test("a server limit is shown against the end time", async () => {
    render(<ExportDialog {...props()} />);
    fireEvent.change(screen.getByLabelText("Start time"), { target: { value: "09:00:00" } });
    fireEvent.change(screen.getByLabelText("End time"), { target: { value: "11:00:00" } });
    await userEvent.click(screen.getByRole("button", { name: "Start export" }));
    expect(await screen.findByText(/limited to 60 minutes/)).toBeInTheDocument();
  });
});
