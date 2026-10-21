"""Deterministic discovery of a target codebase.

Pure stdlib, no network, no git dependency. Produces the facts Phase 1
needs and the agent selection that Phase 2 consumes.
"""

import os
import stat
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

ENTRY_POINT_NAMES = frozenset({
    "__main__.py", "main.py", "cli.py", "app.py", "manage.py", "server.py",
    "index.js", "server.js", "main.go", "main.rs", "Program.cs",
})

DB_MARKERS = frozenset({
    "migrations", "alembic.ini", "schema.sql", "prisma", "knexfile.js",
    "ormconfig.json",
})

CONTAINER_MARKERS = frozenset({
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml",
})

BASE_AGENTS = [
    "architecture", "code_quality", "security", "tech_debt", "documentation",
    "standards", "process_quality",
]


def _is_test_file(rel_parts, name):
    """Return True when a path looks like a test file."""
    if any(part.lower() in TEST_DIR_NAMES for part in rel_parts):
        return True
    if name.startswith(TEST_FILE_PREFIXES):
        return True
    return name.endswith(TEST_FILE_SUFFIXES)


def _process_file(full, rel_root, name, size, state):
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
    else:
        top = "."
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
    truncated = False
    for root, dirs, names in os.walk(str(target)):
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


def _build_facts(target, state, truncated):
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
    root_entries = {p.name for p in target.iterdir()} if target.exists() else set()
    for marker in DB_MARKERS:
        if marker in root_entries:
            database.append(marker)

    ci = []
    for marker in CI_PATHS:
        candidate = target / marker
        if candidate.is_file():
            ci.append(marker)
        elif candidate.is_dir():
            ci.extend(
                sorted(
                    str((candidate / f.name).relative_to(target)).replace("\\", "/")
                    for f in candidate.iterdir()
                    if f.suffix.lower() in (".yml", ".yaml")
                )
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

    return _build_facts(target, state, truncated)


def active_agents(manifest, facts):
    """Return the agent ids whose health dimensions apply to the target."""
    active = list(manifest.get("base_agents") or BASE_AGENTS)
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
    return [a["id"] for a in manifest["agents"] if a["id"] in wanted]


def _resolve_agent(manifest, token):
    """Map an id or report name to a canonical agent id."""
    cleaned = token.strip().lower().replace(" ", "_").replace("-", "_")
    for agent in manifest["agents"]:
        if agent["id"] == cleaned:
            return agent["id"]
        if agent["report"].lower().replace(" ", "_") == cleaned:
            return agent["id"]
        if agent["name"].lower().replace(" ", "_").replace("(", "").replace(")", "") == cleaned:
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
        chosen = {_resolve_agent(manifest, token) for token in override.split(",")}
        return [agent_id for agent_id in order if agent_id in chosen]
    if effort == "min":
        quick = set(manifest["thresholds"]["quick_agents"])
        return [agent_id for agent_id in order if agent_id in quick]
    return active_agents(manifest, facts)


def plan(manifest, target_dir, effort="max", override=None, max_files=None):
    """Build the Phase 1 + Phase 2 plan for a target.

    Returns:
        dict: discovery facts, selected agents, timeout, and quick flag.
    """
    facts = discover(target_dir, max_files=max_files)
    agents = select_agents(manifest, facts, effort=effort, override=override)
    timeout = 900
    if effort == "min":
        timeout = int(manifest["thresholds"]["quick_timeout_sec"])
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
