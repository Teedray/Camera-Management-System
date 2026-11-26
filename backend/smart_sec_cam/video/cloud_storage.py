"""Durable cloud sync: one-hour local buffer, thirty-day cloud retention."""
import hashlib
import logging
from datetime import datetime, timedelta, timezone

from smart_sec_cam.video.catalogue import media_file

logger = logging.getLogger(__name__)


LOCAL_RETENTION = timedelta(hours=1)
CLOUD_RETENTION = timedelta(days=30)


class LocalCopyUnavailable(ValueError):
    """The local variant is missing or differs from its verified upload."""


class CloudCopyUnavailable(ValueError):
    """Local cleanup is blocked until the cloud copy is verified."""


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
    def __init__(self, conn, root, store, cleanup=False, local_cleanup=False, formats=('mp4',)):
        self.conn, self.root, self.store = conn, root, store
        self.cleanup = cleanup
        self.local_cleanup = local_cleanup
        self.formats = tuple(formats)
        self.backend = getattr(store, 'identity', 'test')
        self.setup()

    def setup(self):
        from smart_sec_cam.video.operations import setup
        setup(self.conn)
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
            CREATE INDEX IF NOT EXISTS idx_cloud_uploads_due
                ON cloud_uploads(state, next_attempt);
            CREATE TABLE IF NOT EXISTS cloud_holds (
                recording_id TEXT NOT NULL REFERENCES recordings(id),
                owner TEXT NOT NULL,
                PRIMARY KEY(recording_id, owner)
            );
        ''')
        columns = {row[1] for row in self.conn.execute('PRAGMA table_info(cloud_uploads)')}
        with self.conn:
            if 'verified_at' not in columns:
                self.conn.execute('ALTER TABLE cloud_uploads ADD COLUMN verified_at TEXT')
            if 'local_deleted' not in columns:
                self.conn.execute('ALTER TABLE cloud_uploads ADD COLUMN local_deleted INTEGER NOT NULL DEFAULT 0')
            self.conn.execute('CREATE TABLE IF NOT EXISTS cloud_policy (name TEXT PRIMARY KEY)')
            policy = 'local-1h-cloud-30d'
            if not self.conn.execute('SELECT 1 FROM cloud_policy WHERE name=?', (policy,)).fetchone():
                # Repair persisted one-hour cloud deadlines from the earlier
                # reversed policy. Requeue expired/deleted objects for recovery.
                rows = self.conn.execute('''SELECT u.recording_id,u.format,r.capture_end_utc
                    FROM cloud_uploads u JOIN recordings r ON r.id=u.recording_id''').fetchall()
                for rid, fmt, end in rows:
                    capture = datetime.fromisoformat(end)
                    if capture.tzinfo is None:
                        raise ValueError('Capture time must include timezone')
                    capture = capture.astimezone(timezone.utc)
                    self.conn.execute('''UPDATE cloud_uploads SET expires_at=?,next_attempt=?,
                        state=CASE WHEN state IN ('expired','deleted') THEN 'pending' ELSE state END,
                        sha256=CASE WHEN state IN ('expired','deleted') THEN NULL ELSE sha256 END,
                        last_error=NULL WHERE recording_id=? AND format=?''',
                        ((capture + CLOUD_RETENTION).isoformat(), capture.isoformat(), rid, fmt))
                self.conn.execute('INSERT INTO cloud_policy VALUES (?)', (policy,))
            self.conn.execute('CREATE TABLE IF NOT EXISTS cloud_backend (identity TEXT NOT NULL)')
            binding = self.conn.execute('SELECT identity FROM cloud_backend').fetchone()
            if binding and binding[0] != self.backend:
                raise ValueError('Queue belongs to another cloud destination; migrate it before switching')
            if not binding:
                if self.conn.execute("SELECT 1 FROM cloud_uploads WHERE state='uploaded'").fetchone():
                    raise ValueError('Existing uploaded queue needs an explicit provider migration')
                self.conn.execute('INSERT INTO cloud_backend VALUES (?)', (self.backend,))

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
            days, = self.conn.execute("SELECT cloud_days FROM operation_settings").fetchone()
            for rid, fmt, end in self.conn.execute('''
                SELECT v.recording_id, v.format, r.capture_end_utc
                FROM recording_variants v JOIN recordings r ON r.id=v.recording_id
                LEFT JOIN cloud_uploads u ON u.recording_id=v.recording_id AND u.format=v.format
                WHERE u.recording_id IS NULL
            ''').fetchall():
                if fmt not in self.formats:
                    continue
                captured = datetime.fromisoformat(end)
                if captured.tzinfo is None:
                    raise ValueError('Capture time must include timezone')
                expires = captured.astimezone(timezone.utc) + timedelta(days=days)
                self.conn.execute('''INSERT OR IGNORE INTO cloud_uploads
                    (recording_id,format,object_key,expires_at,next_attempt)
                    VALUES (?,?,?,?,?)''',
                    (rid, fmt, 'routine/{}/clip.{}'.format(rid, fmt),
                     expires.isoformat(), now.isoformat()))

    def protected(self, rid):
        return recording_protected(self.conn, rid)

    def tick(self, now=None, limit=100):
        """Run one pass over due uploads, local cleanup and cloud expiry.

        Network calls (upload, read-back, cloud checksum, delete) run without a
        database transaction, so the website can keep writing while Drive is slow
        or unreachable. Each row's decision is re-checked under a short
        BEGIN IMMEDIATE before its result is recorded: a hold taken meanwhile still
        protects the recording, and a cloud copy is marked as being removed (state
        'expired', which playback refuses) before it is deleted.
        """
        fixed_time = now
        now = now or utc_now()
        if now.tzinfo is None:
            raise ValueError('Worker time must include timezone')
        now = now.astimezone(timezone.utc)
        with self.conn:
            self.conn.execute("UPDATE operation_settings SET worker_seen=?,local_cleanup=?,cloud_cleanup=? WHERE id=1",
                              (now.isoformat(),self.local_cleanup,self.cleanup))
        if self.conn.execute("SELECT paused FROM operation_settings").fetchone()[0]:
            return
        self.discover(now)
        placeholders = ','.join('?' for _ in self.formats)
        rows = self.conn.execute('''SELECT recording_id,format FROM cloud_uploads
            WHERE state IN ('pending','uploaded','expired') AND next_attempt<=?
            AND format IN (''' + placeholders + ''')
            ORDER BY next_attempt, recording_id, format LIMIT ?''',
            (now.isoformat(), *self.formats, limit)).fetchall()
        for rid, fmt in rows:
            if fixed_time is None:
                now = utc_now().astimezone(timezone.utc)
            attempts = 0
            expired = False
            expiry = (now + CLOUD_RETENTION).isoformat()
            try:
                if self.conn.execute("SELECT paused FROM operation_settings").fetchone()[0]:
                    break
                row = self._row(rid, fmt, now)
                if row is None:
                    continue
                key, expiry, state, attempts, relative, size, verified_sha, local_deleted, end = row
                local_expiry = datetime.fromisoformat(end).astimezone(timezone.utc) + LOCAL_RETENTION
                expired = datetime.fromisoformat(expiry) <= now
                path = media_file(self.root, relative)

                # 1. Local cleanup: verify both copies first, without holding the lock.
                if (self.local_cleanup and state == 'uploaded' and not local_deleted
                        and now >= local_expiry and not self.protected(rid)):
                    if not verified_sha or self.store.sha256(key) != verified_sha:
                        raise CloudCopyUnavailable('Cloud copy could not be verified')
                    if path is not None:
                        with path.open('rb') as local:
                            if digest(local) != verified_sha:
                                raise LocalCopyUnavailable('Local copy differs from verified upload')
                    if self._remove_local(rid, fmt, row):
                        local_deleted = True

                # 2. Cloud expiry: claim the removal under the lock, delete outside it.
                if expired:
                    if self.cleanup:
                        if self._claim_cloud_removal(rid, fmt, now):
                            self.store.delete(key)
                            self._record(rid, fmt, "state='deleted',last_error=NULL")
                            continue
                    elif state == 'pending':
                        self._record(rid, fmt, "state='expired',last_error=NULL", only_if_unprotected=True)
                        state = 'expired' if not self.protected(rid) else state

                # 3. Upload (also an expired recording still protected by a hold or incident).
                if state in ('pending', 'expired') and not (expired and not self.protected(rid)):
                    if path is None or path.stat().st_size != size:
                        raise ValueError('Completed local variant is missing or changed')
                    with path.open('rb') as source:
                        sha = digest(source)
                        source.seek(0)
                        self.store.upload(key, source, size, fmt)
                    if self.store.sha256(key) != sha:
                        raise ValueError('Cloud read-back checksum mismatch')
                    self._record(rid, fmt, "state='uploaded',sha256=?,last_error=NULL,verified_at=?", (sha, now.isoformat()))

                # Revisit uploaded rows at the local cutoff before the later
                # cloud cutoff. A disabled/held cleanup gets another check in a minute.
                next_check = datetime.fromisoformat(expiry)
                if not local_deleted:
                    next_check = min(next_check, local_expiry)
                next_check = max(now + timedelta(minutes=1), next_check)
                self._record(rid, fmt, 'next_attempt=?', (next_check.isoformat(),))
            except Exception as exc:
                if self.conn.in_transaction:
                    self.conn.rollback()
                # Keep details out of persisted errors: SDK exceptions can contain
                # endpoints and credentials. Full operational investigation is separate.
                # Expired deletes retry every minute. Upload retries must not
                # defer the first expiry check beyond the capture-based deadline.
                delay = min(60 if expired else 3600, 5 * 2 ** min(attempts, 10))
                retry_at = now + timedelta(seconds=delay)
                if not expired:
                    retry_at = min(retry_at, datetime.fromisoformat(expiry))
                with self.conn:
                    self.conn.execute('''UPDATE cloud_uploads SET attempts=attempts+1,
                        next_attempt=?,last_error=? WHERE recording_id=? AND format=?''',
                        (retry_at.isoformat(),
                         type(exc).__name__, rid, fmt))
                logger.warning('Cloud operation pending for %s/%s: %s', rid, fmt, type(exc).__name__)

    def _row(self, rid, fmt, now):
        """The row's current state, read without a transaction (None if not due)."""
        row = self.conn.execute('''SELECT u.object_key,u.expires_at,u.state,
            u.attempts,v.path,v.size_bytes,u.sha256,u.local_deleted,r.capture_end_utc FROM cloud_uploads u
            JOIN recording_variants v USING(recording_id,format)
            JOIN recordings r ON r.id=u.recording_id
            WHERE u.recording_id=? AND u.format=? AND u.next_attempt<=?''',
            (rid, fmt, now.isoformat())).fetchone()
        if not row or row[2] not in ('pending', 'uploaded', 'expired'):
            return None
        return row

    def _record(self, rid, fmt, assignments, params=(), only_if_unprotected=False):
        """Apply one short update under BEGIN IMMEDIATE (serialized with hold acquisition)."""
        self.conn.execute('BEGIN IMMEDIATE')
        try:
            if only_if_unprotected and self.protected(rid):
                self.conn.rollback()
                return False
            self.conn.execute('UPDATE cloud_uploads SET ' + assignments +
                              ' WHERE recording_id=? AND format=?', (*params, rid, fmt))
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            raise

    def _claim_cloud_removal(self, rid, fmt, now):
        """Mark an expired, unprotected copy as being removed; playback refuses it from now on."""
        self.conn.execute('BEGIN IMMEDIATE')
        try:
            row = self.conn.execute('SELECT expires_at,state FROM cloud_uploads WHERE recording_id=? AND format=?',
                                    (rid, fmt)).fetchone()
            if self.conn.execute("SELECT paused FROM operation_settings").fetchone()[0]:
                self.conn.rollback()
                return False
            if (not row or row[1] not in ('pending', 'uploaded', 'expired')
                    or datetime.fromisoformat(row[0]) > now or self.protected(rid)):
                self.conn.rollback()
                return False
            self.conn.execute("UPDATE cloud_uploads SET state='expired' WHERE recording_id=? AND format=?",
                              (rid, fmt))
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            raise

    def _remove_local(self, rid, fmt, row):
        """Delete the verified local pair if nothing protected it meanwhile."""
        self.conn.execute('BEGIN IMMEDIATE')
        try:
            current = self.conn.execute('''SELECT state,local_deleted,sha256 FROM cloud_uploads
                WHERE recording_id=? AND format=?''', (rid, fmt)).fetchone()
            if self.conn.execute("SELECT paused FROM operation_settings").fetchone()[0]:
                self.conn.rollback()
                return False
            if (not current or current[0] != 'uploaded' or current[1] or current[2] != row[6]
                    or self.protected(rid)):
                self.conn.rollback()
                return False
            path = media_file(self.root, row[4])
            if path is not None:
                path.unlink()
            # WebM is a local compatibility encoding. A verified MP4
            # cloud copy preserves the recording when its local pair expires.
            if fmt == 'mp4' and self.formats == ('mp4',):
                peer = self.conn.execute('''SELECT path FROM recording_variants
                    WHERE recording_id=? AND format=?''', (rid, 'webm')).fetchone()
                peer_path = media_file(self.root, peer[0]) if peer else None
                if peer_path is not None:
                    peer_path.unlink()
            self.conn.execute('''UPDATE cloud_uploads SET local_deleted=1
                WHERE recording_id=? AND format=?''', (rid, fmt))
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            raise

    def _state(self, rid, fmt, state):
        self.conn.execute('''UPDATE cloud_uploads SET state=?,last_error=NULL
            WHERE recording_id=? AND format=?''', (state, rid, fmt))


def recording_protected(conn, rid):
    if conn.execute('SELECT 1 FROM cloud_holds WHERE recording_id=?', (rid,)).fetchone():
        return True
    # Existing incident archives are separate files. Also protect the recording
    # an incident was cut from: incident_clips.source_filename names it, while
    # filename is the archived clip's own name (still matched for legacy rows).
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='incident_clips'").fetchone():
        columns = {row[1] for row in conn.execute('PRAGMA table_info(incident_clips)')}
        names = 'i.filename, i.source_filename' if 'source_filename' in columns else 'i.filename'
        return conn.execute('''SELECT 1 FROM incident_clips i
            JOIN recording_variants v ON v.filename IN (''' + names + ''')
            WHERE v.recording_id=? AND i.incident_flag=1''', (rid,)).fetchone() is not None
    return False


class S3Store:
    """Private S3-compatible bucket adapter, including Cloudflare R2."""
    def __init__(self, client, bucket):
        self.client, self.bucket = client, bucket

    def upload(self, key, source, size, fmt):
        self.client.put_object(Bucket=self.bucket, Key=key, Body=source,
                               ContentLength=size, ContentType=('video/' + fmt if fmt in ('mp4', 'webm')
                                                               else 'application/octet-stream'))

    def sha256(self, key):
        body = self.client.get_object(Bucket=self.bucket, Key=key)['Body']
        try:
            return digest(body)
        finally:
            body.close()

    def download(self, key, target):
        body = self.client.get_object(Bucket=self.bucket, Key=key)['Body']
        try:
            for chunk in iter(lambda: body.read(1024 * 1024), b''):
                target.write(chunk)
        finally:
            body.close()

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=key)


def queue_status(conn, now=None):
    """Read-only operational summary; safe before the worker has initialized."""
    now = now or utc_now()
    if now.tzinfo is None:
        raise ValueError('Status time must include timezone')
    now = now.astimezone(timezone.utc).isoformat()
    states = dict.fromkeys(('pending', 'uploaded', 'expired', 'deleted'), 0)
    ready = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cloud_uploads'"
    ).fetchone() is not None
    result = {'queue_ready': ready, 'states': states, 'failed': 0,
              'due': 0, 'overdue': 0, 'holds': 0, 'verified_recent': 0,
              'local_removed': 0, 'local_retention_hours': 1, 'cloud_retention_days': 30}
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='operation_settings'").fetchone():
        result["cloud_retention_days"] = conn.execute("SELECT cloud_days FROM operation_settings").fetchone()[0]
    if not ready:
        return result
    states.update(dict(conn.execute('SELECT state,COUNT(*) FROM cloud_uploads GROUP BY state')))
    for field, condition, params in (
        ('failed', 'last_error IS NOT NULL', ()),
        ('due', "state!='deleted' AND next_attempt<=?", (now,)),
        ('overdue', "state!='deleted' AND expires_at<=?", (now,)),
        ('verified_recent', "state='uploaded' AND expires_at>?", (now,)),
    ):
        result[field] = conn.execute(
            'SELECT COUNT(*) FROM cloud_uploads WHERE ' + condition, params
        ).fetchone()[0]
    columns = {row[1] for row in conn.execute('PRAGMA table_info(cloud_uploads)')}
    if 'local_deleted' in columns:
        result['local_removed'] = conn.execute(
            'SELECT COUNT(*) FROM cloud_uploads WHERE local_deleted=1').fetchone()[0]
    result['holds'] = conn.execute('SELECT COUNT(*) FROM cloud_holds').fetchone()[0]
    return result
