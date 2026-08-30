# Requirements: VISTA HSSD R2 + City Sample Live R1

Status: Approved for implementation within the existing playable-home goal;
R5 amended from pinned R6 evidence during implementation
Updated: 2026-08-30

The R5 amendment resolves a contradiction discovered by failed append-only
attempt `hssd-r2-citysample-live-r5-20260830d`: the original text treated the
standalone HSSD R2 source state as the copied R6 runtime state, while R1 and R3
require the R6 parent to remain exact. The amendment is preservation-only. It
does not promote the diagnostic, collision, interaction, runtime, visual or
GTA acceptance; all such acceptance remains human-owned and pending.

## Problem

The current R6 live demo preserves the City Sample human, R4 lighting,
phone/cup presentation meshes and game controls, but its HSSD dressing predates
the reviewed R2 placement authority. It contains 42 legacy HSSD shells rather
than one closed six-room inventory. Replacing the R6 map with the standalone
HSSD R2 map would discard the better R4/City Sample lineage and break the
dynamic pickup presentations.

The next candidate must upgrade a sealed R6 copy. It must combine the reviewed
HSSD R2 placement authority with the human-operated candidate, finish all six
rooms consistently, and add simple collision evidence without claiming that an
automated build is already visually accepted, interaction accepted, or GTA
quality.

## Goals

- Produce one fresh, receipt-bound six-room candidate derived only from R6.
- Upgrade the exact 42 legacy HSSD shells into 60 R2 visual slots while
  preserving the three pickup presentation authorities.
- Preserve the City Sample human, R4 lighting, game mode, navigation, doors,
  VISTA events, phone/cup/pot pickup and all unrelated map actors.
- Complete bedroom, office and bathroom/laundry architecture finish with
  materials and geometry already present in the project.
- Generate three deterministic project-authored fixture archetypes through a
  headless Blender script, keeping GLB/UE payloads Git-external.
- Add simple query collision for the 20 R2 secondary candidates while retaining
  19 semantic proxy authorities and 21 explicit detail no-collision policies.
- Validate first through a network-isolated, GPU-free NullRHI lane, then expose
  the result through a separate live launcher with reversible R6 rollback.

## Non-goals

- Downloading, redistributing or committing City Sample, MetaHuman, HSSD,
  Unreal packages, textures or other binary assets.
- Using Epic content for VISTA data, AI/VLM training, testing, evaluation or
  automated review.
- Completing the root-owned R8 animation-import authority or claiming the five
  CC0 animations are active in this project.
- Implementing hand/foot IK, cabinet physics, fall/ragdoll, multi-NPC behavior,
  packaged performance acceptance or production deployment.
- Setting visual, interaction, photoreal-human, runtime or GTA acceptance from
  commandlet output, screenshots, an AI agent or a VLM.
- Mutating or stopping R6 before source review, CPU tests and NullRHI
  current-byte validation pass.

## Assumptions and fixed inputs

- The user confirmed private noncommercial HSSD scope and Epic/UE entitlement;
  external assets remain outside Git.
- R6 combined receipt SHA-256 is
  `6370e4e179a1f2485ddf3fab572a15426b7703eefa6ae6c6ea6d9ca7f7648870`.
- R6 project tree is 2,444 files and 9,152,756,805 bytes with digest
  `fdb1921eecb7c446c6a49ac2b8fdf174ab6177a3de6ecb4674da65f80b663106`;
  source map digest is
  `2380c96c28af6239df800e050e0ea1aab328ab4018e61c3aaad0b6632eaef564`.
- HSSD R2 host, scene and build-plan SHA-256 values are respectively
  `e911fc34a6b869f41ebc294f7f0f3c67db25abe853fcfb2af34b91e416c51115`,
  `f7d225fb07a51f6eeb76e565df589a317f57c7618b489393c44b79b23a5f4a4d`,
  and `4b2ded463a0be4caf26cd326a06944ab171d93c917d5de530fd36ca9b3ae9de2`.
- R6 and HSSD R2 contain byte-identical 208-file HSSD namespaces; the
  implementation independently recomputes and pins that equality.
- A read-only NullRHI observation of the pinned R6 map records the 16 static
  semantic proxies in a 34,078-byte diagnostic with SHA-256
  `c6c5c534944d7d544b882c6aae15d52431df109434505837c228eed3793579de`
  and canonical content digest
  `8621f19e5601c0793cfc8eaf942fb55fa67e994e9cf4639bc98e436882a9c15f`.
  Its `accepted_as_runtime_authority` claim remains false; it is factual parent
  evidence used only to prevent the upgrader from rewriting or misreporting
  the copied R6 state.
- Sunshine, Xvfb `:118` and the input relay stay running. R6 is the rollback
  baseline.

## Requirements

### R1. R6 is the only mutable-lineage parent

WHEN a candidate is planned THEN the system SHALL revalidate the exact R6
combined receipt, descriptor, full static tree, source map and legal gates
before creating output.

Acceptance notes:
- Dry-run creates no attempt directory.
- Apply creates one fresh direct child of the fixed Git-external run parent.
- R6 and prior evidence are never mutated.
- Successful output differs from the copied R6 static tree only by the map and
  one exact sealed inventory of R9 fixture mesh/material packages.

### R2. The final visual-slot inventory is exact

WHEN the copied R6 map loads THEN the commandlet SHALL observe exactly 42
legacy HSSD shells, apply the fixed minimal migration, and publish exactly 60
R2 visual slots after save and cold reload.

Acceptance notes:
- Exactly 41 valid legacy shells are reused at their R2 transforms, the legacy
  bedroom-phone shell is removed, and exactly 16 missing shells are spawned;
  the resulting 57 slots are HSSD NoCollision `StaticMeshActor` shells.
- Every reused shell retains its exact source actor path and class while its
  label, tags, transform, mesh and component policy become the exact R2
  placement state. Legacy-only tags such as `VistaRole=hssd_curated_overlay`
  are not required to survive that closed migration.
- Bedroom phone, kitchen coffee cup and kitchen pot retain existing dynamic
  presentation authorities as the other three slots.
- All slots bind R2 instance, room and source asset. The 57 static shells bind
  exact R2 remediated transforms and the 17-override projection. The three
  dynamic slots instead bind their complete sealed R6 actor/proxy/presentation
  fit observations and logical R2 slot identity; their actor and relative
  presentation transforms are not rewritten or recomputed.
- Missing, duplicate, unknown, prefix-only or extra shell identities fail; a
  delete-all/recreate-all implementation is not accepted as minimal mutation.
- Dynamic presentations leave no duplicate static visual after pickup/drop;
  any phone/cup/pot actor, proxy, fitted envelope or relative-transform drift
  fails closed.

### R3. Existing human-operated gameplay survives unchanged

WHEN the overlay is applied THEN the system SHALL preserve the exact 108
non-HSSD source-map actors and R6 City Sample provider, game mode, doors,
navigation, VISTA overlay, player controls and pickup state.

Acceptance notes:
- City Sample remains runtime-spawned by `VistaPlayableHomeGameMode`.
- Phone/cup/pot PresentationMesh identity, pickup collision and attachment state
  are verified after cold reload.
- All non-owned actors use closed before/after observations.

### R4. All six rooms receive a closed finish pass

WHEN saved THEN each room SHALL have explicit floor, wall and ceiling finish,
deterministic trim, and one fixture/light binding from a versioned profile.

Acceptance notes:
- Reuse bedroom carpet, office cork, bathroom tile, warm-white wall and white
  ceiling materials already in the project.
- Bedroom, office and bathroom/laundry receive baseboards, door trim and
  room-appropriate details; the bathroom wet zone is explicit.
- A fixed headless Blender forge produces pendant, flush-dome and linear-panel
  archetypes from procedural geometry/materials without downloaded textures.
  Their exact imported mesh/material packages replace the six bare cylinders
  while preserving R4 light actors/exposure.
- Missing/default materials and caller-selected assets fail closed.
- The forge script, recipe, output GLB digests, import receipts and package
  inventory are closed; GLB/UAsset binaries remain outside Git.
- Procedural finish is not photoreal or GTA acceptance.

### R5. Collision authority is explicit and non-promotional

WHEN composed THEN the system SHALL preserve 19 semantic proxies, create 20
deterministic secondary query proxies and retain 21 detail no-collision rows.

Acceptance notes:
- The standalone HSSD R2 source contract remains exactly 19 hidden
  QueryOnly/Custom semantic proxies; it cannot overwrite the copied R6 runtime
  state.
- The copied R6 runtime has one exact 16-instance static collision authority,
  digest
  `0ed6768227333ca708b133a184b101a9745215f2f6361d063c3b8da768082ed9`.
  Shoe bench, dining table, stove, coffee table and sofa retain
  QueryAndPhysics/BlockAll; the other eleven retain QueryOnly/Custom. Every row
  stays hidden, non-simulating, Pawn/Visibility blocking, and preserves its
  pinned overlap and navigation flags. Missing, extra, swapped or coherently
  resealed mode/profile rows fail closed.
- Three pickup proxies independently retain their complete R6
  presentation/collision policy.
- Secondary boxes use pinned derived bounds, QueryOnly Pawn/Visibility block,
  no physics, overlap events or navigation authority.
- Five protected portals remain conflict-free in the static ledger.
- Eighteen wall fixtures, faucet support, ladder and five visual contacts remain
  explicit review items.
- Playable-collision and interaction acceptance stay false until human review.

### R6. NullRHI execution and evidence are closed

WHEN apply is authorized THEN the host SHALL run one fixed UE 5.7 commandlet
through Bubblewrap with network/PID namespaces, NullRHI, TraceServer disabled,
and no GPU/display credentials.

Acceptance notes:
- Parent evidence, R2 contracts, scripts and finish profile are copied exactly
  and revalidated before/after UE.
- Process-group and log closure precede host publication.
- Save/reload receipts close actor, material, collision, pickup and negative
  claim schemas.
- Current execution, scene, map and logs are revalidated after host receipt.

### R7. Live launch is separate and reversible

WHEN the NullRHI candidate is admitted for human review THEN a dedicated
launcher SHALL validate it and start it on `:118`/GPU0 without restarting
Sunshine or the input relay.

Acceptance notes:
- No caller-selected project, map, executable or provider.
- Human-operated/Epic acknowledgements are required; agent/VLM adapters fail.
- R6 is checkpointed and stopped only for the switch; failure restores R6.
- Because the current R6 unit is transient, rollback does not assume that
  `systemctl start` can recreate it. Before stopping R6, the runtime owner
  validates one fixed reconstruction command from the exact R6 v4 receipt,
  launcher and working directory; rollback uses that command through a new
  transient unit or a contained direct launch.
- Source completion does not authorize switching an actively used demo.

### R8. Human review owns acceptance

WHEN live THEN a human SHALL inspect at least six overview and six player-eye
views and exercise controls, phone/cup pickup/drop and five portals both ways.

Acceptance notes:
- Visual, interaction, photoreal-human and GTA fields remain false beforehand.
- Suggested 1080p targets: median >=55 FPS, 1% low >=30 FPS, p95 <=25 ms,
  and no stall over one second.
- Epic pixels are not sent to automated visual review.

### R9. License and repository boundaries remain closed

IF input is Epic/UE-only or HSSD noncommercial content THEN its payload SHALL
remain Git-external; Git may contain only source, profiles, digests, non-pixel
receipts and attribution/provenance metadata.

## Edge cases

- R6 has 41 or 43 legacy shells instead of 42.
- A pickup presentation is missing, hidden, duplicated or on the wrong actor.
- A broad label matches but exact identity tags do not.
- HSSD namespaces agree in count but differ in bytes/tree digest.
- A secondary proxy intersects a protected portal or gains physics/nav state.
- HSSD source QueryOnly state is mistaken for copied R6 runtime state, or one
  static runtime proxy is consistently resealed into another permitted pair.
- UE exits zero but evidence changes after first validation.
- Live startup fails after R6 stops; rollback must restore R6 without restarting
  Sunshine.

## Open questions

- Human review decides whether secondary boxes need per-object tuning.
- Provider-specific grip offsets and hand IK are deferred until this baseline is
  stable.

## Approval

- Requested by: yhliu
- Approved for implementation by prior `好的請你幫我做好`, `批准`, `允許`, and
  current `那請你繼續做我們可以做的部分` within the approved goal.
- This does not grant visual, interaction, human-quality or GTA acceptance and
  does not authorize AI/VLM review of Epic pixels.
- Date: 2026-08-30
