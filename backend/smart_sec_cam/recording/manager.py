"""RecordingManager (SDS 3.1, SR-01-02, PR-01, SQR-02): continuous recording for every camera.

Each camera gets its own ``CameraRecorder`` with two threads:

* an intake thread that groups frames (timestamped on arrival by the manager)
  into 30-second segments, and
* an encoder thread that turns completed segments into catalogue entries.

A failure in one camera's threads never touches another camera, and a dead
recorder is replaced on the next health check.
"""
import logging
import queue
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Dict, Optional, Tuple

import cv2
import numpy as np

from smart_sec_cam.recording.segmenter import SEGMENT_SECONDS, STALL_SECONDS, Segment, SegmentGenerator
from smart_sec_cam.video.writer import VideoWriter

logger = logging.getLogger(__name__)

# How often to look for newly streaming cameras. A new camera's footage before
# its channel is discovered is not recorded, so keep this short; the check is
# one Redis KEYS call over a handful of keys.
CHANNEL_REFRESH_SECONDS = 1
IDLE_SLEEP_SECONDS = 0.01
_STOP = object()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def decode_frame(frame):
    """Accept JPEG bytes from the camera gateway, or an already decoded image."""
    if isinstance(frame, (bytes, bytearray, memoryview)):
        image = cv2.imdecode(np.frombuffer(frame, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Undecodable frame")
        return image
    return frame


def write_segment(segment: Segment, video_dir: str, resolution: Tuple[int, int] = (640, 480)) -> Optional[str]:
    """Encode a completed segment through VideoWriter so the catalogue registers it once."""
    writer = VideoWriter(segment.channel, path=video_dir, resolution=resolution)
    for frame in segment.frames:
        try:
            writer.add_frame(decode_frame(frame))
        except (ValueError, cv2.error):
            logger.warning("Skipping undecodable frame from %s", segment.channel)
    if not writer.frame_buffer:
        return None
    return writer.write(capture_start=segment.start, capture_end=segment.end, fps=segment.fps)


class CameraRecorder:
    def __init__(self, channel: str, video_dir: str, segment_seconds: int = SEGMENT_SECONDS,
                 stall_seconds: float = STALL_SECONDS, clock: Callable[[], datetime] = utc_now,
                 writer: Callable[[Segment, str], Optional[str]] = write_segment):
        self.channel = channel
        self.video_dir = video_dir
        self.clock = clock
        self.writer = writer
        self.frames: "queue.Queue" = queue.Queue()
        self.segments: "queue.Queue" = queue.Queue()
        self.generator = SegmentGenerator(channel, self.segments.put, segment_seconds, stall_seconds)
        self.intake_thread = threading.Thread(target=self._intake, name=f"record-{channel}", daemon=True)
        self.encoder_thread = threading.Thread(target=self._encode, name=f"encode-{channel}", daemon=True)
        self.segments_written = 0
        self.segments_failed = 0

    def start(self):
        self.intake_thread.start()
        self.encoder_thread.start()
        return self

    def submit(self, frame, captured_at: datetime):
        self.frames.put((frame, captured_at))

    def stop(self, timeout: float = None):
        """Close the open segment, finish encoding and stop both threads."""
        self.frames.put(_STOP)
        self.intake_thread.join(timeout)
        self.encoder_thread.join(timeout)

    def is_alive(self) -> bool:
        return self.intake_thread.is_alive() and self.encoder_thread.is_alive()

    def _intake(self):
        try:
            while True:
                try:
                    item = self.frames.get(timeout=1)
                except queue.Empty:
                    # Only an empty queue means the camera has gone quiet. Checking
                    # while frames are backlogged would split a delayed but
                    # continuous stream into tiny segments.
                    self.generator.tick(self.clock())
                    continue
                if item is _STOP:
                    self.generator.flush()
                    break
                frame, captured_at = item
                self.generator.add_frame(frame, captured_at)
        finally:
            self.segments.put(_STOP)

    def _encode(self):
        while True:
            segment = self.segments.get()
            if segment is _STOP:
                break
            try:
                if self.writer(segment, self.video_dir) is not None:
                    self.segments_written += 1
                    logger.info("Recorded %s segment %s - %s", self.channel,
                                segment.start.isoformat(), segment.end.isoformat())
            except Exception:
                # Keep recording later segments; the missing interval shows as a gap.
                self.segments_failed += 1
                logger.exception("Failed to write %s segment starting %s", self.channel, segment.start)


class RecordingManager:
    def __init__(self, receiver, video_dir: str, segment_seconds: int = SEGMENT_SECONDS,
                 stall_seconds: float = STALL_SECONDS, clock: Callable[[], datetime] = utc_now,
                 recorder_factory: Callable[..., CameraRecorder] = CameraRecorder,
                 channel_refresh_seconds: float = CHANNEL_REFRESH_SECONDS):
        self.receiver = receiver
        self.channel_refresh_seconds = channel_refresh_seconds
        self.video_dir = video_dir
        self.segment_seconds = segment_seconds
        self.stall_seconds = stall_seconds
        self.clock = clock
        self.recorder_factory = recorder_factory
        self.recorders: Dict[str, CameraRecorder] = {}

    def recorder(self, channel: str) -> CameraRecorder:
        recorder = self.recorders.get(channel)
        if recorder is None or not recorder.is_alive():
            if recorder is not None:
                logger.error("Recorder for %s stopped unexpectedly; restarting", channel)
            recorder = self.recorder_factory(
                channel, self.video_dir, segment_seconds=self.segment_seconds,
                stall_seconds=self.stall_seconds, clock=self.clock
            ).start()
            self.recorders[channel] = recorder
        return recorder

    def handle_message(self, message) -> bool:
        if not message or message.get("type") != "message":
            return False
        channel, frame = message.get("channel"), message.get("data")
        if isinstance(channel, bytes):
            channel = channel.decode("utf-8", errors="replace")
        if not isinstance(channel, str) or not channel or not isinstance(frame, bytes):
            return False
        # Timestamp on arrival, before any queueing, so encoding never skews times.
        self.recorder(channel).submit(frame, self.clock())
        return True

    def refresh_channels(self):
        channels = sorted(self.receiver.get_all_channels())
        # Compare as sets: Redis returns keys in no fixed order, and every
        # resubscription briefly drops messages.
        if set(channels) != set(self.receiver.subscribed_channels):
            self.receiver.set_channels(channels)
        for channel in list(self.recorders):
            if channel not in channels:
                logger.info("Camera channel %s removed; closing its recording", channel)
                self.recorders.pop(channel).stop(timeout=60)

    def stop(self):
        for recorder in self.recorders.values():
            recorder.stop(timeout=60)
        self.recorders.clear()

    def run_forever(self, stop_event: threading.Event = None):
        last_refresh = None
        while stop_event is None or not stop_event.is_set():
            if last_refresh is None or time.monotonic() - last_refresh >= self.channel_refresh_seconds:
                try:
                    self.refresh_channels()
                except Exception:
                    logger.exception("Could not refresh camera channel list")
                last_refresh = time.monotonic()
            if not self.handle_message(self.receiver.get_new_message()):
                time.sleep(IDLE_SLEEP_SECONDS)
