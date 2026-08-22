# FileCortex Roadmap

> Current version: 6.5.3 | Updated: 2026-08-23 | Current verification: 800 passed, Ruff 0 errors

## Delivered in 6.5.3

- [x] Windows config-lock liveness probe replaced with a console-safe Win32 API check (previously sent Ctrl+C to itself).
- [x] Corrupt/out-of-range disk config no longer bricks saves; the file is rewritten from in-memory state.
- [x] Desktop path-collection dialog presets work with Pydantic profile models.
- [x] Case-only renames work on case-insensitive filesystems; ZIP archive members use forward-slash names.
- [x] Global-settings API tolerates null fields; the Web UI guards NaN inputs.
- [x] WebSocket backpressure handles Python 3.10's `concurrent.futures.TimeoutError`; CORS preflight passes through token auth.
- [x] Tree view honors directory-only gitignore rules; exclude patterns are case-faithful on POSIX.
- [x] CLI exits non-zero on failures; CLI/MCP search honors the project's content-size limit; MCP search runs off the event loop.
- [x] Desktop tool execution moved to a background thread (UI no longer freezes).

## Delivered in 6.5.2

### Trust Boundary and Data Integrity

- [x] Registered-workspace containment now resolves real paths and blocks symlink escapes.
- [x] Context generation, token statistics, and path collection require a registered project and validate every requested path.
- [x] Local Web defaults use a localhost origin allowlist; non-loopback binding requires `FCTX_API_TOKEN`.
- [x] Batch rename validates computed targets; archive creation refuses replacement and source/output overlap.
- [x] Large or binary previews cannot enter the text editor; preview and context-menu delete operations capture their target.
- [x] Text saves preserve the detected encoding and file mode.

### Reliability and Resource Control

- [x] Configuration saves use an owner-aware inter-process lock, three-way merge, temporary write, and atomic replacement.
- [x] Batch copy rolls back completed copies on failure; categorization reports failed paths and retains them in staging.
- [x] ZIP extraction validates path safety, member count, member size, total size, compression ratio, and rolls back committed files on failure.
- [x] Content search has a bounded in-flight queue; WebSocket search/tool output applies bounded backpressure and cleanup.
- [x] XML context has a single root node, safe CDATA handling, escaped path attributes, and explicit truncation markers.
- [x] Project settings are validated and persisted as one request.

### Packaging and Verification

- [x] wheel/sdist include `templates`, `static`, and `file_cortex_core.gui`.
- [x] Added regression coverage for external-path rejection, rename traversal, configuration merging, copy rollback, ZIP limits, XML parsing, tag consistency, and frontend race guards.
- [x] Current baseline: 800 passed, Ruff 0 errors, wheel/sdist build verified.

## Next: Phase 1 Usability

- [ ] Recent destinations and named destination presets.
- [ ] Context-aware right-click actions.
- [ ] Detailed operation summary with per-item reasons.
- [ ] Keyboard-first tree, menu, and staging operations; ARIA/focus improvements.
- [ ] First-run onboarding and daily workflow guidance.
- [ ] Local operation history.

## Then: Phase 2 Maintainability and Release Engineering

- [ ] Extract application services from routes and `DataManager`.
- [ ] Split Web and desktop controller modules by feature.
- [ ] Add Windows/macOS CI and a clean-install wheel smoke test.
- [ ] Add Playwright E2E tests for destructive-operation confirmations and async races.
- [ ] Introduce gradual static typing checks for core modules.

## Later: Phase 3 Context Compiler

- [ ] JSON export manifest and deterministic context recipes.
- [ ] Accurate tokenizer and enforceable token budgets.
- [ ] Tree-sitter symbol compression and repository map.
- [ ] Git diff/change-aware context ranking.
- [ ] Secret scan report and export explainability.

## Optional: Phase 4 Local Index and Organization

- [ ] SQLite/FTS5 incremental workspace index.
- [ ] Optional local embeddings and reranking.
- [ ] Optional document parsing and OCR.
- [ ] Rule-first categorization plan, dry-run, approval, audit trail, and undo.

## Historical Milestones

| Version | Date | Release snapshot |
|---|---|---|
| 6.5.3 | 2026-08-23 | Review-driven bugfix round: Windows lock probe, corrupt-config recovery, case-only rename, gitignore/tree parity, CLI exit codes, WS 3.10 compat; 800 passed. |
| 6.5.2 | 2026-08-09 | P0/P1/P2 security, correctness, packaging, and consistency remediation; 786 passed. |
| 6.5.1+ | 2026-07-25 | Frontend event delegation, themes, virtual search results, layout controls, and stabilization. |
| 6.5.1 | 2026-06-15 | Deployment hardening, MCP packaging, path validation, and process handling. |
| 6.5.0 | 2026-06-07 | Core security hardening, test consolidation, CLI search/export, and context limits. |
