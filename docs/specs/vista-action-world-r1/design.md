# Design: VISTA Action World R1

Status: Approved for iterative implementation
Updated: 2026-08-28
Depends on: requirements.md

## Summary

R1 separates three concerns that the experimental package currently mixes:

1. **Action intent and evidence** are owned by a closed, versioned action catalog
   and one shared action executor.
2. **Visual realism** is owned by a deterministic asset/placement pipeline with
   metric materials and provenance-bound provider adapters.
3. **Human appearance** is owned by a replaceable character-provider receipt,
   initially Manny for reproducibility and MetaHuman for the photoreal milestone.

The world is idle by default. VISTA or an agent issues finite actions; no
controller synthesizes ambient patrol. External assets remain outside Git and no
existing live package is edited in place.

## Architecture and Flow

### Command and action flow

```text
NLP / VISTA EventSpec / local input
  -> closed ActionIntent
  -> ActionCatalog lookup + queue preflight
  -> command ticket / idempotency ledger
  -> shared ActionExecutor
       -> approach/navigation
       -> semantic alignment + Motion Warp target
       -> montage variant + hand/foot IK
       -> typed contact notify
       -> transactional object-state commit
       -> typed completion notify + montage end
       -> terminal ActionReceipt
  -> clean Idle
```

`AVistaHomeNpcController` continues to own path following but never creates its
own action. `UVistaAnimationComponent` remains a clip/signal adapter. A new shared
executor becomes the sole owner of physical-action phases, target snapshots,
commit/rollback and receipts. The player and NPC both call it.

### Visual asset flow

```text
VisualProfile + ScenePlacementSpec
  -> explicit provider request (Poly Haven / HSSD / YCB / project / Fab)
  -> local acquisition receipt and exact digest verification
  -> AssetDescriptor (geometry, UV, PBR, collision, sockets, license)
  -> headless Blender normalization / metric UV / modular export
  -> Unreal StaticMesh + MaterialInstance + semantic actor binding
  -> visual, collision, performance and provenance acceptance receipt
```

Golden Living Room is promoted first. Three already acquired but unused Poly
Haven models (ceiling lamp, throw pillows and apple) are zero-download wins. New
public visual acquisitions prefer CC0. HSSD supplies private-research visual
shell candidates for the unfinished rooms; YCB supplies interactive small
objects. Staticized HSSD geometry never provides articulation authority.

### Character-provider flow

```text
CharacterProviderSpec
  -> entitlement/source inventory
  -> assembled character + skeleton/LOD/material digests
  -> IK/retarget validation
  -> action-catalog coverage validation
  -> package-only provider receipt
```

The local UE 5.7.3 distribution includes MetaHuman tooling and core data. The
first MetaHuman is assembled in a disposable project, retargeted to the action
catalog and materialized only into a package run. Manny remains the deterministic
fallback and is never mislabeled as photoreal acceptance.

## Interfaces and Contracts

### ActionDefinition

The catalog entry is data, not caller-supplied code. At minimum it contains:

- stable action ID and accepted VISTA aliases;
- actor/target/affordance and approach requirements;
- accepted hand, foot, height, weight and direction variants;
- root-motion, Motion Warping, hand-IK and foot-IK policies;
- ordered phase/notifies: approach, aligned, contact, release/state-commit,
  completion;
- authoritative state effect and rollback policy;
- timeout and contact/alignment error thresholds;
- animation provider candidates, license/readiness and exact object path after
  project-owned materialization.

### ActionReceipt

Receipts are append-only and bounded in live memory. They include:

- receipt sequence, command ID/generation and action ID/type;
- actor, target, event and world revision identities;
- start/end time, terminal status/code and cancellation/preemption reason;
- actor transform/room before and after;
- target state/transform before contact and after completion;
- held-item state and carrier identity;
- selected animation variant, skeleton, contact/completion signals and timing;
- alignment/IK measurements and rollback outcome.

Read APIs query by `after_sequence` or action ID. Immediate queue responses return
a ticket; they do not imply completion.

### Agent behavior policy

R1 removes synthesized patrol in `StartNextAction`. The NPC character and map
composer serialize auto-start as false for compatibility. A finite scripted
patrol is merely a normal sequence of `navigate_to` actions. Empty-queue cancel
or a dedicated typed cancel operation produces a terminal receipt and stops
movement immediately.

### Asset descriptors and placement

The first Golden Room slice may extend the existing closed visual profile and
placement manifest. The six-room phase introduces versioned AssetDescriptor,
ScenePlacement and Articulation contracts with provider/source identity, license,
per-file hashes, metric bounds/pivot/orientation, UV/texel density, PBR color
spaces, LOD/Nanite, collision/physics, interaction sockets and articulation
parts/joints.

## Data Model and Migration

- Existing `vista.playable-animation-profile/v1` remains an inventory record; it
  is not rewritten to pretend the experimental ten montages are accepted.
- A new action catalog refers to verified animation providers and can mark each
  semantic variant `verified`, `candidate`, `blocked_on_source`,
  `blocked_on_license` or `rejected_placeholder`.
- Existing NPC patrol-room lists remain route metadata during migration, but no
  runtime consumes them implicitly.
- Existing EventSpec files remain valid. The action union is expanded only after
  the catalog validator and executor support the new entries.
- Existing external placement and visual profiles remain readable; V2 contracts
  are introduced alongside them and materialized by explicit adapters.
- Runs and packages remain append-only. No canonical dataset or previous receipt
  is rewritten.

## File Plan

Initial commanded-idle slice:

- `unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome/Public/VistaHomeNpcCharacter.h`
- `unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome/Private/VistaHomeNpcController.cpp`
- `tools/ue/vista_playable_home/compose_home_commandlet.py`
- focused navigation/composition/runtime tests

Action execution slice:

- new action catalog schema/profile under `world_packs/`
- `VistaPlayableHomeTypes.h`, `VistaWorldTcpAdapter.cpp`, EventSpec schema/compiler
- new shared executor component and receipt ledger in the runtime plugin
- animation authoring/inspection tools and focused tests

Golden Living Room slice:

- external placement and acquisition manifests
- Blender realism config, materials, architecture UV and placement modules
- retained-gate, external-forge, profile-binding and UE import tests

Provider/six-room slices:

- new asset/placement/articulation schemas and adapters
- HSSD private-research binding receipts
- YCB interaction kit manifests
- MetaHuman character provider/retarget/package scripts and receipts

## Failure Handling

- Queue validation is atomic; no partial queue begins after a failed preflight.
- Contact state uses a before-snapshot. Interruption, timeout, missing completion
  notify or post-contact failure runs compensating restore and records success or
  failure of rollback.
- A missing provider, hash drift, license mismatch, unsupported NoAI policy,
  absent texture, invalid UV or invalid collider rejects the build.
- A character provider failure falls back to Manny only with an explicit
  unavailability status; it never passes the photoreal gate.
- Live/runtime failure never overwrites the currently sealed package.

## Testing Strategy

- Contract tests validate closed schemas, aliases, cross-references, licenses,
  action effects and provider readiness.
- Source/unit tests cover idle invariant, cancel/preemption, queue idempotency,
  wait/timeout ordering, receipt clearing and state rollback.
- UE editor/package tests validate actual class/skeleton/object paths, montage
  notifies, Motion Warp windows, IK rigs, semantic sockets and material imports.
- Live acceptance verifies no movement before command, explicit pickup/place,
  exact contact state, interruption rollback, final idle, reset and replay.
- Blender gates measure output size, mesh/material counts, metric UV/texel
  density, PBR semantics, bounds, collision clearance and nonblank captures.
- Performance evidence records renderer status and frame-time telemetry at
  1920x1080 without undocumented 30 fps or 70% render caps.

## Rollout and Observability

1. Commit and test commanded-idle behavior without touching the live package.
2. Build the action catalog and transactional pickup/place vertical slice.
3. Rebuild and visually accept Golden Living Room from retained CC0 assets.
4. Package an exact-tip candidate in a new append-only run and smoke it on a new
   loopback port before switching any demo launcher.
5. Add private-research HSSD bindings, YCB interaction objects and MetaHuman as
   independently promotable providers.
6. Expand action coverage only when each action has state, animation and evidence
   closure.

Observable runtime state includes the active ticket, phase, selected animation,
contact/completion signals, target state, receipt sequence and last terminal
receipt. Visual builds expose source/placement digests and performance metrics.

## Tradeoffs

- Removing ambient patrol makes the untouched scene less visually busy but makes
  research runs deterministic and prevents background actions from contaminating
  evidence.
- HSSD accelerates private research realism but cannot be the public distributable
  baseline; CC0/project-authored content remains that baseline.
- MetaHuman gives the strongest human fidelity but has higher LOD/material cost;
  the provider boundary lets research packages select quality tiers.
- Blender/Control Rig generation is reserved for genuine catalog gaps. Reusing a
  wrong montage is cheaper but invalidates the action semantics.
- World Partition, Mass AI and broad PCG are deferred; six indoor rooms benefit
  more from action fidelity, modular instances and deterministic dressing.

## Traceability

- R1 -> commanded-idle controller/composer changes and startup live probe
- R2 -> queue preflight, cancel, ticket/idempotency ledger
- R3 -> ActionDefinition schema/catalog and EventSpec/TCP parity
- R4 -> shared executor, notifies, transaction snapshots and rollback
- R5 -> player interaction migration to shared executor
- R6 -> Golden Room and six-room placement acceptance
- R7 -> metric UV/material generation and UE import gates
- R8 -> character-provider contract and MetaHuman/Manny implementations
- R9 -> provider manifests, digests, licenses and external-only payload policy
- R10 -> 1080p performance capture and quality profiles
- R11 -> package/action/visual acceptance receipts
- R12 -> isolated worktree and append-only run rollout

## Open Questions

- MetaHuman appearance/wardrobe remains an art-direction choice, not an
  architectural blocker.
- A final target GPU quality tier will be selected after the Golden Room frame
  budget is measured at 100% screen percentage.

## Approval

- Requested by: Ives Liu
- Approved by: Ives Liu, via explicit implementation instruction
- Date: 2026-08-28
