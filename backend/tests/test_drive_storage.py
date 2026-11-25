import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from smart_sec_cam.video.drive_storage import DriveStore
import test_cloud_storage as fixtures
from smart_sec_cam.video.cloud_storage import CloudQueue


class Missing(Exception):
    resp = SimpleNamespace(status=404)


class Request:
    def __init__(self, action):
        self.action = action

    def execute(self, **kwargs):
        return self.action()

    def next_chunk(self, **kwargs):
        return None, self.action()


class FakeDrive:
    def __init__(self):
        self.items = {}
        self.generated = 0
        self.lose_response = False
        self.private = True

    def files(self):
        return self

    def close(self):
        pass

    def list(self, **kwargs):
        return Request(lambda: {'files': []})

    def generateIds(self, **kwargs):
        self.generated += 1
        return Request(lambda: {'ids': ['file-' + str(self.generated)]})

    def get(self, fileId, **kwargs):
        def action():
            if fileId == 'folder':
                return {'mimeType': 'application/vnd.google-apps.folder',
                        'permissions': [{'type': 'user', 'role': 'owner'}] if self.private
                        else [{'type': 'anyone', 'role': 'reader'}]}
            if fileId not in self.items:
                raise Missing()
            return self.items[fileId]
        return Request(action)

    def create(self, body, media_body, **kwargs):
        def action():
            file_id = body['id']
            self.items[file_id] = dict(body, data=media_body.getbytes(0, media_body.size()))
            if self.lose_response:
                self.lose_response = False
                raise OSError('response lost after successful create')
            return {'id': file_id}
        return Request(action)

    def update(self, fileId, media_body, **kwargs):
        def action():
            self.items[fileId]['data'] = media_body.getbytes(0, media_body.size())
            return {'id': fileId}
        return Request(action)

    def get_media(self, fileId):
        return Request(lambda: self.items[fileId]['data'])

    def delete(self, fileId):
        def action():
            self.items.pop(fileId, None)
        return Request(action)


class Download:
    def __init__(self, target, request, **kwargs):
        self.target, self.request = target, request

    def next_chunk(self, **kwargs):
        self.target.write(self.request.execute())
        return None, True


class DriveTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.index = Path(self.directory.name, 'index.db')
        self.service = FakeDrive()
        self.store = DriveStore(self.service, 'folder', self.index)
        self.addCleanup(lambda: self.store.close())
        self.key = 'routine/' + 'a' * 32 + '/clip.mp4'
        patcher = patch('googleapiclient.http.MediaIoBaseDownload', Download)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_upload_download_checksum_and_delete(self):
        self.store.upload(self.key, io.BytesIO(b'video'), 5, 'mp4')
        self.assertEqual(self.store.sha256(self.key), hashlib.sha256(b'video').hexdigest())
        self.store.delete(self.key)
        self.assertFalse(self.service.items)
        self.store.delete(self.key)  # repeat delete is harmless

    def test_uncertain_upload_reuses_persisted_file_id_after_restart(self):
        self.service.lose_response = True
        with self.assertRaises(OSError):
            self.store.upload(self.key, io.BytesIO(b'video'), 5, 'mp4')
        self.store.close()
        self.store = DriveStore(self.service, 'folder', self.index)
        self.store.upload(self.key, io.BytesIO(b'video'), 5, 'mp4')
        self.assertEqual(self.service.generated, 1)
        self.assertEqual(len(self.service.items), 1)

    def test_rejects_unrelated_parent_before_read_or_delete(self):
        self.store.upload(self.key, io.BytesIO(b'video'), 5, 'mp4')
        self.service.items['file-1']['parents'] = ['unrelated-folder']
        with self.assertRaises(ValueError):
            self.store.delete(self.key)
        with self.assertRaises(ValueError):
            self.store.sha256(self.key)
        self.assertEqual(len(self.service.items), 1)

    def test_rejects_shared_folder_and_non_mp4_routine_keys(self):
        self.store.check_folder()
        self.service.private = False
        with self.assertRaises(ValueError):
            self.store.check_folder()
        with self.assertRaises(ValueError):
            self.store.upload(self.key.replace('.mp4', '.webm'), io.BytesIO(b'x'), 1, 'webm')

    def test_duplicate_recovery_is_not_silently_selected(self):
        self.service.list = lambda **kwargs: Request(lambda: {'files': [{'id': 'one'}, {'id': 'two'}]})
        with self.assertRaises(ValueError):
            self.store.upload(self.key, io.BytesIO(b'video'), 5, 'mp4')


class MP4PolicyTests(unittest.TestCase):
    setUp = fixtures.CloudTests.setUp

    def test_default_queue_only_uploads_mp4_and_removes_local_pair_after_verification(self):
        from datetime import timedelta
        queue = CloudQueue(self.db.conn, self.root, self.store, local_cleanup=True)
        queue.tick(self.now)
        self.assertEqual(list(self.store.objects), ['routine/' + self.rid + '/clip.mp4'])
        queue.tick(self.now + timedelta(hours=1))
        self.assertFalse(list(self.root.glob('catalogue/*/clip.*')))
        self.assertEqual(len(self.store.objects), 1)

    def test_changing_provider_cannot_reuse_verified_upload_state(self):
        self.queue.tick(self.now)
        self.store.identity = 'drive:different-destination'
        with self.assertRaises(ValueError):
            CloudQueue(self.db.conn, self.root, self.store)
