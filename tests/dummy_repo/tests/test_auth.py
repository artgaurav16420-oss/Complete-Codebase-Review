import os
import sys
import unittest
from unittest.mock import patch, MagicMock

class TestAuth(unittest.TestCase):
    def test_login_success(self):
        from auth.login import login
        with patch.dict(os.environ, {"AUTH_SECRET": "correct_password"}):
            self.assertTrue(login("admin", "correct_password"))

    def test_login_failure(self):
        from auth.login import login
        with patch.dict(os.environ, {"AUTH_SECRET": "correct_password"}):
            self.assertFalse(login("admin", "wrong_password"))

    def test_login_missing_secret(self):
        from auth.login import login
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(login("admin", "any_password"))

    def test_login_blank_secret(self):
        from auth.login import login
        with patch.dict(os.environ, {"AUTH_SECRET": ""}):
            self.assertFalse(login("admin", ""))

    def test_login_unauthorized_user(self):
        from auth.login import login
        with patch.dict(os.environ, {"AUTH_SECRET": "correct_password"}):
            self.assertFalse(login("hacker", "correct_password"))

    def test_ping(self):
        from auth.login import ping_host
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = ping_host("127.0.0.1")
            self.assertTrue(result)

    @patch.dict('sys.modules', {'notifications.email': MagicMock()})
    def test_create_user(self):
        from auth.user import create_user
        mock_send_email = sys.modules['notifications.email'].send_email
        user_id = create_user("Alice", "alice@example.com")
        self.assertEqual(user_id, hash("Alice"))
        mock_send_email.assert_called_once_with("alice@example.com", "Welcome", "Hi Alice")
