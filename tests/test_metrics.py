"""Tests for tools.metrics cyclomatic complexity counting."""

import ast
import unittest

from tools.metrics import _cc


def cc(source):
    tree = ast.parse(source)
    fn = tree.body[0]
    return _cc(fn)


class TestComplexity(unittest.TestCase):
    def test_linear_function(self):
        self.assertEqual(cc("def f():\n    return 1\n"), 1)

    def test_branches(self):
        self.assertEqual(
            cc("def f(x):\n    if x:\n        return 1\n    return 2\n"), 2
        )

    def test_boolop_counts_operands(self):
        self.assertEqual(cc("def f(a, b):\n    return a and b\n"), 2)

    def test_with_does_not_add_complexity(self):
        source = (
            "def f(path):\n"
            "    with open(path) as handle:\n"
            "        return handle.read()\n"
        )
        self.assertEqual(cc(source), 1)

    def test_nested_def_not_double_counted(self):
        source = (
            "def outer(x):\n"
            "    def inner(y):\n"
            "        if y:\n"
            "            return 1\n"
            "        return 2\n"
            "    return inner(x)\n"
        )
        self.assertEqual(cc(source), 1)


if __name__ == "__main__":
    unittest.main()
