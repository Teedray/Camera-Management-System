import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ResultsList from "./ResultsList";
import { toGaps, toSegments } from "../utils/playbackPlan";

const seg = (id, start) => ({ id, start, end: new Date(Date.parse(start) + 30000).toISOString(), formats: ["webm"] });

describe("ResultsList", () => {
  const segments = toSegments([
    seg(1, "2026-11-18T14:00:00.000Z"), seg(2, "2026-11-18T14:00:30.000Z"), seg(3, "2026-11-18T14:03:00.000Z"),
  ]);

  test("shows continuous footage as one row and marks the missing period (TS-03-05)", () => {
    const gaps = toGaps([{ start: "2026-11-18T14:01:00.000Z", end: "2026-11-18T14:03:00.000Z", type: "missing" }]);
    render(<ResultsList segments={segments} gaps={gaps} onPlay={() => {}} onGap={() => {}} />);
    const items = screen.getAllByRole("button");
    expect(items).toHaveLength(3);                                   // run, gap, run
    expect(items[0]).toHaveTextContent("9:00:00 AM – 9:01:00 AM");   // Jamaica time
    expect(items[0]).toHaveTextContent("2 clips");
    expect(items[1]).toHaveTextContent("Missing");
    expect(items[1]).toHaveTextContent("2 min");
    expect(items[2]).toHaveTextContent("1 clip");
  });

  test("expired footage is labelled as past the retention period (TS-03-07)", () => {
    const gaps = toGaps([{ start: "2026-11-18T14:01:00.000Z", end: "2026-11-18T14:03:00.000Z", type: "expired" }]);
    render(<ResultsList segments={segments} gaps={gaps} onPlay={() => {}} onGap={() => {}} />);
    expect(screen.getByText("Expired")).toBeInTheDocument();
    expect(screen.getByText(/30-day retention/)).toBeInTheDocument();
  });

  test("clicking footage asks to play from its start; clicking a gap reports the gap", async () => {
    const onPlay = jest.fn();
    const onGap = jest.fn();
    const gaps = toGaps([{ start: "2026-11-18T14:01:00.000Z", end: "2026-11-18T14:03:00.000Z", type: "missing" }]);
    render(<ResultsList segments={segments} gaps={gaps} onPlay={onPlay} onGap={onGap} />);
    const items = screen.getAllByRole("button");
    await userEvent.click(items[0]);
    expect(onPlay).toHaveBeenCalledWith(expect.objectContaining({ startMs: Date.parse("2026-11-18T14:00:00.000Z") }));
    await userEvent.click(items[1]);
    expect(onGap).toHaveBeenCalledWith(expect.objectContaining({ type: "missing" }));
  });

  test("the run being played is highlighted", () => {
    render(<ResultsList segments={segments} gaps={[]} activeMs={Date.parse("2026-11-18T14:00:10.000Z")}
                        onPlay={() => {}} onGap={() => {}} />);
    expect(screen.getByText("Playing")).toBeInTheDocument();
  });

  test("no recordings gives a clear 'No footage found' message", () => {
    render(<ResultsList segments={[]} gaps={[]} onPlay={() => {}} onGap={() => {}} />);
    expect(screen.getByRole("status")).toHaveTextContent("No footage found");
  });

  test("an empty result explains when the footage has expired", () => {
    const gaps = toGaps([{ start: "2026-10-01T14:00:00.000Z", end: "2026-10-01T15:00:00.000Z", type: "expired" }]);
    render(<ResultsList segments={[]} gaps={gaps} onPlay={() => {}} onGap={() => {}} />);
    expect(screen.getByRole("status")).toHaveTextContent(/30-day retention/);
  });
});
