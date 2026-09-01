# Tasks: VISTA Action World R1

Status: In progress
Updated: 2026-09-01
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
    now participate in a 45-placement whole-home build with 30 living-room
    placements. A fresh Blender 4.5.8 smoke build closes placement, protected
    clearance, staticization, alpha and retained-output gates. Eye-level close-up
    review and visible-vs-semantic support/seat reconciliation remain open, so
    this presentation milestone is intentionally not checked.

- [ ] T8. Correct architecture material resolution and metric UV
  - Files: Blender config/build/materials/architecture modules and tests
  - Depends on: T7
  - Requirements: R7, R9
  - Validation: 2K default, 1024 texels/metre metric UV proof, 4K retained hero
    materials, nonblank headless renders and UE texture/material inspection
  - Progress: the forge now defaults to 2K, generates production textures through
    a bounded NumPy path, preserves the historical 64 px smoke, applies one-metre
    metric box UVs to all 211 project components and fail-closed validates every
    component receipt and every GLB primitive UV0. A complete 2K scene forge and
    Unreal texture/material observation remain open.

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
  - Progress: the exact 26-model/60-placement HSSD source now has a deterministic
    R2 transform layer. It reduces protected portal assignments from 10 to 0,
    collision-blocking overlap pairs from 1 to 0 and semantic-proxy alignment
    violations from 2 to 0 while retaining all six rooms. A fresh private
    Blender 4.5.8 attempt `hssd-six-room-scene-r5-20260830t030529` produced a
    13,380,140-byte review GLB, 14,580,958-byte source blend and two nonblank
    1920x1080 renders; result digest
    `b6471bc4be1aa510d6fbd5909b6120a8153c26befdef778133217f85529a5965`
    remains `assembled_rendered_review_pending` and `accepted=false`. The faucet and
    ladder remain two hard support outliers, all 18 wall fixtures remain without
    fixture authority and 20 secondary collision candidates still require UE
    receipts. The first isolated UE 5.7 import remains permanently quarantined
    after seven assets because a no-op transmission extension made Interchange
    select Transmission over ClearCoat and left the coffee-table clear-coat
    texture unbound. One washer material has real transmission plus real
    clear-coat and remains an explicit full-fidelity blocker pending a custom
    material bridge. The new Blender views verify composition, not GTA-level
    fidelity, playable collision or Unreal runtime.

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
  - Progress: the local UE 5.7.3 MetaHuman Character plugin, 29 presets, native
    retarget rigs, UEFN locomotion set and Manny/Quinn fallback are inventoried.
    The Vivian provider now has a closed byte-pinned contract, zero-write-first
    materializer and a fail-closed runtime visual bridge. A real UE 5.7.3
    lifecycle smoke verifies the effective optimized/high legacy pipeline while
    performing no cloud, build or save calls. The bridge compiles for UnrealEditor
    Development plus UnrealGame Development/Shipping and preserves Manny with
    `photoreal_character_unavailable` until every visual component is ready. Epic
    device authorization, the assembled candidate, component/package receipts,
    retarget evidence and player-eye UE acceptance remain open.
    SimWorld Human_Avatar motion reuse is license-blocked.

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

- [ ] T15. Deliver the first player/agent action-event vertical slice
  - Files: player character/HUD/input, shared executor and event bridge, action
    catalog/EventSpec/TCP parity, articulated fridge actor/composer, focused tests
  - Depends on: T3-T5, T9, T11, T13 as narrowed to the selected slice
  - Requirements: R2-R5, R9, R11-R13
  - Selected actions: pickup, place, drop, open, close and inspect
  - Validation: a YCB mug reaches the hand only at pickup contact and reaches a
    support only at place release; the visible fridge leaf moves only after the
    handle contact signal; Inspect has an explicit key, camera/card feedback and
    exit; every success records one matching VISTA interaction while failures and
    rollbacks record zero; Sunshine human playtest passes in a fresh run
  - Rollout: preserve the current City Sample R6 service as rollback and launch a
    separately named candidate service only after offline and UE gates pass

- [ ] T16. Integrate transactional seat/posture actions
  - Files: seat/posture authorities, shared executor, animation adapter,
    player/NPC/TCP/Event adapters and focused UE/Python proofs
  - Depends on: T3-T5, T13 as narrowed to the approved R15 CC0 posture clips
  - Requirements: R2-R5, R11-R13
  - Selected actions: sit, authoritative seated idle and stand
  - Validation: occupancy commits only on `vista_sit_completed`; vacancy commits
    only on `vista_stand_completed`; post-contact failure restores the exact
    standing or seated snapshot; a terminal receipt and session generation
    finalize atomically; seated movement is gated while camera look remains
    available; player, NPC and typed TCP use the shared executor
  - Progress: source integration, 71 focused Python tests, a fresh UE 5.7.3
    Editor/Game/Shipping plugin build and the NullRHI automation test
    `VISTA.PlayableHome.SeatPosture.ActionExecutorIntegration` pass. Composition
    of the four semantic seats, a fresh package and a Sunshine human playtest
    remain open, so this task is intentionally not checked.

- [ ] T17. Integrate one transactional two-target Pour action
  - Files: pickup/liquid receiver authorities, shared semantic executor,
    animation adapter, player/NPC/TCP adapters and focused UE/Python proofs
  - Depends on: T3-T5, T11, T13 as narrowed to the approved R15 CC0 Pour clip
  - Requirements: R2-R5, R9, R11-R13
  - Selected action: pour from the exact held source into one exact receiver
  - Validation: source and receiver reserve as one tuple; the approved contact
    signal commits one deterministic liquid transfer and zero direct rigid-body
    mutations; parent-derived world pose during actor alignment is distinguished
    from item mutation; post-contact failure restores both liquids, requester
    transform and the exact held-item snapshot; destruction and retry release
    both halves; player, generic NPC queue and typed TCP use the shared executor
  - Progress: source integration and the NullRHI automation tests
    `VISTA.PlayableHome.Pour.ActionExecutorIntegration` and
    `VISTA.PlayableHome.PourTransactionR1.AtomicTwoTargetMutation` pass. EventSpec
    v3 deliberately remains closed to Pour pending a separately versioned public
    schema. Scene composition, a fresh package and Sunshine human playtest remain
    open, so this task is intentionally not checked.

## Current Iteration

- Completed: T2 commanded-idle baseline; the current 698-test tool suite plus
  120 subtests pass without touching the live package.
- Completed: T3 adds an exact-key `npc_cancel` operation, appended canceled
  status, exactly-once/reentrant-safe terminalization, atomic callback handling
  and a post-cancel Idle snapshot. Focused contracts pass; packaged behavioral
  evidence remains part of T14.
- Completed in source: T7 now plans 45 purposeful placements, 30 in the living
  room, while retaining exactly 20 CC0 models plus two retained 4K materials.
- Completed in source: T8 now has a 2K production default, honest effective vs
  design-minimum texel-density receipts, metric UV generation and GLB-level UV
  evidence gates. Full-scene 2K and UE observation remain acceptance work.
- Active next slice (2026-09-01 user priority): T15 closes player-visible
  pickup/place/drop, articulated fridge open/close and explicit Inspect before
  further presentation-only character or material work. The functional CC0
  action authority and the Epic/City Sample human-operated visual lane remain
  separately labeled; neither is promoted as dataset/VLM evidence without its
  own acceptance receipt.
- Completed in source and offline UE automation: T16 wires the seat/posture
  authority through player, NPC, animation, TCP, VISTA-event reset and the shared
  action ledger. Sit/stand now compensate exact retained snapshots when terminal
  finalization fails, and pickup/place/drop use the same game-thread atomic
  terminal finalizer. This is not yet a packaged or Sunshine-accepted demo.
- Completed in source and offline UE automation: T17 wires a two-target Pour
  transaction through the shared executor, player interaction, generic NPC
  queue and typed TCP. The exact source/receiver pair is signed, both liquid
  states roll back together and UE 5.7 held-item collision/lifecycle regressions
  are closed. EventSpec v3 remains fail-closed; no Pour receiver has yet been
  composed into or human-tested in the live package.
- Golden Room R2 smoke evidence: append-only accepted forge
  `golden-room-r2-smoke-20260827T212250Z` contains 45 placements, 40 external
  dressing instances, 211 components and seven GLBs. All 424 vertical-slice
  primitives and 63 joined-UE-bundle primitives retain valid UV0; the three
  room review GLBs do as well, and all 211 project component UV receipts bind
  back to the manifest. The retained-output gate passes. Its receipt remains
  `smoke_only`, `accepted_as_r2_visual_evidence=false`; the
  overview is diagnostic evidence, not a GTA-quality acceptance image.
- Golden Room R2 player-eye rejection: the first 1920x1080 eye-level render
  proved that real CC0 PBR props alone do not close the requested fidelity bar;
  the procedural sofa and wall/exposure treatment remain visibly blockout. The
  other two renders were stopped, and the partial output is retained only as
  rejected evidence under `golden-room-r2-player-eye-20260828T102000Z`.
- HSSD R1 source contract: 26 exact private-research HSSD models and 60
  unassembled plan placements (ten per room across six rooms) are byte-pinned.
  Catalog name, WordNet/category metadata and multi-object state are sealed but
  visual review remains pending. A real Blender 4.5.8 execution produced and
  revalidated 26 normalized PBR GLBs plus 26 receipts under the private external
  R5 run `hssd-private-research-r5-20260828t040000z`; the result intentionally says
  `scene_assembly_status=plan_only_not_assembled` and is not accepted scene
  evidence. Static visual use is allowed only under CC-BY-NC-4.0; fridge, desk,
  nightstand, wardrobe and stove articulation remain explicitly pending.
- HSSD six-room R2 placement evidence: external attempt
  `hssd-six-room-scene-r5-20260830t030529` imports each of the 26 prototypes once
  and emits 60 linked instances. The review GLB has 427,783 triangles, 100 PBR
  materials and 82 base/normal/ORM texture-slot groups, with no exported camera,
  light, prototype or proxy markers. Visual inspection shows a coherent,
  nonblack living-room close-up and all six room shells, but also confirms sparse
  dressing, bare architecture, no human character and insufficient close-range
  texture/material fidelity. It is useful composition evidence, not GTA-quality
  acceptance.
- Runtime/GPU ownership: none; current live package remains untouched.

## Notes

- The 10 authored experimental montages remain useful technical evidence, but
  door-as-pickup, lift-foot-as-jump, brace-as-heavy-pickup, non-physical drag,
  0.033 second look-at and unaligned fall/recover are not semantic acceptance.
- The retained CC0 set is ready for rebuild, not an accepted current UE
  presentation package.
- HSSD is research-only and staticized by the current forge; articulated state is
  owned by UE semantic actors.
