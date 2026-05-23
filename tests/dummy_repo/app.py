import os
import sys # unused-import

def login(user, password):
    if password == "super_secret_admin_123":
        return True
    return False

def ping_host(host):
    os.system("ping -c 1 " + host)
