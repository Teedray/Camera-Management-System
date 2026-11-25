import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CookiesProvider } from "react-cookie";

import SearchPage from "./SearchPage";
import { todayInTz } from "../utils/time";

// Mock mode: no server, no login, generated recordings.
jest.mock("../config", () => ({ SERVER_URL: "https://localhost:8443", USE_MOCK: true }));

// react-router-dom 7 can only be loaded through its package "exports" map, which the Jest
// bundled with Create React App 5 does not read. A stand-in for the two hooks the page uses is enough.
jest.mock("react-router-dom", () => ({
  useNavigate: () => jest.fn(),
  useLocation: () => ({ pathname: "/search" }),
}), { virtual: true });

beforeAll(() => {
  window.HTMLMediaElement.prototype.load = jest.fn();
  window.HTMLMediaElement.prototype.pause = jest.fn();
  window.HTMLMediaElement.prototype.play = jest.fn(() => Promise.resolve());
});

const daysAgo = (n) => todayInTz(undefined, new Date(Date.now() - n * 86400000));

function renderPage() {
  return render(
    <CookiesProvider>
      <SearchPage />
    </CookiesProvider>
  );
}

// The nav bar also has a "Search" link, so look for the submit button inside the form.
const submit = () => within(screen.getByRole("form", { name: "Search recordings" })).getByRole("button", { name: /search/i });

async function search({ camera = "CAM_ENTRANCE", date, start = "01:00", end = "03:00" }) {
  if (camera) {
    await userEvent.click(await screen.findByRole("combobox"));
    await userEvent.click(await screen.findByRole("option", { name: camera }));
  }
  fireEvent.change(screen.getByLabelText("Date"), { target: { value: date } });
  fireEvent.change(screen.getByLabelText("Start time"), { target: { value: start } });
  fireEvent.change(screen.getByLabelText("End time"), { target: { value: end } });
  await userEvent.click(submit());
}

describe("SearchPage", () => {
  test("starts with an invitation to search and the player waiting", async () => {
    renderPage();
    expect(await screen.findByText(/Choose a camera, a date and a time range/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Play" })).toBeDisabled();
  });

  test("TS-03-01 / TS-03-05: a search lists the footage and marks the missing period", async () => {
    renderPage();
    await search({ date: daysAgo(1) });
    const results = await screen.findByRole("list", { name: "Search results" });
    expect(within(results).getByText("Missing")).toBeInTheDocument();
    expect(screen.getAllByText(/continuous/).length).toBeGreaterThanOrEqual(2);   // footage before and after the outage
    expect(screen.getByTestId("timeline-missing")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Play" })).toBeEnabled();
  });

  test("TS-03-07: a day past the retention period reports expired footage", async () => {
    renderPage();
    await search({ date: daysAgo(60) });
    expect(await screen.findByText("No footage found")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/30-day retention/);
  });

  test("TS-03-02: an end time before the start time is stopped before any search", async () => {
    renderPage();
    await search({ date: daysAgo(1), start: "10:00", end: "09:00" });
    expect(await screen.findByText("The end time must be after the start time.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Search results" })).not.toBeInTheDocument();
  });

  test("a new search replaces the previous results", async () => {
    renderPage();
    await search({ date: daysAgo(1) });
    await screen.findByRole("list", { name: "Search results" });
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: daysAgo(60) } });
    await userEvent.click(submit());
    await waitFor(() => expect(screen.queryByRole("list", { name: "Search results" })).not.toBeInTheDocument());
    expect(screen.getByText("No footage found")).toBeInTheDocument();
  });

  test("F04/F05: the save and export buttons wait for a search, then open their dialogs", async () => {
    renderPage();
    expect(await screen.findByRole("button", { name: /save as incident/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /trim and download/i })).toBeDisabled();
    await search({ date: daysAgo(1) });
    await screen.findByRole("list", { name: "Search results" });
    await userEvent.click(screen.getByRole("button", { name: /save as incident/i }));
    expect(await screen.findByRole("dialog", { name: "Save incident clip" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /trim and download/i }));
    expect(await screen.findByRole("dialog", { name: "Trim and download" })).toBeInTheDocument();
  });
});
