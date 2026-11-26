"""Authorize cloud footage from the shared catalogue; never return a public URL."""
import logging
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from uuid import uuid4

from smart_sec_cam.video.catalogue import assigned_variants
from smart_sec_cam.video.cloud_storage import digest, recording_protected


logger = logging.getLogger(__name__)


def _delete_hold(conn, recording_id, owner, attempts=20, wait=0.5):
    """Release a hold, retrying while the database is briefly locked.

    A hold left behind would protect its recording from cleanup for good, and an
    exception here would replace the caller's real response.
    """
    for attempt in range(attempts):
        try:
            with conn:
                conn.execute('DELETE FROM cloud_holds WHERE recording_id=? AND owner=?',
                             (recording_id, owner))
            return True
        except sqlite3.OperationalError:
            if attempt == attempts - 1:
                logger.error('Could not release cloud hold %s on %s; release it manually', owner, recording_id)
                return False
            time.sleep(wait)


def cloud_entry(db, filename, now=None):
    if not db.conn.execute("SELECT 1 FROM sqlite_master WHERE name='cloud_uploads'").fetchone():
        return None
    row = db.conn.execute('''SELECT u.recording_id,u.object_key,u.sha256,
        v.size_bytes,u.expires_at FROM cloud_uploads u
        JOIN recording_variants v USING(recording_id,format)
        WHERE v.filename=? AND v.format='mp4' AND u.state='uploaded'
    ''', (filename,)).fetchone()
    if row is None or not row[2]:
        return None
    if datetime.fromisoformat(row[4]) <= (now or datetime.now(timezone.utc)):
        if not recording_protected(db.conn, row[0]):
            return None
    return row


class LimitedTarget:
    def __init__(self, stream, limit):
        self.stream, self.limit = stream, limit

    def write(self, data):
        if self.stream.tell() + len(data) > self.limit:
            raise ValueError('Cloud response exceeds catalogue size')
        return self.stream.write(data)


def fetch_cloud_recording(db, user_id, filename, store_factory):
    """Return a verified, seekable temporary stream or None after authorization.

    A durable hold protects the source during download. Callers own the returned
    stream and must close it when their response or job finishes.
    """
    if not assigned_variants(db, user_id, 'mp4', filename):
        return None
    entry = cloud_entry(db, filename)
    if entry is None:
        return None
    owner = 'playback:' + uuid4().hex
    store = None
    target = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    held = False
    try:
        db.conn.execute('BEGIN IMMEDIATE')
        entry = cloud_entry(db, filename)
        if entry is None:
            db.conn.rollback()
            target.close()
            return None
        rid, key, expected_sha, size, _ = entry
        db.conn.execute('INSERT INTO cloud_holds VALUES (?,?)', (rid, owner))
        db.conn.commit()
        held = True
        store = store_factory()
        binding = db.conn.execute('SELECT identity FROM cloud_backend').fetchone()
        if not binding or binding[0] != store.identity:
            raise ValueError('Cloud provider does not match the upload destination')
        store.download(key, LimitedTarget(target, size))
        if target.tell() != size:
            raise ValueError('Cloud response size differs from catalogue')
        target.seek(0)
        if digest(target) != expected_sha:
            raise ValueError('Cloud response checksum mismatch')
        # Long downloads must not grant access after a camera assignment changes.
        if not assigned_variants(db, user_id, 'mp4', filename):
            target.close()
            return None
        target.seek(0)
        return target, size
    except Exception:
        db.conn.rollback()
        target.close()
        raise
    finally:
        if held:
            _delete_hold(db.conn, rid, owner)
        if store is not None and hasattr(store, 'close'):
            store.close()


def acquire_local_job_hold(db, user_id, filename):
    """Protect a catalogued local source while an incident is extracted."""
    if not db.conn.execute("SELECT 1 FROM sqlite_master WHERE name='cloud_holds'").fetchone():
        return None
    fmt = filename.rsplit('.', 1)[-1]
    if not assigned_variants(db, user_id, fmt, filename):
        return None
    row = db.conn.execute('SELECT recording_id FROM recording_variants WHERE filename=?',
                          (filename,)).fetchone()
    owner = 'incident:' + uuid4().hex
    with db.conn:
        db.conn.execute('INSERT INTO cloud_holds VALUES (?,?)', (row[0], owner))
    return row[0], owner


def release_job_hold(db, hold):
    if hold:
        _delete_hold(db.conn, *hold)
