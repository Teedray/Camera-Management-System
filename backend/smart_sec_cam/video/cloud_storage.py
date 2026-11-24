"""Durable, single-worker cloud sync. Local footage is never removed here."""
import hashlib
import logging
from datetime import datetime, timedelta, timezone

from smart_sec_cam.video.catalogue import media_file

logger = logging.getLogger(__name__)


def utc_now():
    return datetime.now(timezone.utc)


def digest(stream):
    result = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        result.update(chunk)
    return result.hexdigest()


class CloudQueue:
    """Use a dedicated SQLite connection; call setup after catalogue setup.

    Holds and cleanup share SQLite's write lock. A save/export caller must
    acquire a hold before using a cloud copy and release it after completion.
    Holds deliberately survive crashes until explicitly released.
    """
    def __init__(self, conn, root, store, cleanup=False):
        self.conn, self.root, self.store = conn, root, store
        self.cleanup = cleanup
        self.setup()

    def setup(self):
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS cloud_uploads (
                recording_id TEXT NOT NULL,
                format TEXT NOT NULL,
                object_key TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending'
                    CHECK(state IN ('pending','uploaded','expired','deleted')),
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt TEXT NOT NULL,
                last_error TEXT,
                sha256 TEXT,
                PRIMARY KEY(recording_id, format),
                FOREIGN KEY(recording_id, format)
                    REFERENCES recording_variants(recording_id, format)
            );
            CREATE TABLE IF NOT EXISTS cloud_holds (
                recording_id TEXT NOT NULL REFERENCES recordings(id),
                owner TEXT NOT NULL,
                PRIMARY KEY(recording_id, owner)
            );
        ''')

    def hold(self, recording_id, owner):
        if not owner:
            raise ValueError('A job or incident owner is required')
        with self.conn:
            self.conn.execute('INSERT OR IGNORE INTO cloud_holds VALUES (?, ?)',
                              (recording_id, owner))

    def release(self, recording_id, owner):
        with self.conn:
            self.conn.execute('DELETE FROM cloud_holds WHERE recording_id=? AND owner=?',
                              (recording_id, owner))

    def discover(self, now):
        with self.conn:
            for rid, fmt, end in self.conn.execute('''
                SELECT v.recording_id, v.format, r.capture_end_utc
                FROM recording_variants v JOIN recordings r ON r.id=v.recording_id
            ''').fetchall():
                captured = datetime.fromisoformat(end)
                if captured.tzinfo is None:
                    raise ValueError('Capture time must include timezone')
                expires = captured.astimezone(timezone.utc) + timedelta(hours=1)
                self.conn.execute('''INSERT OR IGNORE INTO cloud_uploads
                    (recording_id,format,object_key,expires_at,next_attempt)
                    VALUES (?,?,?,?,?)''',
                    (rid, fmt, 'routine/{}/clip.{}'.format(rid, fmt),
                     expires.isoformat(), now.isoformat()))

    def protected(self, rid):
        if self.conn.execute('SELECT 1 FROM cloud_holds WHERE recording_id=?', (rid,)).fetchone():
            return True
        # Existing incident archives are separate files. Also conservatively
        # protect an original if a legacy incident record references its name.
        if self.conn.execute("SELECT 1 FROM sqlite_master WHERE name='incident_clips'").fetchone():
            return self.conn.execute('''SELECT 1 FROM incident_clips i
                JOIN recording_variants v ON v.filename=i.filename
                WHERE v.recording_id=? AND i.incident_flag=1''', (rid,)).fetchone() is not None
        return False

    def tick(self, now=None, limit=100):
        now = now or utc_now()
        if now.tzinfo is None:
            raise ValueError('Worker time must include timezone')
        now = now.astimezone(timezone.utc)
        self.discover(now)
        rows = self.conn.execute('''SELECT recording_id,format FROM cloud_uploads
            WHERE state IN ('pending','uploaded','expired') AND next_attempt<=?
            ORDER BY next_attempt, recording_id, format LIMIT ?''',
            (now.isoformat(), limit)).fetchall()
        for rid, fmt in rows:
            attempts = 0
            try:
                # Serialize workers and hold acquisition with the expiry check.
                # Network calls are bounded by the S3 adapter's timeouts.
                self.conn.execute('BEGIN IMMEDIATE')
                row = self.conn.execute('''SELECT u.object_key,u.expires_at,u.state,
                    u.attempts,v.path,v.size_bytes FROM cloud_uploads u
                    JOIN recording_variants v USING(recording_id,format)
                    WHERE u.recording_id=? AND u.format=? AND u.next_attempt<=?''',
                    (rid, fmt, now.isoformat())).fetchone()
                if not row or row[2] not in ('pending', 'uploaded', 'expired'):
                    self.conn.rollback()
                    continue
                key, expiry, state, attempts, relative, size = row
                expired = datetime.fromisoformat(expiry) <= now
                protected = self.protected(rid)
                path = media_file(self.root, relative)
                if expired and not protected:
                    # Delete deterministic keys even for pending rows: a worker
                    # may have crashed after PUT but before its SQLite commit.
                    if self.cleanup and path is not None and path.stat().st_size == size:
                        self.store.delete(key)
                        self._state(rid, fmt, 'deleted')
                    elif state == 'pending':
                        self._state(rid, fmt, 'expired')
                elif state in ('pending', 'expired'):
                    if path is None or path.stat().st_size != size:
                        raise ValueError('Completed local variant is missing or changed')
                    with path.open('rb') as source:
                        sha = digest(source)
                        source.seek(0)
                        self.store.upload(key, source, size, fmt)
                    if self.store.sha256(key) != sha:
                        raise ValueError('Cloud read-back checksum mismatch')
                    self.conn.execute('''UPDATE cloud_uploads SET state='uploaded',
                        sha256=?,last_error=NULL WHERE recording_id=? AND format=?''',
                        (sha, rid, fmt))
                # Completed uploads sleep until expiry; blocked expiry checks
                # sleep one minute so older rows cannot starve new uploads.
                next_check = max(now + timedelta(minutes=1), datetime.fromisoformat(expiry))
                self.conn.execute('''UPDATE cloud_uploads SET next_attempt=?
                    WHERE recording_id=? AND format=?''',
                    (next_check.isoformat(), rid, fmt))
                self.conn.commit()
            except Exception as exc:
                self.conn.rollback()
                # Keep details out of persisted errors: SDK exceptions can contain
                # endpoints and credentials. Full operational investigation is separate.
                with self.conn:
                    self.conn.execute('''UPDATE cloud_uploads SET attempts=attempts+1,
                        next_attempt=?,last_error=? WHERE recording_id=? AND format=?''',
                        ((now + timedelta(seconds=min(3600, 5 * 2 ** min(attempts, 10)))).isoformat(),
                         type(exc).__name__, rid, fmt))
                logger.warning('Cloud operation pending for %s/%s: %s', rid, fmt, type(exc).__name__)

    def _state(self, rid, fmt, state):
        self.conn.execute('''UPDATE cloud_uploads SET state=?,last_error=NULL
            WHERE recording_id=? AND format=?''', (state, rid, fmt))


class S3Store:
    """Private S3-compatible bucket adapter, including Cloudflare R2."""
    def __init__(self, client, bucket):
        self.client, self.bucket = client, bucket

    def upload(self, key, source, size, fmt):
        self.client.put_object(Bucket=self.bucket, Key=key, Body=source,
                               ContentLength=size, ContentType='video/' + fmt)

    def sha256(self, key):
        body = self.client.get_object(Bucket=self.bucket, Key=key)['Body']
        try:
            return digest(body)
        finally:
            body.close()

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=key)
