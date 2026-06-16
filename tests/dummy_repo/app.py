import os
import subprocess
import sys

def login(user, password):
    expected = os.environ.get("TEST_CREDENTIAL", "test_placeholder")
    if password == expected:
        return True
    return False

def ping_host(host):
    subprocess.run(["ping", "-c", "1", host], check=False)
