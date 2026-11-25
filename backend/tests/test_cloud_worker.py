import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from smart_sec_cam.video.cloud_storage import S3Store, queue_status
from smart_sec_cam.video.cloud_worker import check_connection, configured_store, main


class WorkerTests(unittest.TestCase):
    def test_connection_check_uses_only_unique_disposable_objects(self):
        store = Mock()
        store.sha256.return_value = hashlib.sha256(
            b'camera-management-system cloud connection check\n').hexdigest()
        check_connection(store)
        key = store.upload.call_args[0][0]
        self.assertTrue(key.startswith('health-check/'))
        store.delete.assert_called_once_with(key)
        check_connection(store)
        self.assertNotEqual(key, store.upload.call_args[0][0])

    def test_probe_cleans_up_after_corrupt_read_or_uncertain_upload(self):
        for failure in ('read', 'write'):
            with self.subTest(failure=failure):
                store = Mock()
                store.sha256.return_value = 'bad-checksum'
                if failure == 'write':
                    store.upload.side_effect = OSError('connection lost after upload')
                with self.assertRaises((OSError, ValueError)):
                    check_connection(store)
                store.delete.assert_called_once_with(store.upload.call_args[0][0])

    def test_probe_delete_failure_is_not_reported_as_success(self):
        store = Mock()
        store.sha256.return_value = hashlib.sha256(
            b'camera-management-system cloud connection check\n').hexdigest()
        store.delete.side_effect = OSError('offline')
        with self.assertRaises(OSError):
            check_connection(store)

    def test_invalid_settings_fail_before_sdk_or_database_access(self):
        for endpoint in ('', 'http://example.com', 'https://user:secret@example.com',
                         'https://example.com/bucket', 'https://example.com?secret=x'):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                configured_store({'CLOUD_PROVIDER': 's3', 'CLOUD_ENDPOINT_URL': endpoint, 'CLOUD_BUCKET': 'test'})
        with self.assertRaises(ValueError):
            configured_store({'CLOUD_PROVIDER': 's3', 'CLOUD_ENDPOINT_URL': 'https://example.com'})

    def test_status_is_read_only_and_needs_no_credentials_or_sdk(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'shared.db')
            with sqlite3.connect(path) as conn:
                conn.execute('CREATE TABLE application(id INTEGER)')
            before = path.read_bytes()
            output = io.StringIO()
            with patch('smart_sec_cam.video.cloud_worker.configured_store') as factory:
                with redirect_stdout(output):
                    self.assertEqual(main(['--status', '--database', str(path)]), 0)
                factory.assert_not_called()
            self.assertFalse(json.loads(output.getvalue())['queue_ready'])
            self.assertEqual(path.read_bytes(), before)

    def test_status_missing_database_does_not_create_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'missing.db')
            with self.assertRaises(SystemExit) as error:
                main(['--status', '--database', str(path)])
            self.assertEqual(error.exception.code, 2)
            self.assertFalse(path.exists())

    def test_s3_readback_closes_body_even_after_read_failure(self):
        client = Mock()
        body = Mock()
        body.read.side_effect = OSError('disconnected')
        client.get_object.return_value = {'Body': body}
        with self.assertRaises(OSError):
            S3Store(client, 'private').sha256('routine/key')
        body.close.assert_called_once()

    def test_s3_adapter_sends_private_upload_without_public_acl(self):
        client = Mock()
        source = io.BytesIO(b'clip')
        store = S3Store(client, 'private')
        store.upload('routine/key', source, 4, 'mp4')
        client.put_object.assert_called_once_with(
            Bucket='private', Key='routine/key', Body=source,
            ContentLength=4, ContentType='video/mp4')
        body = io.BytesIO(b'clip')
        client.get_object.return_value = {'Body': body}
        self.assertEqual(store.sha256('routine/key'), hashlib.sha256(b'clip').hexdigest())
        self.assertTrue(body.closed)
        store.delete('routine/key')
        client.delete_object.assert_called_once_with(Bucket='private', Key='routine/key')


if __name__ == '__main__':
    unittest.main()
