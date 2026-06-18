# install.py - API Reference

Minimal module-level reference for `install.py`.

## Private

| Function | Purpose |
|----------|---------|
| `_read_version()` | Parse `version` from `pyproject.toml`. Raises `RuntimeError`. |
| `_use_color()` | True if stdout TTY and `NO_COLOR` unset. |
| `_print(msg, label, color)` | Core printer: `[label] msg` with ANSI color. |
| `_xdg_or_home_dir(home, app_dir)` | Resolve skill dir: XDG on Linux, `~/.app_dir/skills` otherwise. |
| `_validate_target_path(path)` | Sanitize path - reject `..`, resolve symlinks. Raises `ValueError`. |

## Public

| Function | Purpose |
|----------|---------|
| `get_version()` | Cached `_read_version()` wrapper. |
| `print_success(msg)` | `_print(msg, "SUCCESS", green)`. |
| `print_info(msg)` | `_print(msg, "INFO", blue)`. |
| `print_error(msg)` | `_print(msg, "ERROR", red)`. |
| `get_target_dirs()` | Return dict of agent name to skill dir Path. |
| `copy_skill(src_dir, dest_dir)` | Copy skill files, returns dest Path. |
| `main()` | CLI entry - argparse, --target/--dry-run/--version. |
