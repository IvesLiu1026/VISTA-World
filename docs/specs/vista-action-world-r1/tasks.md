# Tasks: VISTA Action World R1

Status: In progress
Updated: 2026-08-28
Depends on: requirements.md, design.md

## Rules

- One logical commit per independently reviewable slice.
- External binary payloads and generated UE/Blender packages never enter Git.
- Existing live UE, Sunshine and relay processes are read-only until an exact-tip
  candidate has passed offline gates.
- A task is complete only when its mapped behavioral requirements, tests and
  receipts agree; montage playback alone is not action acceptance.

## Task List

- [x] T1. Discover current assets, animations and autonomous behavior
  - Files: this spec and read-only external run evidence
  - Requirements: R1-R12
  - Validation: source inspection, live read-only `npc_status`, provider/license
    inventory and official documentation review

- [x] T2. Make every agent commanded-idle by default
  - Files: NPC character/controller, composition commandlet, focused tests/docs
  - Depends on: T1
  - Requirements: R1, R2, R12
  - Validation: empty queue has clean Idle/zero velocity, no synthesized patrol,
    composer serializes false, full Python suite

- [x] T3. Add explicit cancel and terminal idle receipts
  - Files: runtime subsystem, TCP adapter, controller/types and tests
  - Depends on: T2
  - Requirements: R1, R2, R11
  - Validation: cancel/preempt terminalizes once, active motion stops, last receipt
    persists while current state is clean Idle

- [ ] T4. Define the VISTA indoor ActionCatalog
  - Files: new schema/catalog, EventSpec schema/compiler and contract tests
  - Depends on: T1
  - Requirements: R2, R3, R9
  - Validation: closed schema, real VISTA aliases, transport/EventSpec parity,
    placeholder clips marked rejected rather than ready
  - Progress: the closed 34-action catalog, exact aliases, readiness states and
    fail-closed validator exist. EventSpec/TCP integration and package-bound
    acceptance evidence remain open, so this task is intentionally not checked.

- [ ] T5. Implement shared transactional pickup/place
  - Files: shared executor/receipt component, controller/player adapters and tests
  - Depends on: T3, T4
  - Requirements: R2-R5, R11
  - Validation: approach -> align -> right-hand contact -> pickup -> navigate ->
    place -> receipt -> Idle; interruption restores pre-contact state

- [ ] T6. Add Motion Warping, hand IK and foot IK acceptance
  - Files: plugin dependencies, authoring/inspection scripts, action variants/tests
  - Depends on: T5
  - Requirements: R3-R5
  - Validation: root/hand/foot thresholds are measured from a packaged run; no
    foot slide or target penetration at accepted contacts

- [ ] T7. Build Golden Living Room R1 without new downloads
  - Files: existing visual/acquisition/placement manifests and Blender forge tests
  - Depends on: T1
  - Requirements: R6, R7, R9
  - Validation: enable retained ceiling lamp and throw pillows, reach 30-45
    purposeful living-room instances, preserve navigation/interaction clearance
  - Progress: all retained 20 CC0 models plus two retained 4K material sources
    now participate in a 30-placement whole-home build (15 living-room
    placements). A fresh Blender 4.5.8 smoke build closes staticization and alpha
    gates, but the close-up review and 30-45 living-room target remain open.

- [ ] T8. Correct architecture material resolution and metric UV
  - Files: Blender config/build/materials/architecture modules and tests
  - Depends on: T7
  - Requirements: R7, R9
  - Validation: 2K default, 1024 texels/metre metric UV proof, 4K retained hero
    materials, nonblank headless renders and UE texture/material inspection

- [ ] T9. Introduce AssetDescriptor/Placement/Articulation contracts
  - Files: new V2 schemas, adapters, manifests and contract tests
  - Depends on: T7
  - Requirements: R6, R7, R9, R12
  - Validation: source/license/hash, UV/PBR, collision, sockets and articulation
    metadata fail closed and cross-reference exactly

- [ ] T10. Finish all six rooms with private-research HSSD bindings
  - Files: HSSD provider plans/receipts and six-room placement manifests
  - Depends on: T8, T9
  - Requirements: R6, R7, R9
  - Validation: >=8 purposeful items/room, >=60 total, exact local HSSD revision,
    no public payload, walkability and semantic hero coverage

- [ ] T11. Add a YCB interaction kit
  - Files: pinned acquisition/attribution manifests, pickup physics/socket profiles
  - Depends on: T5, T9
  - Requirements: R3-R7, R9
  - Validation: mug/bowl/food/tool pickup, mass/collision, hand contact, placement
    and attribution receipts

- [ ] T12. Assemble and retarget one photoreal MetaHuman provider
  - Files: provider spec, disposable-project authoring/retarget scripts and receipts
  - Depends on: T4, T6, T9
  - Requirements: R3, R4, R8-R11
  - Validation: entitlement, assembled assets, skeleton/LOD/material digests,
    action coverage, packaged render and performance tier

- [ ] T13. Replace placeholder motions with semantic variants
  - Files: action catalog, animation authoring sources/recipes and UE content receipts
  - Depends on: T4, T6
  - Requirements: R3-R5, R8, R11
  - Validation: real turn/look, door, sit/stand, brace, drag, step-over, fall and
    recover; each action has world-state effect and visual/contact evidence

- [ ] T14. Package and promote an exact-tip research candidate
  - Files: append-only external run, package/acceptance receipts and runbook update
  - Depends on: T2-T13 as selected for the milestone
  - Requirements: R1-R12
  - Validation: offline/full tests, UE compile/cook/package, no-motion baseline,
    action receipts, six-room visual review, 1080p performance, Moonlight input

## Current Iteration

- Completed: T2 commanded-idle baseline; focused contracts and the full 219-test
  Python suite pass without touching the live package.
- Completed: T3 adds an exact-key `npc_cancel` operation, appended canceled
  status, exactly-once/reentrant-safe terminalization, atomic callback handling
  and a post-cancel Idle snapshot. Focused contracts pass; packaged behavioral
  evidence remains part of T14.
- Active next slices: bind T4 to EventSpec/runtime evidence; expand T7 from 15
  to 30-45 purposeful living-room groups; then complete T8 metric UV and 2K
  production material generation.
- Golden Room smoke evidence: append-only run
  `golden-room-smoke-20260827T203406Z` contains 30 placements, 25 external
  dressing instances, 211 components and seven GLBs. Both retained-output tests
  pass. Its receipt remains `smoke_only`, `accepted_as_r2_visual_evidence=false`;
  the overview is useful but not yet a GTA-quality acceptance image.
- Runtime/GPU ownership: none; current live package remains untouched.

## Notes

- The 10 authored experimental montages remain useful technical evidence, but
  door-as-pickup, lift-foot-as-jump, brace-as-heavy-pickup, non-physical drag,
  0.033 second look-at and unaligned fall/recover are not semantic acceptance.
- The retained CC0 set is ready for rebuild, not an accepted current UE
  presentation package.
- HSSD is research-only and staticized by the current forge; articulated state is
  owned by UE semantic actors.
