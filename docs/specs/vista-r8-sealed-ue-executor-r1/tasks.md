# Tasks: VISTA R8 Sealed UE Executor R1

Status: In progress
Updated: 2026-08-30
Depends on: requirements.md, design.md

## Rules

- Work in `codex/vista-r8-sealed-ue-executor-r1` only.
- No UE, Blender, GPU, root, service or publication execution in this slice.
- Keep existing materializer, commandlet and R5 trusted projection unchanged.
- A worktree invocation may plan but may never become execution authority.
- One logical commit per independently reviewable slice.

## Task List

- [x] T1. Freeze requirements and executor architecture
  - Files: this spec directory
  - Requirements: R1-R8
  - Validation: cross-check approved R8 runbook, R5 proof and root-publisher
    patterns; record the user's phase-gate approval

- [ ] T2. Implement the closed host plan and authority validators
  - Files: `makehuman_cc0_animation_runtime_executor.py`
  - Depends on: T1
  - Requirements: R1, R2, R4
  - Validation: deterministic zero-write dry plan; fake complete authority;
    owner/mode/symlink/inventory/BuildId/digest drift rejection

- [ ] T3. Implement sealed input snapshots and fixed bwrap command
  - Files: executor and focused tests
  - Depends on: T2
  - Requirements: R2-R4, R7
  - Validation: all memfd seals present; exact mount allowlist; no network, GPU,
    display, mutable engine, repository or host output visibility

- [ ] T4. Implement the private sandbox wrapper and archive protocol
  - Files: `makehuman_cc0_animation_runtime_sandbox_wrapper.py`, focused tests
  - Depends on: T2
  - Requirements: R4, R5, R7
  - Validation: fixed UE command; stderr-only diagnostics; exact canonical USTAR;
    malformed/extra/duplicate/link/traversal/zero-exit-without-proof rejection

- [ ] T5. Implement host archive validation and immutable publication
  - Files: executor and focused tests
  - Depends on: T3, T4
  - Requirements: R5-R7
  - Validation: cross-bound receipt/result checks; exact R3-plus-nine delta;
    fresh direct child; O_EXCL/fsync/no-replace; final 0444/0555 modes

- [ ] T6. Close CPU-only adversarial coverage
  - Files: `test_vista_playable_home_makehuman_cc0_animation_runtime_executor.py`
  - Depends on: T2-T5
  - Requirements: R1-R8
  - Validation: focused tests, related R8 regression suite, Ruff and
    `git diff --check`; no production authority or GPU use

- [ ] T7. Independent review and handoff
  - Files: R8 runtime runbook and this task file
  - Depends on: T6
  - Requirements: R8
  - Validation: reviewer APPROVE with no P0/P1; document remaining root pins and
    one-time execution authorization boundary

## Notes

- The 2026-08-30 BuildPlugin C development package succeeded for Editor,
  UnrealGame Development and Shipping. It is user-owned development evidence,
  not yet the root-owned BuildPlugin authority required by R2.
- Real execution remains blocked until independent root provisioning and pin
  review; completing T2-T7 does not silently lift that gate.
