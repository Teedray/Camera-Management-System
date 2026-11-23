import os
import sqlite3
from typing import List

from smart_sec_cam.auth.models import User


class LastAdministratorError(ValueError):
    pass


class AuthDatabase:
    DATABASE_DIR = "data/"
    FILE_TYPE = ".db"
    USER_TABLE = "users"

    def __init__(self, db_name: str = "smart-sec-cam"):
        self.db_name = db_name
        # Create db directory if it doesnt exist
        if not os.path.exists(self.DATABASE_DIR):
            os.makedirs(self.DATABASE_DIR)
        # Connect to the database
        self.conn = sqlite3.connect(os.path.join(self.DATABASE_DIR, self.db_name + self.FILE_TYPE))
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.setup()

    def setup(self):
        cursor = self.conn.cursor()

        cursor.execute(
            f"CREATE TABLE IF NOT EXISTS {self.USER_TABLE} "
            "(id, username, salt, hash)"
        )

        columns = {
            row[1]
            for row in cursor.execute(
                f"PRAGMA table_info({self.USER_TABLE})"
            )
        }

        if "role" not in columns:
            cursor.execute(
                f"ALTER TABLE {self.USER_TABLE} "
                "ADD COLUMN role TEXT NOT NULL DEFAULT 'viewer' "
                "CHECK (role IN ('administrator', 'manager', 'viewer'))"
            )

        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "idx_users_id_unique ON users(id)"
        )

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cameras (
                id TEXT PRIMARY KEY NOT NULL,
                name TEXT NOT NULL,
                location TEXT NOT NULL,
                channel_name TEXT UNIQUE NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1
                    CHECK (enabled IN (0, 1))
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_cameras (
                user_id TEXT NOT NULL,
                camera_id TEXT NOT NULL,
                PRIMARY KEY (user_id, camera_id),
                FOREIGN KEY (user_id)
                    REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (camera_id)
                    REFERENCES cameras(id) ON DELETE CASCADE
            )
        """)

        self.conn.commit()

        columns = {
            row[1]
            for row in cursor.execute(
                f"PRAGMA table_info({self.USER_TABLE})"
            )
        }

        if "role" not in columns:
            cursor.execute(
                f"ALTER TABLE {self.USER_TABLE} "
                "ADD COLUMN role TEXT NOT NULL DEFAULT 'viewer' "
                "CHECK (role IN ('administrator', 'manager', 'viewer'))"
            )

        self.conn.commit()

    def add_user(self, user: User):
        with self.conn:
            inserted = self.conn.execute(
                f"INSERT INTO {self.USER_TABLE} (id, username, salt, hash, role) "
                "SELECT ?, ?, ?, ?, ? "
                f"WHERE NOT EXISTS (SELECT 1 FROM {self.USER_TABLE} "
                "WHERE id = ? OR username = ?)",
                (
                    user.user_id, user.username, user.salt, user.password_hash,
                    user.role, user.user_id, user.username
                )
            ).rowcount
            if not inserted:
                raise ValueError("A user with this user id or username already exists")

    def list_user_profiles(self):
        rows = self.conn.execute(
            f"SELECT id, username, role FROM {self.USER_TABLE} ORDER BY username, id"
        )
        return [
            {"id": user_id, "username": username, "role": role}
            for user_id, username, role in rows
        ]

    def update_user_role(self, user_id: str, role: str):
        with self.conn:
            # SQLite checks for another administrator while holding the write lock.
            updated = self.conn.execute(
                f"UPDATE {self.USER_TABLE} SET role = ? WHERE id = ? AND ("
                "role != 'administrator' OR ? = 'administrator' OR EXISTS ("
                f"SELECT 1 FROM {self.USER_TABLE} "
                "WHERE role = 'administrator' AND id != ?))",
                (role, user_id, role, user_id)
            ).rowcount
            row = self.conn.execute(
                f"SELECT id, username, role FROM {self.USER_TABLE} WHERE id = ?",
                (user_id,)
            ).fetchone()

            if row is None:
                return None
            if not updated:
                raise LastAdministratorError("Cannot demote the last administrator")

        return {"id": row[0], "username": row[1], "role": row[2]}

    def get_user_by_id(self, user_id: str):
        cursor = self.conn.cursor()
        cursor.execute(
            f"SELECT id, username, salt, hash, role "
            f"FROM {self.USER_TABLE} WHERE id = ?",
            (user_id,)
        )
        row = cursor.fetchone()

        if row is None:
            return None

        return User(
            username=row[1],
            user_id=row[0],
            salt=row[2],
            password_hash=row[3],
            role=row[4]
        )

    def get_user_by_username(self, username: str):
        cursor = self.conn.cursor()
        cursor.execute(
            f"SELECT id, username, salt, hash, role "
            f"FROM {self.USER_TABLE} WHERE username = ?",
            (username,)
        )
        row = cursor.fetchone()

        if row is None:
            return None

        return User(
            username=row[1],
            user_id=row[0],
            salt=row[2],
            password_hash=row[3],
            role=row[4]
        )

    def get_user_by_username_or_id(
        self, user_id: str, username: str
    ) -> List[User]:
        cursor = self.conn.cursor()
        cursor.execute(
            f"SELECT id, username, salt, hash, role "
            f"FROM {self.USER_TABLE} WHERE id = ? OR username = ?",
            (user_id, username)
        )

        return [
            User(
                username=row[1],
                user_id=row[0],
                salt=row[2],
                password_hash=row[3],
                role=row[4]
            )
            for row in cursor.fetchall()
        ]

    def get_num_users(self) -> int:
        cursor = self.conn.cursor()
        result = cursor.execute(f"SELECT Count() FROM {self.USER_TABLE}")
        return result.fetchone()[0]

    def add_camera(self, camera_id, name, location, channel_name):
        values = (camera_id, name, location, channel_name)
        if any(
            not isinstance(value, str) or not value.strip()
            for value in values
        ):
            raise ValueError("Camera fields must be non-empty strings")

        with self.conn:
            self.conn.execute(
                "INSERT INTO cameras "
                "(id, name, location, channel_name) "
                "VALUES (?, ?, ?, ?)",
                tuple(value.strip() for value in values)
            )

    def require_camera_assignment_targets(self, user_id, camera_id):
        if self.get_user_by_id(user_id) is None:
            raise ValueError("User does not exist")

        camera = self.conn.execute(
            "SELECT id FROM cameras WHERE id = ?",
            (camera_id,)
        ).fetchone()

        if camera is None:
            raise ValueError("Camera does not exist")

    def assign_camera(self, user_id, camera_id):
        self.require_camera_assignment_targets(user_id, camera_id)

        with self.conn:
            self.conn.execute(
                "INSERT INTO user_cameras (user_id, camera_id) "
                "VALUES (?, ?) "
                "ON CONFLICT(user_id, camera_id) DO NOTHING",
                (user_id, camera_id)
            )

    def revoke_camera(self, user_id, camera_id):
        with self.conn:
            self.conn.execute(
                "DELETE FROM user_cameras "
                "WHERE user_id = ? AND camera_id = ?",
                (user_id, camera_id)
            )

    def get_user_cameras(self, user_id):
        rows = self.conn.execute(
            "SELECT c.id, c.name, c.location, c.channel_name, c.enabled "
            "FROM cameras c "
            "JOIN user_cameras uc ON uc.camera_id = c.id "
            "JOIN users u ON u.id = uc.user_id "
            "WHERE u.id = ? AND c.enabled = 1 "
            "ORDER BY c.name, c.id",
            (user_id,)
        ).fetchall()

        return [
            {
                "id": row[0],
                "name": row[1],
                "location": row[2],
                "channel_name": row[3],
                "enabled": bool(row[4])
            }
            for row in rows
        ]

    def can_access_camera(self, user_id, camera_id):
        row = self.conn.execute(
            "SELECT 1 "
            "FROM user_cameras uc "
            "JOIN users u ON u.id = uc.user_id "
            "JOIN cameras c ON c.id = uc.camera_id "
            "WHERE u.id = ? AND c.id = ? AND c.enabled = 1",
            (user_id, camera_id)
        ).fetchone()

        return row is not None
