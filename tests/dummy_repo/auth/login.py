import os
import shutil
import subprocess

VALID_USERS = {"admin", "root"}

def login(user, password):
    expected = os.environ.get("AUTH_SECRET")
    if not expected:
        return False
    if user not in VALID_USERS:
        return False
    if password == expected:
        return True
    return False

def ping_host(host):
    try:
        result = subprocess.run(
            ["ping", "-c", "1", host],
            capture_output=True,
            timeout=30,
            check=False,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False

def delete_user(user_id):
    base = "/tmp/users"
    target = os.path.realpath(os.path.join(base, user_id))
    if not target.startswith(os.path.realpath(base) + os.sep):
        return False
    if target == os.path.realpath(base):
        return False
    shutil.rmtree(target, ignore_errors=True)
    return True
