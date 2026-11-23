import datetime
import os

import jwt

from smart_sec_cam.auth.database import AuthDatabase


class Authenticator:
    JWT_SECRET_LENGTH = 32
    TOKEN_DURATION_HOURS = 1

    def __init__(self, auth_db: AuthDatabase):
        self.auth_db = auth_db
        self.secret = os.urandom(self.JWT_SECRET_LENGTH)

    def authenticate(self, username: str, password: str, client_ip_addr) -> str:
        # Get user by id from database. If it doesn't exist, return error
        existing_user = self.auth_db.get_user_by_username(username)
        if not existing_user:
            raise ValueError(f"Failed to find user with username: {username}")
        # Verify that password matches
        if not existing_user.does_password_match(password):
            raise ValueError(f"Password mismatch for user: {username}")
        # Generate JWT and return it
        return self._generate_token(existing_user.user_id, client_ip_addr)

    def validate_token(self, token: str, client_ip_addr: str) -> bool:
        payload = jwt.decode(token, self.secret, algorithms=['HS256'])
        return payload['exp'] > self._now().timestamp() and payload['client_ip'] == client_ip_addr

    def refresh_token(self, token: str, client_ip_addr: str) -> str:
        if self.validate_token(token, client_ip_addr):
            payload = jwt.decode(token, self.secret, algorithms=['HS256'])
            return self._generate_token(payload['sub'], client_ip_addr)

    def get_token_ttl(self, token: str) -> float:
        """
        Returns token's time to live (TTL) in seconds
        """
        payload = jwt.decode(token, self.secret, algorithms=['HS256'])
        return payload['exp'] - self._now().timestamp()

    @staticmethod
    def _now() -> datetime.datetime:
        # Timezone-aware UTC. A naive utcnow() is interpreted as local time by
        # .timestamp(), which shifts 'iat'/'exp' by the host's UTC offset and
        # makes tokens invalid on any server not running in UTC.
        return datetime.datetime.now(datetime.timezone.utc)

    def _generate_token(self, user_id: str, client_ip_addr: str) -> str:
        now = self._now()
        payload = {
            'exp': (now + datetime.timedelta(hours=self.TOKEN_DURATION_HOURS)).timestamp(),
            'iat': (now - datetime.timedelta(seconds=1)).timestamp(),  # Decrement by one to prevent "token not yet valid" error.
            'sub': user_id,
            'client_ip': client_ip_addr
        }
        return jwt.encode(payload, self.secret, algorithm='HS256')

    def get_authenticated_user(self, token: str, client_ip_addr: str):
        payload = jwt.decode(
            token,
            self.secret,
            algorithms=["HS256"],
            options={"require": ["exp", "sub", "client_ip"]}
        )

        if payload["client_ip"] != client_ip_addr:
            raise jwt.InvalidTokenError("Client address mismatch")

        user_id = payload["sub"]
        if not isinstance(user_id, str) or not user_id:
            raise jwt.InvalidTokenError("Invalid user identity")

        user = self.auth_db.get_user_by_id(user_id)
        if user is None:
            raise jwt.InvalidTokenError("User no longer exists")

        return user
