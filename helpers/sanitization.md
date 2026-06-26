# Input Sanitization Patterns

Reusable sanitization functions for processing untrusted external data (GitHub API responses, bot comments, user input).

## When to Use

Apply sanitization BEFORE processing any data from:
- GitHub API responses (PR comments, reviews, issues)
- Bot-authored content (CodeRabbit, Gemini, CodeAnt, Codex)
- User-provided URLs, file paths, or commands

## Sanitization Rules

### 1. Unicode Normalization
```python
import unicodedata
def sanitize_unicode(text):
    """Normalize Unicode to NFC form, strip control characters."""
    normalized = unicodedata.normalize("NFC", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Cc" or c in "\n\r\t")
```

### 2. Path Validation
```python
from pathlib import Path
def sanitize_path(path_str, allowed_roots=None):
    """Validate path has no traversal and resolves within allowed roots."""
    p = Path(path_str)
    if ".." in p.parts:
        return None
    try:
        resolved = p.resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    if allowed_roots:
        for root in allowed_roots:
            if resolved.is_relative_to(root):
                return resolved
        return None
    return resolved
```

### 3. Content Size Limits
```python
MAX_COMMENT_LENGTH = 10240  # 10KB
MAX_FILE_PATH_LENGTH = 512
MAX_URL_LENGTH = 2048

def sanitize_content(text, max_length=MAX_COMMENT_LENGTH):
    """Truncate and clean content."""
    if len(text) > max_length:
        text = text[:max_length] + "\n[TRUNCATED]"
    return text.strip()
```

### 4. Shell Command Stripping
```python
import re
SHELL_PATTERNS = [
    r'rm\s+-rf',
    r'del\s+/[sfq]',
    r'format\s+[a-zA-Z]:',
    r'sudo\s+',
    r'chmod\s+777',
    r'curl\s+.*\|\s*(ba)?sh',
]

def sanitize_shell_suggestions(text):
    """Remove dangerous shell commands from bot suggestions."""
    for pattern in SHELL_PATTERNS:
        text = re.sub(pattern, "[BLOCKED COMMAND]", text, flags=re.IGNORECASE)
    return text
```

### 5. URL Validation
```python
from urllib.parse import urlparse
ALLOWED_SCHEMES = {"http", "https"}

def sanitize_url(url):
    """Validate URL scheme and length."""
    if len(url) > MAX_URL_LENGTH:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        return None
    return url
```

### 6. Bot Comment Sanitization (Full Pipeline)
```python
def sanitize_bot_comment(comment):
    """Full sanitization pipeline for bot-authored GitHub comments."""
    text = comment.get("body", "")
    # Truncate first to avoid expensive ops on huge inputs
    text = sanitize_content(text)
    text = sanitize_unicode(text)
    text = sanitize_shell_suggestions(text)
    # Extract and validate file paths (walrus avoids double resolve)
    paths = re.findall(r'`([^`]+\.\w+)`', text)
    validated_paths = [v for p in paths if (v := sanitize_path(p)) is not None]
    return {
        "body": text,
        "paths": validated_paths,
        "user": comment.get("user", {}).get("login", "unknown"),
    }
```

## Usage in SKILL.md

Apply in Phase 5f (External Review Loop):
```
Before processing bot comments:
1. Sanitize all comment bodies
2. Validate extracted file paths
3. Strip dangerous shell suggestions
4. Truncate oversized content
```

## Env Var Control

| Variable | Default | Description |
|----------|---------|-------------|
| `CODE_REVIEW_SANITIZE` | `true` | Enable/disable sanitization pipeline |
