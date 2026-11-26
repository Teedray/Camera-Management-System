"""Persistent operations shared by the web application and the storage worker."""
import json
import subprocess
from datetime import datetime, timedelta, timezone
from uuid import uuid4



def setup(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS operation_settings (
            id INTEGER PRIMARY KEY CHECK(id=1), cloud_days INTEGER NOT NULL DEFAULT 30,
            paused INTEGER NOT NULL DEFAULT 0, worker_seen TEXT,
            local_cleanup INTEGER, cloud_cleanup INTEGER
        );
        INSERT OR IGNORE INTO operation_settings(id) VALUES(1);
        CREATE TABLE IF NOT EXISTS incident_preservation (incident_id TEXT PRIMARY KEY, until_utc TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, user_id TEXT,
            username TEXT, type TEXT NOT NULL, action TEXT NOT NULL, description TEXT NOT NULL
        );
        CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events
        BEGIN SELECT RAISE(ABORT,'Audit events are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events
        BEGIN SELECT RAISE(ABORT,'Audit events are append-only'); END;
        CREATE TABLE IF NOT EXISTS media_jobs (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, owner TEXT NOT NULL,
            title TEXT NOT NULL, cameras TEXT NOT NULL, created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL, status TEXT NOT NULL, start TEXT, end TEXT
        );
    """)


def new_job(conn, kind, owner, title, cameras, start=None, end=None):
    job = uuid4().hex
    now = datetime.now(timezone.utc)
    with conn:
        conn.execute("INSERT INTO media_jobs VALUES(?,?,?,?,?,?,?,?,?,?)", (
            job, kind, owner, title, json.dumps(sorted(set(cameras))), now.isoformat(),
            (now + timedelta(hours=1)).isoformat(), 'processing', start, end))
    return job


def finish(conn, job, status):
    with conn:
        conn.execute("UPDATE media_jobs SET status=? WHERE id=?", (status, job))


def expire_outputs(conn, root, now):
    for job, in conn.execute(
        "SELECT id FROM media_jobs WHERE status!='expired' AND expires_at<=?", (now,)
    ).fetchall():
        (root / (job + '.mp4')).unlink(missing_ok=True)
        finish(conn, job, 'expired')


def visible_jobs(conn, user_id, camera_ids, kind, job_id=None):
    sql = "SELECT * FROM media_jobs WHERE kind=? AND owner=?"
    params = [kind, user_id]
    if job_id is not None:
        sql += " AND id=?"
        params.append(job_id)
    cursor = conn.execute(sql + " ORDER BY created_at DESC", params)
    names = [col[0] for col in cursor.description]
    for values in cursor:
        row = dict(zip(names, values))
        cameras = json.loads(row.pop('cameras'))
        if set(cameras).issubset(camera_ids):
            row['source_cameras'] = cameras
            row['filename'] = row['title']
            if row['status'] in ('ready', 'completed'):
                row['download_url'] = '/api/v1/' + kind + '/' + row['id'] + '/download'
            yield row


def merge_mp4(paths, output):
    # Decode each video with its own time base before concatenating. Camera
    # segment FPS varies with arrival times, even for adjacent segments.
    from smart_sec_cam.video.h264 import ffmpeg_executable
    import cv2
    first = cv2.VideoCapture(str(paths[0]))
    try:
        width = int(first.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(first.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = first.get(cv2.CAP_PROP_FPS)
        if not first.isOpened() or min(width, height, fps) <= 0:
            raise ValueError("First recording has no decodable video")
    finally:
        first.release()
    width += width % 2
    height += height % 2
    command = [ffmpeg_executable(), '-nostdin', '-loglevel', 'error', '-y']
    for path in paths:
        command.extend(['-i', str(path)])
    filters = [
        f'[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,'
        f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps:.6f},setpts=PTS-STARTPTS[v{i}]'
        for i in range(len(paths))
    ]
    streams = ''.join(f'[v{i}]' for i in range(len(paths)))
    filters.append(f'{streams}concat=n={len(paths)}:v=1:a=0[out]')
    subprocess.run(command + ['-filter_complex_threads','1','-filter_complex',';'.join(filters),
        '-map','[out]','-c:v','libx264','-threads','2','-pix_fmt','yuv420p',
        '-movflags','+faststart',str(output)], check=True, timeout=600,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
