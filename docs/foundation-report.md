# Foundation report

Date: 2026-10-14. Virel AI was derived from the cleaned AI Studio copy and retains original LICENSE attribution.

## Retained and changed

Retained active app/login/package/routes/tests/dependencies/Docker files. Renamed imports from `msemax` to `virel`, public branding to Virel AI and gateway settings to `VIREL_API_KEY`, `VIREL_RATE_LIMIT`, `VIREL_MAX_CONCURRENT`. Runtime profile/session/uploads share project-root paths. Generation behavior was preserved.

Private `.env`, account profiles, old uploads, recordings, screenshots, caches and machine-specific launchers were not copied. The original profile remains available. The user later authorized its reuse after closing the old instance. No private profile is committed.

The earlier cleanup removed 131 files totaling 23,786,663 bytes; see the [inventory](cleanup-inventory.md). Recovery data lives outside this repository and contains private settings.

## Verification

17 offline tests cover auth, validation, Chat JSON/SSE, busy admission, Responses/alias, legacy completions, health/catalog, prompt/image conversion, isolated Chromium DOM extraction and paths from a different working directory. A path mutation was caught and restored. Foundation and branding PR checks passed on GitHub.

HTML/RTL formatting originally verified during foundation was removed at the user's request. All maintained public documentation now uses ordinary English Markdown.

## Inherited gaps

| Gap | Planned stage |
|---|---|
| Browser failures may become success responses; weak readiness; unprotected diagnostics | 002 |
| Dropped assistant history and shared continuous chat | 003 |
| Unrestricted image URL/local-file inputs and missing cleanup | 004 |
| Partial Responses/files and inaccurate usage | 002 / 005 |
| Static catalog and model selection not strictly verified | 007 |
| Missing native client tools/media generation | Dedicated capability stages |
| Custom Responses SSE and incomplete cancellation | 013 / client stages |

The structure supports incremental adapters. Website changes, account limits and model capabilities remain real constraints. Offline tests are not live provider/client certification.

## Stage 002 update

The inherited-gap table records the foundation baseline. Stage 002 repaired default JSON, text-only Responses output, reported request usage, readiness/model verification and protected diagnostics. It replaced the static catalog with the verified current selection. Native n8n Chat and Responses raw/simplified text passed; [stage evidence](../specs/002-n8n-text/evidence.md). History, media safety, tools and full streaming remain deferred.
