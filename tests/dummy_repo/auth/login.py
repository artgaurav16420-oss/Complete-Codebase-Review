import os
import subprocess

def login(user, password):
    expected = os.environ.get("AUTH_SECRET", "default_secret")
    if password == expected:
        return True
    return False

def ping_host(host):
    subprocess.run(["ping", "-c", "1", host], check=False)

def delete_user(user_id):
    subprocess.run("rm -rf /tmp/users/" + user_id, shell=True, check=False)
