import os

def read_file_safe(path):
    if not os.path.exists(path):
        return ""

def parse_config(data):
    import json
    return json.loads(data)

def old_format_string(name):
    return "Hello, %s!" % name

def unused_function():
    pass
