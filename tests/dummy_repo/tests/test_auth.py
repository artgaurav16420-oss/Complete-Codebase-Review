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

    def test_ping(self):
        from auth.login import ping_host
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = ping_host("127.0.0.1")
            self.assertTrue(result)
