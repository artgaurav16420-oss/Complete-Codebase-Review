import os
import unittest
from unittest.mock import patch

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

    def test_delete_user_path_traversal(self):
        from auth.login import delete_user
        result = delete_user("../another_dir")
        self.assertFalse(result)
