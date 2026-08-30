# Design: VISTA R10 h PBR Surface Retrofit R1

Status: Draft; implementation gated on requirements approval
Updated: 2026-08-30
Depends on: requirements.md

## Summary

Build a narrow append-only map overlay from sealed candidate `h`. A fixed
profile declares three actor/component records and nine before/after material
bindings. A zero-write host preflight validates every source pin; after user
approval, a contained NullRHI commandlet copies `h`, changes only those slots,
saves, cold reloads, and publishes closed receipts. Animation and live launch
remain separate phases.

## Architecture and Flow

```text
sealed h receipts + full-tree projection ─┐
sealed scene observations ────────────────┼─ zero-write plan
five existing PBR package pins ───────────┤       │
fixed nine-binding profile ───────────────┘       ▼
                                      fresh h child copy
                                               │
                              isolated UE 5.7 NullRHI commandlet
                                               │
                              bind 9 slots → save → cold reload
                                               │
                         map-only delta + scene/host/complete receipts
                                               │
                              later human-only Sunshine live review
```

## Fixed Binding Contract

The profile uses complete Unreal object paths under the entry-hall presentation
material namespace. The unique replacement package pins are:

| Material | SHA-256 | Bytes |
| --- | --- | ---: |
| `VISTA_M_r2_slate_honed` | `735e5493137d44ef2d371172a6dcb65d185f0ad8bdb2ec9ae01c0033ed4d0cca` | 67,375 |
| `VISTA_M_r2_plaster_warm` | `9ac8086d804df268eac42e0533d379a6fcdac8594ff6f1ad97064ada4527affc` | 67,419 |
| `VISTA_M_r2_ceiling_matte` | `d5c534429d2fa928f7323329a27d606579e0a6577cb6a868ca0e26b274b0ce7d` | 67,427 |
| `r2_external_t_8e98f99344e39` | `1b58b820e3e3e4d646357127c90b8b86606bb1fb4c9e6f041bbc065c94d35899` | 68,184 |
| `r2_external_t_72b7127467c9a` | `e6a290bb97bbdab95863cdf45b30393d711468382394e2add864774d1dd30af5` | 68,070 |

The external-material semantics are closed through the exact production
presentation chain. Its upstream CC0 receipt file is
`6b894d75f61115a2d2d63769c091ae4da511e9ce9697cd0809fff1b3d1f910a3`
with acquisition manifest
`317ca0f30409d04365ae8d7b5aa096e8454d8bc8fbe13a8b386935b19e719774`.
The downstream chain is presentation manifest
`b5c6b0dd2d172255cb5f7bb494657b8c1ed7f2f7a214557b08d7642590e0a71e`
(413,686 bytes), artifact receipt
`f4c55a1ef674ad3ba3cfa980e4321255663437fc0811723768ce32ce604488c5`
(102,998 bytes), and import receipt
`7e46e1fb338b586ca0a64a1a917f07b8ca61a6c16df0b6bf662159ebd86c83b4`
(222,139 bytes). The chain identifies the full material IDs,
4096px base-color/normal/roughness files and imported UE objects; the sealed h
scene then proves those objects resolve at entry component slots 14/15. The R10
runner never reads, copies, or republishes the original JPG files.

The three target component paths are exactly the fixed world prefix plus
`StaticMeshActor_0.StaticMeshComponent0`,
`StaticMeshActor_1.StaticMeshComponent0`, and
`StaticMeshActor_5.StaticMeshComponent0`. Actor 0/1/5 are respectively the
bathroom/laundry, bedroom, and office architecture meshes; there is no
label-based or search-based selection.

## Interfaces and Contracts

Planned CLI surface:

```text
uv run python tools/ue/vista_playable_home/materialize_hssd_r10_pbr_surface_retrofit.py \
  --attempt-name hssd-r10-pbr-surface-retrofit-r1-<suffix>
```

This default is zero-write. A future reviewed apply surface must use one exact
acknowledgement and expose no path, map, material, provider, GPU, or service
override. The Unreal execution document carries only fixed snapshots and the
fresh attempt path.

Proposed schemas:

- `simworld.vista.hssd-r10-pbr-surface-plan/v1`
- `simworld.vista.hssd-r10-pbr-surface-execution/v1`
- `simworld.vista.hssd-r10-pbr-surface-scene-receipt/v1`
- `simworld.vista.hssd-r10-pbr-surface-host-receipt/v1`
- `simworld.vista.hssd-r10-pbr-surface-complete/v1`

All JSON uses duplicate-key rejection, finite values, strict key sets, canonical
content digests, and type-strict booleans.

## Mutation and Evidence Model

Before mutation the commandlet records the complete three actors and the nine
current material paths. It separately captures protected world, actor,
collision, proxy, fixture, portal, pickup, light, and provider projections from
the already sealed `h` contract.

The mutation loop admits only three actor paths, component
`StaticMeshComponent0`, slots 0/1/2, and the profile's exact replacement
objects. It calls no import, actor spawn/delete, transform, collision, tag,
mesh, game mode, lighting, plugin, or provider API. Save and cold reload must
reproduce the exact after rows.

The trusted host re-seals the copied project and admits exactly one changed
relative path:
`Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap`.
Every replacement material package must be byte-identical to its parent copy.

## Data Model and Migration

No canonical dataset or database changes. No parent package is edited in
place. The output is one new Git-external attempt. Rollback is selecting sealed
candidate `h` or the currently running R6 service; no destructive migration is
needed.

## File Plan and Ownership

Owned by the future R10 implementation worker:

- `docs/specs/vista-r10-h-pbr-surface-retrofit-r1/**`
- `world_packs/vista_playable_home_r1/visual_profiles/hssd_r10_pbr_surface_retrofit_r1.json`
- `tools/ue/vista_playable_home/materialize_hssd_r10_pbr_surface_retrofit.py`
- `tools/ue/vista_playable_home/compose_hssd_r10_pbr_surface_retrofit_commandlet.py`
- `tools/tests/test_vista_playable_home_hssd_r10_pbr_surface_retrofit.py`
- `tools/tests/test_vista_playable_home_hssd_r10_pbr_surface_commandlet.py`

Forbidden: all run/evidence directories, existing profiles/materializers,
plugin/animation code, services, GPU state, external packages, and binary
assets.

## Failure Handling and Rollback

- Drift in a present authority fails; it is never downgraded to a warning.
- Dry-run performs no writes. Apply requires a fresh direct child and publishes
  no success receipt until process/log closure and current-byte revalidation.
- UE failure leaves append-only failure evidence and never changes `h` or R6.
- Live visual or control failure restores R6 and retains all acceptance claims
  as false.

## Testing Strategy

- Compact fake parent tests for deterministic/zero-write planning and exact
  five-package pins.
- Parameterized drift for every actor, component, slot, current/replacement
  material, class, size, hash, provider, map, world, game mode, and claim.
- Commandlet contract tests for exact nine mutations, save/reload equality,
  one terminal marker, no actor/import/transform/collision/plugin operations,
  and complete protected projections.
- Host tests for one-map delta, descriptor/material/plugin byte identity,
  containment, process/log closure, fresh-only publication, and false
  acceptance claims.
- Existing HSSD R2/City Sample, launcher, pickup, collision, world-authority,
  animation-overlay, formatting, Ruff, py_compile, and diff checks remain green.

## Rollout and Observability

Source and CPU tests land first. NullRHI execution is a separate approved task.
No live switch occurs while CAR is `WINDOW2_REQUESTED` or `RUNNING`. Human-only
review records close-up views and performance without sending Epic pixels to
an AI/VLM provider.

## Tradeoffs

- Reusing sealed materials is fast, license-safe, and avoids asset growth, but
  their UV scale was authored for presentation bundles rather than the generic
  three-slot shells. Human review may reject wool/oak tiling even when the
  structural receipt passes.
- The external wool/oak chain is stronger semantically than substituting one
  generic wood material, but it adds three pinned provenance documents that
  must all agree. Any break falls closed; office may revert only through a new
  reviewed spec, never an implicit fallback.
- Map-only mutation gives a much smaller provenance surface than reimporting
  architecture meshes. It cannot add displacement, bespoke UVs, decals, wear,
  or room-specific material variation.
- This improves three weak rooms; it is one measurable step toward a convincing
  game world, not GTA-level completion.

## Traceability

- R1 -> fixed parent preflight and fresh append-only attempt
- R2 -> fixed profile, package/provenance pins, exact before/after matrix
- R3 -> narrow commandlet plus host map-only delta validator
- R4 -> isolated NullRHI host lane
- R5 -> closed receipts and negative claims
- R6 -> animation/provider non-mutation assertions
- R7 -> separate coordinated launcher/human review
- R8 -> Git-external payload policy and provenance-only repository changes

## Open Questions

- None before implementation. UV-scale suitability is deliberately a human
  rollout gate, not an unresolved source-design question.

## Approval

- Requested by: Ives / VISTA World owner
- Approved by: pending explicit approval of requirements and design
- Date: 2026-08-30
