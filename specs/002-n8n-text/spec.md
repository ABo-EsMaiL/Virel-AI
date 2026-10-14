# Feature Specification: Native n8n text

**Branch**: `002-n8n-text` | **Created**: 2026-10-14 | **Status**: In progress

## User Scenarios & Testing

### US1 — Native credentials and text (P1)
Configure an ordinary OpenAI credential with the gateway URL/key and run a native text node. Existing workflows/credentials remain intact.

Acceptance: credential catalog request succeeds with the correct key and fails with the wrong key; a native Chat Completion returns the known fixture in raw and simplified output without Code/HTTP replacement nodes. Missing `stream` means JSON. Explicit SSE remains available.

### US2 — Current n8n text operation (P1)
Use the installed current node's text Model Response operation as a normal user.

Acceptance: text-only Responses input returns a completed assistant output with the content type the actual node expects, in raw/simplified output. File/tool/history features remain later stages; their unsupported requests fail explicitly.

### US3 — Honest failure and readiness (P1)
Client-visible failures remain failures, not successful error text.

Acceptance: auth 401, bad input 400/422, busy 429, not-ready/model unavailable 503, upstream failure 502 and timeout 504 have a structured error. A late stream failure emits an error, not successful termination. Diagnostics and shutdown require the configured key. Readiness requires an accessible prompt UI, not just a started browser.

### US4 — Honest request usage (P1)
View input/output/total when the current generation exposes trustworthy metadata. Never receive fabricated word-based counts.

Acceptance: metadata is correlated to one attempt and reset before the next; valid source counts map correctly; partial/stale/inconsistent/missing counts remain unavailable with explicit provenance. JSON and existing SSE retain their protocol shapes. No Google API key/SDK/counter request is introduced. Session aggregation is stage 003.

## Requirements

- FR-001: Native OpenAI credential/model lookup and text operations on installed n8n work without glue nodes.
- FR-002: Text adapters default to non-streaming and return native-readable output.
- FR-003: Map failure states to meaningful HTTP/errors and preserve admission behavior.
- FR-004: Verify prompt readiness and selected default model before generation; record actual UI evidence.
- FR-005: Protect sensitive diagnostic/shutdown routes with existing gateway auth.
- FR-006: Replace word-count usage with observed counts or unavailable; preserve provenance and request identity.
- FR-007: Add focused regressions, preserve foundation checks and publish sanitized native fixtures/evidence.
- FR-008: Use the user-authorized existing profile/key locally; keep credentials and captures private.

## Success Criteria

- SC-001: All foundation checks plus new contract/error/usage tests pass.
- SC-002: Native node outputs contain the known live answer, including current Responses text.
- SC-003: Failed generation never produces successful JSON or normal stream completion.
- SC-004: Counts are attributable to the current attempt; unavailable counts are not numeric zeros or words.
- SC-005: Git/fixtures contain no real key, profile, session or private execution capture.

## Scope and edge cases

Single worker and one request at a time. Text-only, no tools/files/bulk histories. Installed node versions are tested individually, not certified collectively. Cancellation/retries and session totals require later stages; stream failure signaling is repaired here while full protocol streaming remains stage 013. Website login/model changes produce readiness errors rather than selecting silently.
