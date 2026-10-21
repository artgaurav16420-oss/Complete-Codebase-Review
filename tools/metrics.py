"""Print per-function cyclomatic complexity and LOC for Python files."""

import ast
import sys
from pathlib import Path


def _cc(node):
    count = 1
    stack = list(ast.iter_child_nodes(node))
    while stack:
        child = stack.pop()
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.Lambda)):
            continue
        if isinstance(child, (ast.If, ast.For, ast.While, ast.ExceptHandler,
                              ast.With, ast.Assert, ast.comprehension)):
            count += 1
        elif isinstance(child, ast.BoolOp):
            count += len(child.values) - 1
        elif isinstance(child, ast.IfExp):
            count += 1
        stack.extend(ast.iter_child_nodes(child))
    return count


def report(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            loc = (node.end_lineno or node.lineno) - node.lineno + 1
            print("{:40s} LOC={:4d} CC={:3d}  {}".format(
                node.name, loc, _cc(node), path
            ))


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.is_dir():
            for f in sorted(p.rglob("*.py")):
                report(f)
        else:
            report(p)
