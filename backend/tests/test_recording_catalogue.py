import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from smart_sec_cam.auth.database import AuthDatabase
from smart_sec_cam.video.catalogue import import_completed
from smart_sec_cam.video.writer import VideoWriter
from test_admin_camera_api import AdminApiTestCase


class RecordingCatalogueTest(AdminApiTestCase):
    def setUp(self):
        super().setUp()
        self.root = Path(self.server.VIDEO_DIR)
        self.db.add_camera("front", "Front", "Entrance", "front-stream")
        self.db.assign_camera("viewer-id", "front")

    def encode(self, channel="front-stream"):
        writer = VideoWriter(channel, self.root)
        before = datetime.now(timezone.utc)
        for pixel in range(12):
            writer.add_frame(np.full((48, 64, 3), pixel, dtype=np.uint8))
        with patch.object(writer, "_calculate_fps", return_value=6):
            writer.write()
        marker, = (self.root / "catalogue-pending").glob("*.json")
        manifest = json.loads(marker.read_text())
        start = datetime.fromisoformat(manifest["start"])
        end = datetime.fromisoformat(manifest["end"])
        self.assertEqual(start.utcoffset(), timedelta(0))
        self.assertEqual(end.utcoffset(), timedelta(0))
        self.assertLessEqual(before, start)
        self.assertLessEqual(start, end)
        self.assertLessEqual(end, datetime.now(timezone.utc))
        return marker, manifest

    def test_completed_pair_replay_and_permissions(self):
        marker, manifest = self.encode()
        viewer = self.headers["viewer"]
        listing = self.client.get("/api/video/video-list", headers=viewer)
        self.assertEqual(listing.status_code, 200)
        webm, = listing.get_json()["videos"]
        # Repeat delivery, as after a crash between SQLite commit and acknowledgement.
        marker.write_text(json.dumps(manifest))
        import_completed(self.db, self.root)
        self.assertFalse(marker.exists())
        self.assertEqual(self.db.conn.execute(
            "SELECT id,camera_id,capture_start_utc,capture_end_utc FROM recordings"
        ).fetchall(), [(manifest["id"], "front", manifest["start"], manifest["end"])])
        rows = self.db.conn.execute(
            "SELECT format,filename,path,size_bytes,duration_seconds FROM recording_variants"
        ).fetchall()
        self.assertEqual({r[0] for r in rows}, {"webm", "mp4"})
        self.assertEqual(len(rows), 2)
        for fmt, name, relative, size, duration in rows:
            file = self.root / relative
            self.assertEqual(size, file.stat().st_size)
            self.assertAlmostEqual(duration, 2, places=1)
            self.assertEqual(self.client.get("/api/video/video-list?video-format=" + fmt,
                                             headers=viewer).get_json()["videos"], [name])
            with self.client.get("/api/video/" + name, headers=viewer) as response:
                self.assertEqual(response.data, file.read_bytes())
                self.assertEqual(response.mimetype, "video/" + fmt)
            self.assertEqual(self.client.get("/api/video/" + name,
                                             headers=self.headers["administrator"]).status_code, 404)
        self.db.revoke_camera("viewer-id", "front")
        self.assertEqual(self.client.get("/api/video/video-list", headers=viewer).get_json()["videos"], [])
        self.assertEqual(self.client.get("/api/video/" + webm, headers=viewer).status_code, 404)

    def test_legacy_and_catalogued_clips_share_the_list_and_range_playback(self):
        self.encode()
        legacy = "front-stream__2001-01-01_00:00:00.webm"
        (self.root / legacy).write_bytes(b"legacy")
        viewer = self.headers["viewer"]
        names = self.client.get("/api/video/video-list", headers=viewer).get_json()["videos"]
        self.assertEqual(len(names), 2)
        self.assertEqual(names[1], legacy)
        with self.client.get("/api/video/" + names[0], query_string={"token": viewer["x-access-token"]},
                             headers={"Range": "bytes=0-3"}) as response:
            self.assertEqual(response.status_code, 206)
            self.assertEqual(len(response.data), 4)
        with self.client.get("/api/video/" + legacy, headers=viewer) as response:
            self.assertEqual(response.data, b"legacy")

    def test_failed_encoder_never_publishes_partial_pair(self):
        writer = VideoWriter("front-stream", self.root)
        writer.add_frame(np.zeros((48, 64, 3), dtype=np.uint8))
        # An unopened writer: the MP4 encoder fails after the WebM succeeded.
        with patch.object(writer, "_calculate_fps", return_value=1):
            with patch("smart_sec_cam.video.writer.open_mp4_writer",
                       side_effect=lambda *args: cv2.VideoWriter()):
                with self.assertRaises(RuntimeError):
                    writer.write()
        self.assertEqual(self.client.get("/api/video/video-list",
                                         headers=self.headers["viewer"]).get_json()["videos"], [])
        self.assertEqual(self.db.conn.execute("SELECT count(*) FROM recordings").fetchone(), (0,))

    def test_unknown_camera_is_retried_and_symlinks_are_hidden(self):
        marker, _ = self.encode("later")
        import_completed(self.db, self.root)
        self.assertTrue(marker.exists())
        self.assertEqual(self.db.conn.execute("SELECT count(*) FROM recordings").fetchone(), (0,))
        self.db.add_camera("later-id", "Later", "Office", "later")
        import_completed(self.db, self.root)
        self.db.assign_camera("viewer-id", "later-id")
        name, relative = self.db.conn.execute(
            "SELECT filename,path FROM recording_variants WHERE format='mp4'"
        ).fetchone()
        path = self.root / relative
        path.rename(path.with_suffix(".original"))
        os.symlink(path.with_suffix(".original"), path)
        viewer = self.headers["viewer"]
        self.assertEqual(self.client.get("/api/video/" + name, headers=viewer).status_code, 404)
        self.assertEqual(self.client.get("/api/video/video-list?video-format=mp4",
                                         headers=viewer).get_json()["videos"], [])

    def test_upgrade_keeps_existing_cameras_and_assignments(self):
        # Reopen the isolated fixture as a pre-catalogue database.
        self.db.conn.executescript("DROP TABLE recording_variants; DROP TABLE recordings;")
        with patch.object(AuthDatabase, "DATABASE_DIR", str(self.root)):
            upgraded = AuthDatabase("test")
        self.addCleanup(upgraded.conn.close)
        self.assertTrue(upgraded.can_access_camera("viewer-id", "front"))
        self.assertEqual(upgraded.get_num_users(), 3)
        self.assertEqual(upgraded.conn.execute("SELECT count(*) FROM recordings").fetchone(), (0,))
        self.assertEqual(upgraded.conn.execute("PRAGMA foreign_key_check").fetchall(), [])
