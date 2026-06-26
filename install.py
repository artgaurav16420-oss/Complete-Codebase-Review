#!/usr/bin/env python3
"""Universal installer for the Complete Codebase Review skill.

Installs the skill to supported AI agent skill directories:
- Claude Code (~/.claude/skills/)
- OpenCode (~/.opencode/skills/)
- Cursor (~/.cursor/skills/)
- Continue (~/.continue/skills/)

Usage:
    python install.py          # Install to detected agent configs
    python install.py --help   # Show this help message
    python install.py --version  # Show version
"""

import argparse
import os
import re
import shutil
import stat
import sys
import platform
from pathlib import Path

_SKILL_EXCLUDED = {
    ".git", "__pycache__", "install.py", "install.sh",
    "install.ps1", ".skills", ".env", ".secret",
    ".credentials", ".code-review-cache",
    "tests", ".github", "ADRs", ".gitignore",
    ".gitattributes", ".coveragerc", "CONTRIBUTING.md",
    "CHANGELOG.md", "LICENSE", "test.sh", "Makefile",
    "AGENTS.md", "SECURITY.md", "help.md", "pyproject.toml",
    "orchestrator-rules.md",
    # orchestrator-rules.md deliberately excluded — it's an internal
    # protocol document consumed by the orchestrator at repo root,
    # not a runtime requirement for installed skill consumers.
}


def _onerror(func, path, exc_info):
    """Retry a failed rmtree operation by making the path writable first.

    Uses follow_symlinks=False to prevent permission changes on symlink targets
    outside the expected directory tree.

    NOTE: onerror kwarg is deprecated in Python 3.12+ (PEP 632). Removal is
    planned for Python 4.0. Switch to onexc (receives exception instance
    directly) when Python 3.9 support is dropped.
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


def _ignore_skill_files(path, names):
    """Filter files to exclude from skill copy based on _SKILL_EXCLUDED."""
    return [n for n in names if n in _SKILL_EXCLUDED or n.endswith(".pyc")]


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


def _validate_xdg_path(xdg_path, home):
    """Check XDG_CONFIG_HOME resolves under user home; return path or None."""
    resolved = xdg_path.resolve()
    try:
        if resolved.is_relative_to(home.resolve()):
            return resolved
    except (OSError, ValueError):
        pass
    return None


def _xdg_or_home_dir(home, app_dir):
    """Return app skill dir under XDG_CONFIG_HOME on Linux, else ~/.<app_dir>/skills."""
    if platform.system() == "Linux":
        xdg_env = os.environ.get("XDG_CONFIG_HOME", "").strip()
        if xdg_env:
            validated = _validate_xdg_path(Path(xdg_env), home)
            if validated is not None:
                return validated / app_dir / "skills"
    return home / f".{app_dir}" / "skills"


def get_target_dirs():
    """Determine the target installation directories for supported AI agents.

    Returns:
        dict: A dictionary mapping agent names to their respective skill installation directories.
    """
    home = Path.home()

    dirs = {
        "Claude Code": _xdg_or_home_dir(home, "claude"),
        "OpenCode": _xdg_or_home_dir(home, "opencode"),
        "Cursor": _xdg_or_home_dir(home, "cursor"),
        "Continue": _xdg_or_home_dir(home, "continue"),
    }

    return dirs


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
    """
    try:
        if not dest_dir.exists():
            dest_dir.mkdir(parents=True, exist_ok=True)

        skill_dest = dest_dir / "complete-codebase-review"

        if os.path.lexists(skill_dest):
            print_info(f"Updating existing installation in {skill_dest}")
            if os.path.islink(str(skill_dest)):
                skill_dest.unlink()
            else:
                resolved = skill_dest.resolve(strict=False)
                root = dest_dir.resolve(strict=False)
                if not resolved.is_relative_to(root):
                    raise ValueError(
                        f"Resolved path {resolved} is outside target {root}"
                    )
                if resolved.is_dir():
                    shutil.rmtree(str(resolved), onerror=_onerror)
                else:
                    resolved.unlink()

        shutil.copytree(src_dir, skill_dest, ignore=_ignore_skill_files, symlinks=True)
        _validate_no_escaped_symlinks(skill_dest)

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
            try:
                is_link = full_path.is_symlink()
            except OSError:
                continue
            if is_link:
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
    resolved = path.resolve()
    resolved_parent = resolved.parent
    if not resolved_parent.is_relative_to(path.parent.resolve()):
        raise ValueError(
            f"Symlink resolves outside target directory: {path} -> {resolved}"
        )
    return resolved


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
    except (PermissionError, OSError) as e:
        print_error(f"Install failed: {e}")
        sys.exit(1)
    print_success("Installation complete!")


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
        home = Path.home()
        if not target_dir.resolve().is_relative_to(home):
            print_error(
                f"Auto-install target {tool_name} resolves outside home "
                f"directory: {target_dir}"
            )
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
        except (PermissionError, OSError) as e:
            print_error(f"Failed to install to {tool_name}: {e}")
    return installed_any


def _run_local_fallback(src_dir, dry_run):
    """Install to .skills/ under the current working directory, exiting on error."""
    local_target = Path.cwd() / ".skills"
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
    except (PermissionError, OSError) as e:
        print_error(f"Local installation failed: {e}")
        sys.exit(1)


def _run_auto_or_local_install(src_dir, target_dirs, dry_run):
    """Install to auto-detected config dirs, falling back to local .skills/ if none found.""" 
    installed_any = _run_auto_install(src_dir, target_dirs, dry_run)

    if not installed_any:
        print_info("No existing global tool configurations")
        _run_local_fallback(src_dir, dry_run)

    if dry_run:
        print_success("Dry run complete.")
        return

    print_success("Installation complete!")


def main():
    """Execute the main installation process."""
    parser = argparse.ArgumentParser(
        description="Install the Complete Codebase Review skill for AI coding agents.",
        epilog=(
            "Examples:\n"
            "  python install.py\n"
            "  python install.py --target ~/my-skills\n"
            "  python install.py --dry-run\n"
            "  python install.py --version"
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
    args = parser.parse_args()

    if args.version:
        print(f"complete-codebase-review v{get_version()}")
        return

    print_info(f"Starting Universal Installer on {platform.system()}")

    src_dir = Path(__file__).parent.resolve()

    if args.target:
        _run_target_install(src_dir, args.target, args.dry_run)
        return

    target_dirs = get_target_dirs()
    _run_auto_or_local_install(src_dir, target_dirs, args.dry_run)


if __name__ == "__main__":
    main()
