import os
from auth.login import login, ping_host, delete_user
from config import get_config

cfg = get_config()
os.environ.setdefault("AUTH_SECRET", cfg["db_password"])
if login("admin", cfg["db_password"]):
    print("Login OK")
