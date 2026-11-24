import { act, fireEvent, render, screen } from "@testing-library/react";

import SegmentPlayer from "./SegmentPlayer";
import { toSegments } from "../utils/playbackPlan";

jest.mock("../config", () => ({ SERVER_URL: "https://localhost:8443", USE_MOCK: false }));

const clip = (id, start) => ({ id, start, end: new Date(Date.parse(start) + 30000).toISOString(), formats: ["webm"] });
const contiguous = toSegments([
  clip(1, "2026-11-18T14:00:00.000Z"), clip(2, "2026-11-18T14:00:30.000Z"), clip(3, "2026-11-18T14:01:00.000Z"),
]);
const withBreak = toSegments([clip(1, "2026-11-18T14:00:00.000Z"), clip(2, "2026-11-18T14:05:00.000Z")]);

beforeAll(() => {
  // jsdom does not implement media playback
  window.HTMLMediaElement.prototype.load = jest.fn();
  window.HTMLMediaElement.prototype.pause = jest.fn();
  window.HTMLMediaElement.prototype.play = jest.fn(() => Promise.resolve());
});

function setup(segments, ms = segments[0].startMs, play = true) {
  render(<SegmentPlayer segments={segments} token="tok" tz="America/Jamaica" seekRequest={{ ms, play, nonce: 1 }} />);
  const a = screen.getByTestId("video-a");
  const b = screen.getByTestId("video-b");
  a.play = jest.fn(() => Promise.resolve());
  b.play = jest.fn(() => Promise.resolve());
  return { a, b };
}
const idIn = (video) => Number((video.getAttribute("src") || "").match(/recordings\/(\d+)\//)?.[1]);
const visible = (video) => video.style.opacity === "1";

describe("SegmentPlayer", () => {
  test("PR-03: back-to-back clips play with no reload; the buffered clip takes over", () => {
    const { a, b } = setup(contiguous);
    expect(idIn(a)).toBe(1);
    act(() => { fireEvent.loadedMetadata(a); });
    expect(a.play).toHaveBeenCalledTimes(1);
    expect(idIn(b)).toBe(2);                    // next clip is buffered while the first plays

    act(() => { fireEvent.ended(a); });
    expect(b.play).toHaveBeenCalledTimes(1);    // swapped to the buffered clip straight away
    expect(visible(b)).toBe(true);
    expect(visible(a)).toBe(false);
    expect(idIn(a)).toBe(3);                    // the idle element now buffers the third clip

    act(() => { fireEvent.ended(b); });
    expect(a.play).toHaveBeenCalledTimes(2);
    expect(visible(a)).toBe(true);
  });

  test("playback stops with a message after the last clip", () => {
    const { a, b } = setup(contiguous.slice(0, 2));
    act(() => { fireEvent.loadedMetadata(a); });
    act(() => { fireEvent.ended(a); });
    act(() => { fireEvent.ended(b); });
    expect(screen.getByText("End of the recorded footage.")).toBeInTheDocument();
  });

  test("TS-03-05: a break in the footage is skipped and the user is told", () => {
    const { a } = setup(withBreak);
    act(() => { fireEvent.loadedMetadata(a); });
    act(() => { fireEvent.ended(a); });
    expect(screen.getByText(/No footage from 9:00:30 AM to 9:05:00 AM/)).toBeInTheDocument();
    expect(idIn(a)).toBe(2);                    // jumped straight to the next recording
  });

  test("seeking into a gap resumes at the next recording and says so", () => {
    const { a } = setup(withBreak, Date.parse("2026-11-18T14:02:00.000Z"));
    expect(screen.getByText(/Skipped to the next recording/)).toBeInTheDocument();
    expect(idIn(a)).toBe(2);
  });

  test("seeking after the last clip says there is no more footage", () => {
    setup(withBreak, Date.parse("2026-11-18T15:00:00.000Z"), false);
    expect(screen.getByText("There is no footage after this point.")).toBeInTheDocument();
  });

  test("with no results the player explains what to do and the play button is off", () => {
    render(<SegmentPlayer segments={[]} token="tok" tz="America/Jamaica" seekRequest={null} />);
    expect(screen.getByText(/Search for footage/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Play" })).toBeDisabled();
  });

  test("a clip that fails to load shows an error instead of a blank screen", () => {
    const { a } = setup(contiguous);
    act(() => { fireEvent.error(a); });
    expect(screen.getByText(/could not be played/)).toBeInTheDocument();
  });
});
