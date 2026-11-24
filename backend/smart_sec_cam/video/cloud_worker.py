"""Run with python -m smart_sec_cam.video.cloud_worker --help."""
import argparse
import io
import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from smart_sec_cam.auth.database import AuthDatabase
from smart_sec_cam.video.catalogue import import_completed
from smart_sec_cam.video.cloud_storage import CloudQueue, S3Store, digest, queue_status

logger = logging.getLogger(__name__)


def configured_store(environ):
    """Validate settings before importing the optional SDK or touching the database."""
    provider = environ.get('CLOUD_PROVIDER', 'drive')
    if provider == 'drive':
        from smart_sec_cam.video.drive_storage import DriveStore, drive_service
        folder = environ.get('DRIVE_FOLDER_ID', '').strip()
        token = environ.get('DRIVE_TOKEN_FILE', 'data/drive-token.json')
        if not folder:
            raise ValueError('Set DRIVE_FOLDER_ID after running drive_auth')
        if not Path(token).is_file():
            raise ValueError('Drive token file is missing; run drive_auth first')
        store = DriveStore(drive_service(token), folder,
                           environ.get('DRIVE_INDEX_PATH', 'data/drive-index.db'))
        try:
            store.check_folder()
        except Exception:
            store.close()
            raise
        return store
    if provider != 's3':
        raise ValueError('CLOUD_PROVIDER must be drive or s3')
    endpoint = environ.get('CLOUD_ENDPOINT_URL', '')
    url = urlparse(endpoint)
    if (url.scheme != 'https' or not url.hostname or url.username or url.password
            or url.query or url.fragment or url.path not in ('', '/')):
        raise ValueError('Set CLOUD_ENDPOINT_URL to an HTTPS endpoint without credentials or a path')
    bucket = environ.get('CLOUD_BUCKET', '').strip()
    if not bucket:
        raise ValueError('Set CLOUD_BUCKET to the existing private bucket name')
    import boto3
    from botocore.config import Config
    client = boto3.client('s3', endpoint_url=endpoint,
                          region_name=environ.get('AWS_DEFAULT_REGION', 'auto'),
                          config=Config(connect_timeout=5, read_timeout=30,
                                        retries={'max_attempts': 2}))
    store = S3Store(client, bucket)
    store.identity = 's3:' + endpoint.rstrip('/') + '/' + bucket
    return store


def check_connection(store):
    """Test PUT/GET/DELETE on one random, non-footage object.

    This checks credentials and byte integrity, not bucket public-access settings.
    Always try deletion, even if PUT's response is lost or verification fails.
    """
    key = 'health-check/{}.txt'.format(uuid4().hex)
    sample = b'camera-management-system cloud connection check\n'
    try:
        store.upload(key, io.BytesIO(sample), len(sample), 'plain')
        if store.sha256(key) != digest(io.BytesIO(sample)):
            raise ValueError('Cloud read-back checksum mismatch')
    finally:
        try:
            store.delete(key)
        except Exception:
            # A temporary object may remain. Its random key is safe to report.
            logger.error('Could not remove connection-check object: %s', key)
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description='Sync completed footage to private cloud storage')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--once', action='store_true')
    mode.add_argument('--check', action='store_true',
                      help='Upload, verify and delete a small connection-check object')
    mode.add_argument('--status', action='store_true',
                      help='Print local queue JSON without credentials or cloud access')
    parser.add_argument('--database', default='data/smart-sec-cam.db',
                        help='Shared application SQLite database path')
    parser.add_argument('--enable-cleanup', action='store_true',
                        help='Delete routine cloud objects after 30 days; protects holds and incidents')
    parser.add_argument('--enable-local-cleanup', action='store_true',
                        help='Remove local variants after 1 hour only with a verified cloud copy')
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    if args.status:
        path = Path(args.database).resolve()
        if not path.is_file():
            parser.error('Shared database does not exist; start the application first')
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as conn:
            print(json.dumps(queue_status(conn), sort_keys=True))
        return 0
    try:
        store = configured_store(os.environ)
        if args.check:
            try:
                check_connection(store)
            finally:
                if hasattr(store, 'close'):
                    store.close()
            print('Cloud connection check passed: upload, SHA-256 read-back and delete accepted')
            return 0
    except ImportError:
        parser.error("Install the provider dependency first: python -m pip install '.[drive,cloud]'")
    except ValueError as exc:
        parser.error(str(exc))
    except Exception as exc:
        logger.error('Cloud connection check failed: %s', type(exc).__name__)
        return 1

    path = Path(args.database).resolve()
    if not path.is_file():
        parser.error('Shared database does not exist; start the application first')
    # Do not construct AuthDatabase here: the worker should not create an empty
    # application database when started from the wrong directory.
    conn = sqlite3.connect(str(path), timeout=30)
    conn.execute('PRAGMA foreign_keys=ON')
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'recordings', 'recording_variants', 'cameras'}.issubset(tables):
        conn.close()
        parser.error('Database lacks the shared recording catalogue; start the application first')
    db = AuthDatabase.__new__(AuthDatabase)
    db.conn = conn
    root = os.getenv('VIDEO_DIR', 'data/videos')
    try:
        queue = CloudQueue(conn, root, store, cleanup=args.enable_cleanup,
                           local_cleanup=args.enable_local_cleanup)
        while True:
            try:
                import_completed(db, root)
                queue.tick()
                status = queue_status(conn)
                logger.info('Cloud queue: %s', json.dumps(status, sort_keys=True))
                if args.once:
                    return 1 if status['failed'] else 0
            except sqlite3.OperationalError as exc:
                logger.warning('Cloud pass deferred: %s', type(exc).__name__)
                if args.once:
                    return 1
            time.sleep(60)
    finally:
        conn.close()
        if hasattr(store, 'close'):
            store.close()


if __name__ == '__main__':
    raise SystemExit(main())
