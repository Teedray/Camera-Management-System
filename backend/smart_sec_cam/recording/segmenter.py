"""SegmentGenerator (SDS 3.1, SR-01-02): split one camera's stream into 30-second segments."""
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, List, Optional

SEGMENT_SECONDS = 30
# A camera that sends nothing for this long is treated as disconnected: the
# open segment is closed at its last frame so the outage appears as a gap.
STALL_SECONDS = 5


@dataclass
class Segment:
    channel: str
    window_start: datetime
    start: datetime
    end: Optional[datetime] = None
    frames: List[Any] = field(default_factory=list)
    last_frame_at: Optional[datetime] = None

    @property
    def duration_seconds(self) -> float:
        return (self.end - self.start).total_seconds()

    @property
    def fps(self) -> float:
        """Frame rate that makes the encoded file last as long as the real capture."""
        duration = self.duration_seconds
        if duration <= 0 or not math.isfinite(duration):
            return 1.0
        return max(len(self.frames) / duration, 0.1)


class SegmentGenerator:
    """Groups timestamped frames into clock-aligned segments for one camera.

    Segment windows start on whole multiples of ``segment_seconds`` in UTC
    (with 30 s: hh:mm:00 and hh:mm:30), so segments from different cameras
    line up. A completed segment is handed to ``on_segment``.
    """

    def __init__(self, channel: str, on_segment: Callable[[Segment], None],
                 segment_seconds: int = SEGMENT_SECONDS, stall_seconds: float = STALL_SECONDS):
        if segment_seconds <= 0 or stall_seconds <= 0:
            raise ValueError("segment_seconds and stall_seconds must be positive")
        self.channel = channel
        self.on_segment = on_segment
        self.segment_seconds = segment_seconds
        self.stall = timedelta(seconds=stall_seconds)
        self.current: Optional[Segment] = None

    def window_start(self, moment: datetime) -> datetime:
        seconds = math.floor(moment.timestamp() / self.segment_seconds) * self.segment_seconds
        return datetime.fromtimestamp(seconds, timezone.utc)

    def add_frame(self, frame, captured_at: datetime):
        if captured_at.tzinfo is None:
            raise ValueError("captured_at must be timezone-aware")
        captured_at = captured_at.astimezone(timezone.utc)
        current = self.current

        if current is not None:
            if captured_at < current.last_frame_at:
                return  # Out-of-order frame: never rewrite an earlier interval.
            window = self.window_start(captured_at)
            if captured_at - current.last_frame_at > self.stall:
                self._close(self._estimated_end(current))
            elif window != current.window_start:
                # Continuous footage across the boundary: the segment runs to it.
                self._close(current.window_start + timedelta(seconds=self.segment_seconds))

        if self.current is None:
            self.current = Segment(
                channel=self.channel, window_start=self.window_start(captured_at), start=captured_at
            )
        self.current.frames.append(frame)
        self.current.last_frame_at = captured_at

    def tick(self, now: datetime):
        """Close the open segment if the camera has stopped sending frames."""
        current = self.current
        if current is not None and now - current.last_frame_at > self.stall:
            self._close(self._estimated_end(current))

    def flush(self):
        if self.current is not None:
            self._close(self._estimated_end(self.current))

    def _estimated_end(self, segment: Segment) -> datetime:
        window_end = segment.window_start + timedelta(seconds=self.segment_seconds)
        count = len(segment.frames)
        if count > 1:
            interval = (segment.last_frame_at - segment.start) / (count - 1)
            return min(segment.last_frame_at + interval, window_end)
        return min(segment.last_frame_at + timedelta(milliseconds=100), window_end)

    def _close(self, end: datetime):
        segment, self.current = self.current, None
        segment.end = max(end, segment.start)
        self.on_segment(segment)
