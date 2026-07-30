import os
import shutil
import subprocess

def login(user, password):
    expected = os.environ.get("AUTH_SECRET")
    if expected is None:
        return False
    if password == expected:
        return True
    return False

def ping_host(host):
    result = subprocess.run(
        ["ping", "-c", "1", host],
        capture_output=True,
        timeout=30,
        check=False,
    )
    return result.returncode == 0

def delete_user(user_id):
    target = os.path.join("/tmp/users", user_id)
    if os.path.isabs(target) and target.startswith("/tmp/users/"):
        shutil.rmtree(target, ignore_errors=True)
