import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import SearchForm, { validateSearch } from "./SearchForm";

const cameras = [{ name: "CAM_ENTRANCE" }, { name: "CAM_CASHIER" }];
const initial = { camera: "CAM_ENTRANCE", date: "2026-11-18", start: "09:00", end: "10:00" };

describe("validateSearch", () => {
  test("accepts a valid search", () => {
    expect(validateSearch(initial)).toEqual({});
  });

  test.each([
    [{ camera: "" }, "camera", "Select a camera."],
    [{ date: "" }, "date", "Choose a date."],
    [{ start: "" }, "start", "Enter the start time."],
    [{ end: "" }, "end", "Enter the end time."],
    [{ start: "10:00", end: "09:00" }, "end", "The end time must be after the start time."],
    [{ start: "09:00", end: "09:00" }, "end", "The end time must be after the start time."],
  ])("rejects %j", (change, field, message) => {
    expect(validateSearch({ ...initial, ...change })[field]).toBe(message);
  });
});

describe("SearchForm", () => {
  test("TS-03-02: an end time before the start time shows an error and sends nothing", async () => {
    const onSearch = jest.fn();
    render(<SearchForm cameras={cameras} onSearch={onSearch} initialValues={{ ...initial, start: "10:00", end: "09:00" }} />);
    await userEvent.click(screen.getByRole("button", { name: /search/i }));
    expect(screen.getByText("The end time must be after the start time.")).toBeInTheDocument();
    expect(onSearch).not.toHaveBeenCalled();
  });

  test("a valid form sends the values exactly as entered", async () => {
    const onSearch = jest.fn();
    render(<SearchForm cameras={cameras} onSearch={onSearch} initialValues={initial} />);
    await userEvent.click(screen.getByRole("button", { name: /search/i }));
    expect(onSearch).toHaveBeenCalledWith(initial);
  });

  test("no camera chosen: asks for one", async () => {
    const onSearch = jest.fn();
    render(<SearchForm cameras={cameras} onSearch={onSearch} initialValues={{ ...initial, camera: "" }} />);
    await userEvent.click(screen.getByRole("button", { name: /search/i }));
    expect(screen.getByText("Select a camera.")).toBeInTheDocument();
    expect(onSearch).not.toHaveBeenCalled();
  });

  test("an error from the server appears on the field it names", () => {
    render(<SearchForm cameras={cameras} onSearch={() => {}} initialValues={initial}
                       serverError={{ field: "start", message: "The start time is in the future." }} />);
    expect(screen.getByText("The start time is in the future.")).toBeInTheDocument();
  });

  test("the button is disabled while a search is running", () => {
    render(<SearchForm cameras={cameras} loading onSearch={() => {}} initialValues={initial} />);
    expect(screen.getByRole("button", { name: /searching/i })).toBeDisabled();
  });

  test("with no cameras the camera box is disabled", () => {
    render(<SearchForm cameras={[]} onSearch={() => {}} initialValues={{ ...initial, camera: "" }} />);
    expect(screen.getByRole("combobox")).toHaveAttribute("aria-disabled", "true");
  });
});
