"""Integration of incident clips (F04) with the shared database and access control (F06/SR-06)."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from smart_sec_cam.video.catalogue import import_completed
from smart_sec_cam.video.writer import VideoWriter
from test_admin_camera_api import AdminApiTestCase


INCIDENTS_URL = "/api/v1/incidents"


class IncidentApiTest(AdminApiTestCase):
    def setUp(self):
        super().setUp()
        self.root = Path(self.server.VIDEO_DIR)
        archive = tempfile.TemporaryDirectory()
        self.addCleanup(archive.cleanup)
        self.archive = Path(archive.name)
        self.start_patch("INCIDENT_ARCHIVE_DIR", archive.name)

        self.db.add_camera("front", "Front", "Entrance", "front-stream")
        self.db.add_camera("till", "Till", "Cashier", "till-stream")
        for user_id in ("manager-id", "viewer-id"):
            self.db.assign_camera(user_id, "front")
        self.db.assign_camera("administrator-id", "till")

        self.front = self.record("front-stream")
        self.till = self.record("till-stream")

    def record(self, channel):
        """Encode a 3-second, 10 FPS recording and register it in the catalogue."""
        writer = VideoWriter(channel, self.root, resolution=(64, 48))
        for pixel in range(30):
            writer.add_frame(np.full((48, 64, 3), pixel * 8, dtype=np.uint8))
        with patch.object(writer, "_calculate_fps", return_value=10):
            writer.write()
        import_completed(self.db, self.root)
        return self.db.conn.execute(
            "SELECT v.filename FROM recording_variants v "
            "JOIN recordings r ON r.id = v.recording_id "
            "JOIN cameras c ON c.id = r.camera_id "
            "WHERE c.channel_name = ? AND v.format = 'mp4'",
            (channel,)
        ).fetchone()[0]

    def save(self, role="manager", **overrides):
        body = {
            "filename": self.front, "start_time": 1, "end_time": 2,
            "title": "Shoplifting at entrance", "notes": "Customer left without paying."
        }
        body.update(overrides)
        return self.client.post(INCIDENTS_URL, json=body, headers=self.headers[role])

    def test_manager_saves_verified_flagged_clip_into_shared_database(self):
        response = self.save()
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        incident = response.get_json()["data"]
        self.assertEqual(incident["camera"], "front-stream")
        self.assertTrue(incident["incident_flag"])
        self.assertEqual(incident["title"], "Shoplifting at entrance")
        self.assertEqual(incident["notes"], "Customer left without paying.")
        self.assertEqual(incident["created_by"], "manager-id")
        self.assertIsNotNone(incident["created_at"])

        # Stored in the same SQL database as users, cameras and the catalogue.
        filename, = self.db.conn.execute(
            "SELECT filename FROM incident_clips WHERE id = ?", (incident["id"],)
        ).fetchone()
        clip = self.archive / filename
        self.assertTrue(clip.is_file())
        self.assertNotIn(":", filename)

        video = cv2.VideoCapture(str(clip))
        try:
            self.assertTrue(video.isOpened())
            fps = video.get(cv2.CAP_PROP_FPS)
            self.assertAlmostEqual(video.get(cv2.CAP_PROP_FRAME_COUNT) / fps, 1.0, places=1)
        finally:
            video.release()

        # The archived clip is retrievable through the API (AC-04-03).
        with self.client.get(incident["video_url"], headers=self.headers["manager"]) as video_response:
            self.assertEqual(video_response.status_code, 200)
            self.assertEqual(video_response.mimetype, "video/mp4")
            self.assertEqual(video_response.data, clip.read_bytes())

    def test_viewer_role_cannot_save_incident_clips(self):
        response = self.save("viewer")
        self.assert_error(response, 403, "Manager or administrator role required")
        self.assertEqual(list(self.archive.iterdir()), [])

    def test_unassigned_camera_is_refused_before_footage_is_reached(self):
        response = self.save(filename=self.till)
        self.assert_error(response, 404, "Recording unavailable")
        self.assertEqual(list(self.archive.iterdir()), [])
        self.assertEqual(self.server.incident_repository().list_incidents(), [])

    def test_invalid_requests_are_rejected_without_side_effects(self):
        for overrides, error in (
            ({"title": " "}, "title must be a non-empty text value"),
            ({"start_time": 2, "end_time": 2}, "start_time must be before end_time"),
            ({"start_time": 2, "end_time": 1}, "start_time must be before end_time"),
            ({"start_time": "1"}, "start_time and end_time must be numbers of seconds"),
            ({"end_time": True}, "start_time and end_time must be numbers of seconds"),
            ({"filename": "../secret.mp4"}, "filename must be a recording name"),
            ({"camera": "front"}, "Unsupported incident fields"),
        ):
            with self.subTest(overrides=overrides):
                self.assert_error(self.save(**overrides), 400, error)

        # A range beyond the recording fails verification (SAF-02).
        self.assert_error(
            self.save(end_time=60), 422,
            "Incident clip could not be saved; check the selected interval"
        )
        self.assertEqual(list(self.archive.iterdir()), [])

    def test_incident_listing_and_playback_follow_camera_assignments(self):
        front_id = self.save().get_json()["data"]["id"]
        till_id = self.save(
            "administrator", filename=self.till, title="Till discrepancy"
        ).get_json()["data"]["id"]

        def listed(role):
            response = self.client.get(INCIDENTS_URL, headers=self.headers[role])
            self.assertEqual(response.status_code, 200)
            return [item["id"] for item in response.get_json()["data"]["items"]]

        self.assertEqual(listed("manager"), [front_id])
        self.assertEqual(listed("viewer"), [front_id])
        self.assertEqual(listed("administrator"), [till_id])

        detail = self.client.get(f"{INCIDENTS_URL}/{front_id}", headers=self.headers["viewer"])
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.get_json()["data"]["title"], "Shoplifting at entrance")
        self.assertEqual(
            self.client.get(f"{INCIDENTS_URL}/{till_id}", headers=self.headers["viewer"]).status_code,
            404
        )
        self.assertEqual(
            self.client.get(f"{INCIDENTS_URL}/{till_id}/video",
                            query_string={"token": self.headers["viewer"]["x-access-token"]}).status_code,
            404
        )

        # Revoking the camera hides its incidents as well as its recordings.
        self.db.revoke_camera("viewer-id", "front")
        self.assertEqual(listed("viewer"), [])
        self.assertEqual(
            self.client.get(f"{INCIDENTS_URL}/{front_id}/video", headers=self.headers["viewer"]).status_code,
            404
        )

    def test_incident_clip_survives_removal_of_the_source_recording(self):
        incident_id = self.save().get_json()["data"]["id"]
        # Simulate routine retention deleting the catalogued source footage.
        for source in (self.root / "catalogue").rglob("clip.*"):
            source.unlink()
        self.assertEqual(
            self.client.get("/api/video/" + self.front, headers=self.headers["manager"]).status_code,
            404
        )
        response = self.client.get(f"{INCIDENTS_URL}/{incident_id}/video", headers=self.headers["manager"])
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_endpoints_require_authentication(self):
        for method, url in (
            ("post", INCIDENTS_URL), ("get", INCIDENTS_URL),
            ("get", f"{INCIDENTS_URL}/x"), ("get", f"{INCIDENTS_URL}/x/video"),
        ):
            with self.subTest(method=method, url=url):
                self.assert_error(getattr(self.client, method)(url), 401, "Missing token")
