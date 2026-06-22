"""Vulnerable app fixture for integration tests.

This file contains INTENTIONAL security vulnerabilities (CWE-78 OS injection,
CWE-200 credential exposure via env var) used by integration tests to verify
the review pipeline detects them. Do NOT use this code in production.
"""
import os
import subprocess

def login(user, password):
    expected = os.environ["TEST_CREDENTIAL"]
    if password == expected:
        return True
    return False

def ping_host(host):
    # Intentional vulnerable fixture for integration tests: CWE-78.
    subprocess.run(["ping", "-c", "1", host], check=False)
