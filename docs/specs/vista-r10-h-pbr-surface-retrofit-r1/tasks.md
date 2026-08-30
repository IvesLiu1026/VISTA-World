# Tasks: VISTA R10 h PBR Surface Retrofit R1

Status: In progress; T3-T6 authorized, T7 remains separately gated
Updated: 2026-08-30
Depends on: requirements.md, design.md

## Rules

- This branch owns only the paths listed in the design file plan.
- Candidate `h` and all prior evidence are immutable; future execution is
  append-only.
- No services, GPU, Blender, downloads, AI/VLM review, external binary writes,
  animation authority, or existing production-file edits in this source slice.
- Stage named files only and keep R10 separate from the animation overlay.

## Task List

- [x] T1. Audit the sealed parent and material candidates
  - Files: requirements.md, design.md
  - Depends on: none
  - Requirements: R1-R3, R6, R8
  - Validation: exact h receipt/tree/map pins, nine generic cold-reload rows,
    five replacement UAssets, 4K wool/oak provenance, and protected world
    boundaries independently observed

- [x] T2. Review and approve the R10 contract
  - Files: requirements.md, design.md, tasks.md
  - Depends on: T1
  - Requirements: R1-R8
  - Validation: user approves the exact nine-binding matrix, map-only mutation,
    source ownership, CPU/NullRHI boundary, and human acceptance gate
  - Result: explicitly approved by Ives in Codex on 2026-08-30; no waiver or
    scope change was required

- [x] T3. Add the fixed profile and zero-write preflight
  - Files: profile, materializer, host tests
  - Depends on: T2
  - Requirements: R1-R3, R5, R6, R8
  - Validation: deterministic no-write output, exact five package pins and nine
    rows, no caller overrides, parent drift/collision/case-fold tests
  - Result: fixed five-package/nine-binding profile, independent host literal
    authority, closed CLI, and zero-write planning tests implemented

- [x] T4. Implement the narrow UE commandlet and host publication
  - Files: materializer, commandlet, commandlet tests
  - Depends on: T3
  - Requirements: R2-R6
  - Validation: exact nine rebinds, save/cold reload, protected projections,
    map-only delta, process/log/current-byte closure, negative claims
  - Result: independent UE literal authority, fixed mutation surface,
    save/cold-reload validation, append-only receipts, and terminal
    current-byte/sidecar/log revalidation implemented without executing UE

- [x] T5. Run source integration and independent review
  - Files: all owned files
  - Depends on: T3, T4
  - Requirements: R1-R8
  - Validation: focused and related regressions, Ruff/format/py_compile,
    `git diff --check`, secret/binary scan, and read-only review PASS
  - Result: 64 focused and 668 related tests passed; Ruff, formatting,
    py_compile, JSON, diff, secret, and binary gates passed; independent host
    and commandlet reviewers returned PASS

- [ ] T6. Commit, push, and integrate source
  - Files: all owned files
  - Depends on: T5
  - Requirements: R8
  - Validation: named-file commit, feature branch push, clean integration
    cherry-pick, repeated tests, both worktrees clean

- [ ] T7. Execute one fresh append-only NullRHI candidate
  - Files: Git-external run evidence only
  - Depends on: T5 and explicit execution approval
  - Requirements: R1-R6, R8
  - Validation: UE zero, cold reload, exact nine bindings, one-map delta,
    current-byte validation, all human/GTA claims false

- [ ] T8. Perform coordinated human live review
  - Files: Git-external review evidence only
  - Depends on: T7 and CAR GPU0 release
  - Requirements: R5, R7
  - Validation: R6 checkpoint/rollback, three-room close-ups, UV/normal/tiling,
    controls, portals, pickups, performance, human signature

## Notes

- T2 was explicitly approved by Ives on 2026-08-30. Independent commandlet and
  host publication reviews returned PASS with no remaining T3-T6 source
  blocker.
- The R10 visual slice does not clear either R8 animation-overlay authority
  blocker.
- Passing NullRHI proves structure and provenance only. It does not prove visual
  quality, interaction quality, or GTA-level realism.
