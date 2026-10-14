# Feature Specification: Project foundation

**Branch**: `001-project-foundation` | **Created**: 2026-10-14 | **Status**: Delivered

## User Scenarios & Testing

### US1 — Independent source (P1)
Run the active application without depending on old source files. Imports, config, Docker and tests use the new package. Private runtime is not copied or committed.

### US2 — Understand and navigate (P1)
Find module ownership, request flow, input examples, cleanup evidence and the next stage from README. The originally requested RTL preview was verified, then explicitly superseded by ordinary Markdown and English public documentation.

### US3 — Incremental versioned work (P2)
Use official Spec Kit, constitution, feature branch, tests and release tags. Distinguish offline evidence from live client certification.

## Requirements

- FR-001: Retain active source and LICENSE attribution; exclude private/generated data.
- FR-002: Rebrand imports/settings/Docker/tests while preserving generation behavior.
- FR-003: Root environment/profile/session paths at the project directory.
- FR-004: Document ownership, request/response shapes, cleanup, limits and staged acceptance.
- FR-005: Initialize official Spec Kit, Git history and CI.
- FR-006: Report evidence honestly; do not implement all future stages automatically.

## Success Criteria

- SC-001: 16 inherited offline tests plus one path regression pass.
- SC-002: No private runtime tracked and no old package imports in active source.
- SC-003: Readable preview and valid document links.
- SC-004: Feature artifacts, main history and release tags exist.

## Scope and history

Live Google/client tests and future provider capabilities were outside foundation. The initial private-profile copy was intentionally omitted. Later user decisions authorize profile reuse, Virel AI branding and plain English Markdown; current instructions govern future work.
