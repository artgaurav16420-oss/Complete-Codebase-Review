# Contributing

## Zero-Dependency Rule

This project uses **only Python stdlib**. No `requirements.txt`, no `pip install`, no virtualenv needed. Pull requests that introduce external dependencies will be rejected.

## Test Conventions

### Running Tests

```bash
# All compliance checks (139 assertions)
python tests/test_compliance.py

# Installer unit tests (49 tests, unittest)
python -m unittest tests.test_install -v

# CLI smoke tests (18 tests, unittest)
python -m unittest tests.test_smoke -v

# All unittest suites
python -m unittest discover -s tests -p "test_*.py" -v
```

### Writing Tests

| Suite | Framework | When to use |
|-------|-----------|-------------|
| `test_compliance.py` | Custom `make_checker()` DSL | Only for SKILL.md string-matching checks |
| All other test files | `unittest.TestCase` | All new tests |

**New test files must use `unittest.TestCase`.** The `make_checker()` DSL is a legacy pattern used only by `test_compliance.py`.

### Naming

- Test files: `tests/test_<module>.py`
- Test classes: `Test<Module><Scenario>` (e.g. `TestCopySkill`, `TestMainEdgeCases`)
- Test methods: `test_<what_it_checks>` in snake_case

### Patterns

- Use `with self.subTest(...)` for iterating over multiple cases within one test method.
- Use `tempfile.TemporaryDirectory()` for filesystem tests — never test in the repo root.
- Use `unittest.mock.patch` for mocking; prefer context managers over decorators for complex setups.
- Assert on behavior, not implementation details (e.g., assert file exists, not that `copytree` was called).

## Code Style

- **No type hints** — project targets Python 3.9+ but zero-dep means no `typing` imports beyond what stdlib provides.
- **No f-strings with expressions** — use simple f-strings or `%` formatting.
- **Line length**: 100 characters soft limit.
- **Docstrings**: `"""Triple double-quotes"""` on functions with external visibility. One-line docstrings for simple getters/setters.

## Commit Convention

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <description>

[optional body]
```

Types: `feat`, `fix`, `test`, `docs`, `refactor`, `ci`, `chore`.

## PR Checklist

Before submitting:

- [ ] `python tests/test_compliance.py` passes
- [ ] `python -m unittest discover -s tests -p "test_*.py"` passes
- [ ] No new dependencies introduced
- [ ] New test files use `unittest.TestCase`
- [ ] Docstrings added for new public functions
- [ ] ADR added for significant architecture decisions
