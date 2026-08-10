import unittest
from utils.helper import parse_config
import json

class TestHelper(unittest.TestCase):
    def test_parse_config_valid(self):
        result = parse_config('{"key": "value"}')
        self.assertEqual(result, {"key": "value"})

    def test_parse_config_invalid(self):
        with self.assertRaises(json.JSONDecodeError):
            parse_config('{"key": "value"')
