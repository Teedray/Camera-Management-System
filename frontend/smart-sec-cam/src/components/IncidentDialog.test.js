import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import IncidentDialog from "./IncidentDialog";
import { resetMock } from "../api/mockBackend";

jest.mock("../config", () => ({ SERVER_URL: "https://localhost:8443", USE_MOCK: true }));

const props = () => ({
  open: true, onClose: jest.fn(), onSaved: jest.fn(), token: "tok", camera: "CAM_ENTRANCE", tz: "America/Jamaica",
  rangeStartMs: Date.parse("2026-11-18T14:00:00Z"), rangeEndMs: Date.parse("2026-11-18T15:00:00Z"),
  posMs: Date.parse("2026-11-18T14:10:00Z"),
});
beforeEach(() => resetMock());

async function fillAndSave({ title = "Till discrepancy", flag = "Dispute or complaint" } = {}) {
  if (title) await userEvent.type(screen.getByLabelText(/^Title/), title);
  if (flag) {
    await userEvent.click(screen.getByRole("combobox", { name: /flag/i }));
    await userEvent.click(await screen.findByRole("option", { name: flag }));
  }
  await userEvent.click(screen.getByRole("button", { name: "Save clip" }));
}

describe("IncidentDialog (F04)", () => {
  test("starts at the current playback position, five minutes long", () => {
    render(<IncidentDialog {...props()} />);
    expect(screen.getByLabelText("Start time")).toHaveValue("09:10:00");
    expect(screen.getByLabelText("End time")).toHaveValue("09:15:00");
  });

  test("asks for a title and a flag before saving", async () => {
    const p = props();
    render(<IncidentDialog {...p} />);
    await userEvent.click(screen.getByRole("button", { name: "Save clip" }));
    expect(screen.getByText("Enter a title.")).toBeInTheDocument();
    expect(screen.getByText("Choose a flag.")).toBeInTheDocument();
    expect(p.onSaved).not.toHaveBeenCalled();
  });

  test("rejects an end time before the start, and times outside the searched range", async () => {
    render(<IncidentDialog {...props()} />);
    fireEvent.change(screen.getByLabelText("End time"), { target: { value: "09:00:00" } });
    await userEvent.click(screen.getByRole("button", { name: "Save clip" }));
    expect(screen.getByText("The end time must be after the start time.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("End time"), { target: { value: "11:00:00" } });
    await userEvent.click(screen.getByRole("button", { name: "Save clip" }));
    expect(screen.getByText(/Choose times between 9:00 AM and 10:00 AM/)).toBeInTheDocument();
  });

  test("SAF-02: shows 'Saved' only after the server confirms the clip", async () => {
    const p = props();
    render(<IncidentDialog {...p} />);
    await fillAndSave();
    expect(await screen.findByText(/Saved\. This clip is kept in the incident archive/)).toBeInTheDocument();
    expect(p.onSaved).toHaveBeenCalledWith(expect.objectContaining({ title: "Till discrepancy", status: "saved", flag: "dispute" }));
    expect(screen.queryByRole("button", { name: "Save clip" })).not.toBeInTheDocument();
  });

  test("a server message about something the dialog does not show still appears", async () => {
    render(<IncidentDialog {...props()} camera="" />);
    await fillAndSave();
    expect(await screen.findByText("Select a camera.")).toBeInTheDocument();
  });
});
