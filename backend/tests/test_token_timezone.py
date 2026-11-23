"""Tokens must be valid regardless of the server's local timezone."""
import os
import time
import unittest
from unittest.mock import MagicMock

import jwt

from smart_sec_cam.auth.authentication import Authenticator


@unittest.skipUnless(hasattr(time, "tzset"), "time.tzset is required to change the timezone")
class TokenTimezoneTest(unittest.TestCase):
    def setUp(self):
        original = os.environ.get("TZ")

        def restore():
            if original is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original
            time.tzset()

        self.addCleanup(restore)
        self.authenticator = Authenticator(MagicMock())

    def test_tokens_are_valid_on_hosts_behind_and_ahead_of_utc(self):
        # Jamaica (UTC-5, the deployment site) and a zone ahead of UTC.
        for zone in ("America/Jamaica", "Asia/Tokyo", "UTC"):
            with self.subTest(zone=zone):
                os.environ["TZ"] = zone
                time.tzset()
                token = self.authenticator._generate_token("user-1", "127.0.0.1")

                payload = jwt.decode(
                    token, self.authenticator.secret, algorithms=["HS256"],
                    options={"require": ["exp", "iat", "sub", "client_ip"]}
                )
                now = time.time()
                self.assertLessEqual(payload["iat"], now)
                self.assertAlmostEqual(
                    payload["exp"] - now,
                    Authenticator.TOKEN_DURATION_HOURS * 3600, delta=5
                )
                self.assertTrue(self.authenticator.validate_token(token, "127.0.0.1"))
                self.assertAlmostEqual(
                    self.authenticator.get_token_ttl(token),
                    Authenticator.TOKEN_DURATION_HOURS * 3600, delta=5
                )
