"""Deterministic discovery of a target codebase.

Pure stdlib, no network, no git dependency. Produces the facts Phase 1
needs and the agent selection that Phase 2 consumes.
"""

import os
import stat
from itertools import islice
from pathlib import Path

IGNORED_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".code-review-cache", ".skills", "dist",
    "build", ".idea", ".vscode", ".eggs", ".next", "target",
})

LANGUAGE_BY_EXT = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".hpp": "C++",
    ".swift": "Swift",
    ".sh": "Shell",
    ".ps1": "PowerShell",
    ".sql": "SQL",
}

CODE_LANGUAGES = frozenset({
    "Python", "JavaScript", "TypeScript", "Go", "Rust", "Java", "Kotlin",
    "Ruby", "PHP", "C#", "C", "C++", "Swift",
})

MARKUP_EXTS = frozenset({".html", ".css", ".scss", ".vue", ".svelte"})
UI_DOC_DIRS = frozenset({
    "docs", "site", "documentation", "theme", "themes",
})

DEPENDENCY_MANIFESTS = {
    "pyproject.toml": "Python",
    "setup.py": "Python",
    "setup.cfg": "Python",
    "requirements.txt": "Python",
    "package.json": "Node",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "pom.xml": "Maven",
    "build.gradle": "Gradle",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
}

CI_PATHS = [
    ".github/workflows",
    ".gitlab-ci.yml",
    ".circleci/config.yml",
    "Jenkinsfile",
    ".travis.yml",
    "azure-pipelines.yml",
]

TEST_DIR_NAMES = frozenset({"test", "tests", "spec", "specs", "__tests__"})
TEST_FILE_PREFIXES = ("test_", "spec_")
TEST_FILE_SUFFIXES = ("_test.py", "_test.go", ".test.js", ".test.ts", ".spec.js")
# Token match so `tools/main-harness.js` and `parser_spec.rb` count, while
# `contest.js` and `latest.js` do not.
TEST_NAME_TOKENS = frozenset({"test", "tests", "spec", "specs", "harness"})
# The token rule only applies to source files: `docs/load-harness.md` is
# documentation about a harness, not a test.
TEST_FILE_EXTENSIONS = frozenset(LANGUAGE_BY_EXT)

ENTRY_POINT_NAMES = frozenset({
    "__main__.py", "main.py", "cli.py", "app.py", "manage.py", "server.py",
    "index.js", "server.js", "main.go", "main.rs", "Program.cs",
})

DB_MARKERS = frozenset({
    "migrations", "alembic.ini", "schema.sql", "prisma", "knexfile.js",
    "ormconfig.json",
})

# Directory levels listed when looking for DB_MARKERS below the target root.
# Three levels (root, its subdirs, and their subdirs) reach a service's own
# layout such as server/prisma/ or apps/api/migrations/ without rescanning the
# whole tree that _scan_tree already covers.
DB_SCAN_DEPTH = 3

# Upper bound on directory entries the DB scan visits and on subdirectories
# it recurses into, when the caller sets no file cap. Both bounds apply to the
# whole scan, so a pathological tree cannot stream an unbounded directory
# while max_files only bounds the main walk. 5000 still covers a root plus the
# first levels of a monorepo, where markers live (prisma/, migrations/ at
# depth <= 3).
DB_SCAN_MAX_ENTRIES = 5000

CONTAINER_MARKERS = frozenset({
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml",
})


def _is_test_file(rel_parts, name):
    """Return True when a path looks like a test file."""
    if any(part.lower() in TEST_DIR_NAMES for part in rel_parts):
        return True
    if name.startswith(TEST_FILE_PREFIXES):
        return True
    if name.endswith(TEST_FILE_SUFFIXES):
        return True
    if Path(name).suffix.lower() not in TEST_FILE_EXTENSIONS:
        return False
    stem = Path(name).stem.lower()
    for separator in ("-", "_", "."):
        stem = stem.replace(separator, " ")
    return any(token in TEST_NAME_TOKENS for token in stem.split())


def _process_file(full, rel_root, name, size, state):
    """Tally one file into the discovery state dict."""
    state["files"] += 1
    state["total_bytes"] += size
    if _is_test_file(rel_root.parts, name):
        state["test_files"] += 1

    ext = full.suffix.lower()
    language = LANGUAGE_BY_EXT.get(ext)
    if language:
        languages = state["languages"]
        languages[language] = languages.get(language, 0) + 1
    if ext in MARKUP_EXTS:
        top = rel_root.parts[0].lower() if rel_root.parts else ""
        if top not in UI_DOC_DIRS:
            state["ui_files"] += 1

    if name in DEPENDENCY_MANIFESTS:
        state["dependency_manifests"].append(name)
    if name in CONTAINER_MARKERS:
        state["containers"].append(name)
    if name in ENTRY_POINT_NAMES:
        state["entry_points"].append(
            str(Path(rel_root) / name).replace("\\", "/")
        )

    if rel_root.parts:
        top = rel_root.parts[0]
        top_dirs = state["top_dirs"]
        top_dirs[top] = top_dirs.get(top, 0) + 1


def _is_reparse_dir(path):
    """Return True for symlinked or junction directories (loop risk)."""
    try:
        if os.path.islink(str(path)):
            return True
        attrs = getattr(os.lstat(str(path)), "st_file_attributes", 0)
    except OSError:
        return False
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(flag and attrs & flag)


def _scan_tree(target, limit, state):
    """Walk the target tree into the state dict; report truncation."""
    truncated = False

    def _fail(exc):
        raise ValueError(
            "cannot scan target directory: {} ({})".format(target, exc)
        )

    for root, dirs, names in os.walk(str(target), onerror=_fail):
        dirs[:] = sorted(
            d for d in dirs
            if d not in IGNORED_DIRS and not _is_reparse_dir(Path(root) / d)
        )
        rel_root = Path(root).relative_to(target)
        for name in sorted(names):
            if limit and state["files"] >= limit:
                truncated = True
                break
            full = Path(root) / name
            try:
                size = full.stat().st_size
            except OSError:
                continue
            _process_file(full, rel_root, name, size, state)
        if truncated:
            break
    return truncated


def _has_symlinked_component(target, marker):
    """True when any component of target/marker is a link or junction."""
    current = target
    for part in Path(marker).parts:
        current = current / part
        if _is_reparse_dir(current):
            return True
    return False


def _find_db_markers(directory, depth, found, budget=None):
    """Collect DB marker names under directory, down to DB_SCAN_DEPTH levels.

    ``budget`` is a two-element list shared by the recursion: slot 0 is how
    many directory entries the whole scan may still visit, slot 1 how many
    subdirectories it may still descend into. The entry budget bounds a very
    wide directory even when the caller capped file discovery; the descent
    budget bounds the number of open directories. Markers found before the
    budget runs out stay in ``found``, and the scan stops when it is spent.
    Each directory is streamed in order, so a marker in the tail is reached
    while the budget lasts; only marker names and at most the remaining
    descent budget of subdirectory names are held in memory. Collected
    subdirectories are sorted so the walk stays deterministic.
    """
    if budget is None:
        budget = [DB_SCAN_MAX_ENTRIES, DB_SCAN_MAX_ENTRIES]
    if budget[0] <= 0:
        return
    subdirs = []
    try:
        with os.scandir(str(directory)) as iterator:
            # islice takes the budget once, so the loop pulls at most that
            # many entries and never looks one past the cap.
            for entry in islice(iterator, budget[0]):
                budget[0] -= 1
                # Check for links before recording: a junction named
                # "migrations" or "prisma" must not activate the database
                # agent from outside the tree.
                if _is_reparse_dir(entry.path):
                    continue
                if entry.name in DB_MARKERS:
                    found.append(entry.name)
                if depth >= DB_SCAN_DEPTH or entry.name in IGNORED_DIRS:
                    continue
                if len(subdirs) >= budget[1]:
                    continue
                try:
                    is_dir = entry.is_dir()
                except OSError:
                    # The entry vanished between listing and inspection.
                    is_dir = False
                if is_dir:
                    subdirs.append(entry.name)
    except OSError as exc:
        raise ValueError(
            "cannot list directory: {} ({})".format(directory, exc)
        )
    subdirs.sort()
    # Pay for every descent up front so the whole scan stays inside budget.
    budget[1] -= len(subdirs)
    for name in subdirs:
        _find_db_markers(Path(directory) / name, depth + 1, found, budget)


def _build_facts(target, state, truncated, max_files=None):
    """Derive the discovery facts dict from the accumulated state."""
    files = state["files"]
    total_bytes = state["total_bytes"]
    languages = state["languages"]
    top_dirs = state["top_dirs"]
    dependency_manifests = state["dependency_manifests"]
    containers = state["containers"]
    entry_points = state["entry_points"]
    ui_files = state["ui_files"]
    test_files = state["test_files"]

    database = []
    if target.exists():
        # Depth 1 is the target root; DB_SCAN_DEPTH counts levels from it.
        # A capped run carries its cap into the marker scan so discovery
        # stays bounded on a very wide tree; an uncapped run keeps the
        # documented default budget.
        entries = max_files if max_files else DB_SCAN_MAX_ENTRIES
        budget = [entries, DB_SCAN_MAX_ENTRIES]
        _find_db_markers(target, 1, database, budget)

    ci = []
    try:
        for marker in CI_PATHS:
            candidate = target / marker
            if candidate.is_file() and not _has_symlinked_component(
                target, marker
            ):
                ci.append(marker)
            elif candidate.is_dir() and not _has_symlinked_component(target, marker):
                ci.extend(
                    sorted(
                        str((candidate / f.name).relative_to(target)).replace("\\", "/")
                        for f in candidate.iterdir()
                        if f.is_file()
                        and not _is_reparse_dir(f)
                        and f.suffix.lower() in (".yml", ".yaml")
                    )
                )
    except OSError as exc:
        raise ValueError(
            "cannot list CI directory under: {} ({})".format(target, exc)
        )

    code_files = sum(
        count for language, count in languages.items()
        if language in CODE_LANGUAGES
    )
    return {
        "target": str(target),
        "files": files,
        "bytes": total_bytes,
        "truncated": truncated,
        "languages": dict(sorted(languages.items())),
        "code_files": code_files,
        "top_dirs": dict(sorted(top_dirs.items())),
        "dependency_manifests": sorted(set(dependency_manifests)),
        "ci": ci,
        "test_files": test_files,
        "entry_points": sorted(set(entry_points)),
        "database": sorted(set(database)),
        "containers": sorted(set(containers)),
        "ui_files": ui_files,
    }


def discover(target_dir, max_files=None):
    """Map a codebase into a discovery facts dict.

    Args:
        target_dir: Directory to scan.
        max_files: Optional cap on files inspected. None means unlimited.

    Returns:
        dict: Counts, detected tooling, entry points, and truncated flag.

    Raises:
        ValueError: If target_dir is not a directory.
    """
    target = Path(target_dir).resolve()
    if not target.is_dir():
        raise ValueError("target is not a directory: " + str(target))

    limit = int(max_files) if max_files is not None else 0
    if max_files is not None and limit < 1:
        raise ValueError("max_files must be >= 1")
    state = {
        "files": 0,
        "total_bytes": 0,
        "languages": {},
        "top_dirs": {},
        "dependency_manifests": [],
        "containers": [],
        "entry_points": [],
        "ui_files": 0,
        "test_files": 0,
    }
    truncated = _scan_tree(target, limit, state)

    return _build_facts(target, state, truncated, limit)


def active_agents(manifest, facts):
    """Return the agent ids whose health dimensions apply to the target.

    Raises ValueError when a triggered id is missing from the manifest, so a
    renamed agent fails loudly instead of silently dropping its domain.
    """
    active = list(manifest.get("base_agents") or [])
    if facts.get("test_files"):
        active.append("test_health")
    if facts.get("dependency_manifests"):
        active.append("dependencies")
    if facts.get("ci"):
        active.append("build_ci")
    if facts.get("database"):
        active.append("database")
    if facts.get("ui_files"):
        active.append("ui_ux")
    if facts.get("containers"):
        active.append("devops")
    if facts.get("code_files", 0) >= 20 or facts.get("ui_files"):
        active.append("performance")
    wanted = set(active)
    known = {a["id"] for a in manifest["agents"]}
    unknown = sorted(wanted - known)
    if unknown:
        raise ValueError(
            "agent trigger not in manifest: " + ", ".join(unknown)
        )
    return [a["id"] for a in manifest["agents"] if a["id"] in wanted]


def _normalize_agent_token(text):
    """Lower-case a token and drop the punctuation agent names carry."""
    return (
        str(text).strip().lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("(", "")
        .replace(")", "")
    )


def resolve_agent(manifest, token):
    """Map an id, report name or display name to a canonical agent id.

    Ids are matched across the whole roster before any alias, so an earlier
    agent's display name cannot shadow a later agent's id.
    """
    cleaned = _normalize_agent_token(token)
    for agent in manifest["agents"]:
        if _normalize_agent_token(agent["id"]) == cleaned:
            return agent["id"]
    for agent in manifest["agents"]:
        if _normalize_agent_token(agent["report"]) == cleaned:
            return agent["id"]
        if _normalize_agent_token(agent["name"]) == cleaned:
            return agent["id"]
    raise ValueError("unknown agent: " + token)


def select_agents(manifest, facts, effort="max", override=None):
    """Choose agents by precedence: override > Quick Mode > dimensions.

    Args:
        manifest: Loaded pipeline manifest.
        facts: Result of discover().
        effort: "max" (default) or "min" for Quick Mode.
        override: Comma-separated agent ids or names.

    Returns:
        list: Canonical agent ids in manifest order.

    Raises:
        ValueError: On an unknown effort value or agent name.
    """
    if effort not in ("max", "min"):
        raise ValueError("effort must be 'max' or 'min'")
    order = [a["id"] for a in manifest["agents"]]
    if override:
        tokens = [token for token in override.split(",") if token.strip()]
        if not tokens:
            raise ValueError("--agents contained no agent ids")
        chosen = {resolve_agent(manifest, token) for token in tokens}
        return [agent_id for agent_id in order if agent_id in chosen]
    if effort == "min":
        quick = set(manifest["thresholds"]["quick_agents"])
        return [agent_id for agent_id in order if agent_id in quick]
    return active_agents(manifest, facts)


def _timeout_sec(manifest, effort):
    """Resolve the agent timeout for the selected effort.

    Full runs honour CODE_REVIEW_TIMEOUT_SEC, falling back to the manifest
    env-var default. Quick Mode keeps its own manifest timeout.
    """
    if effort == "min":
        return int(manifest["thresholds"]["quick_timeout_sec"])
    default = 900
    for var in manifest.get("env_vars", []):
        if var.get("name") == "CODE_REVIEW_TIMEOUT_SEC":
            default = var.get("default", default)
            break
    raw = os.environ.get("CODE_REVIEW_TIMEOUT_SEC", "")
    if raw:
        try:
            value = int(raw)
        except ValueError:
            value = 0
        if value > 0:
            return value
    try:
        return int(default)
    except (TypeError, ValueError):
        return 900


def plan(manifest, target_dir, effort="max", override=None, max_files=None):
    """Build the Phase 1 + Phase 2 plan for a target.

    Returns:
        dict: discovery facts, selected agents, timeout, and quick flag.
    """
    facts = discover(target_dir, max_files=max_files)
    agents = select_agents(manifest, facts, effort=effort, override=override)
    timeout = _timeout_sec(manifest, effort)
    return {
        "target": facts["target"],
        "effort": effort,
        "quick_mode": effort == "min",
        "timeout_sec": timeout,
        "agents": agents,
        "agent_names": [
            a["name"] for a in manifest["agents"] if a["id"] in agents
        ],
        "facts": facts,
    }
