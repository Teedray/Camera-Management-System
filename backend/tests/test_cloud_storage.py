import hashlib
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from smart_sec_cam.auth.database import AuthDatabase
from smart_sec_cam.video.cloud_storage import CloudQueue


class MemoryStore:
    def __init__(self):
        self.objects = {}
        self.offline = False
        self.corrupt = False

    def upload(self, key, source, size, fmt):
        if self.offline:
            raise OSError('offline')
        self.objects[key] = source.read()

    def sha256(self, key):
        return 'bad' if self.corrupt else hashlib.sha256(self.objects[key]).hexdigest()

    def delete(self, key):
        if self.offline:
            raise OSError('offline')
        self.objects.pop(key, None)


class CloudTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = AuthDatabase.__new__(AuthDatabase)
        self.db.conn = sqlite3.connect(self.root / 'test.db')
        self.db.conn.execute('PRAGMA foreign_keys=ON')
        self.addCleanup(self.db.conn.close)
        self.db.setup()
        self.db.add_camera('camera', 'Front', 'Door', 'front')
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.rid = 'a' * 32
        with self.db.conn:
            self.db.conn.execute('INSERT INTO recordings VALUES (?,?,?,?)',
                                 (self.rid, 'camera', self.now.isoformat(), self.now.isoformat()))
            for fmt in ('mp4', 'webm'):
                relative = 'catalogue/{}/clip.{}'.format(self.rid, fmt)
                path = self.root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'completed')
                self.db.conn.execute('INSERT INTO recording_variants VALUES (?,?,?,?,?,?)',
                                     (self.rid, fmt, 'front.' + fmt, relative, 9, 30))
        self.store = MemoryStore()
        self.queue = CloudQueue(self.db.conn, self.root, self.store, formats=('mp4','webm'))

    def states(self):
        return [row[0] for row in self.db.conn.execute('SELECT state FROM cloud_uploads')]

    def local_files(self):
        return list(self.root.glob('catalogue/*/clip.*'))

    def test_cloud_retained_at_one_hour_and_expires_at_thirty_days(self):
        self.queue.cleanup = True
        self.queue.tick(self.now)
        self.queue.tick(self.now + timedelta(hours=1))
        self.assertEqual(len(self.store.objects), 2)
        self.queue.tick(self.now + timedelta(days=30, microseconds=-1))
        self.assertEqual(len(self.store.objects), 2)
        self.queue.tick(self.now + timedelta(days=30, minutes=1))
        self.assertEqual(self.states(), ['deleted', 'deleted'])
        self.assertFalse(self.store.objects)
        self.assertEqual(len(self.local_files()), 2)  # local cleanup separately opt-in

    def test_local_cutoff_at_one_hour_keeps_cloud_for_thirty_days(self):
        self.queue.local_cleanup = True
        self.queue.tick(self.now)
        self.queue.tick(self.now + timedelta(hours=1, microseconds=-1))
        self.assertEqual(len(self.local_files()), 2)
        self.queue.tick(self.now + timedelta(hours=1))
        self.assertFalse(self.local_files())
        self.assertEqual(len(self.store.objects), 2)
        self.queue.cleanup = True
        self.queue.tick(self.now + timedelta(days=30))
        self.assertEqual(self.states(), ['deleted', 'deleted'])
        self.assertFalse(self.store.objects)

    def test_both_cleanup_modes_disabled_by_default(self):
        self.queue.tick(self.now)
        self.queue.tick(self.now + timedelta(days=31))
        self.assertEqual(len(self.local_files()), 2)
        self.assertEqual(len(self.store.objects), 2)

    def test_failed_or_unverified_upload_never_removes_local_buffer(self):
        for corrupt in (False, True):
            self.store.offline = not corrupt
            self.store.corrupt = corrupt
            self.queue.local_cleanup = True
            self.queue.tick(self.now + timedelta(hours=2, seconds=10 if corrupt else 0))
            self.assertEqual(self.states(), ['pending', 'pending'])
            self.assertEqual(len(self.local_files()), 2)

    def test_remote_missing_or_corrupt_blocks_local_cleanup(self):
        self.queue.tick(self.now)
        self.queue.local_cleanup = True
        self.store.corrupt = True
        self.queue.tick(self.now + timedelta(hours=1))
        self.assertEqual(len(self.local_files()), 2)
        self.assertEqual({r[0] for r in self.db.conn.execute(
            'SELECT last_error FROM cloud_uploads')}, {'CloudCopyUnavailable'})
        self.store.corrupt = False
        self.queue.tick(self.now + timedelta(hours=1, minutes=1))
        self.assertFalse(self.local_files())

    def test_same_size_local_corruption_is_reported_and_not_removed(self):
        self.queue.tick(self.now)
        (self.root / 'catalogue' / self.rid / 'clip.mp4').write_bytes(b'corrupted')
        self.queue.local_cleanup = True
        self.queue.tick(self.now + timedelta(hours=1))
        self.assertEqual(len(self.local_files()), 1)
        error, = self.db.conn.execute("SELECT last_error FROM cloud_uploads WHERE format='mp4'").fetchone()
        self.assertEqual(error, 'LocalCopyUnavailable')
        self.assertEqual(len(self.store.objects), 2)

    def test_hold_protects_local_and_cloud_until_job_finishes(self):
        self.queue.hold(self.rid, 'export:job1')
        self.queue.local_cleanup = self.queue.cleanup = True
        self.queue.tick(self.now)
        self.queue.tick(self.now + timedelta(days=31))
        self.assertEqual(len(self.local_files()), 2)
        self.assertEqual(len(self.store.objects), 2)
        self.queue.release(self.rid, 'export:job1')
        self.queue.tick(self.now + timedelta(days=31, minutes=1))
        self.assertFalse(self.local_files())
        self.assertFalse(self.store.objects)

    def test_saved_incident_reference_protects_both_tiers(self):
        from smart_sec_cam.video.incident_database import IncidentDatabase
        IncidentDatabase(conn=self.db.conn).add_incident(
            'incident', 'front.mp4', 'front', 0, 10)
        archive = self.root / 'incident_archive' / 'saved.mp4'
        archive.parent.mkdir()
        archive.write_bytes(b'important saved copy')
        self.queue.local_cleanup = self.queue.cleanup = True
        self.queue.tick(self.now)
        self.queue.tick(self.now + timedelta(days=31))
        self.assertEqual(len(self.local_files()), 2)
        self.assertEqual(len(self.store.objects), 2)
        self.assertEqual(archive.read_bytes(), b'important saved copy')

    def test_incident_saved_under_its_archive_name_protects_its_source(self):
        # Real incident records store the archived clip's name in filename and
        # the recording it was cut from in source_filename (merge branch schema).
        from smart_sec_cam.video.incident_database import IncidentDatabase
        IncidentDatabase(conn=self.db.conn)
        columns = {row[1] for row in self.db.conn.execute('PRAGMA table_info(incident_clips)')}
        if 'source_filename' not in columns:
            self.db.conn.execute('ALTER TABLE incident_clips ADD COLUMN source_filename TEXT')
        with self.db.conn:
            self.db.conn.execute(
                "INSERT INTO incident_clips (id, filename, camera, start_time, end_time, incident_flag, source_filename) "
                "VALUES ('incident', 'incident_front_0_100_" + 'a' * 32 + ".mp4', 'front', 0, 10, 1, 'front.mp4')")
        self.queue.local_cleanup = self.queue.cleanup = True
        self.queue.tick(self.now)
        self.queue.tick(self.now + timedelta(days=31))
        self.assertEqual(len(self.local_files()), 2)
        self.assertEqual(len(self.store.objects), 2)

    def test_incident_without_a_source_does_not_protect_unrelated_footage(self):
        from smart_sec_cam.video.incident_database import IncidentDatabase
        IncidentDatabase(conn=self.db.conn)
        columns = {row[1] for row in self.db.conn.execute('PRAGMA table_info(incident_clips)')}
        if 'source_filename' not in columns:
            self.db.conn.execute('ALTER TABLE incident_clips ADD COLUMN source_filename TEXT')
        with self.db.conn:
            self.db.conn.execute(
                "INSERT INTO incident_clips (id, filename, camera, start_time, end_time, incident_flag, source_filename) "
                "VALUES ('other', 'incident_other.mp4', 'front', 0, 10, 1, NULL)")
        self.queue.local_cleanup = self.queue.cleanup = True
        self.queue.tick(self.now)
        self.queue.tick(self.now + timedelta(days=31))
        self.assertFalse(self.store.objects)

    def test_delay_past_local_hour_still_uploads_with_original_thirty_day_expiry(self):
        self.queue.tick(self.now + timedelta(days=2))
        self.assertEqual(self.states(), ['uploaded', 'uploaded'])
        expiries = self.db.conn.execute('SELECT expires_at FROM cloud_uploads').fetchall()
        self.assertEqual({r[0] for r in expiries}, {(self.now + timedelta(days=30)).isoformat()})

    def test_older_than_thirty_days_is_skipped_and_crash_keys_are_cleaned(self):
        self.store.objects['routine/' + self.rid + '/clip.mp4'] = b'crash leftover'
        self.queue.tick(self.now + timedelta(days=31))
        self.assertEqual(self.states(), ['expired', 'expired'])
        self.queue.cleanup = True
        self.queue.tick(self.now + timedelta(days=31, minutes=1))
        self.assertFalse(self.store.objects)
        self.assertEqual(self.states(), ['deleted', 'deleted'])
        # Never delete a local variant that did not reach verified upload state.
        self.assertEqual(len(self.local_files()), 2)

    def test_retry_persists_across_real_database_reconnection(self):
        self.store.offline = True
        self.queue.tick(self.now)
        self.store.offline = False
        with sqlite3.connect(self.root / 'test.db') as conn:
            restarted = CloudQueue(conn, self.root, self.store, formats=('mp4','webm'))
            restarted.tick(self.now + timedelta(seconds=1))
            self.assertFalse(self.store.objects)
            restarted.tick(self.now + timedelta(seconds=6))
        self.assertEqual(self.states(), ['uploaded', 'uploaded'])

    def test_retry_never_schedules_past_thirty_day_capture_expiry(self):
        self.store.offline = True
        self.queue.discover(self.now)
        with self.db.conn:
            self.db.conn.execute('UPDATE cloud_uploads SET attempts=20')
        self.queue.tick(self.now + timedelta(days=30, minutes=-1))
        deadlines = self.db.conn.execute('SELECT next_attempt FROM cloud_uploads').fetchall()
        self.assertEqual({r[0] for r in deadlines}, {(self.now + timedelta(days=30)).isoformat()})

    def test_expired_cloud_delete_failure_retries_within_a_minute(self):
        self.queue.tick(self.now)
        self.queue.cleanup = True
        self.store.offline = True
        with self.db.conn:
            self.db.conn.execute('UPDATE cloud_uploads SET attempts=20')
        current = self.now + timedelta(days=31)
        self.queue.tick(current)
        deadlines = self.db.conn.execute('SELECT next_attempt FROM cloud_uploads').fetchall()
        self.assertEqual({r[0] for r in deadlines}, {(current + timedelta(minutes=1)).isoformat()})
        self.store.offline = False
        self.queue.tick(current + timedelta(minutes=1))
        self.assertFalse(self.store.objects)

    def test_clock_rechecked_at_thirty_day_cloud_boundary(self):
        from unittest.mock import patch
        with patch('smart_sec_cam.video.cloud_storage.utc_now',
                   side_effect=[self.now + timedelta(days=30, minutes=-1),
                                self.now + timedelta(days=30),
                                self.now + timedelta(days=30)]):
            self.queue.tick()
        self.assertFalse(self.store.objects)
        self.assertEqual(self.states(), ['expired', 'expired'])

    def test_uploaded_rows_do_not_starve_pending_work(self):
        self.queue.tick(self.now, limit=1)
        self.queue.tick(self.now + timedelta(seconds=1), limit=1)
        self.assertEqual(self.states(), ['uploaded', 'uploaded'])

    def test_existing_one_hour_deadlines_are_migrated_and_deleted_rows_requeued(self):
        self.queue.tick(self.now)
        with self.db.conn:
            self.db.conn.execute('DELETE FROM cloud_policy')
            self.db.conn.execute("UPDATE cloud_uploads SET expires_at=?,state='deleted'",
                                 ((self.now + timedelta(hours=1)).isoformat(),))
        self.store.objects.clear()
        restarted = CloudQueue(self.db.conn, self.root, self.store, formats=('mp4','webm'))
        self.assertEqual(self.states(), ['pending', 'pending'])
        restarted.tick(self.now + timedelta(hours=2))
        self.assertEqual(self.states(), ['uploaded', 'uploaded'])
        expiries = self.db.conn.execute('SELECT expires_at FROM cloud_uploads').fetchall()
        self.assertEqual({r[0] for r in expiries}, {(self.now + timedelta(days=30)).isoformat()})

    def test_status_reports_both_retention_periods_and_removed_local_variants(self):
        from smart_sec_cam.video.cloud_storage import queue_status
        self.queue.tick(self.now)
        self.queue.local_cleanup = True
        self.queue.tick(self.now + timedelta(hours=1))
        status = queue_status(self.db.conn, self.now + timedelta(hours=2))
        self.assertEqual((status['local_retention_hours'], status['cloud_retention_days']), (1, 30))
        self.assertEqual((status['local_removed'], status['verified_recent'], status['overdue']), (2, 2, 0))


if __name__ == '__main__':
    unittest.main()
