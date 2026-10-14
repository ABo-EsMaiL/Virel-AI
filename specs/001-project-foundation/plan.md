# Implementation Plan: Project foundation

**Branch**: `001-project-foundation` | **Date**: 2026-10-14 | **Spec**: [spec.md](spec.md)

Copy active Python/FastAPI/Playwright source into an independent package; retain module boundaries, generation behavior and dependency versions. Root configuration and runtime storage at the project directory. Keep one worker for the single browser.

## Sequence

1. Inventory active files; exclude private/generated data.
2. Update imports, configuration, health, Docker and tests.
3. Initialize official Spec Kit, constitution and feature branch.
4. Add reference/roadmap/client docs and GitHub checks.
5. Verify offline contracts, paths, source differences, links and preview; review, commit, merge and tag.

## Validation

17 offline checks; mutation of profile-relative logic caught; AST parse; Markdown links/render; tracked-private-file check. Foundation and branding checks passed on GitHub. No Google account/client calls were part of foundation verification.

## Historical formatting

The initial Arabic RTL documentation was later replaced by ordinary English Markdown at the user's request. No empty future modules or new runtime abstraction were created.
