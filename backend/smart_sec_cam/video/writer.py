import datetime
import json
import math
import uuid
from pathlib import Path
import time
from typing import Tuple

import cv2


from smart_sec_cam.video.catalogue import MEDIA_DIR, QUEUE_DIR
from smart_sec_cam.video.h264 import open_mp4_writer


class VideoWriter:
    FILENAME_DELIM = "__"

    def __init__(self, channel: str, path="data/videos/",
                 resolution: Tuple[int, int] = (640, 480)):
        self.channel = channel
        self.video_dir = path
        Path(path).mkdir(parents=True, exist_ok=True)
        self.resolution = resolution
        self.frame_buffer = []
        self.first_frame_time = time.monotonic()

    def add_frame(self, frame):
        resized_frame = cv2.resize(frame, self.resolution)
        if not self.frame_buffer:
            self.capture_start = datetime.datetime.now(datetime.timezone.utc)
            self.first_frame_time = time.monotonic()
        self.frame_buffer.append(resized_frame)

    def write(self, capture_start: datetime.datetime = None,
              capture_end: datetime.datetime = None, fps: float = None) -> str:
        """Encode the buffered frames, queue them for cataloguing and return the recording ID.

        Continuous recording passes the segment's real UTC capture interval and
        frame rate (SR-01-02/03); motion-triggered callers keep the defaults,
        which measure them from the wall clock.
        """
        if capture_start is not None:
            self.capture_start = capture_start
        if capture_end is None:
            capture_end = datetime.datetime.now(datetime.timezone.utc)
        if fps is None:
            fps = max(1, self._calculate_fps())
        recording_id = uuid.uuid4().hex
        root = Path(self.video_dir)
        directory = root / MEDIA_DIR / recording_id
        directory.mkdir(parents=True)
        durations = {}
        for fmt in ("webm", "mp4"):
            path = str(directory / ("clip." + fmt))
            if fmt == "mp4":
                # H.264, so the MP4 (the copy kept in the cloud) plays in every browser.
                writer = open_mp4_writer(path, fps, self.resolution)
            else:
                writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"VP90"), fps, self.resolution)
            try:
                if not writer.isOpened():
                    raise RuntimeError(f"Cannot encode {fmt} recording")
                for frame in self.frame_buffer:
                    writer.write(frame)
            finally:
                writer.release()

            capture = cv2.VideoCapture(path)
            try:
                rate = capture.get(cv2.CAP_PROP_FPS)
                frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
                if not capture.read()[0] or not (rate > 0 and frames > 0 and math.isfinite(frames / rate)):
                    raise RuntimeError(f"Cannot measure completed {fmt} recording")
                durations[fmt] = frames / rate
            finally:
                capture.release()

        manifest = {
            "id": recording_id, "channel": self.channel,
            "start": self.capture_start.isoformat(), "end": capture_end.isoformat(),
            "durations": durations
        }
        pending = root / QUEUE_DIR
        pending.mkdir(exist_ok=True)
        marker = directory / "completed.tmp"
        marker.write_text(json.dumps(manifest))
        marker.rename(pending / (recording_id + ".json"))
        self._clear_frame_buffer()
        return recording_id

    def reset(self):
        self._clear_frame_buffer()
        self.first_frame_time = time.monotonic()

    def _clear_frame_buffer(self):
        self.frame_buffer = []

    def _calculate_fps(self) -> int:
        elapsed_time = time.monotonic() - self.first_frame_time
        return int(len(self.frame_buffer) / elapsed_time)
