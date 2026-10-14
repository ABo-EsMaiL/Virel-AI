# Virel agent instructions

Virel (Visual Interface Relay) exposes client HTTP protocols through an AI Studio browser session. Do not assume a Google API key or a Google SDK is involved.

## Read first

- `tasks/plan.md`: staged roadmap. It is planning, not blanket implementation authorization.
- `tasks/todo.md`: current work. Stage 001 is the foundation; stage 002 is the proposed next feature.
- `docs/architecture.md`: actual ownership and request flow.
- `docs/foundation-report.md`: inherited limits; never claim client compatibility from offline tests.
- `.specify/memory/constitution.md`: mandatory project principles.

## Ownership

Protocol shapes: `virel/routes/` and `schemas.py`. Prompt/media conversion: `messages.py`.
Browser lifecycle/UI actions: `browser.py`. DOM extraction JS: `dom.py`.
Shared process state: `runtime.py`. Environment/paths: `config.py`. Auth: `auth.py`.
Keep `app.py` a launcher. Use one process/worker for the current single browser design.

Do not create empty future feature modules. Add a boundary when an implemented feature needs it. Preserve behavior when moving code. Native clients must work without custom Code/HTTP nodes being counted as compatibility.

## Feature workflow

Use the installed official Spec Kit Codex skills: `$speckit-specify`, `$speckit-plan`, `$speckit-tasks`, then `$speckit-implement` for the agreed feature. Run `$speckit-converge` and tests before merge. The Git extension creates sequential feature branches; do not create all roadmap branches ahead of time. Feature contracts and evidence live in `specs/<feature>/`; `tasks/` is the high-level index, not a duplicate feature task ledger.

Run `python -m unittest discover -s tests -v`. These are offline HTTP and isolated Chromium DOM tests. An integration passes only after testing the actual client and recording version, operation, request shape, actual UI model, result, and regressions. Never suppress tests to accommodate broken behavior. Record inherited defects separately from intended contracts.

Never commit `.env`, `runtime/`, browser profiles, session data, uploads, private debug captures, or backups. Preserve LICENSE attribution. Use VIREL_API_KEY/VIREL_RATE_LIMIT/VIREL_MAX_CONCURRENT; load .env from project root. Do not migrate private Google profiles automatically or share one running profile with another process.

## Usage accounting

Read `docs/usage.md` before adding usage fields. Prefer request-correlated counts reported by the browser UI or its observed generation response; no Google API/SDK dependency is authorized for counting. Word counts are not token counts. Distinguish reported, estimated, and unknown, including per-field provenance for partial observations. Count effective context, preserve request/attempt/session identities, and never report missing cache/thinking/media fields as observed zeros. The current Responses word-count usage is inherited and must be replaced in stage 002; no new counter is implemented by this documentation update.

## Documentation

All authored Arabic Markdown must have an outer `<div class="rtl-doc" dir="rtl" lang="ar" style="direction: rtl; text-align: right;">`, blank lines around it, and a closing `</div>`. English inline technical identifiers use `<code dir="ltr" style="unicode-bidi: isolate;">`; fenced code blocks have an LTR div wrapper. Keep the VS Code markdown.styles setting and docs/rtl.css. Preserve upstream Spec Kit templates/skills in their original language. Write short Egyptian Arabic explanations; distinguish implemented, offline-tested, live-tested, planned, and unavailable.
