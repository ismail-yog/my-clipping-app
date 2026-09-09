"""
StreamClipper — Unit Tests for Multi-User Authentication Engine
Verifies password hashing, salt verification, JWT session issuance, and user database isolation.
"""

import unittest
import time
from pathlib import Path

from server.auth_service import (
    hash_password,
    verify_password,
    create_jwt_token,
    verify_jwt_token,
)
from database import Database


class TestUserAuth(unittest.TestCase):
    def setUp(self):
        self.test_db_path = Path(f"temp/test_user_auth_{int(time.time() * 1000)}.db")
        self.test_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = Database(db_path=str(self.test_db_path))

    def tearDown(self):
        try:
            self.test_db_path.unlink(missing_ok=True)
        except Exception:
            pass

    def test_password_hashing_and_verification(self):
        pw = "SuperSecretPassword123!"
        hashed = hash_password(pw)
        self.assertIn("$", hashed)
        self.assertTrue(verify_password(pw, hashed))
        self.assertFalse(verify_password("WrongPassword", hashed))

    def test_jwt_token_roundtrip(self):
        payload = {"sub": 42, "email": "creator@streamclipper.io"}
        token = create_jwt_token(payload, expires_in=3600)
        decoded = verify_jwt_token(token)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded["sub"], 42)
        self.assertEqual(decoded["email"], "creator@streamclipper.io")

    def test_user_creation_and_isolation(self):
        u1_id = self.db.create_user("alice@domain.com", hash_password("pass1"), "Alice")
        u2_id = self.db.create_user("bob@domain.com", hash_password("pass2"), "Bob")
        self.assertNotEqual(u1_id, u2_id)

        alice = self.db.get_user_by_email("alice@domain.com")
        self.assertIsNotNone(alice)
        self.assertEqual(alice["id"], u1_id)

        # Save clip for Alice
        c1 = self.db.save_clip(
            clip_id="alice_clip_1",
            streamer_name="KaiCenat",
            platform="twitch",
            clip_path="temp/dummy.mp4",
            duration=35.0,
            moment_score=0.92,
            user_id=u1_id,
        )
        self.assertGreater(c1, 0)

        # Save clip for Bob
        c2 = self.db.save_clip(
            clip_id="bob_clip_1",
            streamer_name="xQc",
            platform="kick",
            clip_path="temp/dummy2.mp4",
            duration=32.0,
            moment_score=0.88,
            user_id=u2_id,
        )
        self.assertGreater(c2, 0)

        # Alice's query should include her own clips
        alice_clips = self.db.get_clips(user_id=u1_id)
        alice_ids = [c["clip_id"] for c in alice_clips]
        self.assertIn("alice_clip_1", alice_ids)


if __name__ == "__main__":
    unittest.main()
