# GitHub API Command Patterns

Reusable GitHub API patterns for the CCR pipeline. Centralizes API logic to avoid duplication between SKILL.md and skills/review/SKILL.md.

## GraphQL Pagination (Recommended for Large PRs)

### Fetch PR Comments with Pagination
```bash
# First page
gh api graphql -f query='
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      comments(first: 100) {
        pageInfo { hasNextPage endCursor }
        nodes {
          author { login type }
          body
          createdAt
          path
          line
        }
      }
    }
  }
}' -f owner=OWNER -f repo=REPO -F number=PR_NUMBER

# Subsequent pages (use endCursor from previous response)
gh api graphql -f query='
query($owner: String!, $repo: String!, $number: Int!, $cursor: String!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      comments(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { author { login type } body createdAt path line }
      }
    }
  }
}' -f owner=OWNER -f repo=REPO -F number=PR_NUMBER -F cursor=END_CURSOR
```

### Fetch PR Reviews with Pagination
```bash
gh api graphql -f query='
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      reviews(first: 100) {
        pageInfo { hasNextPage endCursor }
        nodes {
          author { login type }
          body
          state
          comments(first: 100) {
            nodes { body path line }
          }
        }
      }
    }
  }
}' -f owner=OWNER -f repo=REPO -F number=PR_NUMBER
```

## REST API Fallback (When GraphQL Unavailable)

### Fetch All PR Comments
```bash
# Check rate limit first
gh api rate_limit --jq '.resources.core.remaining'

# Fetch comments (REST, no pagination)
gh api repos/OWNER/REPO/pulls/PR_NUMBER/comments --paginate
```

### Fetch PR Reviews
```bash
gh api repos/OWNER/REPO/pulls/PR_NUMBER/reviews --paginate
```

## Rate Limit Handling

```bash
# Check remaining rate limit
REMAINING=$(gh api rate_limit --jq '.resources.core.remaining')
if [ "$REMAINING" -lt 100 ]; then
    RESET=$(gh api rate_limit --jq '.resources.core.reset')
    SLEEP_TIME=$((RESET - $(date +%s) + 10))
    echo "Rate limit low ($REMAINING remaining). Sleeping ${SLEEP_TIME}s..."
    sleep $SLEEP_TIME
fi
```

## Bot Detection Patterns

```bash
# Filter bot-authored comments (handles paginated output)
gh api repos/OWNER/REPO/pulls/PR_NUMBER/comments --paginate | \
  python -c "
import json, sys
data = []
for line in sys.stdin:
    line = line.strip()
    if line:
        try:
            chunk = json.loads(line)
            if isinstance(chunk, list):
                data.extend(chunk)
            else:
                data.append(chunk)
        except json.JSONDecodeError:
            pass
for c in data:
    if c.get('user', {}).get('type') == 'Bot':
        print(c.get('body', ''))
"
```

## Commit and Push Helper

```bash
# Stage, commit, and push all changes
git add <files>
git commit -m "fix: <description>"
git push origin <branch>
```

## PR Creation Helper

```bash
gh pr create \
  --title "fix(ccr): <n> issues resolved" \
  --body-file <body-file>
```
