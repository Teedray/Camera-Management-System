import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from test_admin_camera_api import AdminApiTestCase
from test_cloud_storage import MemoryStore
from smart_sec_cam.video.cloud_storage import CloudQueue


class PlaybackStore(MemoryStore):
    identity = 'test'

    def download(self, key, target):
        if self.offline:
            raise OSError('offline')
        target.write(self.objects[key])


class CloudPlaybackTests(AdminApiTestCase):
    def setUp(self):
        super().setUp()
        self.db.add_camera('camera', 'Front', 'Door', 'front')
        self.db.assign_camera('viewer-id', 'camera')
        self.db.assign_camera('manager-id', 'camera')
        self.now = datetime.now(timezone.utc)
        self.rid = 'a' * 32
        self.filename = 'front__2026-01-01_00:00:00-' + self.rid + '.mp4'
        self.payload = b'0123456789'
        capture = self.now - timedelta(hours=2)
        relative = 'catalogue/' + self.rid + '/clip.mp4'
        local = Path(self.server.VIDEO_DIR, relative)
        local.parent.mkdir(parents=True)
        local.write_bytes(self.payload)
        with self.db.conn:
            self.db.conn.execute('INSERT INTO recordings VALUES (?,?,?,?)',
                                 (self.rid, 'camera', capture.isoformat(), capture.isoformat()))
            self.db.conn.execute('INSERT INTO recording_variants VALUES (?,?,?,?,?,?)',
                                 (self.rid, 'mp4', self.filename, relative, len(self.payload), 30))
        self.store = PlaybackStore()
        self.queue = CloudQueue(self.db.conn, self.server.VIDEO_DIR, self.store, local_cleanup=True)
        self.queue.tick(capture)
        self.queue.tick(self.now)
        self.assertFalse(local.exists())
        self.start_patch('configured_store', lambda environ: self.store)
        self.url = '/api/video/' + self.filename

    def test_cloud_only_recording_is_listed_and_supports_full_and_range_playback(self):
        headers = self.headers['viewer']
        listing = self.client.get('/api/video/video-list?video-format=mp4', headers=headers)
        self.assertEqual(listing.get_json()['videos'], [self.filename])
        with self.client.get(self.url, headers=headers) as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, self.payload)
            self.assertIn('no-store', response.headers['Cache-Control'])
        with self.client.get(self.url, headers=dict(headers, Range='bytes=2-5')) as response:
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.data, b'2345')
            self.assertEqual(response.headers['Content-Range'], 'bytes 2-5/10')
        self.assertEqual(self.db.conn.execute('SELECT COUNT(*) FROM cloud_holds').fetchone()[0], 0)

    def test_search_catalogue_lists_cloud_only_recording_as_mp4(self):
        # The website's search uses /api/v1/recordings; footage whose local copy
        # was cleaned up must stay findable there, as its MP4 cloud copy.
        response = self.client.get('/api/v1/recordings', headers=self.headers['viewer'])
        self.assertEqual(response.status_code, 200)
        items = response.get_json()['data']['items']
        self.assertEqual([i['filename'] for i in items], [self.filename])
        self.assertEqual(items[0]['format'], 'mp4')
        self.assertEqual(items[0]['camera_id'], 'camera')

    def test_search_catalogue_hides_expired_cloud_only_recording(self):
        with self.db.conn:
            self.db.conn.execute("UPDATE cloud_uploads SET expires_at=?",
                                 ((self.now - timedelta(seconds=1)).isoformat(),))
        response = self.client.get('/api/v1/recordings', headers=self.headers['viewer'])
        self.assertEqual(response.get_json()['data']['items'], [])

    def test_camera_recordings_count_cloud_only_footage_not_as_a_gap(self):
        capture = self.now - timedelta(hours=2)
        with self.db.conn:
            self.db.conn.execute('UPDATE recordings SET capture_start_utc=? WHERE id=?',
                                 ((capture - timedelta(seconds=30)).isoformat(), self.rid))
        response = self.client.get(
            '/api/v1/cameras/camera/recordings?start=' + (capture - timedelta(seconds=30)).isoformat().replace('+00:00', 'Z')
            + '&end=' + capture.isoformat().replace('+00:00', 'Z'), headers=self.headers['manager'])
        data = response.get_json()['data']
        self.assertEqual([s['id'] for s in data['segments']], [self.rid])
        self.assertEqual(data['gaps'], [])

    def test_hold_release_survives_a_briefly_locked_database(self):
        import sqlite3, threading
        from smart_sec_cam.video.cloud_playback import _delete_hold
        with self.db.conn:
            self.db.conn.execute("INSERT INTO cloud_holds VALUES (?, 'playback:test')", (self.rid,))
        db_path = self.db.conn.execute('PRAGMA database_list').fetchone()[2]
        blocker = sqlite3.connect(db_path, timeout=5, check_same_thread=False)
        blocker.execute('BEGIN EXCLUSIVE')
        threading.Timer(1.0, blocker.rollback).start()
        self.db.conn.execute('PRAGMA busy_timeout = 100')
        try:
            self.assertTrue(_delete_hold(self.db.conn, self.rid, 'playback:test', attempts=20, wait=0.2))
        finally:
            blocker.close()
        self.assertEqual(self.db.conn.execute('SELECT COUNT(*) FROM cloud_holds').fetchone()[0], 0)

    def test_revoked_or_unassigned_camera_never_downloads_cloud_bytes(self):
        def forbidden(*args):
            raise AssertionError('must not download without camera permission')
        self.store.download = forbidden
        self.assertEqual(self.client.get(self.url, headers=self.headers['administrator']).status_code, 404)
        self.db.revoke_camera('viewer-id', 'camera')
        self.assertEqual(self.client.get(self.url, headers=self.headers['viewer']).status_code, 404)
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_every_new_range_request_rechecks_current_assignment(self):
        headers = dict(self.headers['viewer'], Range='bytes=0-1')
        self.assertEqual(self.client.get(self.url, headers=headers).status_code, 206)
        self.db.revoke_camera('viewer-id', 'camera')
        self.assertEqual(self.client.get(self.url, headers=headers).status_code, 404)

    def test_cloud_expiry_hides_recording_unless_held(self):
        with self.db.conn:
            self.db.conn.execute('UPDATE cloud_uploads SET expires_at=?',
                                 ((self.now - timedelta(seconds=1)).isoformat(),))
        self.assertEqual(self.client.get(self.url, headers=self.headers['viewer']).status_code, 404)
        self.queue.hold(self.rid, 'incident:saved')
        self.assertEqual(self.client.get(self.url, headers=self.headers['viewer']).status_code, 200)

    def test_cloud_failure_or_corruption_is_not_served_as_video(self):
        self.store.offline = True
        self.assertEqual(self.client.get(self.url, headers=self.headers['viewer']).status_code, 503)
        self.store.offline = False
        self.store.objects['routine/' + self.rid + '/clip.mp4'] = b'corrupted!'
        self.assertEqual(self.client.get(self.url, headers=self.headers['viewer']).status_code, 503)
        self.assertEqual(self.db.conn.execute('SELECT COUNT(*) FROM cloud_holds').fetchone()[0], 0)

    def test_provider_mismatch_does_not_return_footage(self):
        self.store.identity = 'drive:another-account'
        self.assertEqual(self.client.get(self.url, headers=self.headers['viewer']).status_code, 503)

    def test_assignment_revoked_during_download_is_refused(self):
        original = self.store.download
        def revoke(key, target):
            original(key, target)
            self.db.revoke_camera('viewer-id', 'camera')
        self.store.download = revoke
        self.assertEqual(self.client.get(self.url, headers=self.headers['viewer']).status_code, 404)

    def test_invalid_range_returns_416_and_releases_hold(self):
        self.assertEqual(self.client.get(self.url, headers=dict(
            self.headers['viewer'], Range='bytes=999-1000')).status_code, 416)
        self.assertEqual(self.db.conn.execute('SELECT COUNT(*) FROM cloud_holds').fetchone()[0], 0)

    def test_cloud_listing_survives_missing_local_root_directory(self):
        self.start_patch('VIDEO_DIR', str(Path(self.server.VIDEO_DIR, 'absent')))
        response = self.client.get('/api/video/video-list?video-format=mp4',
                                   headers=self.headers['viewer'])
        self.assertEqual(response.get_json()['videos'], [self.filename])
