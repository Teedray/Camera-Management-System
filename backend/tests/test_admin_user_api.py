import json
from unittest.mock import patch

from test_admin_camera_api import AdminApiTestCase


USERS_URL = "/api/v1/users"
VIEWER_URL = f"{USERS_URL}/viewer-id"
NEW_USER = {"username": "new-user", "password": "test-only-password"}


class AdminUserApiTest(AdminApiTestCase):
    def test_requires_a_current_administrator_for_every_method(self):
        with patch.object(self.server.authenticator, "TOKEN_DURATION_HOURS", -1):
            login = self.client.post("/api/auth/login", json={
                "username": "administrator", "password": "test-password"
            })
        expired = {"x-access-token": json.loads(login.data)["token"]}

        for headers, status, error in (
            ({}, 401, "Missing token"),
            ({"x-access-token": "invalid"}, 401, "Invalid or expired token"),
            (expired, 401, "Invalid or expired token"),
            (self.headers["manager"], 403, "Administrator role required"),
            (self.headers["viewer"], 403, "Administrator role required")
        ):
            for method, url, payload in (
                ("GET", USERS_URL, None),
                ("POST", USERS_URL, NEW_USER),
                ("PATCH", VIEWER_URL, {"role": "administrator"})
            ):
                with self.subTest(method=method, status=status, error=error):
                    response = self.client.open(url, method=method, headers=headers, json=payload)
                    self.assert_error(response, status, error)

        self.assertEqual(self.db.get_num_users(), 3)
        self.assertEqual(self.db.get_user_by_id("viewer-id").role, "viewer")

    def test_list_returns_only_public_user_fields(self):
        response = self.client.get(USERS_URL, headers=self.headers["administrator"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "success": True,
            "data": {"items": [
                {"id": f"{role}-id", "username": role, "role": role}
                for role in ("administrator", "manager", "viewer")
            ]}
        })

    def test_creates_users_with_default_and_explicit_roles(self):
        admin = self.headers["administrator"]
        for username, requested_role, expected_role in (
            ("new-viewer", {}, "viewer"),
            ("new-manager", {"role": "manager"}, "manager"),
            ("new-admin", {"role": "administrator"}, "administrator")
        ):
            with self.subTest(username=username):
                password = "  " + NEW_USER["password"] + "  "
                response = self.client.post(USERS_URL, headers=admin, json={
                    "username": username, "password": password, **requested_role
                })
                self.assertEqual(response.status_code, 201)

                stored_user = self.db.get_user_by_username(username)
                self.assertRegex(stored_user.user_id, r"^[0-9a-f]{32}$")
                self.assertTrue(stored_user.does_password_match(password))
                self.assertNotEqual(stored_user.password_hash, password.encode())
                self.assertEqual(response.get_json(), {
                    "success": True,
                    "data": {"id": stored_user.user_id, "username": username, "role": expected_role}
                })

                login = self.client.post("/api/auth/login", json={
                    "username": username, "password": password
                })
                self.assertEqual(login.status_code, 200)
                token = {"x-access-token": json.loads(login.data)["token"]}
                cameras = self.client.get("/api/v1/cameras", headers=token).get_json()
                self.assertEqual(cameras["data"]["items"], [])

    def test_duplicate_creation_keeps_the_existing_account_and_assignment(self):
        self.db.add_camera("cam", "Camera", "Entrance", "stream")
        self.db.assign_camera("viewer-id", "cam")
        response = self.client.post(USERS_URL, headers=self.headers["administrator"], json={
            "username": "viewer", "password": "different-password", "role": "administrator"
        })
        self.assert_error(response, 409, "Username already exists")

        self.assertEqual(self.db.get_num_users(), 3)
        viewer = self.db.get_user_by_id("viewer-id")
        self.assertEqual(viewer.role, "viewer")
        self.assertTrue(viewer.does_password_match("test-password"))
        self.assertTrue(self.db.can_access_camera("viewer-id", "cam"))

    def test_rejects_invalid_creation_inputs(self):
        admin = self.headers["administrator"]
        for body in ("{", "null", "[]"):
            response = self.client.post(
                USERS_URL, headers=admin, data=body, content_type="application/json"
            )
            self.assert_error(response, 400, "Expected a JSON object")

        for payload, error in (
            ({}, "username must be a non-empty text value"),
            ({"username": "name"}, "password must be a non-empty text value"),
            ({**NEW_USER, "username": " "}, "username must be a non-empty text value"),
            ({**NEW_USER, "username": 9}, "username must be a non-empty text value"),
            ({**NEW_USER, "password": " "}, "password must be a non-empty text value"),
            ({**NEW_USER, "password": None}, "password must be a non-empty text value"),
            ({**NEW_USER, "username": "name\0"}, "username must be a non-empty text value"),
            ({**NEW_USER, "password": "\ud800"}, "Username and password must contain valid Unicode"),
            ({**NEW_USER, "role": "owner"}, "Invalid user role"),
            ({**NEW_USER, "role": None}, "Invalid user role"),
            ({**NEW_USER, "id": "custom-id"}, "Unsupported user fields")
        ):
            with self.subTest(payload_keys=list(payload), error=error):
                response = self.client.post(USERS_URL, headers=admin, json=payload)
                self.assert_error(response, 400, error)

        self.assertEqual(self.db.get_num_users(), 3)

    def test_role_changes_take_effect_for_existing_tokens_and_keep_assignments(self):
        admin = self.headers["administrator"]
        viewer = self.headers["viewer"]
        self.db.add_camera("cam", "Camera", "Entrance", "stream")
        self.db.assign_camera("viewer-id", "cam")

        response = self.client.patch(VIEWER_URL, headers=admin, json={"role": "administrator"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "success": True,
            "data": {"id": "viewer-id", "username": "viewer", "role": "administrator"}
        })
        self.assertEqual(self.client.get(USERS_URL, headers=viewer).status_code, 200)
        self.assertTrue(self.db.can_access_camera("viewer-id", "cam"))
        self.assertFalse(self.db.can_access_camera("administrator-id", "cam"))

        response = self.client.patch(
            f"{USERS_URL}/administrator-id", headers=viewer, json={"role": "manager"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"]["role"], "manager")
        self.assert_error(
            self.client.get(USERS_URL, headers=admin), 403, "Administrator role required"
        )
        self.assertFalse(self.db.can_access_camera("administrator-id", "cam"))

        response = self.client.patch(
            f"{USERS_URL}/administrator-id", headers=viewer, json={"role": "viewer"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"]["role"], "viewer")

    def test_rejects_invalid_role_updates_and_reports_unknown_users(self):
        admin = self.headers["administrator"]
        response = self.client.patch(VIEWER_URL, headers=admin, json=["viewer"])
        self.assert_error(response, 400, "Expected a JSON object")

        for payload, error in (
            ({}, "Only the role field is supported"),
            ({"role": "manager", "username": "renamed"}, "Only the role field is supported"),
            ({"role": "manager", "password": "changed"}, "Only the role field is supported"),
            ({"role": "owner"}, "Invalid user role"),
            ({"role": ["viewer"]}, "Invalid user role")
        ):
            with self.subTest(payload=payload):
                response = self.client.patch(VIEWER_URL, headers=admin, json=payload)
                self.assert_error(response, 400, error)

        response = self.client.patch(
            f"{USERS_URL}/missing", headers=admin, json={"role": "viewer"}
        )
        self.assert_error(response, 404, "User does not exist")
        self.assertEqual(self.db.get_user_by_id("viewer-id").role, "viewer")

    def test_last_administrator_cannot_be_demoted(self):
        admin = self.headers["administrator"]
        url = f"{USERS_URL}/administrator-id"
        for role in ("manager", "viewer"):
            response = self.client.patch(url, headers=admin, json={"role": role})
            self.assert_error(response, 409, "Cannot demote the last administrator")

        response = self.client.patch(url, headers=admin, json={"role": "administrator"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(USERS_URL, headers=admin).status_code, 200)
