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
        self.queue = CloudQueue(self.db.conn, self.root, self.store)

    def states(self):
        return [row[0] for row in self.db.conn.execute('SELECT state FROM cloud_uploads')]

    def test_upload_restart_and_one_hour_cloud_only_expiry(self):
        self.queue.tick(self.now)
        self.assertEqual(self.states(), ['uploaded', 'uploaded'])
        self.assertEqual(len(self.store.objects), 2)
        queue = CloudQueue(self.db.conn, self.root, self.store, cleanup=True)
        queue.tick(self.now + timedelta(minutes=59))
        self.assertEqual(len(self.store.objects), 2)
        queue.tick(self.now + timedelta(hours=1))
        self.assertEqual(self.states(), ['deleted', 'deleted'])
        self.assertFalse(self.store.objects)
        self.assertEqual(len(list(self.root.glob('catalogue/*/clip.*'))), 2)

    def test_outage_retries_survive_reopening_queue(self):
        self.store.offline = True
        self.queue.tick(self.now)
        self.assertEqual(self.states(), ['pending', 'pending'])
        self.store.offline = False
        queue = CloudQueue(self.db.conn, self.root, self.store)
        queue.tick(self.now + timedelta(seconds=1))
        self.assertFalse(self.store.objects)
        queue.tick(self.now + timedelta(seconds=6))
        self.assertEqual(self.states(), ['uploaded', 'uploaded'])
        self.assertEqual(len(self.store.objects), 2)

    def test_checksum_failure_is_not_success(self):
        self.store.corrupt = True
        self.queue.tick(self.now)
        self.assertEqual(self.states(), ['pending', 'pending'])

    def test_holds_protect_both_variants_until_released(self):
        self.queue.hold(self.rid, 'export:job1')
        self.queue.tick(self.now)
        self.queue.cleanup = True
        self.queue.tick(self.now + timedelta(hours=2))
        self.assertEqual(len(self.store.objects), 2)
        self.queue.release(self.rid, 'export:job1')
        self.queue.tick(self.now + timedelta(hours=2, minutes=1))
        self.assertFalse(self.store.objects)

    def test_default_cleanup_is_disabled_and_missing_local_copy_blocks_delete(self):
        self.queue.tick(self.now)
        self.queue.tick(self.now + timedelta(hours=2))
        self.assertEqual(len(self.store.objects), 2)
        (self.root / 'catalogue' / self.rid / 'clip.mp4').unlink()
        self.queue.cleanup = True
        self.queue.tick(self.now + timedelta(hours=2, minutes=1))
        self.assertEqual(list(self.store.objects), ['routine/' + self.rid + '/clip.mp4'])

    def test_old_pending_rows_are_not_uploaded_and_crash_leftovers_are_removed(self):
        self.store.objects['routine/' + self.rid + '/clip.mp4'] = b'crash leftover'
        self.queue.tick(self.now + timedelta(hours=2))
        self.assertEqual(self.states(), ['expired', 'expired'])
        self.queue.cleanup = True
        self.queue.tick(self.now + timedelta(hours=2, minutes=1))
        self.assertFalse(self.store.objects)
        self.assertEqual(self.states(), ['deleted', 'deleted'])

    def test_uploaded_rows_do_not_starve_pending_work(self):
        self.queue.tick(self.now, limit=1)
        self.queue.tick(self.now + timedelta(seconds=1), limit=1)
        self.assertEqual(self.states(), ['uploaded', 'uploaded'])

    def test_legacy_incident_reference_is_protected(self):
        from smart_sec_cam.video.incident_database import IncidentDatabase
        incidents = IncidentDatabase(conn=self.db.conn)
        incidents.add_incident('incident', 'front.mp4', 'front', 0, 10)
        self.queue.tick(self.now)
        self.queue.cleanup = True
        self.queue.tick(self.now + timedelta(hours=2))
        self.assertEqual(len(self.store.objects), 2)

    def test_delete_outage_retries(self):
        self.queue.tick(self.now)
        self.queue.cleanup = True
        self.store.offline = True
        self.queue.tick(self.now + timedelta(hours=2))
        self.assertEqual(self.states(), ['uploaded', 'uploaded'])
        self.store.offline = False
        self.queue.tick(self.now + timedelta(hours=2, minutes=1))
        self.assertEqual(self.states(), ['deleted', 'deleted'])


class CloudFollowupTests(unittest.TestCase):
    setUp = CloudTests.setUp
    states = CloudTests.states

    def test_live_clock_is_rechecked_between_operations(self):
        from unittest.mock import patch
        # Selection starts before expiry, but processing reaches the deadline.
        with patch('smart_sec_cam.video.cloud_storage.utc_now',
                   side_effect=[self.now + timedelta(minutes=59),
                                self.now + timedelta(hours=1),
                                self.now + timedelta(hours=1)]):
            self.queue.tick()
        self.assertFalse(self.store.objects)
        self.assertEqual(self.states(), ['expired', 'expired'])

    def test_retry_never_schedules_past_capture_expiry(self):
        self.store.offline = True
        self.queue.discover(self.now)
        with self.db.conn:
            self.db.conn.execute('UPDATE cloud_uploads SET attempts=20')
        self.queue.tick(self.now + timedelta(minutes=59))
        deadlines = self.db.conn.execute('SELECT next_attempt FROM cloud_uploads').fetchall()
        self.assertEqual({r[0] for r in deadlines}, {(self.now + timedelta(hours=1)).isoformat()})

    def test_expired_retry_delay_is_at_most_one_minute(self):
        self.queue.tick(self.now)
        self.queue.cleanup = True
        self.store.offline = True
        with self.db.conn:
            self.db.conn.execute('UPDATE cloud_uploads SET attempts=20')
        current = self.now + timedelta(hours=2)
        self.queue.tick(current)
        deadlines = self.db.conn.execute('SELECT next_attempt FROM cloud_uploads').fetchall()
        self.assertEqual({r[0] for r in deadlines}, {(current + timedelta(minutes=1)).isoformat()})

    def test_same_size_local_corruption_blocks_cloud_deletion(self):
        self.queue.tick(self.now)
        (self.root / 'catalogue' / self.rid / 'clip.mp4').write_bytes(b'corrupted')
        self.queue.cleanup = True
        self.queue.tick(self.now + timedelta(hours=2))
        self.assertEqual(list(self.store.objects), ['routine/' + self.rid + '/clip.mp4'])
        error, = self.db.conn.execute("SELECT last_error FROM cloud_uploads WHERE format='mp4'").fetchone()
        self.assertEqual(error, 'LocalCopyUnavailable')

    def test_status_counts_failures_holds_and_verified_recent(self):
        from smart_sec_cam.video.cloud_storage import queue_status
        self.store.offline = True
        self.queue.tick(self.now)
        self.queue.hold(self.rid, 'export:1')
        status = queue_status(self.db.conn, self.now)
        self.assertEqual((status['failed'], status['holds'], status['verified_recent']), (2, 1, 0))
        self.store.offline = False
        self.queue.tick(self.now + timedelta(seconds=6))
        status = queue_status(self.db.conn, self.now + timedelta(seconds=6))
        self.assertEqual((status['failed'], status['verified_recent']), (0, 2))
        self.assertEqual(queue_status(self.db.conn, self.now + timedelta(hours=2))['overdue'], 2)

    def test_queue_survives_real_database_reconnection(self):
        self.store.offline = True
        self.queue.tick(self.now)
        # A fresh connection reads the persisted retry deadlines and failure state.
        with sqlite3.connect(self.root / 'test.db') as conn:
            restarted = CloudQueue(conn, self.root, self.store)
            self.store.offline = False
            restarted.tick(self.now + timedelta(seconds=1))
            self.assertFalse(self.store.objects)
            restarted.tick(self.now + timedelta(seconds=6))
        self.assertEqual(self.states(), ['uploaded', 'uploaded'])


if __name__ == '__main__':
    unittest.main()
