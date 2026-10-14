# Implementation Plan: Native n8n text

**Branch**: `002-n8n-text` | **Date**: 2026-10-14 | **Spec**: [spec.md](spec.md)

## Technical Context
Python 3.12 / existing FastAPI, Pydantic, Playwright and unittest. n8n Docker 2.41.4; native OpenAI node 1.8 and 2.3. Single host browser/worker. Existing private key/profile selected by user, stored only in ignored .env. No new service/database/dependency.

## Constitution Check
Native acceptance is mandatory; mocks do not substitute for it. Keep protocol/UI/input boundaries. Complete measurement is not assumed from partial metadata. Inherited history/media limits remain scoped out and documented.

## Design and sequence
1. Verify installed credential/request contracts and observe the actual UI/generation metadata.
2. Write failing native JSON default, typed-output, failure/auth/readiness and usage regressions.
3. Add the smallest shared generation/error boundary for existing adapters; normalize observed metadata without fabricating counts. Keep browser actions in their existing module.
4. Correct prompt/model readiness, protect diagnostic routes and stop logging prompt excerpts.
5. Run focused/full tests. Start local gateway, import uniquely named inactive native test workflows and a private credential, execute through actual n8n nodes, retain sanitized fixtures/evidence.
6. Review/converge, regression checks, PR, merge/tag after native acceptance.

## Storage and privacy
Private .env/runtime captures/temporary credentials only. Sanitized n8n workflow exports contain credential placeholders, not actual IDs or keys. Request telemetry stores counts/provenance/outcomes, not raw prompts or authentication material. Session ledger is not implemented here.

## Deferred work
History isolation, image validation/lifecycle, files/PDF, tools, dynamic model catalog and complete Responses streaming. If native text is blocked by login or missing UI capability, record it precisely; do not label the feature complete.
