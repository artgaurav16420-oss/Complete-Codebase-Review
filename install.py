#!/usr/bin/env python3
"""Universal installer for the Complete Codebase Review skill.

Installs the skill to supported AI agent skill directories:
- Claude Code (~/.claude/skills/)
- OpenCode (~/.config/opencode/skills/)
- Cursor (~/.cursor/skills/)
- Continue (~/.continue/skills/)

Usage:
    python install.py          # Install to detected agent configs
    python install.py --help   # Show this help message
    python install.py --version  # Show version
    python install.py --uninstall  # Remove installed copies
"""

import argparse
import hashlib
import os
import re
import shutil
import stat
import sys
import time
import platform
from pathlib import Path

try:
    import fcntl as _fcntl
except ImportError:  # Windows has no flock
    _fcntl = None

try:
    import msvcrt as _msvcrt
except ImportError:  # POSIX has no msvcrt
    _msvcrt = None


def _is_link_like(path):
    """Return True for symlinks and, on Windows, directory junctions."""
    path = Path(path)
    try:
        if os.path.islink(str(path)):
            return True
    except OSError:
        pass
    isjunction = getattr(os.path, "isjunction", None)
    if isjunction is not None:
        try:
            return bool(isjunction(str(path)))
        except OSError:
            return False
    try:
        attrs = getattr(os.lstat(str(path)), "st_file_attributes", 0)
    except OSError:
        return False
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(flag and attrs & flag)


def _remove_link_like(path):
    """Remove a symlink or junction without touching its target."""
    path = Path(path)
    try:
        # Works for a file symlink and for a symlink to a directory on POSIX.
        path.unlink()
        return
    except OSError:
        pass
    # Windows refuses unlink on a directory symlink and on a junction; both
    # are removed by rmdir, which deletes the reparse point, not its target.
    os.rmdir(str(path))


def _containment_root(path):
    """Anchor a containment check without following a link at ``path``.

    Resolving ``path`` itself would move the anchor onto a link's target, so
    only the ancestors are resolved and the last component is kept as named.
    A directory swapped for a link therefore stays outside its own anchor and
    the child comparison fails instead of redirecting the delete.
    """
    path = Path(path)
    if path.parent == path:
        return path
    return path.parent.resolve(strict=False) / path.name


def _compute_sha256(file_path):
    """Compute SHA-256 hash of a file.
    
    Args:
        file_path: Path to the file to hash.
        
    Returns:
        Hexadecimal string of the SHA-256 hash.
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def _verify_checksum(file_path, expected_hash):
    """Verify a file's SHA-256 hash matches the expected value.
    
    Args:
        file_path: Path to the file to verify.
        expected_hash: Expected SHA-256 hash (hex string).
        
    Returns:
        True if hash matches, False otherwise.
        
    Raises:
        FileNotFoundError: If file_path does not exist.
    """
    if not Path(file_path).exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    actual_hash = _compute_sha256(file_path)
    return actual_hash.lower() == expected_hash.lower()


def _is_sha256(text):
    """Return True if text is exactly 64 hexadecimal characters."""
    return len(text) == 64 and all(
        c in "0123456789abcdefABCDEF" for c in text
    )


_SKILL_EXCLUDED = {
    # VCS and build artifacts — never ship these
    ".git", "__pycache__",
    # Local environments and build output — a checkout's working state
    ".venv", "venv", "node_modules", "build", "dist", "htmlcov",
    ".mypy_cache", ".pytest_cache",
    # Credential stores — whole directories, not just files
    ".aws", ".ssh", ".gnupg", ".docker", ".kube",
    # Installer scripts — not part of the skill itself
    "install.py", "install.sh", "install.ps1", "install.py.sha256",
    # CI, tests, design docs — runtime skill doesn't need these
    ".github", "tests", "ADRs", "test.sh", "Makefile",
    # Security/advisory files — GitHub standard files, not skill content
    "SECURITY.md", "CONTRIBUTING.md", "CHANGELOG.md",
    ".gitignore", ".gitattributes", ".gitmessage",
    # Project metadata — not consumed at runtime
    "pyproject.toml", "AGENTS.md", "help.md", ".coveragerc",
    # Dev-only tooling — generators and fixtures never ship
    "tools",
    # Self-audit and coverage artifacts — generated, not runtime content
    "CCR_REPORT.md", "ARCH_QUALITY_FINDINGS.md",
    "coverage.json", "coverage_report.txt", "coverage_run.txt",
    # Config/credentials — never shipped
    ".skills", ".env", ".secret", ".credentials",
    # Cache directory and foreign skills index — runtime artifacts
    ".code-review-cache", ".skills-index.json",
    # orchestrator-rules.md deliberately excluded — it's an internal
    # protocol document consumed by the orchestrator at repo root,
    # not a runtime requirement for installed skill consumers.
    "orchestrator-rules.md",
}


def _onerror(func, path, exc_info):
    """Retry a failed rmtree operation by making the path writable first.

    Uses follow_symlinks=False to prevent permission changes on symlink targets
    outside the expected directory tree.

    Invoked as either an `onerror` (Python 3.9-3.11) or `onexc` (3.12+) callback;
    the third argument is ignored, so both calling conventions are supported.
    """
    try:
        try:
            os.chmod(path, stat.S_IWRITE, follow_symlinks=False)
        except NotImplementedError:
            if not os.path.islink(path):
                os.chmod(path, stat.S_IWRITE)
    except OSError:
        pass
    func(path)


_CREDENTIAL_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore", ".jks")
_CREDENTIAL_PREFIXES = ("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519")
# The words a credential file is named after. A file that carries one of
# them is a credential store whatever else the name says: the extension
# (credentials.yaml), the local override suffix (.envrc.local), the
# leading dot and a qualifier in front (aws-credentials.json) are
# variations on the same thing, and a list of whole names misses the
# variants that actually turn up in a checkout.
_CREDENTIAL_WORDS = {
    "env", "envrc", "direnv", "netrc", "npmrc", "pypirc", "htpasswd",
    "credential", "credentials", "secret", "secrets",
}
# The name is split into words on these separators, so a word is matched
# whole: "aws-credentials.json" carries the word "credentials", while
# "environment.py" carries the word "environment" and is kept.
_CREDENTIAL_WORD_SEPARATORS = re.compile(r"[._-]+")


def _is_credential_name(name):
    """True for names that commonly hold private keys or credentials.

    The rule is about the words the file is named after, not about the
    whole name: exact-name matching alone misses the variants that
    actually exist in a checkout (.env.local, credentials.json,
    .envrc.local, prod.env, aws-credentials.json, id_rsa_work, *.pem),
    and those files would otherwise be copied into every agent skill
    directory.
    """
    lowered = name.lower()
    if lowered.startswith(_CREDENTIAL_PREFIXES):
        return True
    if lowered.endswith(_CREDENTIAL_SUFFIXES):
        return True
    words = _CREDENTIAL_WORD_SEPARATORS.split(lowered.lstrip("."))
    return any(word in _CREDENTIAL_WORDS for word in words)


def _ignore_skill_files(path, names, dest=None, collector=None):
    """Filter files to exclude from skill copy based on _SKILL_EXCLUDED.

    Links are skipped outright: a copy either dangles (its target was filtered)
    or resolves outside the checkout (a junction on Windows is not a symlink,
    so ``copytree`` follows it). The skill tree needs neither.

    ``dest`` is the directory the copy installs into, and it is left out of
    the copy. The staging tree is created inside it, so a destination inside
    the source tree is copied into itself: the copy walks into the
    destination, finds the staging tree it is building, and copies that too,
    until the copy fails.

    ``collector`` is an optional list. When given, the full path of every
    credential-like entry is appended to it, so the caller can report after
    the copy which files the credential rule kept out. An entry that is also
    in ``_SKILL_EXCLUDED`` is still collected: the report is about the
    credential rule, not about which filter won.
    """
    if collector is not None:
        collector.extend(
            str(Path(path) / name)
            for name in names
            if _is_credential_name(name)
        )
    skipped = [
        n for n in names
        if n in _SKILL_EXCLUDED
        or _is_credential_name(n)
        or _is_link_like(Path(path) / n)
        or n.endswith(".pyc")
        or n.endswith(".egg-info")
        or n == ".coverage"
    ]
    if dest is None:
        return skipped
    try:
        here = Path(path).resolve(strict=False)
    except (OSError, RuntimeError):
        here = None
    if here is not None and (here == dest or dest in here.parents):
        # The directory being scanned is the destination, or lives inside
        # it: nothing in there belongs in the copy.
        return list(names)
    for n in names:
        if n in skipped or n != dest.name:
            continue
        try:
            child = (Path(path) / n).resolve(strict=False)
        except (OSError, RuntimeError):
            continue
        if child == dest:
            skipped.append(n)
    return skipped


def _read_version():
    """Parse version from pyproject.toml. Raises RuntimeError if missing."""
    pyproject = Path(__file__).parent / "pyproject.toml"
    if not pyproject.exists():
        raise RuntimeError("pyproject.toml not found; cannot determine version")
    match = re.search(
        r'(?m)^version\s*=\s*"([^"]+)"',
        pyproject.read_text(encoding="utf-8")
    )
    if not match:
        raise RuntimeError("version missing from pyproject.toml")
    return match.group(1)


_VERSION_CACHE = None


def get_version():
    """Return the cached version string, reading from pyproject.toml on first call."""
    global _VERSION_CACHE
    if _VERSION_CACHE is None:
        _VERSION_CACHE = _read_version()
    return _VERSION_CACHE


def _use_color():
    """Return True if stdout is a TTY and NO_COLOR env var is unset."""
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _print(msg, label, color):
    """Print [label] msg with ANSI color if supported, else plain text."""
    if _use_color():
        print(f"[{color}{label}\033[0m] {msg}")
    else:
        print(f"[{label}] {msg}")


def print_success(msg):
    """Print a success message."""
    _print(msg, "SUCCESS", "\033[92m")


def print_info(msg):
    """Print an informational message."""
    _print(msg, "INFO", "\033[94m")


def print_error(msg):
    """Print an error message."""
    _print(msg, "ERROR", "\033[91m")


def _validate_xdg_path(xdg_path):
    """Check an environment config dir resolves; return resolved path or None.

    Per the XDG spec, XDG_CONFIG_HOME may be outside the user's home
    directory (e.g. /mnt/storage/config). The same rule applies to each
    tool's native override: verify it is absolute, has no traversal
    components, resolves successfully, and can be created. A file cannot
    hold a ``skills`` child, so an override that names a file (such as a
    tool's config.json) or lives below one falls back to the default
    instead of producing ``<file>/skills``. A path that does not exist yet
    stays valid when its nearest existing ancestor is a directory: a
    selected target can be created from there.
    """
    if ".." in xdg_path.parts:
        return None
    if not xdg_path.is_absolute():
        return None
    try:
        resolved = xdg_path.resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    probe = resolved
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if probe.exists() and not probe.is_dir():
        return None
    return resolved


def _env_config_dir(names):
    """Return the first validated config dir named by an env var, or None.

    Each tool follows its own environment rules, so the caller names the
    variables to try in precedence order. A value that is empty, relative, or
    traversal-bearing is ignored, the way an unsafe XDG override is.
    """
    for name in names:
        raw = os.environ.get(name, "").strip()
        if not raw:
            continue
        validated = _validate_xdg_path(Path(raw))
        if validated is not None:
            return validated
    return None


def _tool_skills_dir(home, app_dir, env_names=(), xdg=False, fallback=None):
    """Resolve one tool's skills dir from its own environment rules.

    Precedence is the tool's native override, then XDG on Linux for the tools
    that read it, then ``fallback``. The default fallback is
    ``~/.<app_dir>/skills``; OpenCode passes its XDG-style ``~/.config`` root
    instead.
    """
    override = _env_config_dir(env_names)
    if override is not None:
        return override / "skills"
    if xdg and platform.system() == "Linux":
        xdg_env = os.environ.get("XDG_CONFIG_HOME", "").strip()
        if xdg_env:
            validated = _validate_xdg_path(Path(xdg_env))
            if validated is not None:
                return validated / app_dir / "skills"
    if fallback is None:
        fallback = home / f".{app_dir}"
    return fallback / "skills"


def get_target_dirs():
    """Determine the target installation directories for supported AI agents.

    Each tool follows its own environment rules: Claude Code reads
    ``CLAUDE_CONFIG_DIR`` and not XDG, OpenCode reads XDG on Linux,
    Continue reads ``CONTINUE_GLOBAL_DIR``, and Cursor has no tool-specific
    override. OpenCode falls back to its ``~/.config/opencode`` root; the
    other tools fall back to ``~/.<tool>``.

    Returns:
        dict: A dictionary mapping agent names to their respective skill installation directories.
    """
    home = Path.home()

    dirs = {
        "Claude Code": _tool_skills_dir(
            home, "claude", env_names=("CLAUDE_CONFIG_DIR",)
        ),
        "OpenCode": _tool_skills_dir(
            home, "opencode", xdg=True, fallback=home / ".config" / "opencode"
        ),
        "Cursor": _tool_skills_dir(home, "cursor"),
        "Continue": _tool_skills_dir(
            home, "continue", env_names=("CONTINUE_GLOBAL_DIR",)
        ),
    }

    return dirs


STAGING_PREFIX = ".complete-codebase-review.staging-"
PREVIOUS_PREFIX = ".complete-codebase-review.old-"
# A run holds an OS lock for as long as it works. The kernel drops the lock
# when the process dies, so a crashed run's lock is free and its trees stay
# removable, while a run that is still working keeps its lock and its trees
# are left alone whatever their age.
RUN_LOCK_PREFIX = ".complete-codebase-review.run-"
# A run creates its lock file and locks it a moment later, so a file that
# is still fresh may belong to a run that has not taken its lock yet. A
# sweep only removes a lock file older than this, which is far longer than
# the gap between the create and the lock and far shorter than a run takes.
LOCK_FILE_GRACE_SEC = 60
# A pid cannot be probed for liveness on Windows (os.kill would terminate the
# process), so leftovers are told from a live install by age instead. A tree
# younger than this may belong to a run that is still working.
LEFTOVER_MAX_AGE_SEC = 3600
# The copy is done in chunks so the staging tree's mtime can be refreshed
# between them. The chunk has to be copied well inside the age the sweep
# uses, so that a tree is never left looking stale while it is still
# being written.
COPY_CHUNK_BYTES = 64 * 1024


def _lock_supported():
    """Return True when this platform has a file-locking primitive.

    Without one, nobody can hold a lock: the liveness signal is simply
    absent, and the install still works.
    """
    return _msvcrt is not None or _fcntl is not None


def _run_lock_path(dest_dir, token):
    """Return the path of the lock file a run holds."""
    return Path(dest_dir) / (RUN_LOCK_PREFIX + token + ".lock")


class _RunLock:
    """An OS-held lock that says one install run is still working.

    The kernel drops the lock when the holding process ends, so a crashed
    run's lock is free and its trees are removable. A lock file that is
    created and deleted instead needs a staleness rule of its own, and that
    rule races with itself: two contenders judge the same file stale, one
    replaces it, and the other then removes the replacement, so both enter
    the protected section.
    """

    def __init__(self, path):
        self.path = Path(path)
        self._handle = None

    def acquire(self, create=True):
        """Take the lock. Raises OSError when someone else holds it."""
        if not _lock_supported():
            # This platform has no locking primitive, so nobody can hold a
            # lock and there is nothing to take. The install continues
            # without the signal rather than failing on a platform that
            # cannot provide one.
            return self
        mode = "a+b" if create else "r+b"
        try:
            self._handle = open(str(self.path), mode)
            if _msvcrt is not None:
                # msvcrt locks a byte range, so the file needs a byte to
                # lock.
                self._handle.seek(0, os.SEEK_END)
                if self._handle.tell() == 0:
                    self._handle.write(b"\0")
                    self._handle.flush()
                self._handle.seek(0)
                _msvcrt.locking(self._handle.fileno(), _msvcrt.LK_NBLCK, 1)
            else:
                _fcntl.flock(
                    self._handle.fileno(), _fcntl.LOCK_EX | _fcntl.LOCK_NB
                )
        except OSError:
            self.close()
            raise
        return self

    def release(self):
        """Drop the lock and close the file."""
        if self._handle is None:
            return
        try:
            if _msvcrt is not None:
                self._handle.seek(0)
                _msvcrt.locking(self._handle.fileno(), _msvcrt.LK_UNLCK, 1)
            else:
                _fcntl.flock(self._handle.fileno(), _fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            self.close()

    def close(self):
        """Close the file without touching the lock."""
        if self._handle is not None:
            try:
                self._handle.close()
            except OSError:
                pass
            self._handle = None


def _lock_is_held(path):
    """Return True when the lock file is held by a run that is working.

    The answer comes from the kernel: a lock that can be taken is free, so
    the run that held it is gone and its trees are removable. A file that
    cannot be opened is treated as held, because a tree is only removed
    when the run that owns it is known to be gone.
    """
    path = Path(path)
    if _msvcrt is None and _fcntl is None:
        return False
    lock = _RunLock(path)
    try:
        lock.acquire(create=False)
    except FileNotFoundError:
        return False
    except PermissionError:
        return True
    except OSError:
        # The lock is held: the run that owns it is still working.
        return True
    lock.release()
    return False


def _sweep_run_locks(dest_dir):
    """Remove the lock files of runs that are no longer working.

    The kernel drops the lock when a run's process dies, but the file it
    locked stays. A free lock file is litter, so it goes here; a lock that
    is held belongs to a run that is still working and stays.

    A lock file is only removed when it is old enough that no run can be
    between creating it and locking it, and when the lock can be taken.
    The probe is released before the file is removed because Windows
    refuses to delete an open file, and no other run can take the lock in
    that gap: a run's token is unique to it, so no other run ever opens
    this name.
    """
    for path in sorted(Path(dest_dir).glob(RUN_LOCK_PREFIX + "*.lock")):
        try:
            age = time.time() - path.lstat().st_mtime
        except OSError:
            continue
        if age < LOCK_FILE_GRACE_SEC:
            # A run creates its lock file and locks it a moment later; a
            # file this fresh may still be that run's.
            continue
        lock = _RunLock(path)
        try:
            lock.acquire(create=False)
        except OSError:
            # The lock is held: the run that owns it is still working.
            continue
        lock.release()
        try:
            os.unlink(str(path))
        except OSError:
            pass


def _leftovers(dest_dir, max_age=0):
    """Return the staging and backup trees in dest_dir older than max_age.

    Both names carry the pid of the run that made them, so a tree left behind
    belongs to a run that died before its cleanup. Left alone they accumulate
    one copy of the skill per crash.
    """
    found = []
    now = time.time()
    for prefix in (STAGING_PREFIX, PREVIOUS_PREFIX):
        for path in sorted(Path(dest_dir).glob(prefix + "*")):
            if max_age:
                if _is_link_like(path):
                    # A parked link keeps the age of the link the user
                    # configured: a link's own timestamp cannot be refreshed
                    # on every platform, so an age-based sweep would delete
                    # a rollback copy while the install that parked it is
                    # still running. Only an explicit uninstall (max_age=0)
                    # removes these.
                    continue
                try:
                    # lstat: a parked link is judged by its own age, not by
                    # whatever directory it points at.
                    age = now - path.lstat().st_mtime
                except OSError:
                    age = max_age
                if age < max_age:
                    continue
            found.append(path)
    return found


def _refresh_mtime(path):
    """Refresh a path's mtime so an age-based sweep leaves it alone.

    The sweep tells a live run's tree from a crashed run's by age, so a
    run that is still working has to say so. A tree whose mtime cannot be
    refreshed is reported rather than left to be swept: the copy would
    fail later, in the middle of writing, with an error that says
    nothing about the cause.
    """
    try:
        os.utime(str(path), None)
    except (NotImplementedError, OSError) as exc:
        raise OSError(
            "cannot refresh the mtime of " + str(path)
            + "; a concurrent install would treat it as a stale leftover"
        ) from exc


def _copy_file_with_heartbeat(src, dst, root):
    """Copy one file, refreshing the staging tree's mtime as it goes.

    The sweep that clears a crashed run's leftovers judges a tree by age,
    so the tree has to stay fresh for as long as the copy runs. Refreshing
    it only before and after a file is not enough: one large file can take
    longer than the age the sweep uses, and the tree would look stale while
    it was still being written, so a concurrent install's sweep would
    delete it.

    The file is copied in chunks and the mtime is refreshed between them,
    so the tree never goes stale for longer than one chunk takes. What is
    left is a run that is paused for longer than the sweep's age (a
    hibernated machine, a suspended process): the copy then fails with the
    error the sweep caused, and the install is retried.
    """
    try:
        mode = os.stat(src).st_mode
    except OSError:
        mode = None
    if mode is None or not stat.S_ISREG(mode):
        # shutil.copyfile refuses a special file with a clear error, and
        # reading one here could block on a fifo. Keep that behaviour.
        shutil.copy2(src, dst)
        return
    with open(src, "rb") as source, open(dst, "wb") as target:
        while True:
            chunk = source.read(COPY_CHUNK_BYTES)
            if not chunk:
                break
            target.write(chunk)
            _refresh_mtime(root)
    # The metadata is copied last, the way shutil.copy2 does it: the
    # timestamps of the source belong to the finished file.
    shutil.copystat(src, dst)


def _copy_with_heartbeat(root):
    """Return a copy function that keeps the staging tree's mtime fresh.

    The sweep that clears a crashed run's leftovers judges a tree by age:
    anything older than an hour is assumed to belong to a dead run. A copy
    that takes over an hour would leave the staging tree looking stale, and
    a concurrent install's sweep would delete it while it is still being
    written, so the copy fails on a file that was there a moment ago.

    The mtime is refreshed before and after every file, and between the
    chunks of every file, so the tree stays fresh for the whole copy.
    """

    def copy(src, dst):
        _refresh_mtime(root)
        _copy_file_with_heartbeat(src, dst, root)
        _refresh_mtime(root)
        return dst

    return copy


def _copy_filter(root, dest=None, collector=None):
    """Return the filter the copy uses, with a heartbeat on the staging tree.

    The sweep that clears a crashed run's leftovers judges a tree by age,
    so a copy that is still working has to keep saying so. The filter is
    called once for every directory the copy walks into, so refreshing the
    tree's mtime there covers the gaps the file copy leaves: a tree of
    directories copies no file at all, and a slow traversal can spend a
    long time between two files.

    ``collector`` collects the credential-like entries the copy leaves out,
    so the caller can report them after the copy.
    """
    def filter_files(path, names):
        # The copy creates the staging tree itself, so it does not exist
        # yet when the filter is called for the source root.
        if root.exists():
            _refresh_mtime(root)
        return _ignore_skill_files(path, names, dest=dest, collector=collector)

    return filter_files


def _sweep_leftovers(dest_dir, max_age=LEFTOVER_MAX_AGE_SEC, protect=()):
    """Remove the staging and backup trees a crashed run left behind.

    A leftover that cannot be removed is reported and skipped: it is unrelated
    to the copy that follows, so it must not abort the install. Returns True
    when every leftover was removed, so callers that only sweep (uninstall)
    can report the failure.

    A target that has become a link is refused rather than swept: the glob
    would run through it and delete same-named trees inside whatever it points
    at, which is the traversal the containment checks exist to stop. The
    window between this check and the glob is accepted: it takes a writer with
    control of the parent directory acting between two statements.

    ``protect`` names the leftovers that are left alone: the trees of an
    install that is still working. A run that still holds its lock is
    working, so its trees are left alone as well.
    """
    if _is_link_like(dest_dir):
        print_info(
            f"[WARN] refusing to sweep a link-like target: {dest_dir}"
        )
        return False
    removed_all = True
    live = _live_runs(dest_dir)
    for path in _leftovers(dest_dir, max_age):
        if path in protect or _run_token(path) in live:
            continue
        try:
            if _is_link_like(path):
                _remove_link_like(path)
            else:
                _remove_tree(path)
        except OSError as exc:
            print_info(f"[WARN] Could not remove leftover {path}: {exc}")
            removed_all = False
    return removed_all


def _run_token(path):
    """Return the run token a leftover's name carries.

    A run's staging tree and its parked backup are named after the same
    token, so the token says which run a leftover belongs to.
    """
    name = Path(path).name
    for prefix in (STAGING_PREFIX, PREVIOUS_PREFIX):
        if name.startswith(prefix):
            return name[len(prefix):]
    return ""


def _live_runs(dest_dir):
    """Return the tokens of the installs that are still working.

    A live run holds an OS lock for as long as it works, and the kernel
    drops the lock when the process dies. The parked backup carries the
    same token as the staging tree, so it belongs to that run even after
    the staging tree is gone, which is the case between the park and the
    swap.
    """
    live = set()
    for path in _leftovers(dest_dir):
        token = _run_token(path)
        if not token:
            continue
        if _lock_is_held(_run_lock_path(dest_dir, token)):
            live.add(token)
    return live


def copy_skill(src_dir, dest_dir):
    """Copy the skill files from the source directory to the destination directory.

    Args:
        src_dir (Path): The source directory containing the skill files.
        dest_dir (Path): The destination directory where the skill should be installed.

    Returns:
        Path: The path to the newly installed skill directory.

    Raises:
        PermissionError: If the destination is not writable.
        OSError: If the copy operation fails.
        ValueError: If the destination is a link-like target, or is the
            source directory itself.
    """
    try:
        if _is_link_like(dest_dir):
            # Installing through a link would copy into, and delete an old
            # install from, the link's target rather than the named directory.
            raise ValueError(
                "Refusing to install through a link-like target: "
                + str(dest_dir)
            )
        # The staging tree is created inside the destination. A destination
        # inside the source tree is therefore copied into itself: the copy
        # walks into the destination, finds the staging tree it is building,
        # and copies that too, until the copy fails. The destination is left
        # out of the copy instead, so the install still succeeds.
        resolved_src = Path(src_dir).resolve(strict=False)
        resolved_dest = Path(dest_dir).resolve(strict=False)
        if resolved_dest == resolved_src:
            raise ValueError(
                "Refusing to install the skill into its own source directory: "
                + str(dest_dir)
            )
        excluded_credentials = []
        # The destination is left out of the copy when it sits inside the
        # source tree; otherwise the copy carries it along.
        ignore_dest = None
        if resolved_dest.is_relative_to(resolved_src):
            ignore_dest = resolved_dest
        if not dest_dir.exists():
            dest_dir.mkdir(parents=True, exist_ok=True)

        skill_dest = dest_dir / "complete-codebase-review"
        # The pid alone is not unique over time: after a crash the OS can hand
        # the same pid to a later run. Clearing a name this run would reuse
        # would then delete that dead run's backup, which can be the only copy
        # of the previous install when the crash landed between the park and
        # the swap. A random suffix makes the name belong to this run alone.
        token = str(os.getpid()) + "-" + os.urandom(4).hex()
        staging = dest_dir / (STAGING_PREFIX + token)
        previous = dest_dir / (PREVIOUS_PREFIX + token)
        lock = _RunLock(_run_lock_path(dest_dir, token))

        # Build the new tree beside the old one and swap it in at the end.
        # Deleting the working install first means a failure mid-copy leaves
        # the user with no usable skill at all. The old tree is moved aside
        # rather than deleted for the same reason: if the swap fails it is
        # moved back, so the previous install survives every failure path.
        _sweep_leftovers(dest_dir)
        # Lock files left by crashed runs are removed: the kernel drops the
        # lock when the process dies, so a free lock file is litter.
        _sweep_run_locks(dest_dir)
        # The guard above runs before the sweep, and a sweep can take long
        # enough for the target to become a link. This is the last check
        # before the write: copying through a link would put the staging tree
        # inside whatever it points at, which is the traversal the guards
        # exist to stop.
        if _is_link_like(dest_dir):
            raise ValueError(
                "Refusing to install through a link-like target: "
                + str(dest_dir)
            )
        # The run takes an OS lock before it writes anything. A concurrent
        # install or uninstall sees the lock held and leaves this run's
        # staging tree and parked backup alone, and the kernel drops the
        # lock when this process ends, so a crashed run's trees stay
        # removable.
        try:
            lock.acquire()
        except OSError:
            try:
                os.unlink(str(lock.path))
            except OSError:
                pass
            raise
        # Whether this run's own swap landed. A concurrent install can park
        # the tree this run installs, and the missing live install that
        # leaves behind is not evidence that this run's swap failed.
        swapped = False
        try:
            shutil.copytree(
                src_dir, staging,
                ignore=_copy_filter(
                    staging, ignore_dest, excluded_credentials
                ),
                symlinks=True,
                copy_function=_copy_with_heartbeat(staging),
            )
            # The copy ends by putting the source directory's own
            # timestamps on the staging tree, and a source directory can
            # be days old. The sweep would then read a freshly copied tree
            # as a crashed run's leftover and delete it, so the mtime is
            # refreshed once more before the tree is put in place.
            _refresh_mtime(staging)
            _validate_no_escaped_symlinks(staging)

            if os.path.lexists(skill_dest):
                print_info(f"Updating existing installation in {skill_dest}")
                if _is_link_like(skill_dest):
                    # Park the link itself instead of deleting it: renaming
                    # the entry leaves the link's target untouched, and if
                    # the swap below fails the finally block puts the link
                    # back where the user configured it.
                    parked = skill_dest
                else:
                    parked = skill_dest.resolve(strict=False)
                    root = _containment_root(dest_dir)
                    if parked == root:
                        raise ValueError(
                            f"Refusing to replace target root {root}"
                        )
                    if not parked.is_relative_to(root):
                        raise ValueError(
                            f"Resolved path {parked} is outside target {root}"
                        )
                # A rename keeps the entry's old mtime, which would make this
                # live backup look like a crashed run's leftover to a
                # concurrent install's age-based sweep. Stamp the entry that
                # is about to be renamed, never the target a link points at,
                # and stamp it before the rename: refreshing the mtime after
                # the park leaves a window in which the backup already has its
                # old name and the sweep would delete it.
                link_like = _is_link_like(parked)
                try:
                    if link_like:
                        os.utime(str(parked), None, follow_symlinks=False)
                    else:
                        os.utime(str(parked), None)
                except (NotImplementedError, OSError) as exc:
                    # A directory whose mtime cannot be refreshed would be
                    # parked with its old age, so a concurrent sweep could
                    # delete the only rollback copy. Refuse before touching
                    # the live install instead. A link is parked anyway:
                    # stamping one is not supported everywhere, and losing
                    # it costs the entry, never what it points at.
                    if not link_like:
                        raise OSError(
                            "cannot refresh the mtime of the existing install "
                            "before parking it: " + str(parked)
                        ) from exc
                os.replace(str(parked), str(previous))

            # Re-assert at the last moment: dest_dir was checked before the
            # copy, and a swap in between would send the final rename into the
            # link's target instead of the named directory.
            if _is_link_like(dest_dir):
                raise ValueError(
                    "Refusing to install through a link-like target: "
                    + str(dest_dir)
                )
            os.replace(str(staging), str(skill_dest))
            swapped = True
        finally:
            # Restore before any cleanup: a locked staging tree must not take
            # the only surviving copy of the previous install with it.
            #
            # Only when this run's own swap did not happen. A missing live
            # install does not prove that: a concurrent install may have
            # parked the tree this run put in place, and restoring this
            # run's older backup over that gap would put the stale version
            # back. The backup stays a leftover for the next run's sweep
            # instead.
            if (
                not swapped
                and os.path.lexists(previous)
                and not os.path.lexists(skill_dest)
            ):
                try:
                    os.replace(str(previous), str(skill_dest))
                except OSError:
                    pass  # previous remains as a leftover for the next run
            try:
                _remove_tree(staging)
            except OSError:
                pass  # a leftover; the next run sweeps it
            # Once the new tree is in place the old one is redundant; if the
            # restore above failed it is the only copy and must stay.
            if os.path.lexists(skill_dest) and os.path.lexists(previous):
                try:
                    _remove_tree(previous)
                except OSError:
                    pass
            # The lock is dropped last: while it is held this run's trees
            # are protected from a concurrent sweep, and the file it locked
            # goes with it. A crashed run leaves the file behind, and the
            # next run's sweep removes it.
            lock.release()
            try:
                os.unlink(str(lock.path))
            except OSError:
                pass

        for relative in sorted({
            Path(os.path.relpath(path, src_dir)).as_posix()
            for path in excluded_credentials
        }):
            print_info(f"excluded (credential-like): {relative}")
        copied = sum(len(files) for _, _, files in os.walk(skill_dest))
        print_info(f"Copied {copied} file(s) to {skill_dest}")
        return skill_dest
    except PermissionError:
        print_error(f"Permission denied: cannot write to {dest_dir}")
        raise
    except OSError as e:
        print_error(f"Failed to copy skill: {e}")
        raise
    except ValueError as e:
        print_error(str(e))
        raise


def _remove_tree(path):
    """Remove a file or directory tree, whichever ``path`` names.

    ``onexc`` is 3.12+, ``onerror`` was removed in 3.14, so the call is split
    on the version the same way the rest of this module does it.
    """
    if not os.path.lexists(path):
        return
    if _is_link_like(path):
        # Windows refuses to unlink a directory symlink or junction; only
        # rmdir removes the reparse point itself without entering the target.
        _remove_link_like(path)
        return
    if os.path.isdir(path):
        if sys.version_info >= (3, 12):
            shutil.rmtree(str(path), onexc=_onerror)
        else:
            shutil.rmtree(str(path), onerror=_onerror)
    else:
        os.unlink(str(path))


def _validate_no_escaped_symlinks(skill_dest):
    """Validate no copied symlinks escape the skill directory (T-002).

    Collects violations during the walk to avoid calling rmtree
    while os.walk holds directory handles (Windows PermissionError).
    """
    root_resolved = skill_dest.resolve(strict=False)
    errors = []
    for dirpath, dirnames, filenames in os.walk(skill_dest):
        for name in dirnames + filenames:
            full_path = Path(dirpath) / name
            if _is_link_like(full_path):
                try:
                    target = full_path.resolve(strict=True)
                except (OSError, RuntimeError) as err:
                    errors.append((
                        f"Broken symlink {full_path} in skill directory",
                        err
                    ))
                    continue
                if not target.is_relative_to(root_resolved):
                    errors.append((
                        f"Symlink {full_path} points outside skill dir: "
                        f"{target}",
                        None
                    ))
    if errors:
        if sys.version_info >= (3, 12):
            shutil.rmtree(str(skill_dest), onexc=_onerror)
        else:
            shutil.rmtree(str(skill_dest), onerror=_onerror)
        msg, cause = errors[0]
        if cause:
            raise ValueError(msg) from cause
        raise ValueError(msg)


def _validate_target_path(path):
    """Validate target path has no path traversal components.

    Checks for explicit '..' components which could allow writing outside the
    intended directory.

    Args:
        path (Path): The target path to validate.

    Returns:
        Path: The resolved absolute path.

    Raises:
        ValueError: If path traversal is detected.
    """
    if ".." in path.parts:
        raise ValueError(f"Path traversal detected: {path}")
    try:
        resolved = path.resolve()
        parent_resolved = path.parent.resolve()
    except (OSError, ValueError, RuntimeError) as e:
        raise ValueError(f"Failed to resolve path: {path}") from e
    # Verify canonical path stays within intended parent boundary
    # Skip check when resolved equals parent (installing to CWD via -t .)
    if resolved != parent_resolved and not resolved.parent.is_relative_to(parent_resolved):
        raise ValueError(
            f"Symlink escapes target directory: {path} -> {resolved}"
        )
    return resolved


def _resolve_local_skills():
    """Resolve .skills/ in the working directory, refusing links.

    A link-like .skills is never a legitimate local install. One pointing at
    the working directory (or an ancestor) resolves to the repo root, so
    installing would copy the skill into the checkout and uninstall would
    delete it from there; one pointing at a child of the checkout would copy
    or delete the source tree inside itself.

    Returns:
        Path: The resolved local .skills directory.

    Raises:
        ValueError: If the path is a link, or resolves to the working
            directory or one of its parents.
    """
    local = Path.cwd() / ".skills"
    if _is_link_like(local):
        raise ValueError(
            "Refusing to use a link-like .skills directory: " + str(local)
        )
    resolved = _validate_target_path(local)
    cwd = Path.cwd().resolve()
    if resolved == cwd or cwd.is_relative_to(resolved):
        raise ValueError(
            "Refusing to use a .skills directory that resolves to the "
            "working directory or a parent: {} -> {}".format(local, resolved)
        )
    return resolved


def _print_ccr_hint():
    """Explain how to run the bundled ccr module after installation."""
    print_info(
        "The ccr core ships inside the skill directory and is not installed "
        "as a console script. Run it with the skill directory on PYTHONPATH:"
    )
    print_info(
        '  POSIX:      PYTHONPATH="<skill-dir>" python -m ccr plan .'
    )
    print_info(
        '  PowerShell: $env:PYTHONPATH="<skill-dir>"; python -m ccr plan .'
    )


def _run_target_install(src_dir, target, dry_run):
    """Install skill to a user-specified --target directory, exiting on error."""
    try:
        resolved = _validate_target_path(Path(target))
    except ValueError as e:
        print_error(str(e))
        sys.exit(1)
    if dry_run:
        skill_dest = resolved / 'complete-codebase-review'
        print_info(f"[DRY-RUN] Would install to {skill_dest}")
        print_success("Dry run complete.")
        return
    try:
        dest_path = copy_skill(src_dir, resolved)
        print_success(f"Installed to: {dest_path}")
    except (OSError, ValueError) as e:
        print_error(f"Install failed: {e}")
        sys.exit(1)
    print_success("Installation complete!")
    _print_ccr_hint()


def _run_auto_install(src_dir, target_dirs, dry_run):
    """Install to all detected AI agent config directories. Returns True if any succeeded."""
    installed_any = False
    for tool_name, target_dir in target_dirs.items():
        if not target_dir.parent.exists():
            continue
        print_info(f"Detected {tool_name} configuration at {target_dir.parent}")
        try:
            target_dir = _validate_target_path(target_dir)
        except ValueError as e:
            print_error(f"Invalid target path for {tool_name}: {e}")
            continue
        if dry_run:
            skill_dest = target_dir / 'complete-codebase-review'
            print_info(f"[DRY-RUN] Would install to {tool_name}: {skill_dest}")
            installed_any = True
            continue
        try:
            dest_path = copy_skill(src_dir, target_dir)
            print_success(f"Installed to {tool_name}: {dest_path}")
            installed_any = True
        except (OSError, ValueError) as e:
            print_error(f"Failed to install to {tool_name}: {e}")
    return installed_any


def remove_skill(dest_dir, dry_run):
    """Remove an installed skill directory. Returns True if something was removed."""
    if _is_link_like(Path(dest_dir)):
        # Refuse before anything under dest_dir is resolved. A directory
        # swapped for a link after the caller validated it would otherwise
        # move the containment root onto the link target and let the
        # recursive delete run outside the intended tree.
        raise ValueError(
            "Refusing to remove from a link-like target: " + str(dest_dir)
        )
    skill_dest = Path(dest_dir) / "complete-codebase-review"
    installed = os.path.lexists(str(skill_dest))
    # A crashed install can leave the old tree aside with no live skill at all
    # (the swap never ran). Those leftovers are still this tool's files, and
    # the live-skill early return would otherwise make them permanent.
    target = Path(dest_dir)
    leftovers = _leftovers(target) if target.is_dir() else []
    # An install that is still working owns a staging tree it is writing and,
    # between the park and the swap, the backup it would put back if the swap
    # failed. Removing them breaks that install and takes its rollback copy
    # with it, so they are left alone. The backup is recognised by the token
    # it shares with the staging tree, not by its own age: a parked link
    # keeps the age of the link the user configured, and on Windows that
    # timestamp cannot be refreshed at all. The run that owns them holds an
    # OS lock, which the kernel drops when the process dies, so a crashed
    # run's trees are still removed.
    live = _live_runs(target) if target.is_dir() else set()
    protect = {
        path for path in leftovers if _run_token(path) in live
    }
    if not installed and not leftovers:
        print_info("Not installed: " + str(skill_dest))
        return False
    if dry_run:
        if installed:
            print_info("[DRY-RUN] Would remove " + str(skill_dest))
        for path in leftovers:
            if path in protect:
                print_info(
                    "[DRY-RUN] Would leave leftover " + str(path)
                    + ": an install may still be running"
                )
            else:
                print_info("[DRY-RUN] Would remove leftover " + str(path))
        return True
    root = _containment_root(dest_dir)
    # Re-assert as late as possible. The caller validated dest_dir before this
    # call, and a swap in between would move the containment root with it, so
    # the check is repeated immediately before anything is resolved or removed.
    if _is_link_like(Path(dest_dir)):
        raise ValueError(
            "Refusing to remove from a link-like target: " + str(dest_dir)
        )
    # An explicit uninstall clears every leftover, whatever its age: it is a
    # destructive request to remove this tool from the tree. The trees of an
    # install that is still working are the exception: they are left alone,
    # because removing them breaks that install and takes its rollback copy
    # with it.
    if not _sweep_leftovers(target, max_age=0, protect=protect):
        # Nothing else is removed: a caller that treats "removed nothing" as
        # "nothing to do" would report success while these trees survive.
        raise OSError(
            "could not remove the leftover files in " + str(dest_dir)
        )
    # The lock files of runs that are gone are litter; a lock that is still
    # held belongs to an install that is still working.
    _sweep_run_locks(target)
    for path in protect:
        print_info(
            "Left " + str(path) + ": an install may still be running"
        )
    if not installed:
        if protect:
            print_info("Nothing else to remove in " + str(target))
        else:
            print_success("Removed leftover files from " + str(target))
        return True
    if _is_link_like(skill_dest):
        _remove_link_like(skill_dest)
    else:
        resolved = skill_dest.resolve(strict=False)
        if resolved == root:
            raise ValueError("Refusing to remove target root: " + str(resolved))
        if not resolved.is_relative_to(root):
            raise ValueError("Refusing to remove path outside target: " + str(resolved))
        # Last gate before the recursive delete: rmtree refuses a symlink root
        # but follows a Windows junction, so check the reparse point here.
        if _is_link_like(resolved):
            raise ValueError(
                "Refusing to remove a link-like target: " + str(resolved)
            )
        if resolved.is_dir():
            if sys.version_info >= (3, 12):
                shutil.rmtree(str(resolved), onexc=_onerror)
            else:
                shutil.rmtree(str(resolved), onerror=_onerror)
        else:
            resolved.unlink()
    print_success("Removed " + str(skill_dest))
    return True


def _run_uninstall(target, dry_run):
    """Remove the skill from an explicit target or all detected config dirs."""
    removed = 0
    failed = 0
    if target:
        try:
            resolved = _validate_target_path(Path(target))
        except ValueError as e:
            print_error(str(e))
            sys.exit(1)
        try:
            removed += int(remove_skill(resolved, dry_run))
        except (OSError, ValueError) as e:
            print_error("Uninstall failed: " + str(e))
            sys.exit(1)
    else:
        targets = get_target_dirs()
        # Earlier releases installed OpenCode to ~/.opencode/skills. Current
        # OpenCode reads ~/.config/opencode/skills, so auto-uninstall clears
        # both instead of leaving the old copy behind after an upgrade.
        legacy = Path.home() / ".opencode" / "skills"
        if legacy not in targets.values():
            targets["OpenCode (legacy)"] = legacy
        for tool_name, target_dir in targets.items():
            if not target_dir.parent.exists():
                continue
            try:
                if remove_skill(target_dir, dry_run):
                    removed += 1
                    print_info("Removed from " + tool_name)
            except (OSError, ValueError) as e:
                failed += 1
                print_error("Failed to remove from {}: {}".format(tool_name, e))
        local = Path.cwd() / ".skills"
        if local.exists():
            try:
                local = _resolve_local_skills()
                if remove_skill(local, dry_run):
                    removed += 1
                    print_info("Removed local .skills install")
            except (OSError, ValueError) as e:
                failed += 1
                print_error("Failed to remove local install: " + str(e))
    if failed:
        print_error("Uninstall incomplete: {} location(s) failed".format(failed))
        return 1
    if removed == 0:
        print_info("Nothing to uninstall.")
    elif dry_run:
        print_success("Dry run complete.")
    else:
        print_success("Uninstall complete.")
    return 0


def _run_local_fallback(src_dir, dry_run):
    """Install to .skills/ under the current working directory, exiting on error."""
    local_target = Path.cwd() / ".skills"
    try:
        local_target = _resolve_local_skills()
    except ValueError as e:
        print_error(f"Local installation failed: {e}")
        sys.exit(1)
    gitignore = Path.cwd() / ".gitignore"
    if gitignore.exists() and any(
        line.strip() in [".skills", ".skills/"]
        for line in gitignore.read_text(encoding="utf-8").splitlines()
    ):
        print_info(
            "WARNING: .skills/ is listed in .gitignore — "
            "your local install will not be tracked by git."
        )
    if dry_run:
        skill_dest = local_target / 'complete-codebase-review'
        print_info(
            f"[DRY-RUN] Would install to local directory: {skill_dest}"
        )
        return
    try:
        dest_path = copy_skill(src_dir, local_target)
        print_success(f"Installed to local directory: {dest_path}")
    except (OSError, ValueError) as e:
        print_error(f"Local installation failed: {e}")
        sys.exit(1)


def _run_auto_or_local_install(src_dir, target_dirs, dry_run):
    """Install to auto-detected config dirs, falling back to local .skills/ if none found.""" 
    installed_any = _run_auto_install(src_dir, target_dirs, dry_run)

    if not installed_any:
        detected = any(
            target_dir.parent.exists() for target_dir in target_dirs.values()
        )
        if detected:
            print_info("No detected installations succeeded")
        else:
            print_info("No existing global tool configurations")
        _run_local_fallback(src_dir, dry_run)

    if dry_run:
        print_success("Dry run complete.")
        return

    print_success("Installation complete!")
    _print_ccr_hint()


def _parse_args():
    """Build the CLI parser and return the parsed arguments."""
    parser = argparse.ArgumentParser(
        description="Install the Complete Codebase Review skill for AI coding agents.",
        epilog=(
            "Examples:\n"
            "  python install.py\n"
            "  python install.py --target ~/my-skills\n"
            "  python install.py --dry-run\n"
            "  python install.py --version\n"
            "  python install.py --self-verify\n"
            "  python install.py --checksum <SHA256_HASH>\n"
            "  python install.py --uninstall"
        ),
    )
    parser.add_argument(
        "--target", "-t",
        metavar="DIR",
        default=None,
        help="Install to a specific directory instead of auto-detecting agent configs.",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        default=False,
        help="Print what would be installed without copying any files.",
    )
    parser.add_argument(
        "--version", "-V",
        action="store_true",
        help="Show version and exit.",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        default=False,
        help="Remove the installed skill from detected or --target directories.",
    )
    verify_group = parser.add_mutually_exclusive_group()
    verify_group.add_argument(
        "--checksum",
        metavar="HASH",
        default=None,
        help="Post-load self-check: verify the extracted installer's SHA-256.",
    )
    verify_group.add_argument(
        "--self-verify",
        action="store_true",
        default=False,
        help="Verify this script against install.py.sha256 (if present) and exit.",
    )
    return parser.parse_args()


def _handle_version(args):
    """Print the version when --version was given. Returns True if handled."""
    if not args.version:
        return False
    print(f"complete-codebase-review v{get_version()}")
    return True


def _handle_self_verify(args):
    """Verify this script against install.py.sha256, exiting 0 on match or 1 on failure."""
    script_path = Path(__file__).resolve()
    checksum_file = script_path.parent / "install.py.sha256"
    if not checksum_file.exists():
        print_error("install.py.sha256 not found")
        sys.exit(1)
    checksum_content = checksum_file.read_text(encoding="utf-8").strip()
    if not checksum_content:
        print_error("install.py.sha256 is empty — verification failed")
        sys.exit(1)
    expected_hash = checksum_content.split()[0]
    if not _is_sha256(expected_hash):
        print_error(
            "install.py.sha256 contains invalid checksum format"
            " (expected 64 hex characters)"
        )
        sys.exit(1)
    if _verify_checksum(script_path, expected_hash):
        print_success("Checksum verification passed")
        sys.exit(0)
    print_error("Checksum verification FAILED — script may be corrupted")
    sys.exit(1)


def _handle_checksum(args):
    """Verify this script against --checksum, exiting 0 on match or 1 on failure."""
    script_path = Path(__file__).resolve()
    if not _is_sha256(args.checksum):
        print_error(
            "Invalid checksum format (expected 64 hexadecimal characters)"
        )
        sys.exit(1)
    if _verify_checksum(script_path, args.checksum):
        print_success("Checksum verification passed")
        sys.exit(0)
    print_error("Checksum verification FAILED")
    sys.exit(1)


def _dispatch(args):
    """Run the installer mode selected by the parsed arguments."""
    if _handle_version(args):
        return None
    if args.self_verify:
        _handle_self_verify(args)
    if args.checksum is not None:
        _handle_checksum(args)
    if args.uninstall:
        print_info(f"Starting Universal Uninstaller on {platform.system()}")
        return _run_uninstall(args.target, args.dry_run)

    print_info(f"Starting Universal Installer on {platform.system()}")

    src_dir = Path(__file__).parent.resolve()

    if args.target:
        _run_target_install(src_dir, args.target, args.dry_run)
        return None

    target_dirs = get_target_dirs()
    _run_auto_or_local_install(src_dir, target_dirs, args.dry_run)
    return None


def main():
    """Execute the main installation process."""
    return _dispatch(_parse_args())


if __name__ == "__main__":
    sys.exit(main())
