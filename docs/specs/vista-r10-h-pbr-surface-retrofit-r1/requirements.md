# Requirements: VISTA R10 h PBR Surface Retrofit R1

Status: Approved for source implementation; T7 execution remains separately gated
Updated: 2026-08-30

## Problem

The sealed six-room candidate `hssd-r2-citysample-live-r5-20260830h` is the
best current playable-home baseline, but nine architecture material bindings
in the bathroom/laundry, bedroom, and office still use generic Interchange
fallback materials. The project already contains sealed 4K PBR wool and white
oak materials plus the reviewed R2 slate, plaster, and ceiling materials. The
next visual slice should reuse those existing bytes instead of importing more
assets or changing gameplay.

## Goals

- Replace exactly nine generic floor/wall/ceiling bindings with existing PBR
  material objects already present in sealed candidate `h`.
- Preserve the exact six-room world, actors, geometry, collision, semantics,
  fixtures, City Sample provider, controls, and external-asset boundaries.
- Produce one fresh append-only child with a map-only static-tree delta and
  closed save/cold-reload evidence.
- Keep runtime, interaction, human visual, photoreal character, and GTA-quality
  acceptance false until a separate human-operated live review.

## Non-goals

- Editing or reimporting any material, texture, mesh, City Sample, HSSD, R3
  character, R8 animation, or BuildPlugin package.
- Adding downloadable assets, procedural geometry, Blender work, animation,
  IK, NPC behavior, physics, or new interaction mechanics.
- Mutating candidate `h`, the R6 live baseline, GPU0 services, Sunshine, Xvfb,
  or CAR coordination state during source implementation or NullRHI review.
- Claiming that a material-only pass reaches GTA visual quality.

## Assumptions and Fixed Inputs

- Candidate `h` complete receipt is
  `52ec26972109b0b2ca195607f8536b845c56b2c413e50d5a207609452e46211a`;
  combined receipt is
  `869c8247e975cd79af9be5a7cca4dc169b2de8b7b3badf673ec3f93f425bdc48`,
  host receipt is
  `ec35ebc8aa6989fa3486207866779d5ff1898ecb2116bf7a4a0f9bf652a73848`,
  scene receipt is
  `67cbea713749283bec2cbcb15cd4d47d79b9d7a857602cfc313d3db33ba0ef57`,
  map is
  `1fda153459fea9845cab969b9802ce418bdde51bdbf6884ccd17c77b796dd588`,
  and the 2,453-file / 9,153,718,809-byte project tree is
  `74846d5a0afeb7f72ee3b21bbe965afd46968a4b16e60ca9dff08d665c380376`.
- The parent project descriptor is 522 bytes with SHA-256
  `fe11c7e48eb895eec74e48868fc458a24a2290e826f8cbe75edea0e8ba8b674a`;
  the sealed scene receipt is 917,649 bytes.
- The current finish profile is 71,082 bytes with SHA-256
  `065782f443fd659a20d9a2ed5419403b2cf0faf04e336f05b11fc38528e999cb`.
- The sealed scene receipt proves the three target components currently expose
  exactly three material slots and the entry-hall presentation component
  already resolves every proposed replacement object.
- The sealed presentation manifest identifies
  `r2_external_t_8e98f99344e39` as Poly Haven 4K poly-wool herringbone and
  `r2_external_t_72b7127467c9a` as 4K white-oak veneer, each with base-color,
  normal, and roughness maps. The manifest, artifact receipt, and import
  receipt SHA-256 pins are respectively
  `b5c6b0dd2d172255cb5f7bb494657b8c1ed7f2f7a214557b08d7642590e0a71e`,
  `f4c55a1ef674ad3ba3cfa980e4321255663437fc0811723768ce32ce604488c5`,
  and `7e46e1fb338b586ca0a64a1a917f07b8ca61a6c16df0b6bf662159ebd86c83b4`;
  implementation SHALL carry their full pins and cross-document identity
  linkage. Those source assets remain Git-external.
- The shared Poly Haven receipt is CC0-1.0 with file SHA-256
  `6b894d75f61115a2d2d63769c091ae4da511e9ce9697cd0809fff1b3d1f910a3`,
  canonical digest
  `a8a6b03c8fae71b299a2fcb36764e2dc1ec32c1e4dcd0b30ff0d3db3223fef70`,
  and acquisition-manifest SHA-256
  `317ca0f30409d04365ae8d7b5aa096e8454d8bc8fbe13a8b386935b19e719774`.

## Requirements

### R1 — Exact immutable parent

WHEN an R10 plan or execution starts THEN the system SHALL revalidate the exact
candidate `h` complete/combined/host/scene receipts, descriptor, map, legal
scope, provider, and full static-tree projection before creating output.

Acceptance notes:

- Dry-run creates no directory and writes no receipt.
- Apply creates only one fresh direct child of the fixed run parent.
- Candidate `h` and every prior run remain byte-identical.

### R2 — Exact nine-binding matrix

WHEN the fixed world is loaded THEN the system SHALL admit only this matrix:

| Room | Actor | Slot | Current semantic | Replacement |
| --- | --- | ---: | --- | --- |
| bathroom/laundry | `StaticMeshActor_0` | 0 | floor | `VISTA_M_r2_slate_honed` |
| bathroom/laundry | `StaticMeshActor_0` | 1 | wall | `VISTA_M_r2_plaster_warm` |
| bathroom/laundry | `StaticMeshActor_0` | 2 | ceiling | `VISTA_M_r2_ceiling_matte` |
| bedroom | `StaticMeshActor_1` | 0 | floor | `r2_external_t_8e98f99344e39` (4K poly wool) |
| bedroom | `StaticMeshActor_1` | 1 | wall | `VISTA_M_r2_plaster_warm` |
| bedroom | `StaticMeshActor_1` | 2 | ceiling | `VISTA_M_r2_ceiling_matte` |
| office | `StaticMeshActor_5` | 0 | floor | `r2_external_t_72b7127467c9a` (4K white oak) |
| office | `StaticMeshActor_5` | 1 | wall | `VISTA_M_r2_plaster_warm` |
| office | `StaticMeshActor_5` | 2 | ceiling | `VISTA_M_r2_ceiling_matte` |

Acceptance notes:

- Actor, component, slot, current material, replacement object, class, package
  SHA-256, and byte count SHALL all be fixed contract values.
- The five unique replacement packages SHALL be re-hashed from the parent and
  copied unchanged as part of the parent tree; no duplicate package is added.
- Missing, reordered, default, caller-selected, case-variant, or extra bindings
  SHALL fail closed.

### R3 — Map-only minimal mutation

WHEN the commandlet saves and cold reloads the world THEN only the nine
material assignments and the map package bytes SHALL differ from candidate
`h`.

Acceptance notes:

- The three architecture actors retain exact paths, classes, mesh objects,
  transforms, visibility, shadow, and `BlockAll` collision.
- Their components remain Static, `QueryAndPhysics`, `BlockAll`, Pawn and
  Visibility blocking, non-simulating, non-overlapping, navigation-affecting,
  and actor collision-enabled.
- All 108 preserved actors, 60 visual slots, six fixture actors, 19 semantic
  proxies (16 static proxy actors plus three dynamic semantic instances), 20
  secondary proxies, 21 detail-no-collision rows, five portals,
  game mode, world path, WorldSettings, lights, tags, pickup state, and provider
  remain exact except for the nine approved material-list cells on the three
  target components.
- Project descriptor, plugin, materials, textures, R3/R8 namespaces, and all
  non-map packages remain byte-identical.

### R4 — Closed CPU-only execution

IF apply is approved THEN the host SHALL run one fixed UE 5.7 NullRHI
commandlet inside the existing network/PID-isolated containment pattern, with
no GPU/display credentials, Blender, downloads, or AI/VLM review.

Acceptance notes:

- Source receipts and scripts are copied by exact pin and revalidated before
  and after execution.
- Save, cold reload, terminal-marker cardinality, process/log closure, and
  delayed current-byte validation SHALL all pass before publication.
- A malformed or partially present attempt remains append-only failure
  evidence and can never replace `h`.

### R5 — Honest receipts and negative claims

WHEN publication completes THEN host, scene, result, combined, and complete
receipts SHALL close exact before/after binding rows and a one-map delta.

Acceptance notes:

- Structural PBR binding verification may be true.
- Runtime play, visual acceptance, interaction acceptance, photoreal-character
  acceptance, and GTA-quality claims SHALL remain false.
- NullRHI output and automated screenshots SHALL not promote visual quality.

### R6 — Animation and provider separation

WHEN R10 is composed THEN it SHALL preserve
`citysample_crowd_visual_demo_v1` and SHALL not copy the R3 character, future R8
animation packages, or animation-enabled BuildPlugin authority.

Acceptance notes:

- The material child and animation overlay remain independent append-only
  inputs. A later reviewed composition may combine them.
- No animation authority blocker is weakened by this visual slice.

### R7 — Human-operated rollout remains coordinated

IF the NullRHI candidate is admitted for live review THEN the runtime owner
SHALL wait for the CAR GPU0 window to close, checkpoint the existing R6 demo,
and use the established reversible Sunshine/Xvfb launch procedure.

Acceptance notes:

- Human review covers close-up bathroom, bedroom, and office views, UV scale,
  normal-map orientation, tiling, seams, exposure, controls, portals, pickups,
  and performance.
- A failed review restores R6 and leaves the R10 candidate unaccepted.

### R8 — Repository and license boundary

IF content is Epic/UE-only, HSSD noncommercial, or external PBR source data
THEN binary payloads SHALL remain outside Git; Git stores only source,
contracts, hashes, non-pixel receipts, attribution, and tests.

## Edge Cases

- A replacement object exists but resolves to a different class or package
  bytes.
- The nine assignments are correct before save but reorder or revert on cold
  reload.
- A commandlet changes the map plus a material package or descriptor.
- Actor counts remain equal while one protected actor, transform, tag, proxy,
  collision mode, provider, or game-mode object drifts.
- The 4K wool or oak material tiles poorly on the three-slot generic shell;
  structural publication may pass, but human visual acceptance remains false.

## Open Questions

- None for the contract draft. Human review, not the commandlet, decides
  whether 4K wool/white oak UV scale is visually acceptable.

## Approval

- Requested by: Ives / VISTA World owner
- Approved by: Ives, explicit approval in Codex on 2026-08-30
- Date: 2026-08-30
