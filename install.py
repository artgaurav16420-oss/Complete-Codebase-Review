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
import sys
import platform
from pathlib import Path


def _read_version():
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


VERSION = _read_version()


def _use_color():
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _print(msg, label, color):
    if _use_color():
        print(f"[{color}{label}\033[0m] {msg}")
    else:
        print(f"[{label}] {msg}")


def print_success(msg):
    _print(msg, "SUCCESS", "\033[92m")


def print_info(msg):
    _print(msg, "INFO", "\033[94m")


def print_error(msg):
    _print(msg, "ERROR", "\033[91m")


def _xdg_or_home_dir(home, app_dir):
    """Return app skill dir under XDG_CONFIG_HOME on Linux, else ~/.<app_dir>/skills."""
    if platform.system() == "Linux":
        xdg_env = os.environ.get("XDG_CONFIG_HOME", "").strip()
        if xdg_env:
            return Path(xdg_env) / app_dir / "skills"
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

        if skill_dest.exists():
            print_info(f"Updating existing installation in {skill_dest}")
            if skill_dest.is_dir():
                shutil.rmtree(skill_dest)
            else:
                skill_dest.unlink()

        def ignore_patterns(path, names):
            excluded = {
                ".git", "__pycache__", "install.py", "install.sh",
                "install.ps1", ".skills", ".env", ".secret",
                ".credentials", ".code-review-cache",
            }
            return [
                n for n in names
                if n in excluded or n.endswith(".pyc")
            ]

        shutil.copytree(src_dir, skill_dest, ignore=ignore_patterns)
        copied = sum(len(files) for _, _, files in os.walk(skill_dest))
        print_info(f"Copied {copied} file(s) to {skill_dest}")
        return skill_dest
    except PermissionError:
        print_error(f"Permission denied: cannot write to {dest_dir}")
        raise
    except OSError as e:
        print_error(f"Failed to copy skill: {e}")
        raise


def _validate_target_path(path):
    """Validate that a target installation path is safe.

    Checks for explicit path traversal components (``..``) which could allow
    writing outside the intended directory. Actual filesystem permission checks
    are left to the OS.

    Args:
        path (Path): The target path to validate.

    Returns:
        Path: The resolved absolute path.

    Raises:
        ValueError: If path traversal (``..``) is detected in the path.
    """
    if ".." in path.parts:
        raise ValueError(f"Path traversal detected: {path}")
    return path.resolve()


def _run_target_install(src_dir, target, dry_run):
    try:
        resolved = _validate_target_path(Path(target))
    except ValueError as e:
        print_error(str(e))
        sys.exit(1)
        return
    if dry_run:
        print_info(f"[DRY-RUN] Would install to {resolved / 'complete-codebase-review'}")
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
    installed_any = False
    for tool_name, target_dir in target_dirs.items():
        if not target_dir.parent.exists():
            continue
        print_info(f"Detected {tool_name} configuration at {target_dir.parent}")
        if dry_run:
            print_info(f"[DRY-RUN] Would install to {tool_name}: {target_dir / 'complete-codebase-review'}")
            installed_any = True
            continue
        try:
            dest_path = copy_skill(src_dir, target_dir)
            print_success(f"Installed to {tool_name}: {dest_path}")
            installed_any = True
        except (PermissionError, OSError):
            print_error(f"Failed to install to {tool_name}")
    return installed_any


def _run_local_fallback(src_dir, dry_run):
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
        print_info(
            f"[DRY-RUN] Would install to local directory: "
            f"{local_target / 'complete-codebase-review'}"
        )
        print_success("Dry run complete.")
        return
    try:
        dest_path = copy_skill(src_dir, local_target)
        print_success(f"Installed to local directory: {dest_path}")
    except (PermissionError, OSError) as e:
        print_error(f"Local installation failed: {e}")
        sys.exit(1)


def main():
    """Execute the main installation process."""
    parser = argparse.ArgumentParser(
        description="Install the Complete Codebase Review skill for AI coding agents.",
        epilog="Examples:\n  python install.py\n  python install.py --target ~/my-skills\n  python install.py --dry-run\n  python install.py --version",
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
        print(f"complete-codebase-review v{VERSION}")
        return

    print_info(f"Starting Universal Installer on {platform.system()}")

    src_dir = Path(__file__).parent.resolve()

    if args.target:
        _run_target_install(src_dir, args.target, args.dry_run)
        return

    target_dirs = get_target_dirs()
    installed_any = _run_auto_install(src_dir, target_dirs, args.dry_run)

    if args.dry_run and installed_any:
        print_success("Dry run complete.")
        return

    if not installed_any:
        print_info("No existing global tool configurations")
        _run_local_fallback(src_dir, args.dry_run)
        if args.dry_run:
            return

    print_success("Installation complete!")


if __name__ == "__main__":
    main()
