import unittest
import os
import tempfile
from utils.helper import read_file_safe

class TestHelper(unittest.TestCase):
    def test_read_file_safe_exists(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            f.write("test content")
            temp_path = f.name

        try:
            self.assertEqual(read_file_safe(temp_path), "test content")
        finally:
            os.remove(temp_path)

    def test_read_file_safe_missing(self):
        # Generate a path that definitely doesn't exist
        with tempfile.NamedTemporaryFile() as f:
            missing_path = f.name
        # f is closed and deleted here

        self.assertEqual(read_file_safe(missing_path), "")
