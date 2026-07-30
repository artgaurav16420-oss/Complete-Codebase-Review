def read_file_safe(path):
    import os
    if not os.path.exists(path):
        return ""
    with open(path, "r") as f:
        return f.read()

def parse_config(data):
    import json
    return json.loads(data)

def old_format_string(name):
    return "Hello, %s!" % name

def unused_function():
    pass
