import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from smart_sec_cam.auth.authentication import Authenticator
from smart_sec_cam.auth.database import AuthDatabase
from smart_sec_cam.auth.models import User


CAMERAS_URL = "/api/v1/cameras"
ASSIGNMENT_URL = "/api/v1/users/viewer-id/cameras/front-door"
CAMERA = {
    "id": "front-door",
    "name": "Front Door",
    "location": "Entrance",
    "channel_name": "front-stream"
}


class AdminCameraApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from contextlib import ExitStack

        with ExitStack() as cleanup:
            directory = cleanup.enter_context(tempfile.TemporaryDirectory())
            with patch.object(AuthDatabase, "DATABASE_DIR", directory):
                from smart_sec_cam.server import server

            cleanup.callback(server.auth_db.conn.close)
            cls.server = server
            cls.addClassCleanup(cleanup.pop_all().close)

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        with patch.object(AuthDatabase, "DATABASE_DIR", directory.name):
            self.db = AuthDatabase("test")
        self.addCleanup(self.db.conn.close)
        self.start_patch("auth_db", self.db)
        self.start_patch("authenticator", Authenticator(self.db))
        self.start_patch("VIDEO_DIR", directory.name)
        self.client = self.server.app.test_client()

        self.headers = {}
        for role in ("administrator", "manager", "viewer"):
            user = User(role, user_id=f"{role}-id", role=role)
            user.set_password("test-password")
            self.db.add_user(user)
            response = self.client.post("/api/auth/login", json={
                "username": role, "password": "test-password"
            })
            self.assertEqual(response.status_code, 200)
            self.headers[role] = {"x-access-token": json.loads(response.data)["token"]}

    def start_patch(self, attribute, value):
        replacement = patch.object(self.server, attribute, value)
        replacement.start()
        self.addCleanup(replacement.stop)

    def assert_error(self, response, status_code, error):
        self.assertEqual(response.status_code, status_code, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["error"], error)

    def register_camera(self):
        return self.client.post(
            CAMERAS_URL, json=CAMERA, headers=self.headers["administrator"]
        )

    def test_all_mutations_require_an_authenticated_administrator(self):
        self.db.add_camera(*CAMERA.values())
        for headers, status_code, error in (
            ({}, 401, "Missing token"),
            ({"x-access-token": "invalid"}, 401, "Invalid or expired token"),
            (self.headers["manager"], 403, "Administrator role required"),
            (self.headers["viewer"], 403, "Administrator role required")
        ):
            for method, url, payload in (
                ("POST", CAMERAS_URL, {**CAMERA, "id": "another", "channel_name": "another"}),
                ("PUT", ASSIGNMENT_URL, None),
                ("DELETE", ASSIGNMENT_URL, None)
            ):
                # Seed access only for DELETE so an unauthorized mutation is observable.
                if method == "DELETE":
                    self.db.assign_camera("viewer-id", CAMERA["id"])
                with self.subTest(method=method, status=status_code, headers_present=bool(headers)):
                    response = self.client.open(url, method=method, json=payload, headers=headers)
                    self.assert_error(response, status_code, error)
                    self.assertEqual(
                        self.db.can_access_camera("viewer-id", CAMERA["id"]),
                        method == "DELETE"
                    )
                self.db.revoke_camera("viewer-id", CAMERA["id"])
        self.assertEqual(self.db.conn.execute("SELECT COUNT(*) FROM cameras").fetchone(), (1,))

    def test_same_token_uses_current_database_role(self):
        with self.db.conn:
            self.db.conn.execute(
                "UPDATE users SET role = ? WHERE id = ?", ("viewer", "administrator-id")
            )

        self.assert_error(self.register_camera(), 403, "Administrator role required")

        with self.db.conn:
            self.db.conn.execute(
                "UPDATE users SET role = ? WHERE id = ?", ("administrator", "administrator-id")
            )

        self.assertEqual(self.register_camera().status_code, 201)

    def test_registers_camera_and_reports_duplicate_id_or_channel(self):
        headers = self.headers["administrator"]
        response = self.client.post(
            CAMERAS_URL, json={**CAMERA, "name": " Front Door "}, headers=headers
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), {
            "success": True, "data": {**CAMERA, "enabled": True}
        })

        for payload in (
            {**CAMERA, "name": "Replacement", "channel_name": "different-stream"},
            {**CAMERA, "id": "different-camera"}
        ):
            with self.subTest(payload=payload):
                response = self.client.post(CAMERAS_URL, json=payload, headers=headers)
                self.assert_error(response, 409, "Camera ID or channel name already exists")

        self.assertEqual(
            self.db.conn.execute("SELECT id, name, location, channel_name FROM cameras").fetchall(),
            [tuple(CAMERA.values())]
        )

    def test_rejects_invalid_camera_payloads_and_assignment_identifiers(self):
        headers = self.headers["administrator"]
        for body in ("{", "[]", "null"):
            response = self.client.post(
                CAMERAS_URL, data=body, content_type="application/json", headers=headers
            )
            self.assert_error(response, 400, "Expected a JSON object")

        for field, invalid in (("id", None), ("name", 123), ("location", " "), ("channel_name", "\0")):
            with self.subTest(field=field):
                response = self.client.post(
                    CAMERAS_URL, json={**CAMERA, field: invalid}, headers=headers
                )
                self.assert_error(response, 400, f"{field} must be a non-empty text value")

        for field, invalid in (("id", "a/b"), ("channel_name", r"a\b"), ("name", "\ud800")):
            with self.subTest(field=field):
                response = self.client.post(
                    CAMERAS_URL, json={**CAMERA, field: invalid}, headers=headers
                )
                self.assertEqual(response.status_code, 400)

        for method in ("PUT", "DELETE"):
            response = self.client.open(
                "/api/v1/users/%20/cameras/front-door", method=method, headers=headers
            )
            self.assert_error(response, 400, "User ID and camera ID must be non-empty text")

        self.assertEqual(self.register_camera().status_code, 201)

    def test_grant_and_revoke_report_missing_targets(self):
        self.assertEqual(self.register_camera().status_code, 201)
        headers = self.headers["administrator"]
        for method in ("PUT", "DELETE"):
            for url, error in (
                ("/api/v1/users/missing/cameras/front-door", "User does not exist"),
                ("/api/v1/users/viewer-id/cameras/missing", "Camera does not exist")
            ):
                with self.subTest(method=method, url=url):
                    response = self.client.open(url, method=method, headers=headers)
                    self.assert_error(response, 404, error)

    def test_repeated_grants_and_revocations_control_camera_and_footage_access(self):
        self.assertEqual(self.register_camera().status_code, 201)
        admin = self.headers["administrator"]
        viewer = self.headers["viewer"]
        file_name = "front-stream__2026-01-01_10:00:00.webm"
        recording_url = f"/api/video/{file_name}"
        Path(self.server.VIDEO_DIR, file_name).write_bytes(b"test recording")
        socket = self.server.socketio.test_client(
            self.server.app, flask_test_client=self.client
        )
        self.addCleanup(socket.disconnect)
        join_request = {"token": viewer["x-access-token"], "room": CAMERA["channel_name"]}

        self.assertEqual(self.client.get(recording_url, headers=admin).status_code, 404)
        self.assertEqual(self.client.get(CAMERAS_URL, headers=admin).get_json()["data"]["items"], [])
        self.assertEqual(socket.emit("join", join_request, callback=True)["status"], "ERROR")

        for _ in range(2):
            response = self.client.put(ASSIGNMENT_URL, headers=admin)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), {
                "success": True, "data": {"user_id": "viewer-id", "camera_id": CAMERA["id"]}
            })
        self.assertEqual(self.client.get(CAMERAS_URL, headers=viewer).get_json()["data"]["items"],
                         [{**CAMERA, "enabled": True}])
        self.assertEqual(self.client.get("/api/video/video-list", headers=viewer).get_json()["videos"],
                         [file_name])
        with self.client.get(recording_url, headers=viewer) as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b"test recording")
        self.assertEqual(socket.emit("join", join_request, callback=True)["status"], "OK")
        self.server.deliver_live_frame(CAMERA["channel_name"], b"frame")
        self.assertEqual([event["name"] for event in socket.get_received()], ["image"])

        for _ in range(2):
            response = self.client.delete(ASSIGNMENT_URL, headers=admin)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.get_json()["success"])
        self.assertEqual(self.client.get(CAMERAS_URL, headers=viewer).get_json()["data"]["items"], [])
        self.assertEqual(self.client.get("/api/video/video-list", headers=viewer).get_json()["videos"], [])
        self.assertEqual(self.client.get(recording_url, headers=viewer).status_code, 404)
        self.server.deliver_live_frame(CAMERA["channel_name"], b"frame")
        self.assertEqual(socket.get_received(), [])
        self.assertEqual(socket.emit("join", join_request, callback=True)["status"], "ERROR")
