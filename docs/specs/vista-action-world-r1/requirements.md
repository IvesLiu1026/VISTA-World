# Requirements: VISTA Action World R1

Status: Approved for iterative implementation
Updated: 2026-09-01

## Problem

The current playable-home package behaves like a technical demo rather than a
research simulation. Its resident continuously synthesizes patrol actions even
when no VISTA event or agent command is active. Ten UE 5.7.3 montages have been
authored, but several are semantic placeholders (for example door-as-pickup,
lift-foot-as-jump and a 0.033 second look-at), and player interactions still
change object state without animation. Only three of six rooms have a realistic
visual treatment, while the material contract claims a quality level that the
default 512 px forge and non-metric architecture UVs do not deliver.

## Goals

- Make every person idle until an explicit player, VISTA event or agent command
  asks them to act.
- Execute indoor actions as deterministic, observable sequences whose animation
  contact and completion agree with authoritative object state.
- Produce a photoreal, densely dressed six-room research world from licensed,
  provenance-bound assets without committing external payloads to Git.
- Support a photoreal human provider while retaining a reproducible Manny-based
  fallback for contract and package testing.
- Advance through evidence-backed vertical slices instead of labeling
  placeholders as finished animation or GTA-quality content.

## Non-goals

- Building an open city, vehicles, combat, multiplayer or a general GTA clone.
- Adding autonomous social schedules, unprompted wandering or generative NPC
  behavior in R1.
- Redistributing HSSD, Epic, Fab, MetaHuman, SimWorld or other external binary
  payloads through this repository.
- Treating a montage that merely plays as proof that the physical action worked.
- Replacing Unreal's animation and physics systems with unrestricted Blender MCP
  or runtime code execution.

## Assumptions

- The target runtime is Unreal Engine 5.7.3 on Linux and remote interaction is
  through the existing Sunshine/Moonlight display path.
- The retained Poly Haven acquisition contains 22 hash-verified CC0 items
  (20 models and two 4K material sets, 359,529,243 bytes).
- HSSD is available locally for private, non-commercial research under CC BY-NC
  4.0; its payload is never a public-repository dependency.
- UE 5.7.3 has Motion Warping, Pose Search, Control Rig, IK Rig and MetaHuman
  tooling installed. A usable assembled MetaHuman still requires its own
  entitlement and live package receipt.
- This spec's review gate is waived by the user's explicit instruction to begin
  implementation and iterate continuously on 2026-08-28. Contract and package
  acceptance gates are not waived.

## Requirements

### R1. Commanded idle is the baseline

WHEN a world starts or an explicit action queue becomes empty THEN every
non-player agent SHALL stop navigation, clear residual velocity and expose a
clean `Idle` state without synthesizing patrol, wander or follow-up actions.

Acceptance notes:
- Route anchors may remain available as navigation metadata.
- An explicit scripted patrol remains representable as an ordinary finite queue;
  no hidden patrol loop is allowed.
- At 0 and 10 seconds after startup, an untouched actor has the same transform,
  an empty action ID and no queued action.

### R2. Action control is explicit and deterministic

WHEN a player, EventSpec or agent submits an action queue THEN the system SHALL
preflight the complete queue atomically, issue a stable command ticket and run
only the accepted actions in order.

IF a queue is replaced or canceled THEN the active action SHALL produce a
terminal cancellation receipt before the actor returns to idle.

Acceptance notes:
- Command IDs are idempotent within a bounded ledger.
- Missing target, unsupported affordance, unreachable approach, duplicate action
  ID and invalid hand/foot/height parameters fail before execution.
- `wait` completion wins over timeout at their shared boundary.

### R3. VISTA actions have a closed semantic catalog

WHEN an action appears in a VISTA scene or EventSpec THEN it SHALL resolve to a
versioned ActionDefinition containing target policy, approach policy, animation
variant policy, contact phases, state effects, rollback policy and acceptance
thresholds.

IF no verified animation and state-effect implementation exists THEN the action
SHALL fail closed as unsupported instead of using a semantically unrelated clip.

Acceptance notes:
- Initial required primitives are idle, navigate, turn/look, reach, pick up,
  carry, place, open/close, toggle, sit/stand, brace, drag, step/lift foot,
  pause, fall and recover.
- EventSpec and live typed transport expose the same action vocabulary.
- Caller-controlled object paths, class names, scripts and console commands stay
  prohibited.

### R4. Physical actions are animation-state transactions

WHEN an action touches an object THEN execution SHALL follow `Approach -> Align
-> Animate -> ContactCommit -> Complete -> Idle` and mutate authoritative state
only at a typed contact signal.

IF animation is interrupted, times out, misses a required notify or fails after
contact THEN the system SHALL restore the pre-contact actor, carrier and target
state and record that rollback.

Acceptance notes:
- Motion Warping aligns root motion to semantic approach/contact anchors.
- Hand IK and foot IK have measured target/contact errors and no visible ground
  penetration for accepted actions.
- Pickup/place receipts prove `held_by`, `placed_at`, actor and target transforms,
  contact notify and completion notify.

### R5. Player and NPC actions share one executor

WHEN the local player presses an interaction control THEN the request SHALL use
the same ActionDefinition, animation contact, state transaction and receipt path
as a commanded NPC action.

Acceptance notes:
- Player interactions may choose a low-latency presentation, but may not bypass
  validation or mutate state before contact.
- Existing navigation ownership may remain in the controller; physical action
  semantics may not be duplicated between player and NPC code.

### R6. The world is densely and purposefully dressed

WHEN the R1 visual package is accepted THEN all six rooms SHALL use a finished
visual profile, contain at least eight purposeful dressing placements per room,
and contain at least 60 purposeful placements in total.

Acceptance notes:
- The Golden Living Room is the first gate and targets 30-45 purposeful visible
  instances including lighting, soft furnishings, reading/media objects,
  electrical details, window treatment and restrained wear/decal detail.
- Dressing must preserve walkable paths, interaction clearance and semantic hero
  visibility; random clutter alone does not count.
- Repeated non-interactive props use modular instances rather than a single
  joined room mesh where the UE import path supports it.

### R7. Materials and geometry match the declared quality tier

WHEN an architecture or hero asset is accepted THEN its effective texel density,
UV scale, PBR channels, normal convention and material resolution SHALL satisfy
the visual profile rather than only appearing in receipt metadata.

Acceptance notes:
- Architecture defaults to at least 2048 px material generation and 1024
  texels/metre effective scale for the capture-high profile.
- Hero textures are at least 2K; retained 4K sources remain 4K unless a measured
  runtime budget requires a documented derivative.
- Wall, floor, trim and cabinetry UVs are metric and deterministic.
- DefaultMaterial, missing textures, stretched unique hero UVs and unbound mesh
  primitives fail the build.
- WHEN an optional glTF material extension changes UE 5.7's material-branch
  selection despite being semantically inactive THEN the system SHALL create a
  deterministic, receipt-bound compatibility derivative and SHALL leave the
  licensed source bytes immutable.
- A compatibility derivative may remove only a material-local
  `KHR_materials_transmission` whose factor is absent or exactly zero, whose
  texture is absent and whose object contains no unknown fields. Active
  transmission, unknown fields and simultaneous active transmission/clear-coat
  SHALL be retained and surfaced; a dual-active material blocks full-fidelity
  promotion until a custom material bridge is verified.
- Unreal import acceptance continues to require every returned Texture2D to be
  referenced by a bound non-default material. Compatibility work may not weaken
  that gate to hide a material-import precedence error.

### R8. A photoreal human is a provider, not a hidden dependency

WHEN a photoreal character is enabled THEN its body, face, hair, clothing,
skeleton, retarget mapping, LOD/corrective policy, license/entitlement and package
digests SHALL be represented by a reviewed character-provider receipt.

IF that provider is absent THEN the world SHALL remain functional with the
project-owned Manny contract and SHALL report `photoreal_character_unavailable`
rather than silently substituting it as accepted evidence.

Acceptance notes:
- The first preferred provider is an assembled MetaHuman produced with the local
  UE 5.7.3 toolchain.
- A research actor is player-controlled or event-spawned; it does not wander by
  default.

### R9. Every external asset is provenance-bound

WHEN an external asset enters a build THEN the build SHALL verify provider ID,
source/files hash, per-file digest, license, entitlement, authorship,
redistribution/NoAI policy, dimensions, transform derivation, material semantics,
collision and interaction metadata.

Acceptance notes:
- Git stores only manifests, schemas, recipes, licenses, digests and receipts.
- Poly Haven CC0 is the public baseline; HSSD remains private research-only;
  YCB requires attribution; Epic/Fab/MetaHuman content requires entitlement.
- No network fallback or nearest-match substitution occurs during an accepted
  build.

### R10. Realism remains remotely playable

WHEN the canonical package runs at 1920x1080 on the designated GPU THEN it SHALL
maintain a responsive 60 fps target after warm-up, with no input stall during
animation or asset streaming.

Acceptance notes:
- Frame-time, GPU-time, draw-call, triangle, texture-pool and streaming evidence
  are captured for each visual milestone.
- If the 60 fps gate is missed, quality reduction is explicit and measured; the
  package may not hide it behind an undocumented 30 fps/70% render setting.

### R11. Acceptance evidence is action- and image-specific

WHEN a slice is promoted THEN it SHALL include exact-tip source digests, package
digests, typed action receipts, before/contact/after captures, renderer status,
performance evidence and a human-reviewed visual checklist.

IF evidence is absent THEN the slice SHALL remain experimental even when unit
tests, montage playback or map composition succeeds.

### R12. Existing evidence and runtime stay recoverable

WHEN this work changes contracts, composition or packaging THEN existing accepted
run directories SHALL remain append-only, the current live package SHALL not be
mutated in place, and rollback SHALL mean launching the previous sealed package.

### R13. Playable actions have visible feedback and close VISTA events

WHEN the player focuses an interactable object THEN the HUD SHALL expose the
primary contextual action and a separate Inspect control whenever Inspect is an
allowed affordance.

WHEN a player, EventSpec or agent action is accepted THEN the presentation SHALL
show its current phase and SHALL show its terminal success or typed failure code;
an input that is rejected or blocked SHALL never appear to do nothing.

WHEN Inspect succeeds THEN the system SHALL enter a bounded focus presentation
with the target name, semantic identity, affordances and safe public state, and
SHALL provide an explicit exit path without mutating the target.

WHEN a pickup, place, drop, open, close, toggle or inspect action reaches its
authoritative terminal success THEN the shared execution path SHALL publish
exactly one interaction observation to the active VISTA event. Interrupted,
rejected, timed-out or rolled-back actions SHALL publish none.

Acceptance notes:
- The first playable slice uses `E` for the contextual primary action, `I` for
  explicit Inspect, `Q` for drop and `Escape`/`I` to exit Inspect.
- Inspect presentation includes a visible target focus and information card;
  logging `INSPECTED` without user-visible output is not acceptance.
- Articulated doors and appliances commit state at a typed handle/contact signal;
  changing only an invisible semantic proxy is not acceptance.
- Player input, TCP commands and EventSpec actions expose the same terminal
  action/interaction receipt identity even when their presentation differs.

### R14. Detailed actions are selectable, stateful and chainable

WHEN a focused object exposes more than one currently valid affordance THEN the
player SHALL be able to inspect a deterministic action list, select one action
and execute it through the shared executor without relying on a hidden priority
order.

WHEN an item is inserted into or removed from a container THEN the item and
container SHALL reserve as one typed tuple, mutate only at the animation contact
signal and publish one receipt containing both semantic identities and both
before/contact/after states.

IF any step after contact fails THEN the system SHALL restore the exact item
physical state, carrier inventory and container contents before releasing either
reservation.

WHEN a new detailed action is exposed to VISTA events THEN it SHALL enter a new
versioned EventSpec and ActionCatalog beside the frozen prior version; an enum,
montage route or unaccepted schema entry alone SHALL never make the action
runtime-authorized.

Acceptance notes:
- The first detailed-action lab exposes explicit choices for Inspect,
  PickUp/Place/Drop, Open/Close, Press/TurnOn/TurnOff, Sit/Stand and Pour.
- The first chainable storage slice is `open -> insert -> close -> open ->
  remove`; a closed, busy, full or mismatched container rejects before mutation.
- Insert and Remove require dedicated contact/completion animation authority or
  remain fail-closed; silently aliasing them to Place/PickUp is not acceptance.
- Appliance state changes require visible presentation such as door/drawer
  articulation, water, flame, drum motion, indicator light or sound as
  appropriate to the semantic target.

## Edge Cases

- A queue is replaced between contact commit and montage completion.
- The target moves or changes room during approach.
- A held object is deleted, hidden or claimed by another actor.
- A door closes while navigation is approaching its interaction anchor.
- MetaHuman or HSSD content is locally missing despite a manifest reference.
- A Poly Haven upstream `files_hash` changes after the request was pinned.
- A packaged build has the correct montage name but the wrong skeleton or notify.
- A GLB has active clear-coat plus a no-op transmission extension, causing UE to
  choose a transmission material and leave the clear-coat texture unbound.
- A GLB legitimately needs active transmission and active clear-coat on the same
  material, which UE 5.7 Interchange cannot represent through its single branch.
- An animation completes visually but the authoritative target state did not
  change, or state changed without a contact notify.
- A blocked player action returns a typed error but the HUD drops the result.
- A visible HSSD appliance shell is separate from its semantic trace proxy, so
  logical state changes without moving the visible articulated part.
- Inspect is an allowed secondary affordance on an object whose primary action
  is pickup, open/close or toggle.

## Open Questions

- Exact MetaHuman identity, appearance and wardrobe are art-direction choices;
  R1 uses a neutral research participant until the user selects otherwise.
- HSSD may provide private-research visual shells, but articulated appliances
  require separate UE semantic parts and are not accepted as static joined GLBs.
- Generated missing motions may use Control Rig or Blender only after the action
  catalog proves that licensed mocap and existing project assets do not cover the
  required semantic variant.

## Approval

- Requested by: Ives Liu
- Approved by: Ives Liu, via explicit implementation instruction
- Date: 2026-08-28
