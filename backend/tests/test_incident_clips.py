import os
from datetime import datetime, timedelta

import unittest
import tempfile
from pathlib import Path

import cv2
import numpy as np

from smart_sec_cam.video.incident_clips import IncidentClipManager
from smart_sec_cam.video.incident_database import IncidentDatabase


class TestIncidentClips(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        self.video_dir = self.root / "videos"
        self.archive_dir = self.root / "incident_archive"

        self.video_dir.mkdir()

        # Generate a 3-second test video at 10 FPS
        self.filename = "Entrance.mp4"
        video_path = self.video_dir / self.filename

        writer = cv2.VideoWriter(
            str(video_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            10,
            (320, 240)
        )

        if not writer.isOpened():
            raise RuntimeError("Could not create test video")

        for _ in range(30):
            frame = np.zeros((240, 320, 3), dtype=np.uint8)
            writer.write(frame)

        writer.release()

        self.manager = IncidentClipManager(
            video_dir=self.video_dir,
            archive_dir=self.archive_dir,
            authorization_check=lambda user_id: user_id == "manager-001"
        )

        # Replace the default database with an isolated test database
        self.manager.incident_db.conn.close()
        self.manager.incident_db = IncidentDatabase(
            db_path=self.root / "incidents.db"
        )

    def tearDown(self):
        self.manager.incident_db.conn.close()
        self.temp_dir.cleanup()

    def test_save_incident_clip(self):
        result = self.manager.save_incident_clip(
            self.filename,
            1,
            2,
            "manager-001"
        )

        self.assertTrue(result)

        saved_clips = list(self.archive_dir.glob("*.mp4"))
        self.assertEqual(len(saved_clips), 1)

        video = cv2.VideoCapture(str(saved_clips[0]))
        self.assertTrue(video.isOpened())

        fps = video.get(cv2.CAP_PROP_FPS)
        frames = video.get(cv2.CAP_PROP_FRAME_COUNT)
        video.release()

        self.assertAlmostEqual(frames / fps, 1.0, places=1)

    def test_incident_flag_persistence(self):
        result = self.manager.save_incident_clip(
            self.filename,
            1,
            2,
            "manager-001"
        )

        self.assertTrue(result)

        # Retrieve the incident created by save_incident_clip()
        cursor = self.manager.incident_db.conn.cursor()
        cursor.execute(
            "SELECT id FROM incident_clips"
        )

        row = cursor.fetchone()
        self.assertIsNotNone(row)

        clip_id = row[0]

        # Close and reopen the database to test persistence
        db_path = self.manager.incident_db.db_path
        self.manager.incident_db.conn.close()

        self.manager.incident_db = IncidentDatabase(
            db_path=db_path
        )

        incident = self.manager.incident_db.get_incident(clip_id)

        self.assertIsNotNone(incident)
        self.assertEqual(incident[5], 1)

        # Verify the incident flag belongs to the saved file
        saved_path = self.archive_dir / incident[1]
        self.assertTrue(saved_path.is_file())



    def test_incident_archive_accessibility(self):
        result = self.manager.save_incident_clip(
            self.filename,
            1,
            2,
            "manager-001"
        )

        self.assertTrue(result)

        cursor = self.manager.incident_db.conn.cursor()
        cursor.execute(
            "SELECT filename, incident_flag FROM incident_clips"
        )

        record = cursor.fetchone()
        self.assertIsNotNone(record)

        filename, incident_flag = record
        self.assertEqual(incident_flag, 1)

        archived_video = self.archive_dir / filename

        # Confirm the archived recording exists
        self.assertTrue(archived_video.is_file())

        # Confirm the recording can be opened and read
        video = cv2.VideoCapture(str(archived_video))

        try:
            self.assertTrue(video.isOpened())

            success, frame = video.read()

            self.assertTrue(success)
            self.assertIsNotNone(frame)
        finally:
            video.release()

    def test_incident_survives_cleanup(self):
        # Save an incident clip
        result = self.manager.save_incident_clip(
            self.filename,
            1,
            2,
            "manager-001"
        )

        self.assertTrue(result)

        # Retrieve the archived incident
        cursor = self.manager.incident_db.conn.cursor()
        cursor.execute(
            "SELECT id, filename FROM incident_clips"
        )

        record = cursor.fetchone()
        self.assertIsNotNone(record)

        clip_id, archived_filename = record
        archived_path = self.archive_dir / archived_filename

        # Simulate the original recording becoming 31 days old
        old_time = (
            datetime.now() - timedelta(days=31)
        ).timestamp()

        os.utime(
            self.video_dir / self.filename,
            (old_time, old_time)
        )

        # Simulate normal 30-day retention cleanup
        cutoff = datetime.now() - timedelta(days=30)

        for video in self.video_dir.glob("*.mp4"):
            modified = datetime.fromtimestamp(
                video.stat().st_mtime
            )

            if modified < cutoff:
                video.unlink()

        # Verify the expired original was removed
        self.assertFalse(
            (self.video_dir / self.filename).exists()
        )

        # Verify the incident clip was preserved
        self.assertTrue(archived_path.is_file())

        # Verify its incident flag remains accessible
        incident = self.manager.incident_db.get_incident(clip_id)
        self.assertIsNotNone(incident)
        self.assertEqual(incident[5], 1)

        # Verify the archived footage is still readable
        video = cv2.VideoCapture(str(archived_path))

        try:
            self.assertTrue(video.isOpened())
            success, frame = video.read()
            self.assertTrue(success)
            self.assertIsNotNone(frame)
        finally:
            video.release()

    def test_incident_survives_cleanup(self):
        # Save an incident clip
        result = self.manager.save_incident_clip(
            self.filename,
            1,
            2,
            "manager-001"
        )

        self.assertTrue(result)

        # Retrieve the archived incident
        cursor = self.manager.incident_db.conn.cursor()
        cursor.execute(
            "SELECT id, filename FROM incident_clips"
        )

        record = cursor.fetchone()
        self.assertIsNotNone(record)

        clip_id, archived_filename = record
        archived_path = self.archive_dir / archived_filename

        # Simulate the original recording becoming 31 days old
        old_time = (
            datetime.now() - timedelta(days=31)
        ).timestamp()

        os.utime(
            self.video_dir / self.filename,
            (old_time, old_time)
        )

        # Simulate normal 30-day retention cleanup
        cutoff = datetime.now() - timedelta(days=30)

        for video in self.video_dir.glob("*.mp4"):
            modified = datetime.fromtimestamp(
                video.stat().st_mtime
            )

            if modified < cutoff:
                video.unlink()

        # Verify the expired original was removed
        self.assertFalse(
            (self.video_dir / self.filename).exists()
        )

        # Verify the incident clip was preserved
        self.assertTrue(archived_path.is_file())

        # Verify its incident flag remains accessible
        incident = self.manager.incident_db.get_incident(clip_id)
        self.assertIsNotNone(incident)
        self.assertEqual(incident[5], 1)

        # Verify the archived footage is still readable
        video = cv2.VideoCapture(str(archived_path))

        try:
            self.assertTrue(video.isOpened())
            success, frame = video.read()
            self.assertTrue(success)
            self.assertIsNotNone(frame)
        finally:
            video.release()




    def test_unauthorized_user_cannot_save(self):
        # Record the current state before the request
        before_files = set(self.archive_dir.glob("*.mp4"))

        before_records = self.manager.incident_db.conn.execute(
            "SELECT COUNT(*) FROM incident_clips"
        ).fetchone()[0]

        # Attempt to save footage as an unauthorized user
        result = self.manager.save_incident_clip(
            self.filename,
            1,
            2,
            "guest-001"
        )

        # Verify the request was rejected
        self.assertFalse(result)

        # Verify no additional files were created
        after_files = set(self.archive_dir.glob("*.mp4"))
        self.assertEqual(before_files, after_files)

        # Verify no incident records were created
        after_records = self.manager.incident_db.conn.execute(
            "SELECT COUNT(*) FROM incident_clips"
        ).fetchone()[0]

        self.assertEqual(before_records, after_records)

    def test_incident_title_and_notes(self):
        title = "Suspicious Activity"
        notes = "Individual entered through the front entrance."

        result = self.manager.save_incident_clip(
            self.filename,
            1,
            2,
            "manager-001",
            title=title,
            notes=notes
        )

        self.assertTrue(result)

        cursor = self.manager.incident_db.conn.cursor()
        cursor.execute(
            "SELECT id FROM incident_clips"
        )

        row = cursor.fetchone()
        self.assertIsNotNone(row)

        # Reopen the database to verify persistence
        db_path = self.manager.incident_db.db_path
        self.manager.incident_db.conn.close()

        self.manager.incident_db = IncidentDatabase(
            db_path=db_path
        )

        incident = self.manager.incident_db.get_incident(row[0])

        self.assertIsNotNone(incident)
        self.assertEqual(incident[6], title)
        self.assertEqual(incident[7], notes)

        # Confirm the archived video still exists
        self.assertTrue(
            (self.archive_dir / incident[1]).is_file()
        )
