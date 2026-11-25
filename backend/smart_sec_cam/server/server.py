import base64
import ipaddress
import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlsplit
from numbers import Real
from pathlib import Path
from tempfile import TemporaryDirectory

import eventlet
eventlet.monkey_patch()

import jwt.exceptions
from eventlet import tpool
from flask import (
    Flask, send_file, send_from_directory, render_template,
    request, g, jsonify
)
from flask_cors import CORS
from flask_socketio import SocketIO, join_room

from smart_sec_cam.auth.authentication import Authenticator
from smart_sec_cam.auth.database import AuthDatabase, LastAdministratorError
from smart_sec_cam.auth.models import User
from smart_sec_cam.redis import RedisImageReceiver
from smart_sec_cam.video.catalogue import (
    assigned_variants, camera_segments, find_gaps, import_completed, media_file
)
from smart_sec_cam.video.exports import InvalidClipRange, export_clip
from smart_sec_cam.video.incident_clips import IncidentClipManager
from smart_sec_cam.video.incident_database import IncidentDatabase

# SocketIO & CORS
app = Flask(__name__, static_url_path='', static_folder='/backend/build', template_folder='/backend/build')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")
# Authentication
auth_db = AuthDatabase()
authenticator = Authenticator(auth_db)
# Application-specific data
VIDEO_DIR = "data/videos"
# Protected Incident Archive: kept apart from routine recordings so that
# retention cleanup of VIDEO_DIR cannot reach saved incident clips (SR-04-03).
INCIDENT_ARCHIVE_DIR = "data/incident_archive"
# Roles allowed to save incident clips (UC04 precondition, SEC-01).
INCIDENT_ROLES = ("administrator", "manager")
# A camera counts as connected if a frame arrived within this many seconds (SR-01-01).
CAMERA_CONNECTED_SECONDS = 10
# Throttle for persisting each camera's last-frame time.
LAST_SEEN_WRITE_SECONDS = 5
# Longest window a single recordings/gaps query may cover.
MAX_RECORDING_QUERY = timedelta(days=31)
DEFAULT_RECORDING_QUERY = timedelta(hours=1)
last_seen_writes = {}
rooms = {}
live_subscriptions = {}
ENABLE_USER_REGISTRATION = False


def require_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("x-access-token")

        if not token:
            return jsonify(
                status="ERROR",
                error="Missing token"
            ), 401

        try:
            g.current_user = authenticator.get_authenticated_user(
                token, request.remote_addr
            )
        except jwt.exceptions.InvalidTokenError:
            return jsonify(
                status="ERROR",
                error="Invalid or expired token"
            ), 401

        return f(*args, **kwargs)

    return decorated

def require_administrator(f):
    @require_token
    @wraps(f)
    def decorated(*args, **kwargs):
        if g.current_user.role != "administrator":
            return jsonify(
                success=False, error="Administrator role required"
            ), 403

        return f(*args, **kwargs)

    return decorated


def recording_details(file_name):
    if not isinstance(file_name, str):
        return None

    if any(character in file_name for character in ("/", "\\", "\x00")):
        return None

    stem, extension = os.path.splitext(file_name)

    if extension not in (".webm", ".mp4") or "__" not in stem:
        return None

    channel, timestamp_text = stem.rsplit("__", 1)

    if not channel:
        return None

    try:
        timestamp = datetime.strptime(
            timestamp_text, "%Y-%m-%d_%H:%M:%S"
        )
    except ValueError:
        return None

    return channel, timestamp, extension


def resolve_recording(user_id, file_name):
    """Return the file for a recording the user's assigned cameras permit, else None.

    Shared by playback and incident saving so that both pass the same
    per-camera access check before any footage is reached (SR-06-02, LPR-02).
    """
    extension = os.path.splitext(file_name)[1]
    import_completed(auth_db, VIDEO_DIR)
    matches = assigned_variants(auth_db, user_id, extension[1:], file_name)
    if matches:
        return media_file(VIDEO_DIR, matches[0][1])

    # Legacy filenames are disjoint from catalogue filenames (which carry an ID).
    details = recording_details(file_name)
    channels = {camera["channel_name"] for camera in auth_db.get_user_cameras(user_id)}
    return media_file(VIDEO_DIR, file_name) if details and details[0] in channels else None


def has_incident_role(user_id):
    user = auth_db.get_user_by_id(user_id)
    return user is not None and user.role in INCIDENT_ROLES


def incident_repository():
    # Incident records live in the shared SQL database (SDS Data Storage Layer).
    return IncidentDatabase(conn=auth_db.conn)


def incident_manager():
    return IncidentClipManager(
        video_dir=VIDEO_DIR,
        archive_dir=INCIDENT_ARCHIVE_DIR,
        authorization_check=has_incident_role,
        incident_db=incident_repository(),
        source_resolver=lambda file_name, user_id: resolve_recording(user_id, file_name)
    )


def incident_profile(incident):
    return {
        "id": incident["id"],
        "camera": incident["camera"],
        "start_time": incident["start_time"],
        "end_time": incident["end_time"],
        "incident_flag": bool(incident["incident_flag"]),
        "title": incident["title"],
        "notes": incident["notes"],
        "created_by": incident["created_by"],
        "created_at": incident["created_at"],
        "video_url": f"/api/v1/incidents/{incident['id']}/video"
    }


def visible_incident(user_id, incident_id):
    channels = [camera["channel_name"] for camera in auth_db.get_user_cameras(user_id)]
    for incident in incident_repository().list_incidents(channels):
        if incident["id"] == incident_id:
            return incident
    return None


def utc_now():
    return datetime.now(timezone.utc)


def note_camera_frame(channel, now=None):
    """Persist a camera's latest frame time, at most every LAST_SEEN_WRITE_SECONDS."""
    if isinstance(channel, bytes):
        channel = channel.decode("utf-8", errors="replace")
    now = now or utc_now()
    previous = last_seen_writes.get(channel)
    if previous is not None and (now - previous).total_seconds() < LAST_SEEN_WRITE_SECONDS:
        return
    last_seen_writes[channel] = now
    try:
        auth_db.mark_camera_seen(channel, now.isoformat())
    except sqlite3.Error:
        app.logger.exception("Could not record last frame time for %s", channel)


def camera_status(camera, now=None):
    """connected / disconnected / never_connected, from the last frame time (SR-01-01)."""
    last_seen = camera.get("last_seen_utc")
    if not last_seen:
        return "never_connected"
    age = ((now or utc_now()) - datetime.fromisoformat(last_seen)).total_seconds()
    return "connected" if age <= CAMERA_CONNECTED_SECONDS else "disconnected"


def validate_stream_address(value):
    """Return an error message, or None for a USB index or an http/https/rtsp stream URL."""
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        return "stream_address must be a non-empty text value"
    value = value.strip()
    if value.isdigit():
        return None
    try:
        parts = urlsplit(value)
        host = parts.hostname
        parts.port  # Raises ValueError for an invalid port.
    except ValueError:
        return "stream_address has an invalid host or port"
    if parts.scheme not in ("http", "https", "rtsp") or not host:
        return "stream_address must be a USB camera number or an http, https or rtsp URL"
    if all(part.isdigit() for part in host.split(".")):
        try:
            ipaddress.IPv4Address(host)
        except ValueError:
            return "stream_address has an invalid IP address"
    return None


def parse_utc(value, name):
    """Parse an ISO 8601 timestamp that includes a UTC offset."""
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise ValueError(f"{name} must be an ISO 8601 timestamp")
    if moment.tzinfo is None:
        raise ValueError(f"{name} must include a timezone offset, for example Z")
    return moment.astimezone(timezone.utc)


"""
SocketIO endpoints
"""


@socketio.on("join")
def on_join(data):
    if not isinstance(data, dict):
        return {"status": "ERROR", "error": "Invalid request"}

    token = data.get("token")
    room = data.get("room")

    if not isinstance(token, str) or not isinstance(room, str):
        return {"status": "ERROR", "error": "Missing token or room"}

    try:
        user = authenticator.get_authenticated_user(
            token, request.remote_addr
        )
    except jwt.exceptions.InvalidTokenError:
        return {"status": "ERROR", "error": "Invalid or expired token"}

    for camera in auth_db.get_user_cameras(user.user_id):
        channel = camera["channel_name"]
        if room in (channel, str(channel.encode("utf-8"))):
            live_subscriptions[(request.sid, room)] = {
                "token": token,
                "ip": request.remote_addr,
                "camera_id": camera["id"],
                "channel_name": channel
            }
            return {"status": "OK"}

    return {"status": "ERROR", "error": "Camera access denied"}


@socketio.on("leave")
def on_leave(data):
    if isinstance(data, dict) and isinstance(data.get("room"), str):
        live_subscriptions.pop((request.sid, data["room"]), None)


@socketio.on("disconnect")
def on_disconnect(reason=None):
    for key in list(live_subscriptions):
        if key[0] == request.sid:
            live_subscriptions.pop(key, None)


"""
UI Endpoints
"""


@app.route('/register', defaults={'path': 'register'})
@app.route('/videos', defaults={'path': 'videos'})
@app.route('/stream', defaults={'path': 'stream'})
@app.route('/', defaults={'path': ''})
def serve_react_ui(path):
    return render_template("index.html")


"""
API Endpoints
"""


@app.route("/api/auth/login", methods=["POST"])
def authenticate():
    # Get data from request body
    username = request.json.get("username")
    password = request.json.get("password")
    client_ip_addr = request.remote_addr
    # Authenticate request
    try:
        token = authenticator.authenticate(username, password, client_ip_addr)
    except ValueError:
        return json.dumps({'status': "ERROR", "error": "Incorrect username or password"}), 401, \
               {'ContentType': 'application/json'}
    if not token:
        return json.dumps({'status': "ERROR", "error": "Incorrect username or password"}), 401, \
               {'ContentType': 'application/json'}
    return json.dumps({'status': "OK", 'token': token}), 200, {'ContentType': 'application/json'}


@app.route("/api/auth/num-users", methods=["GET"])
def get_num_users():
    return json.dumps({'status': "OK", 'users': auth_db.get_num_users()}), 200, {'ContentType': 'application/json'}


@app.route("/api/auth/register", methods=["POST"])
def register():
    # Check if any users exist and if user registration is enabled
    if auth_db.get_num_users() > 0 and not ENABLE_USER_REGISTRATION:
        return json.dumps({'status': "ERROR", 'error': "User registration is disabled"}), 403, \
               {'ContentType': 'application/json'}
    # Create new user
    username = request.json.get("username")
    password = request.json.get("password")
    new_user = User(username)
    new_user.generate_id()
    new_user.set_password(password)
    try:
        auth_db.add_user(new_user)
    except ValueError:
        return json.dumps({'status': "ERROR", "error": "Username taken"}), 404, {'ContentType': 'application/json'}
    return json.dumps({'status': "OK"}), 200, {'ContentType': 'application/json'}


@app.route("/api/token/validate", methods=["POST"])
def validate_token():
    token = request.json.get("token")
    client_ip_addr = request.remote_addr
    try:
        if not authenticator.validate_token(token, client_ip_addr):
            return json.dumps({'status': "ERROR", "error": "Invalid token"}), 401, {'ContentType': 'application/json'}
    except (jwt.exceptions.InvalidSignatureError, jwt.exceptions.DecodeError, jwt.exceptions.ExpiredSignatureError, jwt.exceptions.ImmatureSignatureError):
        return json.dumps({'status': "ERROR", "error": "Invalid token"}), 401, {'ContentType': 'application/json'}
    return json.dumps({'status': "OK"}), 200, {'ContentType': 'application/json'}


@app.route("/api/token/ttl", methods=["GET"])
def get_token_ttl():
    token = request.args.get("token")
    client_ip_addr = request.remote_addr
    # Validate token
    try:
        if not authenticator.validate_token(token, client_ip_addr):
            return json.dumps({'status': "ERROR", "error": "Invalid token"}), 401, {'ContentType': 'application/json'}
    except (jwt.exceptions.InvalidSignatureError, jwt.exceptions.DecodeError, jwt.exceptions.ExpiredSignatureError):
        return json.dumps({'status': "ERROR", "error": "Invalid token"}), 401, {'ContentType': 'application/json'}
    # Return TTL
    ttl = authenticator.get_token_ttl(token)
    return json.dumps({'status': "OK", "ttl": ttl}), 200, {'ContentType': 'application/json'}


@app.route("/api/token/refresh", methods=["POST"])
def refresh_token():
    token = request.json.get("token")
    client_ip_addr = request.remote_addr
    try:
        if not authenticator.validate_token(token, client_ip_addr):
            return json.dumps({'status': "ERROR", "error": "Invalid token"}), 401, {'ContentType': 'application/json'}
    except (jwt.exceptions.InvalidSignatureError, jwt.exceptions.DecodeError, jwt.exceptions.ExpiredSignatureError):
        return json.dumps({'status': "ERROR", "error": "Invalid token"}), 401, {'ContentType': 'application/json'}
    new_token = authenticator.refresh_token(token, client_ip_addr)
    return json.dumps({'status': "OK", "token": new_token}), 200, {'ContentType': 'application/json'}


@app.route("/api/video/rooms", methods=["GET"])
@require_token
def get_rooms():
    cameras = auth_db.get_user_cameras(g.current_user.user_id)

    permitted_rooms = set()
    for camera in cameras:
        channel = camera["channel_name"]
        permitted_rooms.add(channel)

        # Compatibility with the existing live-stream code,
        # which converts Redis channel bytes using str().
        permitted_rooms.add(str(channel.encode("utf-8")))

    visible_rooms = {
        room: last_seen
        for room, last_seen in list(rooms.items())
        if room in permitted_rooms
    }

    return jsonify(rooms=visible_rooms), 200


@app.route("/api/video/video-list", methods=["GET"])
@require_token
def get_video_list():
    video_format = request.args.get("video-format", "webm")

    if video_format not in ("webm", "mp4"):
        return jsonify(
            status="ERROR", error="Unsupported video format"
        ), 400

    allowed_channels = {
        camera["channel_name"]
        for camera in auth_db.get_user_cameras(
            g.current_user.user_id
        )
    }

    import_completed(auth_db, VIDEO_DIR)
    recordings = [
        (datetime.fromisoformat(start).timestamp(), filename)
        for filename, path, start in assigned_variants(auth_db, g.current_user.user_id, video_format)
        if media_file(VIDEO_DIR, path) is not None
    ]
    # Pre-catalogue files keep their original names and channel-based access rules.

    try:
        with os.scandir(VIDEO_DIR) as entries:
            for entry in entries:
                if not entry.is_file(follow_symlinks=False):
                    continue

                details = recording_details(entry.name)
                if details is None:
                    continue

                channel, timestamp, extension = details

                if (
                    channel in allowed_channels
                    and extension == "." + video_format
                ):
                    recordings.append((timestamp.timestamp(), entry.name))
    except FileNotFoundError:
        return jsonify(videos=[]), 200

    recordings.sort(reverse=True)

    return jsonify(
        videos=[name for timestamp, name in recordings]
    ), 200

@app.route("/api/video/<file_name>", methods=["GET"])
def get_video(file_name):
    token = (
        request.headers.get("x-access-token")
        or request.args.get("token")
    )

    if not token:
        return jsonify(
            status="ERROR", error="Missing token"
        ), 401

    try:
        user = authenticator.get_authenticated_user(
            token, request.remote_addr
        )
    except jwt.exceptions.InvalidTokenError:
        return jsonify(
            status="ERROR", error="Invalid or expired token"
        ), 401

    extension = os.path.splitext(file_name)[1]
    path = resolve_recording(user.user_id, file_name)

    if path is None:
        return jsonify(status="ERROR", error="Recording unavailable"), 404

    mime_type = (
        "video/webm" if extension == ".webm" else "video/mp4"
    )

    return send_from_directory(
        str(path.parent),
        path.name,
        download_name=file_name,
        as_attachment=False,
        mimetype=mime_type
    )

@app.route("/api/v1/auth/me", methods=["GET"])
@require_token
def get_current_user():
    user = g.current_user

    return jsonify(
        success=True,
        data={
            "id": user.user_id,
            "username": user.username,
            "role": user.role,
            "cameras": auth_db.get_user_cameras(user.user_id)
        }
    ), 200


@app.route("/api/v1/users", methods=["GET"])
@require_administrator
def list_users():
    return jsonify(success=True, data={"items": auth_db.list_user_profiles()}), 200


@app.route("/api/v1/users", methods=["POST"])
@require_administrator
def create_user():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(success=False, error="Expected a JSON object"), 400
    if payload.keys() - {"username", "password", "role"}:
        return jsonify(success=False, error="Unsupported user fields"), 400

    for field in ("username", "password"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip() or "\x00" in value:
            return jsonify(
                success=False, error=f"{field} must be a non-empty text value"
            ), 400

    role = payload.get("role", "viewer")
    if role not in User.ROLES:
        return jsonify(success=False, error="Invalid user role"), 400

    user = User(payload["username"], role=role)
    user.generate_id()
    try:
        user.set_password(payload["password"])
        auth_db.add_user(user)
    except UnicodeEncodeError:
        return jsonify(
            success=False, error="Username and password must contain valid Unicode"
        ), 400
    except ValueError:
        return jsonify(success=False, error="Username already exists"), 409

    return jsonify(success=True, data={
        "id": user.user_id, "username": user.username, "role": user.role
    }), 201


@app.route("/api/v1/users/<user_id>", methods=["PATCH"])
@require_administrator
def change_user_role(user_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(success=False, error="Expected a JSON object"), 400
    if payload.keys() != {"role"}:
        return jsonify(success=False, error="Only the role field is supported"), 400
    if payload["role"] not in User.ROLES:
        return jsonify(success=False, error="Invalid user role"), 400

    try:
        profile = auth_db.update_user_role(user_id, payload["role"])
    except LastAdministratorError as error:
        return jsonify(success=False, error=str(error)), 409

    if profile is None:
        return jsonify(success=False, error="User does not exist"), 404

    return jsonify(success=True, data=profile), 200



@app.route("/api/v1/admin/cameras", methods=["GET"])
@require_administrator
def list_all_cameras_for_admin():
    rows = auth_db.conn.execute(
        "SELECT id, name, location, channel_name, enabled "
        "FROM cameras ORDER BY name, id"
    ).fetchall()
    return jsonify(success=True, data={"items": [
        {"id": row[0], "name": row[1], "location": row[2],
         "channel_name": row[3], "enabled": bool(row[4])}
        for row in rows
    ]}), 200


@app.route("/api/v1/admin/assignments", methods=["GET"])
@require_administrator
def list_all_camera_assignments_for_admin():
    rows = auth_db.conn.execute(
        "SELECT user_id, camera_id FROM user_cameras ORDER BY user_id, camera_id"
    ).fetchall()
    return jsonify(success=True, data={"items": [
        {"user_id": row[0], "camera_id": row[1]}
        for row in rows
    ]}), 200


@app.route("/api/v1/recordings", methods=["GET"])
@require_token
def list_catalogue_recordings():
    """Timestamped, permitted, completed catalogue items for the review UI.

    Legacy filename-only recordings cannot be given accurate durations and
    are intentionally excluded from this endpoint and its gap calculations.
    """
    import_completed(auth_db, VIDEO_DIR)
    rows = auth_db.conn.execute("""
        SELECT v.filename, c.id, c.name, c.channel_name,
               r.capture_start_utc, r.capture_end_utc,
               v.duration_seconds, v.format
          FROM recording_variants v
          JOIN recordings r ON r.id = v.recording_id
          JOIN cameras c ON c.id = r.camera_id
          JOIN user_cameras uc ON uc.camera_id = c.id
         WHERE uc.user_id = ? AND c.enabled = 1 AND v.format = 'webm'
         ORDER BY r.capture_start_utc DESC, v.filename
    """, (g.current_user.user_id,)).fetchall()
    items = []
    for filename, camera_id, name, channel, start, end, duration, fmt in rows:
        if media_file(VIDEO_DIR, auth_db.conn.execute(
            "SELECT path FROM recording_variants WHERE filename = ?", (filename,)
        ).fetchone()[0]) is None:
            continue
        items.append({
            "filename": filename,
            "camera_id": camera_id,
            "camera_name": name,
            "channel_name": channel,
            "start": start,
            "end": end,
            "duration_seconds": duration,
            "format": fmt,
        })
    return jsonify(success=True, data={"items": items}), 200


@app.route("/api/v1/cameras", methods=["GET"])
@require_token
def list_assigned_cameras():
    cameras = auth_db.get_user_cameras(g.current_user.user_id)

    return jsonify(
        success=True,
        data={"items": cameras}
    ), 200

@app.route("/api/v1/cameras", methods=["POST"])
@require_administrator
def register_camera():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(
            success=False, error="Expected a JSON object"
        ), 400

    camera = {}
    for field in ("id", "name", "location", "channel_name"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip() or "\x00" in value:
            return jsonify(
                success=False, error=f"{field} must be a non-empty text value"
            ), 400
        camera[field] = value.strip()

    if camera["id"] in (".", "..") or any(
        separator in camera["id"] for separator in ("/", "\\")
    ):
        return jsonify(
            success=False, error="id must be a valid URL path segment"
        ), 400

    if any(separator in camera["channel_name"] for separator in ("/", "\\")):
        return jsonify(
            success=False, error="channel_name cannot contain path separators"
        ), 400

    try:
        auth_db.add_camera(
            camera["id"], camera["name"], camera["location"],
            camera["channel_name"]
        )
    except UnicodeEncodeError:
        return jsonify(
            success=False, error="Camera fields must contain valid Unicode"
        ), 400
    except sqlite3.IntegrityError:
        return jsonify(
            success=False, error="Camera ID or channel name already exists"
        ), 409

    return jsonify(success=True, data={**camera, "enabled": True}), 201


@app.route("/api/v1/cameras/status", methods=["GET"])
@require_token
def list_camera_status():
    """Connection status of the caller's cameras; stream addresses are admin-only."""
    now = utc_now()
    is_admin = g.current_user.role == "administrator"
    items = []
    for camera in auth_db.get_user_camera_details(g.current_user.user_id):
        item = {
            "id": camera["id"],
            "name": camera["name"],
            "location": camera["location"],
            "channel_name": camera["channel_name"],
            "status": camera_status(camera, now),
            "last_seen_utc": camera["last_seen_utc"],
        }
        if is_admin:
            item["stream_address"] = camera["stream_address"]
        items.append(item)
    return jsonify(success=True, data={"items": items}), 200


@app.route("/api/v1/cameras/<camera_id>", methods=["PATCH"])
@require_administrator
def update_camera(camera_id):
    """Update camera details without code changes, validated first (SR-01-01, SQR-04)."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not payload:
        return jsonify(success=False, error="Expected a non-empty JSON object"), 400
    if payload.keys() - {"name", "location", "stream_address"}:
        return jsonify(
            success=False, error="Only name, location and stream_address can be changed"
        ), 400

    fields = {}
    for field in ("name", "location"):
        if field in payload:
            value = payload[field]
            if not isinstance(value, str) or not value.strip() or "\x00" in value:
                return jsonify(success=False, error=f"{field} must be a non-empty text value"), 400
            fields[field] = value.strip()
    if "stream_address" in payload:
        error = validate_stream_address(payload["stream_address"])
        if error:
            return jsonify(success=False, error=error), 400
        fields["stream_address"] = payload["stream_address"].strip()

    if not auth_db.update_camera(camera_id, **fields):
        return jsonify(success=False, error="Camera does not exist"), 404
    camera = auth_db.get_camera(camera_id)
    return jsonify(success=True, data={**camera, "status": camera_status(camera)}), 200


@app.route("/api/v1/cameras/<camera_id>/recordings", methods=["GET"])
@require_token
def list_camera_recordings(camera_id):
    """Catalogued 30-second segments and recording gaps for one camera (SR-01-03)."""
    if not auth_db.can_access_camera(g.current_user.user_id, camera_id):
        return jsonify(success=False, error="Camera does not exist"), 404

    now = utc_now()
    try:
        end = parse_utc(request.args["end"], "end") if "end" in request.args else now
        start = (
            parse_utc(request.args["start"], "start") if "start" in request.args
            else end - DEFAULT_RECORDING_QUERY
        )
    except ValueError as error:
        return jsonify(success=False, error=str(error)), 400
    if start >= end:
        return jsonify(success=False, error="start must be before end"), 400
    if end - start > MAX_RECORDING_QUERY:
        return jsonify(success=False, error="The requested range cannot exceed 31 days"), 400

    import_completed(auth_db, VIDEO_DIR)
    # Only segments whose files are still present count as recorded footage;
    # deleted or missing files show up as gaps instead.
    segments = [
        segment for segment in camera_segments(auth_db, camera_id, start, end)
        if "mp4" in segment["paths"] and media_file(VIDEO_DIR, segment["paths"]["mp4"]) is not None
    ]
    # Time after "now" is not missing footage yet.
    gaps = find_gaps(segments, start, min(end, now))

    camera = auth_db.get_camera(camera_id)
    return jsonify(success=True, data={
        "camera": {"id": camera["id"], "name": camera["name"],
                   "status": camera_status(camera, now), "last_seen_utc": camera["last_seen_utc"]},
        "start": start.isoformat(),
        "end": end.isoformat(),
        "segments": [{
            "id": segment["id"],
            "start": segment["start"].isoformat(),
            "end": segment["end"].isoformat(),
            "duration_seconds": (segment["end"] - segment["start"]).total_seconds(),
            "files": segment["files"],
        } for segment in segments],
        "gaps": [{
            "start": gap["start"].isoformat(),
            "end": gap["end"].isoformat(),
            "seconds": gap["seconds"],
        } for gap in gaps],
    }), 200


@app.route("/api/v1/users/<user_id>/cameras/<camera_id>", methods=["PUT", "DELETE"])
@require_administrator
def update_camera_assignment(user_id, camera_id):
    if any(not value.strip() or "\x00" in value for value in (user_id, camera_id)):
        return jsonify(
            success=False, error="User ID and camera ID must be non-empty text"
        ), 400

    try:
        if request.method == "PUT":
            auth_db.assign_camera(user_id, camera_id)
        else:
            auth_db.require_camera_assignment_targets(user_id, camera_id)
            auth_db.revoke_camera(user_id, camera_id)
    except ValueError as error:
        return jsonify(success=False, error=str(error)), 404
    except sqlite3.IntegrityError:
        # A grant can lose a foreign-key target after validation.
        return jsonify(
            success=False, error="User or camera does not exist"
        ), 404

    return jsonify(
        success=True, data={"user_id": user_id, "camera_id": camera_id}
    ), 200


@app.route("/api/v1/exports", methods=["POST"])
@require_token
def download_export():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Expected a JSON object"), 400

    filename = payload.get("filename")
    if (
        not isinstance(filename, str) or not filename
        or any(character in filename for character in ("/", "\\", "\x00"))
        or Path(filename).suffix not in (".mp4", ".webm")
    ):
        return jsonify(error="Select a valid recording"), 400

    start, end = payload.get("start_time"), payload.get("end_time")
    if any(isinstance(value, bool) or not isinstance(value, Real) for value in (start, end)):
        return jsonify(error="Enter start and end times in seconds"), 400
    if not 0 <= start < end < float("inf"):
        return jsonify(error="The end time must be greater than the start time"), 400

    source = resolve_recording(g.current_user.user_id, filename)
    if source is None:
        return jsonify(error="Recording unavailable"), 404

    workspace = TemporaryDirectory(prefix="camera-export-")
    output = Path(workspace.name) / "clip.mp4"
    try:
        tpool.execute(export_clip, source, output, start, end)
        response = send_file(output, mimetype="video/mp4", as_attachment=True, conditional=False)
    except InvalidClipRange as error:
        workspace.cleanup()
        return jsonify(error=str(error)), 400
    except Exception:
        workspace.cleanup()
        app.logger.exception("Recording export failed")
        return jsonify(error="Could not export the selected clip"), 500

    response.headers["Cache-Control"] = "no-store"
    response.direct_passthrough = False
    response.call_on_close(workspace.cleanup)
    return response


@app.route("/api/v1/incidents", methods=["POST"])
@require_token
def save_incident():
    """Save a portion of a recording as a flagged incident clip (UC04, SR-04-01..03)."""
    user = g.current_user
    if user.role not in INCIDENT_ROLES:
        return jsonify(
            success=False, error="Manager or administrator role required"
        ), 403

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(success=False, error="Expected a JSON object"), 400
    if payload.keys() - {"filename", "start_time", "end_time", "title", "notes"}:
        return jsonify(success=False, error="Unsupported incident fields"), 400

    file_name = payload.get("filename")
    if not isinstance(file_name, str) or not file_name or any(
        character in file_name for character in ("/", "\\", "\x00")
    ):
        return jsonify(success=False, error="filename must be a recording name"), 400

    start_time = payload.get("start_time")
    end_time = payload.get("end_time")
    if any(
        isinstance(value, bool) or not isinstance(value, Real)
        for value in (start_time, end_time)
    ):
        return jsonify(
            success=False, error="start_time and end_time must be numbers of seconds"
        ), 400
    if not 0 <= start_time < end_time:
        return jsonify(
            success=False, error="start_time must be before end_time"
        ), 400

    title = payload.get("title")
    if not isinstance(title, str) or not title.strip() or "\x00" in title:
        return jsonify(success=False, error="title must be a non-empty text value"), 400
    notes = payload.get("notes", "")
    if not isinstance(notes, str) or "\x00" in notes:
        return jsonify(success=False, error="notes must be a text value"), 400

    # Per-camera permission check before any footage is reached.
    if resolve_recording(user.user_id, file_name) is None:
        return jsonify(success=False, error="Recording unavailable"), 404

    incident_id = incident_manager().create_incident_clip(
        file_name, start_time, end_time, user.user_id,
        title=title.strip(), notes=notes
    )
    if incident_id is None:
        # SAF-02: report failure unless the archived clip was verified.
        return jsonify(
            success=False,
            error="Incident clip could not be saved; check the selected interval"
        ), 422

    incident = visible_incident(user.user_id, incident_id)
    return jsonify(success=True, data=incident_profile(incident)), 201


@app.route("/api/v1/incidents", methods=["GET"])
@require_token
def list_incidents():
    channels = [
        camera["channel_name"]
        for camera in auth_db.get_user_cameras(g.current_user.user_id)
    ]
    incidents = incident_repository().list_incidents(channels)
    return jsonify(
        success=True,
        data={"items": [incident_profile(incident) for incident in incidents]}
    ), 200


@app.route("/api/v1/incidents/<incident_id>", methods=["GET"])
@require_token
def get_incident(incident_id):
    incident = visible_incident(g.current_user.user_id, incident_id)
    if incident is None:
        return jsonify(success=False, error="Incident does not exist"), 404
    return jsonify(success=True, data=incident_profile(incident)), 200


@app.route("/api/v1/incidents/<incident_id>/video", methods=["GET"])
def get_incident_video(incident_id):
    token = (
        request.headers.get("x-access-token")
        or request.args.get("token")
    )
    if not token:
        return jsonify(status="ERROR", error="Missing token"), 401

    try:
        user = authenticator.get_authenticated_user(token, request.remote_addr)
    except jwt.exceptions.InvalidTokenError:
        return jsonify(status="ERROR", error="Invalid or expired token"), 401

    incident = visible_incident(user.user_id, incident_id)
    path = media_file(INCIDENT_ARCHIVE_DIR, incident["filename"]) if incident else None
    if path is None:
        return jsonify(status="ERROR", error="Incident clip unavailable"), 404

    return send_from_directory(
        str(path.parent),
        path.name,
        download_name=Path(incident["filename"]).name,
        as_attachment=False,
        mimetype="video/mp4"
    )


def deliver_live_frame(channel, image):
    if isinstance(channel, bytes):
        channel = channel.decode("utf-8")

    if not isinstance(channel, str) or not isinstance(image, bytes):
        return

    encoded_image = None

    for key, subscription in list(live_subscriptions.items()):
        if subscription["channel_name"] != channel:
            continue

        try:
            user = authenticator.get_authenticated_user(
                subscription["token"], subscription["ip"]
            )
        except jwt.exceptions.InvalidTokenError:
            live_subscriptions.pop(key, None)
            continue

        if not auth_db.can_access_camera(
            user.user_id, subscription["camera_id"]
        ):
            live_subscriptions.pop(key, None)
            continue

        if encoded_image is None:
            encoded_image = base64.b64encode(image).decode("utf-8")

        sid, requested_room = key
        socketio.emit(
            "image",
            {"room": requested_room, "data": encoded_image},
            to=sid,
            namespace="/"
        )

def listen_for_images(redis_url: str, redis_port: int):
    image_receiver = RedisImageReceiver(redis_url, redis_port)
    image_receiver.set_channels(image_receiver.get_all_channels())

    while True:
        channel_list = image_receiver.get_all_channels()
        if channel_list != image_receiver.subscribed_channels:
            image_receiver.set_channels(channel_list)

        message = image_receiver.get_new_message()

        if message and message.get("type") == "message":
            image = message.get("data")
            channel = message.get("channel")

            if isinstance(image, bytes) and isinstance(
                channel, (str, bytes)
            ):
                # Preserve the existing frontend's room naming.
                room = str(channel)
                rooms[room] = time.time()
                note_camera_frame(channel)
                deliver_live_frame(channel, image)

        eventlet.sleep(0.001)


def register_completed_recordings():
    while True:
        import_completed(auth_db, VIDEO_DIR)
        socketio.sleep(5)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--redis-url', help='Server address to stream images to', type=str, default='localhost')
    parser.add_argument('--redis-port', help='Server port to stream images to', type=int, default=6379)
    parser.add_argument('--video-dir', help='Directory in which video files are stored', type=str,
                        default="data/videos")
    parser.add_argument('--incident-dir', help='Directory for the protected incident clip archive', type=str,
                        default="data/incident_archive")
    args = parser.parse_args()

    VIDEO_DIR = args.video_dir
    INCIDENT_ARCHIVE_DIR = args.incident_dir
    ENABLE_USER_REGISTRATION = bool(int(os.environ.get("ENABLE_REGISTRATION")))

    socketio.start_background_task(register_completed_recordings)
    socketio.start_background_task(listen_for_images, args.redis_url, args.redis_port)
    # The Werkzeug debugger serves an interactive Python console at /console, so it
    # stays off unless a developer explicitly sets FLASK_DEBUG=1 on their own machine.
    debug = os.environ.get("FLASK_DEBUG") == "1"
    socketio.run(app, host='0.0.0.0', port="8443", debug=debug, certfile='certs/sec-cam-server.cert',
                 keyfile='certs/sec-cam-server.key')
