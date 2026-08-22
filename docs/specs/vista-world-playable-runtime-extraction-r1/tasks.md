# Tasks: VISTA World Playable Runtime Extraction R1

Status: Draft
Updated: 2026-08-22
Depends on: requirements.md, design.md

## Rules

- Do not edit production source until requirements, design and tasks are approved or
  the user explicitly waives the SDD gate.
- Use the standalone VISTA-World repository as the destination and the pinned
  SimWorld source tree only as read-only extraction input.
- Never bulk-merge the realism branch; stage and review named paths only.
- Each writing worker uses a separate branch/worktree and owns non-overlapping paths.
- Preserve accepted schemas, fixture digests, provenance and rollback evidence.
- Use `uv`, never `pip`; stage named files only; one logical change per commit.
- Do not commit external assets, Unreal/Blender binaries, packages, logs, credentials,
  datasets or generated evidence.
- UE, GPU, external downloads, Sunshine/service changes and administrator permissions
  require their explicit later authorization gates.

## Task List

- [ ] T1. Review and approve extraction requirements, design and tasks
  - Files: `docs/specs/vista-world-playable-runtime-extraction-r1/**`
  - Depends on: none
  - Requirements: R1-R15
  - Validation: user confirms private-research policy, UE 5.7.3 baseline,
    `d80aa78f` source pin, first `mmg_044` slice and execution gates.

- [ ] T2. Create the selected-path extraction ledger
  - Files: `docs/migration/playable-runtime-extraction-r1.md`
  - Depends on: T1
  - Requirements: R1-R3, R9-R11, R15
  - Validation: every retained path has source/destination, blob/tree pin, license,
    dependency disposition, validation profile and rollback reference; unrelated
    branch paths are absent.

- [ ] T3. Extract the VistaPlayableHome Unreal plugin source
  - Files: `unreal_plugins/VistaPlayableHome/**`, focused source tests
  - Depends on: T2
  - Requirements: R1-R6, R8, R11, R15
  - Validation: selected source bytes/history match the ledger; runtime module has
    no SimWorld web/server dependency; plugin manifest and module dependencies are
    closed and UE 5.7.3-targeted.

- [ ] T4. Extract deterministic Blender and Unreal pipelines
  - Files: `tools/blender/vista_playable_home/**`,
    `tools/blender/vista_playable_home_realism/**`,
    `tools/ue/vista_playable_home/**`, selected tests
  - Depends on: T2
  - Requirements: R2-R5, R9, R11, R15
  - Validation: offline plans bind accepted standalone contracts, reject stale or
    SimWorld-only inputs, keep presentation/collision authority separate and retain
    attempt quarantine semantics.

- [ ] T5. Extract packaged runtime and Sunshine planning source
  - Files: `tools/runtime/vista_playable_home/**`, selected tests
  - Depends on: T2
  - Requirements: R1, R3-R4, R8, R11-R12, R15
  - Validation: dry-run/preflight paths are standalone, typed readiness remains
    mandatory, package re-hashing and owned-process/listener checks are retained,
    and no service is changed by tests.

- [ ] T6. Close standalone offline dependency parity
  - Files: selected test/support files and narrow import-path fixes
  - Depends on: T3-T5
  - Requirements: R1-R5, R8-R11, R15
  - Validation: focused contract/compiler/plugin-source/pipeline/runtime tests pass;
    dependency audit finds no Studio server/UI/Postgres/Qdrant requirement; secret,
    binary, large-file and external-payload scans pass.

- [ ] T7. Build and pin the Unreal plugin on UE 5.7.3
  - Files: no generated Git content; append-only build receipts outside Git
  - Depends on: T6 and explicit user authorization
  - Requirements: R3-R6, R8, R11, R15
  - Validation: BuildPlugin/UHT/compiler succeed for required Linux targets; package
    tree, loaded module and toolchain digests are sealed; failed attempts quarantine.

- [ ] T8. Reproduce standalone map and package parity
  - Files: no generated Git content; focused acceptance-source fixes only if required
  - Depends on: T7 and explicit user authorization
  - Requirements: R3-R6, R8-R9, R11-R13, R15
  - Validation: disposable compose/save/reload, Linux package, NullRHI typed READY,
    listener ownership and live renderer observation bind one exact source/content
    revision without SimWorld running.

- [ ] T9. Implement the complete EventSpec outcome evaluator
  - Files: `unreal_plugins/VistaPlayableHome/**`, compiler/runtime condition tests
  - Depends on: T6
  - Requirements: R5, R7-R8, R11, R13
  - Validation: entity-state, entity-room, player-room, interaction and elapsed
    conditions drive deterministic success/failure/timeout; invalid targets fail
    before mutation; reset restores exact baseline and generation.

- [ ] T10. Accept the three-room `mmg_044` gameplay slice
  - Files: focused acceptance tooling and append-only runtime evidence
  - Depends on: T8-T9
  - Requirements: R6-R8, R11, R13
  - Validation: continuous entry/living/kitchen traversal, camera recovery, keys
    pickup/carry/place, door open/close, stove toggle and `mmg_044` success/failure/
    reset pass in one packaged standalone session.

- [ ] T11. Promote the private-research visual slice
  - Files: visual manifests/receipts, Blender/UE presentation source and focused tests
  - Depends on: T8, separate external-asset authorization only if new downloads are needed
  - Requirements: R9, R11, R13, R15
  - Validation: selected CC0/CC BY/HSSD research assets have exact policy receipts;
    three rooms pass material, lighting, camera, collision-authority, fixed-shot and
    human review gates; no default/blockout surface is promoted as finished.

- [ ] T12. Add UE 5.7.3 project-owned animation V1
  - Files: versioned animation contracts/recipes, plugin integration and focused tests
  - Depends on: T7, T10
  - Requirements: R3, R6, R8, R10-R11, R15
  - Validation: locomotion, idle, turn, pickup/drop, door, hand IK and foot IK use
    project-owned paths with skeleton, montage, notify, root-motion and live behavior
    receipts; no UE 5.3 profile is treated as current evidence.

- [ ] T13. Add the `mmg_040` animation-rich event slice
  - Files: versioned animation/event contracts and focused acceptance tooling
  - Depends on: T9, T12
  - Requirements: R7-R10, R13-R15
  - Validation: look-at, brace, drag, lift-foot, pause, fall and recover each pass
    contact/collision/completion/rollback evidence; playable duration is not limited
    to the 12-second source reconstruction.

- [ ] T14. Add native World Agent and optional SimWorld adapters
  - Files: standalone agent/transport contracts and `adapters/simworld-studio/**`
  - Depends on: T9-T10
  - Requirements: R4, R8, R14-R15
  - Validation: natural language compiles to closed plans; fake transport and pinned
    SimWorld compatibility tests pass; caller paths/functions/scripts are rejected;
    standalone runtime remains functional with the adapter absent.

- [ ] T15. Close performance, remote input and six-room scale-out
  - Files: performance/remote acceptance source and append-only evidence pointers
  - Depends on: T10-T14 and explicit runtime/admin authorization
  - Requirements: R6, R9-R13, R15
  - Validation: fixed 60-second packaged traversal records frame/VRAM/streaming
    metrics; all six rooms retain gameplay/event parity; Sunshine video and real
    Moonlight input pass after persistent `/dev/uinput` and `/dev/uhid` access is
    independently approved and configured.

## Planned Ownership Sequence

1. Integrator owns T1-T2.
2. Unreal, pipeline and runtime workers may execute T3-T5 in parallel after the
   ledger freezes paths.
3. Integrator closes T6 before any UE execution.
4. One runtime owner executes T7-T8.
5. Event, visual and animation owners advance T9-T13 with non-overlapping files.
6. Adapter and operations work begins only after standalone gameplay acceptance.

## Authorization Checkpoints

- T1-T6: source/spec work only; no UE/GPU/network/service authorization required.
- T7: exact UE 5.7.3 BuildPlugin/toolchain command requires user authorization.
- T8/T10: disposable UE/package/GPU execution requires user authorization and runtime
  ownership preflight.
- T11: existing local assets need no download; any new network fetch or entitlement
  action requires separate authorization.
- T12-T13: UE content authoring/live animation evidence requires user authorization.
- T15: Sunshine changes and administrator device-policy actions require explicit
  owner/admin authorization.

## Notes

- The selected-path source pin is a tree basis, not permission to cherry-pick only
  its final commit or merge every later commit.
- Accepted SimWorld R1/R2 packages remain rollback evidence until T8/T10 close.
- Scope expansion updates requirements/design before implementation.
