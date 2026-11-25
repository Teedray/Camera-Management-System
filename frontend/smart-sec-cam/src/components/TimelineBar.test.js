import { fireEvent, render, screen } from "@testing-library/react";

import TimelineBar from "./TimelineBar";
import { toGaps, toSegments } from "../utils/playbackPlan";

const start = Date.parse("2026-11-18T14:00:00.000Z");
const end = Date.parse("2026-11-18T14:10:00.000Z");
const segments = toSegments([
  { id: 1, start: "2026-11-18T14:00:00.000Z", end: "2026-11-18T14:03:00.000Z", formats: [] },
  { id: 2, start: "2026-11-18T14:06:00.000Z", end: "2026-11-18T14:10:00.000Z", formats: [] },
]);
const gaps = toGaps([{ start: "2026-11-18T14:03:00.000Z", end: "2026-11-18T14:06:00.000Z", type: "missing" }]);

describe("TimelineBar", () => {
  test("shows footage and the missing period, with a legend", () => {
    render(<TimelineBar rangeStartMs={start} rangeEndMs={end} segments={segments} gaps={gaps} posMs={start} onSeek={() => {}} />);
    expect(screen.getAllByTestId("timeline-available")).toHaveLength(2);
    expect(screen.getByTestId("timeline-missing")).toBeInTheDocument();
    ["Footage", "Missing", "Expired"].forEach((label) => expect(screen.getByText(label)).toBeInTheDocument());
  });

  test("expired periods are drawn separately", () => {
    const expired = toGaps([{ start: "2026-11-18T14:03:00.000Z", end: "2026-11-18T14:06:00.000Z", type: "expired" }]);
    render(<TimelineBar rangeStartMs={start} rangeEndMs={end} segments={segments} gaps={expired} posMs={start} onSeek={() => {}} />);
    expect(screen.getByTestId("timeline-expired")).toBeInTheDocument();
  });

  test("moving the slider seeks to that moment once released (TS-03-03)", () => {
    const onSeek = jest.fn();
    render(<TimelineBar rangeStartMs={start} rangeEndMs={end} segments={segments} gaps={gaps} posMs={start} onSeek={onSeek} tz="America/Jamaica" />);
    const slider = screen.getByLabelText("Playback position");
    fireEvent.change(slider, { target: { value: String(start + 120000) } });
    expect(onSeek).not.toHaveBeenCalled();           // still dragging
    fireEvent.pointerUp(slider);
    expect(onSeek).toHaveBeenCalledWith(start + 120000);
  });

  test("the slider announces the time in Jamaica time", () => {
    render(<TimelineBar rangeStartMs={start} rangeEndMs={end} segments={segments} gaps={gaps} posMs={start + 60000} onSeek={() => {}} tz="America/Jamaica" />);
    expect(screen.getByLabelText("Playback position")).toHaveAttribute("aria-valuetext", "9:01:00 AM");
  });
});
