import os
import sqlite3
from typing import List

from smart_sec_cam.auth.models import User


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

        self.conn.commit()

    def add_user(self, user: User):
        cursor = self.conn.cursor()
        # Throw an error if this user already exists
        if self.get_user_by_username_or_id(user.user_id, user.username):
            raise ValueError("A user with this user id or username already exists")
        # Create User
        cursor.execute(
            f"INSERT INTO {self.USER_TABLE} "
            "(id, username, salt, hash, role) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                user.user_id,
                user.username,
                user.salt,
                user.password_hash,
                user.role
            )
        )
        self.conn.commit()

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
