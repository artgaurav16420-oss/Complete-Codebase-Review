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

VERSION = "2.0.2"
import argparse
import os
import shutil
import sys
import platform
from pathlib import Path


def print_success(msg):
    print(f"[\033[92mSUCCESS\033[0m] {msg}")


def print_info(msg):
    print(f"[\033[94mINFO\033[0m] {msg}")


def print_error(msg):
    print(f"[\033[91mERROR\033[0m] {msg}")


def _claude_code_dir(home: Path) -> Path:
    """Return Claude Code skill directory.

    On Linux, honours XDG_CONFIG_HOME when explicitly set, otherwise falls
    back to ~/.claude/skills (the conventional Claude Code install location).
    On other platforms, always returns ~/.claude/skills.
    """
    if platform.system() == "Linux":
        xdg_env = os.environ.get("XDG_CONFIG_HOME", "").strip()
        if xdg_env:
            return Path(xdg_env) / "claude" / "skills"
    return home / ".claude" / "skills"


def get_target_dirs():
    """Determine the target installation directories for supported AI agents.

    Returns:
        dict: A dictionary mapping agent names to their respective skill installation directories.
    """
    home = Path.home()

    dirs = {
        "Claude Code": _claude_code_dir(home),
        "OpenCode": home / ".opencode" / "skills",
        "Cursor": home / ".cursor" / "skills",
        "Continue": home / ".continue" / "skills",
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
        return skill_dest
    except PermissionError:
        print_error(f"Permission denied: cannot write to {dest_dir}")
        raise
    except OSError as e:
        print_error(f"Failed to copy skill: {e}")
        raise


def main():
    """Execute the main installation process."""
    parser = argparse.ArgumentParser(
        description="Install the Complete Codebase Review skill for AI coding agents."
    )
    parser.add_argument(
        "--target",
        metavar="DIR",
        default=None,
        help="Install to a specific directory instead of auto-detecting agent configs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be installed without copying any files.",
    )
    parser.add_argument(
        "--version",
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
        target = Path(args.target)
        if args.dry_run:
            print_info(f"[DRY-RUN] Would install to {target / 'complete-codebase-review'}")
            print_success("Dry run complete.")
            return
        try:
            dest_path = copy_skill(src_dir, target)
            print_success(f"Installed to: {dest_path}")
        except (PermissionError, OSError) as e:
            print_error(f"Install failed: {e}")
            sys.exit(1)
        print_success("Installation complete!")
        return

    target_dirs = get_target_dirs()
    installed_any = False

    for tool_name, target_dir in target_dirs.items():
        if target_dir.parent.exists():
            print_info(
                f"Detected {tool_name} configuration at {target_dir.parent}"
            )
            if args.dry_run:
                print_info(f"[DRY-RUN] Would install to {tool_name}: {target_dir / 'complete-codebase-review'}")
                installed_any = True
                continue
            try:
                dest_path = copy_skill(src_dir, target_dir)
                print_success(f"Installed to {tool_name}: {dest_path}")
                installed_any = True
            except (PermissionError, OSError):
                print_error(f"Failed to install to {tool_name}")
                continue

    if args.dry_run and installed_any:
        print_success("Dry run complete.")
        return

    if not installed_any:
        print_info(
            "No existing global tool configurations detected. Installing locally."
        )
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
        if args.dry_run:
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

    print_success("Installation complete!")


if __name__ == "__main__":
    main()
