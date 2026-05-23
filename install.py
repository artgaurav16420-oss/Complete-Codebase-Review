import os
import sys
import shutil
import platform
from pathlib import Path

def print_success(msg):
    print(f"[\033[92mSUCCESS\033[0m] {msg}")

def print_info(msg):
    print(f"[\033[94mINFO\033[0m] {msg}")

def print_error(msg):
    print(f"[\033[91mERROR\033[0m] {msg}")

def get_target_dirs():
    home = Path.home()

    dirs = {
        "Claude Code": home / ".claude" / "skills",
        "OpenCode": home / ".opencode" / "skills",
        "Cursor": home / ".cursor" / "skills",
        "Continue": home / ".continue" / "skills"
    }

    return dirs

def copy_skill(src_dir, dest_dir):
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
        return [n for n in names if n in ('.git', '__pycache__', 'install.py', 'install.sh', 'install.ps1', '.skills') or n.endswith('.pyc')]

    shutil.copytree(src_dir, skill_dest, ignore=ignore_patterns)
    return skill_dest

def main():
    print_info(f"Starting Universal Installer on {platform.system()}")

    src_dir = Path(__file__).parent.resolve()
    target_dirs = get_target_dirs()
    installed_any = False

    for tool_name, target_dir in target_dirs.items():
        if target_dir.parent.exists():
            print_info(f"Detected {tool_name} configuration at {target_dir.parent}")
            dest_path = copy_skill(src_dir, target_dir)
            print_success(f"Installed to {tool_name}: {dest_path}")
            installed_any = True

    if not installed_any:
        print_info("No existing global tool configurations detected. Installing locally.")
        local_target = Path.cwd() / ".skills"
        dest_path = copy_skill(src_dir, local_target)
        print_success(f"Installed to local directory: {dest_path}")

    print_success("Installation complete!")

if __name__ == "__main__":
    main()
