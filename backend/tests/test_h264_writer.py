import tempfile
import time
import unittest
from pathlib import Path

import cv2
import numpy as np

from smart_sec_cam.video.catalogue import MEDIA_DIR
from smart_sec_cam.video.h264 import H264Writer, ffmpeg_executable, open_mp4_writer, open_webm_writer
from smart_sec_cam.video.writer import VideoWriter


def fourcc_of(path) -> str:
    capture = cv2.VideoCapture(str(path))
    try:
        value = int(capture.get(cv2.CAP_PROP_FOURCC))
    finally:
        capture.release()
    return "".join(chr((value >> 8 * i) & 0xFF) for i in range(4)).lower()


def frames(count, size=(640, 480)):
    for i in range(count):
        frame = np.zeros((size[1], size[0], 3), np.uint8)
        cv2.circle(frame, (20 + i * 10, size[1] // 2), 15, (0, 255, 0), -1)
        yield frame


@unittest.skipUnless(ffmpeg_executable(), "ffmpeg (imageio-ffmpeg) not installed")
class TestH264Writer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_recording_mp4_is_h264(self):
        writer = VideoWriter("Cam1", path=str(self.dir))
        for frame in frames(30):
            writer.add_frame(frame)
        recording_id = writer.write(fps=10)
        mp4 = self.dir / MEDIA_DIR / recording_id / "clip.mp4"
        self.assertIn(fourcc_of(mp4), ("avc1", "h264"))
        capture = cv2.VideoCapture(str(mp4))
        self.assertEqual(int(capture.get(cv2.CAP_PROP_FRAME_COUNT)), 30)
        self.assertTrue(capture.read()[0])
        capture.release()

    def test_recording_webm_is_vp9_and_plays(self):
        writer = VideoWriter("Cam1", path=str(self.dir))
        for frame in frames(30):
            writer.add_frame(frame)
        recording_id = writer.write(fps=10)
        webm = self.dir / MEDIA_DIR / recording_id / "clip.webm"
        self.assertEqual(webm.read_bytes()[:4], bytes.fromhex("1a45dfa3"))
        self.assertEqual(fourcc_of(webm), "vp90")
        capture = cv2.VideoCapture(str(webm))
        self.assertTrue(capture.read()[0])
        capture.release()

    def test_segment_encodes_faster_than_real_time(self):
        # 30 s at 10 fps must encode in well under 30 s or the recorder falls behind.
        started = time.monotonic()
        for name, opener in (("a.mp4", open_mp4_writer), ("a.webm", open_webm_writer)):
            writer = opener(str(self.dir / name), 10, (640, 480))
            for frame in frames(300):
                writer.write(frame)
            self.assertTrue(writer.release())
        self.assertLess(time.monotonic() - started, 20)

    def test_index_is_at_the_start_for_streaming(self):
        path = self.dir / "clip.mp4"
        writer = open_mp4_writer(str(path), 10, (640, 480))
        for frame in frames(10):
            writer.write(frame)
        self.assertTrue(writer.release())
        data = path.read_bytes()
        self.assertLess(data.find(b"moov"), data.find(b"mdat"))

    def test_odd_dimensions_are_padded(self):
        path = self.dir / "odd.mp4"
        writer = open_mp4_writer(str(path), 10, (321, 241))
        for frame in frames(5, (321, 241)):
            writer.write(frame)
        self.assertTrue(writer.release())
        self.assertIn(fourcc_of(path), ("avc1", "h264"))

    def test_failed_encoder_reports_failure(self):
        writer = H264Writer(str(self.dir / "missing-dir" / "x.mp4"), 10, (64, 48),
                            ffmpeg_executable())
        for frame in frames(5, (64, 48)):
            writer.write(frame)
        self.assertFalse(writer.release())


if __name__ == "__main__":
    unittest.main()
