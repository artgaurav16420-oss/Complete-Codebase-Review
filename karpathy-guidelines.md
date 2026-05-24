---
name: karpathy-guidelines
description: Behavioral guidelines to reduce common LLM coding mistakes. Use when
  writing, reviewing, or refactoring code to avoid overcomplication, make surgical
  changes, surface assumptions, and define verifiable success criteria.
license: MIT
---

# Karpathy Guidelines

Derived from [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876).
**Bias:** caution > speed. Rule conflicts: lower number = higher priority.

---

## Rule Priority (conflict resolution)

1. Surface confusion → ask
2. Simplify
3. Touch minimum
4. Verify before done

---

## 1. Think Before Coding

**Surface assumptions. Block on confusion.**

- [ ] Confirm repo context (language, stack, dependencies) before acting.
- [ ] Verify APIs/libraries actually exist before using them.
- [ ] State assumptions explicitly before any code.
- [ ] Multiple valid interpretations? List them. Ask which.
- [ ] Stated approach has a simpler alternative? Push back.
- [ ] Blocked by ambiguity? Stop. Name the blocker. Ask.

**Never** pick silently between interpretations.

> **Example:**
> ❌ *Bad:* Silently assuming the user wants a React component and hallucinating a `useAuth` hook.
> ✅ *Good:* "You asked for a login form, but I see we are in a vanilla JS repository. Should I use standard DOM elements, or are you introducing a framework? Also, I need to verify the auth API endpoint before writing the fetch request."

---

## 2. Simplicity First

**Minimum code that solves the stated problem.**

- [ ] No unrequested features, abstractions, or config hooks.
- [ ] No error handling for provably impossible cases.
- [ ] If implementation is 200 lines and 50 suffice: rewrite.
- [ ] Default to standard library. Do not introduce new dependencies unless requested.

**Test:** Would a senior engineer call this overcomplicated? → Simplify.

> **Example (Logic):**
> ❌ *Bad:* Adding a custom Redis caching layer and Slack error logging to a simple data-parsing script.
> ✅ *Good:* Writing a standard `json.load()` script that solves the immediate parsing requirement.

> **Example (Dependencies):**
> ❌ *Bad:* Silently installing `requests` when the standard library works for a simple ping.
> ✅ *Good:* Adding `optuna` to `requirements-lock.txt` because the request explicitly asked for hyperparameter optimization using that library.

---

## 3. Surgical Changes

**Touch only what the request requires.**

When editing existing code:
- [ ] Don't improve adjacent code, comments, or formatting.
- [ ] Don't refactor working code.
- [ ] Match existing style unconditionally.
- [ ] Check git history before reintroducing previously reverted code.
- [ ] Spot unrelated dead code? **Note it. Don't touch it.**

When your changes create orphans:
- [ ] Remove imports/variables/functions **your changes** made unused.
- [ ] Leave pre-existing dead code unless explicitly asked to remove.

**Test:** Every changed line traces directly to the user's request. If not, revert it.

> **Example:**
> ❌ *Bad:* Fixing a typo in line 12, but also reformatting the indentation of lines 1-50 to match PEP8.
> ✅ *Good:* Modifying exactly one string on line 12. Leaving the messy indentation exactly as found.

### Scope Escalation Protocol

If implementing the request requires touching >3 unrelated modules
or >~100 lines beyond the obvious scope:

1. Stop.
2. Report: what you found, why scope is larger than expected.
3. Ask: proceed, narrow scope, or redesign?

---

## 4. Goal-Driven Execution

**No task is done until success criteria pass.**

- [ ] Transform every task into a verifiable goal.
- [ ] Loop on each step until its verify check passes before moving on.

| Request | Verifiable Goal |
|---|---|
| "Add validation" | Write tests for invalid inputs → make them pass |
| "Fix the bug" | Write test reproducing bug → make it pass |
| "Refactor X" | Tests pass before → tests pass after, no behavior change |

For multi-step tasks, state plan upfront:

```text
1. [Step] → verify: [exact check]
2. [Step] → verify: [exact check]
```

> **Example:**
> ❌ *Bad:* "I updated the database schema. Let me know if it works!"
> ✅ *Good:* "1. Update schema → verify: run `migration_test.py` and ensure the exit code is 0."

### Revert Protocol

If a step's verify check fails and the fix would violate Rules 1–3:

1. Revert the step.
2. Report failure + root cause.
3. Ask before retrying with wider scope.

---

## Anti-Patterns (quick ref)

| Anti-Pattern | Correct Behavior |
|---|---|
| Pick silently between interpretations | List options, ask |
| Add "nice to have" features | Implement only what was asked |
| Refactor working adjacent code | Leave it; note if broken |
| Delete pre-existing dead code | Note it; don't touch |
| Mark done without verification | Run verify check first |
| Expand scope silently | Trigger Scope Escalation Protocol |
