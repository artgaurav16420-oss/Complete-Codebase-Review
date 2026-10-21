# Contributing

## Zero-Dependency Rule

This project uses **only Python stdlib**. No `requirements.txt`, no `pip install`, no virtualenv needed. Pull requests that introduce external dependencies will be rejected.

## Test Conventions

### Running Tests

```bash
# Compliance tests
python tests/compliance_test.py

# All test suites
python -m unittest discover -s tests -p "test_*.py" -v

# Eval harness (fixtures scored against expected issues)
python -m ccr eval

# With coverage
python -m coverage run --source=. -m unittest discover -s tests -p "test_*.py" -v
python -m coverage report
```

### Generated Files

`ccr/pipeline.json` is the single source of truth for agents, env vars, enums,
thresholds, and the version. Do not hand-edit the generated blocks in
`SKILL.md`, `README.md`, `help.md`, or `orchestrator-rules.md`, and do not
hand-edit `install.py.sha256`. Edit the manifest, then run:

```bash
python tools/generate.py          # rewrite generated files
python tools/generate.py --check  # CI mode: fail if stale
```

### Writing Tests

| Suite | Framework | When to use |
|-------|-----------|-------------|
| `compliance_test.py` | `unittest.TestCase` | SKILL.md string-matching checks |
| All other test files | `unittest.TestCase` | All new tests |

**New test files must use `unittest.TestCase`.**

### Naming

- Test files: `tests/test_<module>.py`
- Test classes: `Test<Module><Scenario>` (e.g. `TestCopySkill`, `TestMainEdgeCases`)
- Test methods: `test_<what_it_checks>` in snake_case

### Patterns

- Use `with self.subTest(...)` for iterating over multiple cases within one test method.
- Use `tempfile.TemporaryDirectory()` for filesystem tests — never test in the repo root
- Use `unittest.mock.patch` for mocking; prefer context managers over decorators for complex setups.
- Assert on behavior, not implementation details (e.g., assert file exists, not that `copytree` was called).

### Version Synchronization

The version string is defined in **three places** and must stay in sync:

- `SKILL.md` frontmatter
- `pyproject.toml`
- `CHANGELOG.md`

The compliance test `compliance_test.py:test_version_sources_stay_in_sync` enforces this. If you bump the version in one file, update all three before committing.

## Code Style

- **No type hints** — project targets Python 3.9+ but zero-dep means no `typing` imports beyond what stdlib provides.
- **No complex f-string expressions** — prefer simple f-strings; avoid nested expressions, comprehensions, or inline function calls in f-string braces.
- **Line length**: 100 characters soft limit.
- **Docstrings**: `"""Triple double-quotes"""` on functions with external visibility. One-line docstrings for simple getters/setters.

## Commit Convention

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <description>

[optional body]
```

Types: `feat`, `fix`, `test`, `docs`, `refactor`, `ci`, `chore`.

### Commit Message Template

A `.gitmessage` template is provided in the repo root. To use it:

```bash
git config commit.template .gitmessage
```

This pre-fills the conventional commit format when you run `git commit`.

## Documentation Guidelines

- **README changes**: Keep the README concise. Add new features to the
  feature table, update configuration tables, and add FAQ entries for
  common questions.
- **Docstrings**: Use `"""triple double-quotes"""` on all public
  functions. One-liners for simple accessors; multi-line with
  Args/Returns for complex functions.
- **ADRs**: Add an ADR for any significant architecture or design
  decision (see existing ADRs/ for format).
- **Inline comments**: Document WHY, not WHAT. Assume the reader knows the language.

## PR Checklist

Before submitting:

- [ ] `python tests/compliance_test.py` passes
- [ ] `python -m unittest discover -s tests -p "test_*.py"` passes
- [ ] No new dependencies introduced
- [ ] New test files use `unittest.TestCase`
- [ ] Docstrings added for new public functions
- [ ] ADR added for significant architecture decisions
