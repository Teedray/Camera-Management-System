from datetime import datetime, timedelta, timezone
from pathlib import Path

from test_admin_camera_api import AdminApiTestCase
import test_incident_api as incident_fixtures
from test_cloud_playback import PlaybackStore
from smart_sec_cam.video.cloud_storage import CloudQueue


class CloudIncidentTests(AdminApiTestCase):
    record = incident_fixtures.IncidentApiTest.record
    save = incident_fixtures.IncidentApiTest.save

    def setUp(self):
        # Reuse its camera/encoder setup without inheriting its test methods.
        super().setUp()
        import tempfile
        self.root = Path(self.server.VIDEO_DIR)
        archive = tempfile.TemporaryDirectory()
        self.addCleanup(archive.cleanup)
        self.archive = Path(archive.name)
        self.start_patch('INCIDENT_ARCHIVE_DIR', archive.name)
        self.db.add_camera('front', 'Front', 'Entrance', 'front-stream')
        self.db.assign_camera('manager-id', 'front')
        self.db.assign_camera('viewer-id', 'front')
        self.front = self.record('front-stream')
        self.store = PlaybackStore()
        self.now = datetime.now(timezone.utc)
        capture = self.now - timedelta(hours=2)
        with self.db.conn:
            self.db.conn.execute('UPDATE recordings SET capture_start_utc=?,capture_end_utc=?',
                                 (capture.isoformat(), capture.isoformat()))
        self.queue = CloudQueue(self.db.conn, self.root, self.store, local_cleanup=True)
        self.queue.tick(capture)
        self.queue.tick(self.now)
        self.assertFalse(list(self.root.glob('catalogue/*/clip.*')))
        self.start_patch('configured_store', lambda environ: self.store)

    def test_manager_can_save_verified_incident_after_local_buffer_cleanup(self):
        response = self.save()
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        video_url = response.get_json()['data']['video_url']
        playback = self.client.get(video_url, headers=self.headers['manager'])
        self.assertEqual(playback.status_code, 200)
        self.assertTrue(playback.data)
        self.assertEqual(self.db.conn.execute('SELECT COUNT(*) FROM cloud_holds').fetchone()[0], 0)
        self.queue.cleanup = True
        self.queue.tick(self.now + timedelta(days=31))
        self.assertTrue(list(self.archive.glob('*.mp4')))
        self.assertEqual(self.client.get(video_url, headers=self.headers['manager']).status_code, 200)

    def test_viewer_cannot_save_cloud_incident(self):
        self.assertEqual(self.save('viewer').status_code, 403)

    def test_new_incident_cannot_resurrect_expired_cloud_source(self):
        with self.db.conn:
            self.db.conn.execute('UPDATE cloud_uploads SET expires_at=?',
                                 ((self.now - timedelta(seconds=1)).isoformat(),))
        self.assertEqual(self.save().status_code, 404)
        self.assertFalse(list(self.archive.glob('*.mp4')))
