"""Trim-and-download exports (F05): role, assignment and integrity checks on the server."""
import hashlib
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import cv2
import jwt
import numpy as np

from smart_sec_cam.video.catalogue import import_completed
from smart_sec_cam.video.exports import export_clip
from smart_sec_cam.video.writer import VideoWriter
from test_admin_camera_api import AdminApiTestCase

EXPORTS_URL = "/api/v1/exports"


class ExportApiTest(AdminApiTestCase):
    def setUp(self):
        super().setUp()
        self.root = Path(self.server.VIDEO_DIR)
        self.db.add_camera("front", "Front", "Entrance", "front-stream")
        self.db.add_camera("till", "Till", "Cashier", "till-stream")
        for user_id in ("manager-id", "viewer-id"):
            self.db.assign_camera(user_id, "front")
        self.db.assign_camera("administrator-id", "till")
        self.front = self.record("front-stream")
        self.till = self.record("till-stream")
        # Every export that actually runs goes through export_clip.
        self.exports = patch.object(self.server, "export_clip", wraps=export_clip)
        self.export_calls = self.exports.start()
        self.addCleanup(self.exports.stop)

    def record(self, channel):
        """Encode a 3-second, 10 FPS recording and register it in the catalogue."""
        writer = VideoWriter(channel, self.root, resolution=(64, 48))
        for pixel in range(30):
            writer.add_frame(np.full((48, 64, 3), pixel * 8, dtype=np.uint8))
        with patch.object(writer, "_calculate_fps", return_value=10):
            writer.write()
        import_completed(self.db, self.root)
        return self.db.conn.execute(
            "SELECT v.filename FROM recording_variants v JOIN recordings r ON r.id = v.recording_id "
            "JOIN cameras c ON c.id = r.camera_id WHERE c.channel_name = ? AND v.format = 'mp4'",
            (channel,)
        ).fetchone()[0]

    def source_hash(self, filename):
        path, = self.db.conn.execute(
            "SELECT path FROM recording_variants WHERE filename = ?", (filename,)).fetchone()
        return hashlib.sha256((self.root / path).read_bytes()).hexdigest()

    def export(self, headers, filename=None, start=0.5, end=1.5):
        return self.client.post(EXPORTS_URL, json={
            "filename": filename or self.front, "start_time": start, "end_time": end
        }, headers=headers)

    def assert_mp4(self, response, seconds):
        try:
            if response.status_code != 200:
                self.fail(f"{response.status_code}: {response.get_data(as_text=True)}")
            self.assertEqual(response.mimetype, "video/mp4")
            self.assertIn("attachment", response.headers["Content-Disposition"])
            data = response.data
        finally:
            response.close()   # releases the temporary export file
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as clip:
            clip.write(data)
        self.addCleanup(Path(clip.name).unlink)
        video = cv2.VideoCapture(clip.name)
        try:
            frames = video.get(cv2.CAP_PROP_FRAME_COUNT)
            fps = video.get(cv2.CAP_PROP_FPS)
            self.assertTrue(video.read()[0])
        finally:
            video.release()
        self.assertAlmostEqual(frames / fps, seconds, delta=0.15)

    def test_missing_invalid_or_expired_token_is_refused(self):
        expired = jwt.encode({
            "sub": "manager-id", "client_ip": "127.0.0.1",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1)
        }, self.server.authenticator.secret, algorithm="HS256")
        for headers in ({}, {"x-access-token": "not-a-token"}, {"x-access-token": expired}):
            with self.subTest(headers=list(headers)):
                self.assertEqual(self.export(headers).status_code, 401)
        self.export_calls.assert_not_called()

    def test_assigned_viewer_cannot_export(self):
        before = self.source_hash(self.front)
        self.assert_error(self.export(self.headers["viewer"]), 403,
                          "Manager or administrator role required")
        self.export_calls.assert_not_called()
        self.assertEqual(self.source_hash(self.front), before)

    def test_unassigned_manager_or_administrator_cannot_reach_the_recording(self):
        for role, filename in (("manager", self.till), ("administrator", self.front)):
            with self.subTest(role=role):
                self.assert_error(self.export(self.headers[role], filename), 404,
                                  "Recording unavailable")
        self.export_calls.assert_not_called()

    def test_assigned_manager_and_administrator_get_a_valid_mp4(self):
        for role, filename in (("manager", self.front), ("administrator", self.till)):
            with self.subTest(role=role):
                before = self.source_hash(filename)
                self.assert_mp4(self.export(self.headers[role], filename), seconds=1.0)
                self.assertEqual(self.source_hash(filename), before)

    def test_token_issued_before_demotion_loses_export_access(self):
        self.assert_mp4(self.export(self.headers["manager"]), seconds=1.0)
        self.export_calls.reset_mock()
        with self.db.conn:
            self.db.conn.execute("UPDATE users SET role = 'viewer' WHERE id = 'manager-id'")
        self.assert_error(self.export(self.headers["manager"]), 403,
                          "Manager or administrator role required")
        self.export_calls.assert_not_called()

    def test_revoked_assignment_is_checked_on_every_request(self):
        self.assert_mp4(self.export(self.headers["manager"]), seconds=1.0)
        self.export_calls.reset_mock()
        self.db.revoke_camera("manager-id", "front")
        self.assert_error(self.export(self.headers["manager"]), 404, "Recording unavailable")
        self.export_calls.assert_not_called()

    def test_invalid_ranges_create_no_export(self):
        for start, end, error in ((1, 1, "The end time must be greater than the start time"),
                                  (2, 1, "The end time must be greater than the start time")):
            with self.subTest(start=start, end=end):
                self.assert_error(self.export(self.headers["manager"], start=start, end=end), 400, error)
        self.export_calls.assert_not_called()
        # Past the end of the footage: rejected by the exporter before any file is returned.
        self.assert_error(self.export(self.headers["manager"], start=0, end=500), 400,
                          "Select a range within the recording")
