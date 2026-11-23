import base64
import json
import os
import time
from datetime import datetime
from functools import wraps

import eventlet
eventlet.monkey_patch()

import jwt.exceptions
from flask import (
    Flask, send_from_directory, render_template,
    request, g, jsonify
)
from flask_cors import CORS
from flask_socketio import SocketIO, join_room

from smart_sec_cam.auth.authentication import Authenticator
from smart_sec_cam.auth.database import AuthDatabase
from smart_sec_cam.auth.models import User
from smart_sec_cam.redis import RedisImageReceiver
from smart_sec_cam.video.manager import VideoManager

# SocketIO & CORS
app = Flask(__name__, static_url_path='', static_folder='/backend/build', template_folder='/backend/build')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")
# Authentication
auth_db = AuthDatabase()
authenticator = Authenticator(auth_db)
# Application-specific data
VIDEO_DIR = "data/videos"
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

    recordings = []

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
                    recordings.append((timestamp, entry.name))
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

    details = recording_details(file_name)
    if details is None:
        return jsonify(
            status="ERROR", error="Recording unavailable"
        ), 404

    channel, timestamp, extension = details

    allowed_channels = {
        camera["channel_name"]
        for camera in auth_db.get_user_cameras(user.user_id)
    }

    if channel not in allowed_channels:
        return jsonify(
            status="ERROR", error="Recording unavailable"
        ), 404

    directory = os.path.abspath(VIDEO_DIR)
    path = os.path.join(directory, file_name)

    if not os.path.isfile(path) or os.path.islink(path):
        return jsonify(
            status="ERROR", error="Recording unavailable"
        ), 404

    mime_type = (
        "video/webm" if extension == ".webm" else "video/mp4"
    )

    return send_from_directory(
        directory,
        file_name,
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

@app.route("/api/v1/cameras", methods=["GET"])
@require_token
def list_assigned_cameras():
    cameras = auth_db.get_user_cameras(g.current_user.user_id)

    return jsonify(
        success=True,
        data={"items": cameras}
    ), 200

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
                deliver_live_frame(channel, image)

        eventlet.sleep(0.001)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--redis-url', help='Server address to stream images to', type=str, default='localhost')
    parser.add_argument('--redis-port', help='Server port to stream images to', type=int, default=6379)
    parser.add_argument('--video-dir', help='Directory in which video files are stored', type=str,
                        default="data/videos")
    args = parser.parse_args()

    VIDEO_DIR = args.video_dir
    ENABLE_USER_REGISTRATION = bool(int(os.environ.get("ENABLE_REGISTRATION")))

    socketio.start_background_task(listen_for_images, args.redis_url, args.redis_port)
    socketio.run(app, host='0.0.0.0', port="8443", debug=True, certfile='certs/sec-cam-server.cert',
                 keyfile='certs/sec-cam-server.key')
