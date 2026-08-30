# Tasks: R9 h CC0 Animation Overlay Plan

Status: Complete
Updated: 2026-08-30
Depends on: requirements.md, design.md

## Rules

- This task owns only the five files listed in the design file plan.
- It must not touch candidate `h`, R3, R8 development evidence, root
  authorities, services, GPUs, runtime ports, or generated Unreal assets.
- Keep this branch in its isolated worktree and stage only named files.

## Task List

- [x] T1. Audit and pin the current authority graph
  - Files: requirements.md, design.md
  - Depends on: none
  - Requirements: R1, R2, R3, R4
  - Validation: current file hashes, receipt schemas, 23-package inventory, and
    nine-package executor contract independently observed

- [x] T2. Approve the closed zero-write contract
  - Files: requirements.md, design.md, tasks.md
  - Depends on: T1
  - Requirements: R1-R8
  - Validation: SDD discovery/requirements/design/task checklists reviewed;
    prior user approval and explicit continuation recorded

- [x] T3. Implement the deterministic planner
  - Files: plan_hssd_r2_cc0_animation_overlay.py
  - Depends on: T2
  - Requirements: R1-R7
  - Validation: focused unit tests and production dry-plan output

- [x] T4. Add adversarial regression tests
  - Files: test_vista_playable_home_hssd_r2_cc0_animation_overlay_plan.py
  - Depends on: T3
  - Requirements: R1-R7
  - Validation: parent/package/authority drift, overlap, traversal, case-fold,
    deterministic output, closed host/runtime SHA lineage, exact additive
    project projection, no-override CLI, and subprocess zero-write cases pass

- [x] T5. Run integration checks and independent review
  - Files: all owned files
  - Depends on: T3, T4
  - Requirements: R1-R8
  - Validation: focused pytest plus existing animation regressions, Ruff format
    and lint, py_compile, `git diff --check`, and read-only reviewer PASS
  - Result: 43 focused and 226 related regression tests passed; third-round
    read-only review returned PASS with no remaining blocker

- [x] T6. Commit, push, and integrate
  - Files: all owned files
  - Depends on: T5
  - Requirements: R5, R6, R8
  - Validation: feature branch pushed; one logical commit cherry-picked to the
    clean integration branch and pushed; both worktrees clean
  - Result: feature commit `a2598ef0` was pushed and cherry-picked as
    integration commit `4ca32fb2`; the integration checkout repeated all 226
    related regressions successfully before publication

## Notes

- Candidate `h` remains the immutable visual baseline.
- The current expected production result is blocked only on fresh root R8
  animation publication and reviewed root BuildPlugin authority.
- A future materializer, Unreal run, or human-motion acceptance is a separate
  approved task and must not be inferred from completion of this plan.
