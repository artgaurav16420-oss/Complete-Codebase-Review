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
    python install.py --uninstall  # Remove installed copies
"""

import argparse
import hashlib
import os
import re
import shutil
import stat
import sys
import platform
from pathlib import Path


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
    if os.path.islink(str(path)):
        path.unlink()
        return
    try:
        os.rmdir(str(path))
    except OSError:
        path.unlink()


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


_CREDENTIAL_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
_CREDENTIAL_PREFIXES = ("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519")
_CREDENTIAL_NAMES = {"credentials", "credentials.json", ".netrc"}


def _is_credential_name(name):
    """True for names that commonly hold private keys or credentials.

    Exact-name matching alone misses the variants that actually exist in a
    checkout (.env.local, credentials.json, id_rsa_work, *.pem), and those
    files would otherwise be copied into every agent skill directory.
    """
    lowered = name.lower()
    return (
        lowered in _CREDENTIAL_NAMES
        or lowered.startswith(".env.")
        or lowered.startswith(_CREDENTIAL_PREFIXES)
        or lowered.endswith(_CREDENTIAL_SUFFIXES)
    )


def _is_link_like(path):
    """True for a symlink, a Windows junction, or any reparse point."""
    try:
        if os.path.islink(str(path)):
            return True
        attrs = getattr(os.lstat(str(path)), "st_file_attributes", 0)
    except OSError:
        return False
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(flag and attrs & flag)


def _ignore_skill_files(path, names):
    """Filter files to exclude from skill copy based on _SKILL_EXCLUDED.

    Links are skipped outright: a copy either dangles (its target was filtered)
    or resolves outside the checkout (a junction on Windows is not a symlink,
    so ``copytree`` follows it). The skill tree needs neither.
    """
    return [
        n for n in names
        if n in _SKILL_EXCLUDED
        or _is_credential_name(n)
        or _is_link_like(Path(path) / n)
        or n.endswith(".pyc")
        or n.endswith(".egg-info")
        or n == ".coverage"
    ]


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
    """Check XDG_CONFIG_HOME resolves to an absolute path; return resolved path or None.

    Per XDG spec, XDG_CONFIG_HOME may be outside the user's home directory
    (e.g. /mnt/storage/config). We verify it is absolute, has no traversal
    components, and resolves successfully.
    """
    if ".." in xdg_path.parts:
        return None
    if not xdg_path.is_absolute():
        return None
    try:
        resolved = xdg_path.resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    return resolved


def _xdg_or_home_dir(home, app_dir):
    """Return app skill dir under XDG_CONFIG_HOME on Linux, else ~/.<app_dir>/skills."""
    if platform.system() == "Linux":
        xdg_env = os.environ.get("XDG_CONFIG_HOME", "").strip()
        if xdg_env:
            validated = _validate_xdg_path(Path(xdg_env))
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
            if _is_link_like(skill_dest):
                _remove_link_like(skill_dest)
            else:
                resolved = skill_dest.resolve(strict=False)
                root = dest_dir.resolve(strict=False)
                if resolved == root:
                    raise ValueError(
                        f"Refusing to replace target root {root}"
                    )
                if not resolved.is_relative_to(root):
                    raise ValueError(
                        f"Resolved path {resolved} is outside target {root}"
                    )
                if resolved.is_dir():
                    if sys.version_info >= (3, 12):
                        shutil.rmtree(str(resolved), onexc=_onerror)
                    else:
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
    skill_dest = Path(dest_dir) / "complete-codebase-review"
    if not os.path.lexists(str(skill_dest)):
        print_info("Not installed: " + str(skill_dest))
        return False
    if dry_run:
        print_info("[DRY-RUN] Would remove " + str(skill_dest))
        return True
    root = Path(dest_dir).resolve(strict=False)
    if _is_link_like(skill_dest):
        _remove_link_like(skill_dest)
    else:
        resolved = skill_dest.resolve(strict=False)
        if resolved == root:
            raise ValueError("Refusing to remove target root: " + str(resolved))
        if not resolved.is_relative_to(root):
            raise ValueError("Refusing to remove path outside target: " + str(resolved))
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
        for tool_name, target_dir in get_target_dirs().items():
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
