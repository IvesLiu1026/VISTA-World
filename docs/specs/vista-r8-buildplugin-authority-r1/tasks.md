# Tasks: VISTA R8 BuildPlugin Authority R1

Status: Implemented (administrator publication pending)
Updated: 2026-08-30
Depends on: requirements.md, design.md

## Rules

- Work only in the four owned lane paths.
- No sudo/root, authority write, UE, Blender, GPU, network, service, commit, or
  external attempt mutation.
- Keep each implementation task mapped to stable requirement IDs.

## Task List

- [x] T1. Independently inventory and pin attempt C
  - Files: `docs/specs/vista-r8-buildplugin-authority-r1/**`
  - Depends on: none
  - Requirements: R1, R2
  - Validation: independent SHA/count/size/mode walk; no links/special entries;
    critical-file hashes and strict JSON inspected

- [x] T2. Approve the closed authority contract and threat model
  - Files: `docs/specs/vista-r8-buildplugin-authority-r1/**`
  - Depends on: T1
  - Requirements: R1-R7
  - Validation: SDD checklists; inherited approval recorded before code changes

- [x] T3. Implement held-descriptor source audit
  - Files: `tools/admin/vista_r8_buildplugin_authority.py`
  - Depends on: T2
  - Requirements: R1-R3
  - Validation: fake-tree exact audit plus path/type/mode/pin/TOCTOU negatives

- [x] T4. Implement installed-root and fresh publication boundary
  - Files: `tools/admin/vista_r8_buildplugin_authority.py`
  - Depends on: T3
  - Requirements: R4-R6
  - Validation: worktree/non-root refusal; held-FD-only copy; immutable staged
    audit; fsync and no-replace tests

- [x] T5. Add complete focused pure test suite
  - Files: `tools/tests/test_vista_r8_buildplugin_authority.py`
  - Depends on: T3, T4
  - Requirements: R1-R7
  - Validation: focused pytest and negative reproduction tests pass without
    root/external writes or subprocesses that launch UE/Blender

- [x] T6. Document administrator-only trust anchor and handoff
  - Files: `docs/runbooks/vista-r8-buildplugin-authority-r1.md`
  - Depends on: T4
  - Requirements: R4-R6
  - Validation: source SHA/install/publish steps distinguish audit from authority
    creation and list all remaining execution blockers

- [x] T8. Close independent review findings
  - Files: helper, focused tests, requirements/design/tasks, runbook
  - Depends on: T4, T5, T6
  - Requirements: R3-R7
  - Validation: live `/proc/self/exe` binding; `O_NONBLOCK` FIFO race; closed
    audit report; durability-unknown and reconciliation negative tests

- [x] T7. Final CPU-only review
  - Files: all owned files
  - Depends on: T5, T6, T8
  - Requirements: R7
  - Validation: focused tests, Ruff, compile/AST check, `git diff --check`, owned
    source and tracked-output status; no generated cache is staged or tracked

## Notes

- Independent attempt C result: projection
  `69153cd676ac35579115d1be9c8ced7d86c70beab7f8adb681ad7b8d373ae48e`,
  241 files, 32 directories, and 51,661,522 bytes.
- This branch produces publisher source only; no authority is created here.
- Independent review changes are covered by 19 focused pure tests; the real
  fixed-source zero-write audit and live `/proc/self/exe` pin both pass.
