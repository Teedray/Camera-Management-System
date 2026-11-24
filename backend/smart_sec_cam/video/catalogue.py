"""Import completed recorder manifests from the volume shared with Flask."""
import json
import logging
import math
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


FORMATS = ("webm", "mp4")
MEDIA_DIR = "catalogue"
QUEUE_DIR = "catalogue-pending"
logger = logging.getLogger(__name__)


def media_file(root, relative):
    """Resolve only regular files beneath the video root, without following symlinks."""
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    path = Path(root).resolve()
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            return None
    return path if path.is_file() else None


def register_manifest(db, root, manifest):
    recording_id = manifest["id"]
    if not isinstance(recording_id, str) or not re.fullmatch("[0-9a-f]{32}", recording_id):
        raise ValueError("Invalid recording ID")
    start, end = (datetime.fromisoformat(manifest[field]) for field in ("start", "end"))
    if start.tzinfo is None or end.tzinfo is None or end < start:
        raise ValueError("Invalid capture interval")
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    channel = manifest["channel"]
    if not isinstance(channel, str) or not channel or any(c in channel for c in ("/", "\\", "\0")):
        raise ValueError("Invalid channel")
    variants = []
    for fmt in FORMATS:
        relative = Path(MEDIA_DIR, recording_id, "clip." + fmt)
        path = media_file(root, relative)
        if path is None:
            raise ValueError("Missing completed variant")
        size = path.stat().st_size
        duration = manifest["durations"][fmt]
        if not size or not math.isfinite(duration) or duration <= 0:
            raise ValueError("Invalid completed variant")
        filename = f"{channel}__{start:%Y-%m-%d_%H:%M:%S}-{recording_id}.{fmt}"
        variants.append((recording_id, fmt, filename, str(relative), size, duration))

    with db.conn:
        db.conn.execute("""
            INSERT INTO recordings(id, camera_id, capture_start_utc, capture_end_utc)
            SELECT ?, id, ?, ? FROM cameras WHERE channel_name = ?
            ON CONFLICT(id) DO NOTHING
        """, (recording_id, start.isoformat(), end.isoformat(), channel))
        if not db.conn.execute("SELECT 1 FROM recordings WHERE id = ?", (recording_id,)).fetchone():
            return False  # Keep pending until the camera is registered.
        db.conn.executemany("""
            INSERT INTO recording_variants
            (recording_id, format, filename, path, size_bytes, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(recording_id, format) DO NOTHING
        """, variants)
    return True


def import_completed(db, root):
    root = Path(root)
    pending = root / QUEUE_DIR
    if pending.is_symlink() or not pending.is_dir():
        return
    for marker in pending.glob("*.json"):
        try:
            if marker.is_symlink():
                continue
            manifest = json.loads(marker.read_text())
            if marker.stem != manifest["id"]:
                raise ValueError("Manifest name and ID differ")
            if register_manifest(db, root, manifest):
                marker.rename(root / MEDIA_DIR / marker.stem / "registered.json")
        except FileNotFoundError:
            continue  # Another importer may already have acknowledged this manifest.
        except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
            logger.exception("Recording registration pending for %s", marker.name)


def assigned_variants(db, user_id, fmt, filename=None):
    query = """
        SELECT v.filename, v.path, r.capture_start_utc
        FROM recording_variants v JOIN recordings r ON r.id = v.recording_id
        JOIN cameras c ON c.id = r.camera_id
        JOIN user_cameras a ON a.camera_id = c.id
        WHERE a.user_id = ? AND c.enabled = 1 AND v.format = ?
    """
    params = [user_id, fmt]
    if filename is not None:
        query += " AND v.filename = ?"
        params.append(filename)
    return db.conn.execute(query, params).fetchall()


# Gaps shorter than this are frame jitter between consecutive segments, not outages.
GAP_TOLERANCE_SECONDS = 2.0


def camera_segments(db, camera_id, start, end):
    """Catalogued segments of one camera that overlap [start, end), oldest first.

    ``start`` and ``end`` are timezone-aware datetimes. Each item carries the
    UTC interval and the playable variant filenames.
    """
    rows = db.conn.execute("""
        SELECT r.id, r.capture_start_utc, r.capture_end_utc, v.format, v.filename, v.path
        FROM recordings r JOIN recording_variants v ON v.recording_id = r.id
        WHERE r.camera_id = ? AND r.capture_end_utc > ? AND r.capture_start_utc < ?
        ORDER BY r.capture_start_utc, r.id
    """, (
        camera_id,
        start.astimezone(timezone.utc).isoformat(),
        end.astimezone(timezone.utc).isoformat(),
    )).fetchall()
    segments = {}
    for recording_id, seg_start, seg_end, fmt, filename, path in rows:
        segment = segments.setdefault(recording_id, {
            "id": recording_id,
            "start": datetime.fromisoformat(seg_start),
            "end": datetime.fromisoformat(seg_end),
            "files": {},
            "paths": {},
        })
        segment["files"][fmt] = filename
        segment["paths"][fmt] = path
    return sorted(segments.values(), key=lambda segment: (segment["start"], segment["id"]))


def find_gaps(segments, start, end, tolerance_seconds=GAP_TOLERANCE_SECONDS):
    """Intervals within [start, end) that no segment covers (SR-01-03, TS-01-06).

    Leading and trailing uncovered time counts too, so a camera that stopped
    recording before ``end`` is reported. Returns dicts with start, end and seconds.
    """
    gaps = []
    cursor = start

    def add_gap(gap_start, gap_end):
        seconds = (gap_end - gap_start).total_seconds()
        if seconds > tolerance_seconds:
            gaps.append({"start": gap_start, "end": gap_end, "seconds": seconds})

    for segment in sorted(segments, key=lambda item: item["start"]):
        if segment["end"] <= cursor:
            continue
        if segment["start"] > cursor:
            add_gap(cursor, min(segment["start"], end))
        cursor = max(cursor, segment["end"])
        if cursor >= end:
            break
    if cursor < end:
        add_gap(cursor, end)
    return gaps
