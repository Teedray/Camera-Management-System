import datetime
import json
import math
import uuid
from pathlib import Path
import time
from typing import Tuple

import cv2


from smart_sec_cam.video.catalogue import MEDIA_DIR, QUEUE_DIR


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

    def write(self):
        capture_end = datetime.datetime.now(datetime.timezone.utc)
        fps = max(1, self._calculate_fps())
        recording_id = uuid.uuid4().hex
        root = Path(self.video_dir)
        directory = root / MEDIA_DIR / recording_id
        directory.mkdir(parents=True)
        durations = {}
        for fmt, codec in (("webm", "VP90"), ("mp4", "mp4v")):
            path = str(directory / ("clip." + fmt))
            writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*codec), fps, self.resolution)
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

    def reset(self):
        self._clear_frame_buffer()
        self.first_frame_time = time.monotonic()

    def _clear_frame_buffer(self):
        self.frame_buffer = []

    def _calculate_fps(self) -> int:
        elapsed_time = time.monotonic() - self.first_frame_time
        return int(len(self.frame_buffer) / elapsed_time)
