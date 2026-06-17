# Changelog

## v2.0.1 (2026-05-24)
- **Environment Check**: Added Step 1a to Phase 1 Discovery
- **Output filter**: Added CODE_REVIEW_FILTER env var
- **DA ordering fixed**: Phase 3 order is now Synthesis → DA → Roadmap; DA-ESCALATION findings feed into roadmap
- **SKILL_DIR injection**: karpathy-guidelines.md now resolved via absolute SKILL_DIR injected by orchestrator at spawn time
- **RESOLVED_CACHE_DIR**: cache path resolved once in Phase 1 Step 3, used throughout Phases 3-4 (fixes temp-dir fallback propagation)
- **EST-CONFLICT logging**: Phase 4b reconciliation now logs conflicts and notifies user in fix plan footer
- **Token estimates corrected**: Pre-flight now shows 15K–80K input per agent (was ~5K)
- **Phase 4f**: LOW-ACTIVITY domains now skip agent spawn; previous scores carry forward
- **install.py**: gitignore warning on local fallback install
- **pyproject.toml**: corrected build-backend to setuptools.build_meta
- **CI**: removed invalid update-pip parameter from setup-python action
- **Tests**: dead regex fixed, temp-dir fallback assertion corrected, gitignore warning tests added

## v2.0.0 (2026-05-23)
- **Env vars**: Added `CODE_REVIEW_EFFORT`, `CODE_REVIEW_TIMEOUT_SEC`, `CODE_REVIEW_MAX_FILES`, `CODE_REVIEW_CACHE_DIR`, `CODE_REVIEW_BASELINE`, `CODE_REVIEW_AGENTS`, `CODE_REVIEW_STATUS_INTERVAL`
- **New sections**: Checkpointing, Quick Mode, Sample Output, Changelog
- **Dynamic effort**: Removed hardcoded `model: opus`, effort reads from `CODE_REVIEW_EFFORT` env var
- **Stricter thresholds**: Agent failure threshold changed from `<8 agents` / `≤6` to `75%` (full mode) / `66%` (quick mode)
- **Post-fix verification**: Added Phase 4g to verify fixes didn't introduce issues
- **Cache dir**: All hardcoded `$TEMP_DIR` replaced with `${CODE_REVIEW_CACHE_DIR:-.code-review-cache}`
- **Task invocation example**: Added concrete Task tool usage example in Orchestration
- **Status checkpoint**: Periodic progress logging via `CODE_REVIEW_STATUS_INTERVAL`
- **Cross-platform**: Cache verification fallback to OS temp directories
- **Tests**: Synced compliance and integration tests to match v2.0.0
