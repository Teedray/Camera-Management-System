"""F01 continuous recording: 30-second segments, cataloguing, gaps, isolation and camera status."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from smart_sec_cam.auth.database import AuthDatabase
from smart_sec_cam.recording.manager import CameraRecorder, RecordingManager, write_segment
from smart_sec_cam.recording.segmenter import SegmentGenerator
from smart_sec_cam.video.catalogue import camera_segments, find_gaps, import_completed
from test_admin_camera_api import AdminApiTestCase

T0 = datetime(2026, 11, 23, 15, 0, 0, tzinfo=timezone.utc)
SMALL = (64, 48)


def jpeg(value=0):
    return cv2.imencode(".jpg", np.full((48, 64, 3), value % 255, dtype=np.uint8))[1].tobytes()


def frame_times(start, seconds, fps=2):
    return [start + timedelta(seconds=i / fps) for i in range(int(seconds * fps))]


class SegmentGeneratorTest(unittest.TestCase):
    def setUp(self):
        self.segments = []
        self.generator = SegmentGenerator("Cam1", self.segments.append)

    def feed(self, times):
        for moment in times:
            self.generator.add_frame(b"frame", moment)

    def test_three_minutes_become_six_aligned_30_second_segments(self):
        # TS-01-04: three minutes of continuous footage -> six 30-second segments.
        self.feed(frame_times(T0, 180))
        self.generator.flush()
        self.assertEqual(len(self.segments), 6)
        for index, segment in enumerate(self.segments):
            expected_start = T0 + timedelta(seconds=30 * index)
            self.assertEqual(segment.start, expected_start)
            self.assertEqual(segment.window_start, expected_start)
            self.assertAlmostEqual(segment.duration_seconds, 30, places=3)
            self.assertEqual(len(segment.frames), 60)
            self.assertAlmostEqual(segment.fps, 2, places=3)
        # Consecutive segments touch: continuous footage has no gaps.
        for earlier, later in zip(self.segments, self.segments[1:]):
            self.assertEqual(earlier.end, later.start)

    def test_boundaries_are_aligned_to_the_clock(self):
        self.feed(frame_times(T0 + timedelta(seconds=12), 30))
        self.generator.flush()
        self.assertEqual([s.start for s in self.segments],
                         [T0 + timedelta(seconds=12), T0 + timedelta(seconds=30)])
        self.assertEqual(self.segments[0].end, T0 + timedelta(seconds=30))

    def test_disconnect_closes_segment_and_leaves_a_gap(self):
        # TS-01-06: a ~2-minute disconnection appears as a recording gap.
        self.feed(frame_times(T0, 40))
        self.feed(frame_times(T0 + timedelta(seconds=160), 40))
        self.generator.flush()
        starts = [s.start - T0 for s in self.segments]
        self.assertEqual(starts, [timedelta(0), timedelta(seconds=30), timedelta(seconds=160),
                                  timedelta(seconds=180)])
        self.assertEqual(self.segments[1].end, T0 + timedelta(seconds=40))
        gaps = find_gaps([{"start": s.start, "end": s.end} for s in self.segments],
                         T0, T0 + timedelta(seconds=200))
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["start"], T0 + timedelta(seconds=40))
        self.assertEqual(gaps[0]["end"], T0 + timedelta(seconds=160))
        self.assertEqual(gaps[0]["seconds"], 120)

    def test_tick_closes_a_stalled_segment(self):
        self.feed(frame_times(T0, 10))
        self.generator.tick(T0 + timedelta(seconds=12))
        self.assertEqual(self.segments, [])
        self.generator.tick(T0 + timedelta(seconds=16))
        self.assertEqual(len(self.segments), 1)
        self.assertEqual(self.segments[0].end, T0 + timedelta(seconds=10))

    def test_out_of_order_and_naive_frames(self):
        self.feed([T0 + timedelta(seconds=5), T0 + timedelta(seconds=4)])
        self.generator.flush()
        self.assertEqual(len(self.segments[0].frames), 1)
        with self.assertRaises(ValueError):
            self.generator.add_frame(b"frame", datetime(2026, 11, 23, 15, 0, 0))


class GapDetectionTest(unittest.TestCase):
    def test_leading_trailing_and_tolerated_gaps(self):
        seg = lambda a, b: {"start": T0 + timedelta(seconds=a), "end": T0 + timedelta(seconds=b)}
        segments = [seg(10, 40), seg(41, 70), seg(100, 130)]  # 1 s jitter is tolerated
        gaps = find_gaps(segments, T0, T0 + timedelta(seconds=150))
        self.assertEqual([(g["start"] - T0).seconds for g in gaps], [0, 70, 130])
        self.assertEqual([g["seconds"] for g in gaps], [10, 30, 20])
        self.assertEqual(find_gaps([], T0, T0 + timedelta(seconds=60))[0]["seconds"], 60)


class RecorderCatalogueTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        with patch.object(AuthDatabase, "DATABASE_DIR", str(self.root)):
            self.db = AuthDatabase("test")
        self.addCleanup(self.db.conn.close)
        self.db.add_camera("front", "Front", "Entrance", "Cam1")
        self.writer = partial(write_segment, resolution=SMALL)

    def record(self, channel, times, value=0):
        recorder = CameraRecorder(channel, str(self.root / "videos"), clock=lambda: times[-1],
                                  writer=self.writer).start()
        for index, moment in enumerate(times):
            recorder.submit(jpeg(value + index), moment)
        recorder.stop(timeout=120)
        return recorder

    def test_segments_are_encoded_catalogued_once_with_utc_times(self):
        recorder = self.record("Cam1", frame_times(T0, 180))
        self.assertEqual((recorder.segments_written, recorder.segments_failed), (6, 0))
        import_completed(self.db, self.root / "videos")
        import_completed(self.db, self.root / "videos")  # TS-01-05: re-import stores nothing twice
        rows = self.db.conn.execute(
            "SELECT capture_start_utc, capture_end_utc FROM recordings ORDER BY capture_start_utc"
        ).fetchall()
        self.assertEqual(len(rows), 6)
        for index, (start, end) in enumerate(rows):
            self.assertEqual(datetime.fromisoformat(start), T0 + timedelta(seconds=30 * index))
            self.assertEqual(datetime.fromisoformat(end), T0 + timedelta(seconds=30 * (index + 1)))
        durations = self.db.conn.execute(
            "SELECT duration_seconds FROM recording_variants WHERE format = 'mp4'"
        ).fetchall()
        for (duration,) in durations:
            self.assertAlmostEqual(duration, 30, delta=0.6)
        segments = camera_segments(self.db, "front", T0, T0 + timedelta(minutes=3))
        self.assertEqual(len(segments), 6)
        self.assertEqual(find_gaps(segments, T0, T0 + timedelta(minutes=3)), [])

    def test_failing_camera_does_not_stop_other_cameras(self):
        # SQR-02: isolate camera-specific failures.
        def flaky_writer(segment, video_dir):
            if segment.channel == "broken":
                raise RuntimeError("encoder failure")
            return self.writer(segment, video_dir)

        times = iter(frame_times(T0, 60))
        clock_now = [T0]

        def clock():
            return clock_now[0]

        class Receiver:
            subscribed_channels = []

        manager = RecordingManager(Receiver(), str(self.root / "videos"), clock=clock,
                                   recorder_factory=partial(CameraRecorder, writer=flaky_writer))
        for moment in times:
            clock_now[0] = moment
            for channel in ("Cam1", "broken"):
                manager.handle_message({"type": "message", "channel": channel.encode(), "data": jpeg()})
        recorders = dict(manager.recorders)
        manager.stop()
        self.assertEqual(recorders["Cam1"].segments_written, 2)
        self.assertEqual(recorders["broken"].segments_failed, 2)

    def test_backlogged_frames_are_not_split_by_the_stall_check(self):
        # The clock is far ahead of the frames, as when the queue falls behind.
        late = T0 + timedelta(minutes=5)
        recorder = CameraRecorder("Cam1", str(self.root / "videos"), clock=lambda: late,
                                  writer=lambda segment, _: segment).start()
        for moment in frame_times(T0, 60):
            recorder.submit(b"frame", moment)
        recorder.stop(timeout=30)
        self.assertEqual(recorder.segments_written, 2)

    def test_dead_recorder_is_restarted(self):
        class Receiver:
            subscribed_channels = []

        manager = RecordingManager(Receiver(), str(self.root / "videos"),
                                   recorder_factory=partial(CameraRecorder, writer=self.writer))
        first = manager.recorder("Cam1")
        first.stop(timeout=10)
        self.assertFalse(first.is_alive())
        second = manager.recorder("Cam1")
        self.assertIsNot(first, second)
        self.assertTrue(second.is_alive())
        manager.stop()


class CameraRecordingApiTest(AdminApiTestCase):
    def setUp(self):
        super().setUp()
        self.root = Path(self.server.VIDEO_DIR)
        self.db.add_camera("front", "Front", "Entrance", "Cam1")
        self.db.add_camera("till", "Till", "Cashier", "Cam2")
        self.db.assign_camera("viewer-id", "front")
        self.db.assign_camera("administrator-id", "front")
        self.server.last_seen_writes.clear()
        # Recent footage: 90 s, a 2-minute outage, then 60 s more.
        now = datetime.now(timezone.utc)
        self.base = SegmentGenerator("x", None).window_start(now - timedelta(minutes=10))
        writer = partial(write_segment, resolution=SMALL)
        recorder = CameraRecorder("Cam1", str(self.root), clock=lambda: now, writer=writer).start()
        for moment in frame_times(self.base, 90) + frame_times(self.base + timedelta(seconds=210), 60):
            recorder.submit(jpeg(), moment)
        recorder.stop(timeout=120)

    def recordings(self, role="viewer", camera="front", **params):
        query = {"start": self.base.isoformat(), "end": (self.base + timedelta(seconds=270)).isoformat()}
        query.update(params)
        return self.client.get(f"/api/v1/cameras/{camera}/recordings", query_string=query,
                               headers=self.headers[role])

    def test_lists_segments_and_flags_the_outage(self):
        response = self.recordings()
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        data = response.get_json()["data"]
        self.assertEqual(len(data["segments"]), 5)
        for segment in data["segments"]:
            self.assertEqual(datetime.fromisoformat(segment["start"]).second % 30, 0)
            self.assertAlmostEqual(segment["duration_seconds"], 30, delta=0.6)
            self.assertEqual(set(segment["files"]), {"webm", "mp4"})
        self.assertEqual(len(data["gaps"]), 1)
        gap = data["gaps"][0]
        self.assertEqual(datetime.fromisoformat(gap["start"]), self.base + timedelta(seconds=90))
        self.assertEqual(datetime.fromisoformat(gap["end"]), self.base + timedelta(seconds=210))
        # Each listed file plays through the existing access-controlled endpoint.
        name = data["segments"][0]["files"]["mp4"]
        with self.client.get("/api/video/" + name, headers=self.headers["viewer"]) as playback:
            self.assertEqual(playback.status_code, 200)

    def test_deleted_segment_files_show_as_gaps(self):
        first = self.recordings().get_json()["data"]["segments"][0]
        recording_dir = next((self.root / "catalogue").glob(f"{first['id']}"))
        for media in recording_dir.glob("clip.*"):
            media.unlink()
        gaps = self.recordings().get_json()["data"]["gaps"]
        self.assertEqual(datetime.fromisoformat(gaps[0]["start"]), self.base)
        self.assertEqual(gaps[0]["seconds"], 30)

    def test_access_and_input_validation(self):
        self.assert_error(self.recordings(camera="till"), 404, "Camera does not exist")
        self.assert_error(self.recordings(role="manager"), 404, "Camera does not exist")
        self.assert_error(self.recordings(start="yesterday"), 400, "start must be an ISO 8601 timestamp")
        self.assert_error(self.recordings(start="2026-11-23T10:00:00"), 400,
                          "start must include a timezone offset, for example Z")
        self.assert_error(self.recordings(start=self.base.isoformat(), end=self.base.isoformat()),
                          400, "start must be before end")
        self.assert_error(self.recordings(start=(self.base - timedelta(days=32)).isoformat()),
                          400, "The requested range cannot exceed 31 days")
        self.assert_error(self.client.get("/api/v1/cameras/front/recordings"), 401, "Missing token")

    def test_camera_status_follows_last_frame(self):
        def status(role):
            response = self.client.get("/api/v1/cameras/status", headers=self.headers[role])
            self.assertEqual(response.status_code, 200)
            item, = response.get_json()["data"]["items"]
            return item

        self.assertEqual(status("viewer")["status"], "never_connected")
        now = datetime.now(timezone.utc)
        self.server.note_camera_frame(b"Cam1", now)
        self.assertEqual(status("viewer")["status"], "connected")
        self.assertNotIn("stream_address", status("viewer"))
        self.assertIn("stream_address", status("administrator"))
        # Throttled: a frame 1 s later is not written; 6 s later it is.
        self.server.note_camera_frame("Cam1", now + timedelta(seconds=1))
        self.assertEqual(self.db.get_camera("front")["last_seen_utc"], now.isoformat())
        later = now + timedelta(seconds=6)
        self.server.note_camera_frame("Cam1", later)
        self.assertEqual(self.db.get_camera("front")["last_seen_utc"], later.isoformat())
        # No frame for more than 10 s: disconnected.
        self.server.last_seen_writes.clear()
        self.server.note_camera_frame("Cam1", now - timedelta(seconds=20))
        self.assertEqual(status("viewer")["status"], "disconnected")

    def test_admin_updates_stream_address_with_validation(self):
        url = "/api/v1/cameras/front"
        admin = self.headers["administrator"]
        # TS-01-02: an invalid camera IP address is rejected with a clear error.
        for address, error in (
            ("http://999.168.1.20:8080/video", "stream_address has an invalid IP address"),
            ("http://192.168.1.20:99999/video", "stream_address has an invalid host or port"),
            ("ftp://192.168.1.20/video", "stream_address must be a USB camera number or an http, https or rtsp URL"),
            (" ", "stream_address must be a non-empty text value"),
        ):
            with self.subTest(address=address):
                self.assert_error(self.client.patch(url, json={"stream_address": address}, headers=admin),
                                  400, error)
        self.assertIsNone(self.db.get_camera("front")["stream_address"])

        response = self.client.patch(url, json={"stream_address": "http://192.168.1.20:8080/video",
                                                "name": "Front Door"}, headers=admin)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["data"]["stream_address"], "http://192.168.1.20:8080/video")
        self.assertEqual(self.db.get_camera("front")["name"], "Front Door")
        self.assertEqual(self.client.patch(url, json={"stream_address": "0"}, headers=admin).status_code, 200)

        self.assert_error(self.client.patch(url, json={"name": "X"}, headers=self.headers["viewer"]),
                          403, "Administrator role required")
        self.assert_error(self.client.patch("/api/v1/cameras/missing", json={"name": "X"}, headers=admin),
                          404, "Camera does not exist")
        self.assert_error(self.client.patch(url, json={"channel_name": "X"}, headers=admin),
                          400, "Only name, location and stream_address can be changed")
