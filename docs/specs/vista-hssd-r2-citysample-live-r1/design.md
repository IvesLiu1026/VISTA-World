# Design: VISTA HSSD R2 + City Sample Live R1

Status: Ready for implementation review
Updated: 2026-08-30
Depends on: requirements.md

## Architecture

This is an append-only map upgrader plus a separate live launcher. It does not
extend the sealed R6 materializer/launcher in place.

```text
sealed R6 receipt/project ─┐
                          ├─ host materializer ─ copied R6 project
HSSD R2 v4 receipts/plan ─┤                        │
R9 finish profile ────────┘                        ▼
                                  fixed NullRHI UE commandlet
                                             │
                                 save → cold reload → scene receipt
                                             │
                              host current-byte + combined receipts
                                             │
                                  human-only live launcher
                                             │
                                  Xvfb :118 / GPU0 / Sunshine
```

## Fixed lineage

The runner admits only the R6 combined receipt at `6370e4e1...7648870`,
its static tree `fdb1921e...63106`, and HSSD R2 attempt
`hssd-ue-phase2-r2-diagnostic-20260829T203309Z` with host
`e911fc34...51115`, scene `f7d225fb...f4a4d`, and plan `4b2ded46...9de2`.

The exact 208-file HSSD namespace already inside R6 is re-sealed against the
R2 project. No HSSD payload is re-imported or copied. The standalone HSSD map
`60c4f719...f4d1` is authority evidence, never the base map.

The R6 static-semantic diagnostic is a read-only NullRHI observation, SHA-256
`c6c5c534...3579de`, 34,078 bytes, with canonical content digest
`8621f19e...9c15f`. Its negative acceptance claim is retained. The closed
16-row mode/profile projection derived from those observations has digest
`0ed67682...082ed9`; the pinned commandlet and host validator independently
embed and cross-check the same projection. This closes factual parent-state
validation without turning the diagnostic into visual or interaction
acceptance.

## Repository file plan

- `world_packs/vista_playable_home_r1/visual_profiles/hssd_r2_citysample_live_r1.json`
- `tools/blender/vista_playable_home_r9_fixtures/` with a host forge and fixed
  headless Blender worker
- `tools/ue/vista_playable_home/materialize_hssd_r2_citysample_live.py`
- `tools/ue/vista_playable_home/compose_hssd_r2_citysample_live_commandlet.py`
- `tools/runtime/vista_playable_home/hssd_r2_human_visual_demo_launch.py`
- matching runner, commandlet and launcher tests
- this spec directory

The host may import stable hashing/tree helpers, but owns its paths, schemas,
pins, plan and terminal validation. UE receives copied fixed script snapshots,
not live worktree imports.

## Actor migration

Before mutation, build exact observations for 42 legacy shells (10 bathroom,
10 bedroom, 10 office, 6 entry, 1 kitchen, 5 living), 108 other actors, 19
semantic proxies, three pickup presentations, six R4 lights and architecture.
The 42-row observation requires the exact legacy instance-ID set, tags, class
and paths. Deletion authority is a separate exact singleton: only
`hssd.r1/bedroom.phone.01` at its pinned actor path/class/tags may be destroyed.
The other 41 rows may receive only their closed R2 transform/tags/component
policy. A prefix alone grants neither deletion nor mutation authority.

For each reuse, the before evidence records the complete source actor identity.
The after-save and cold-reload evidence must retain the same actor path and
class while matching the complete R2 placement tags. This intentionally permits
the 12 observed legacy `VistaRole=hssd_curated_overlay` tags to disappear; it
does not permit replacing the actor under the same instance ID. Both the UE
validator and trusted host validator enforce that lineage split.

Final projection:

- 57 HSSD NoCollision shells at R2 remediated transforms;
- `hssd.r1/bedroom.phone.01` represented by City Sample phone;
- `hssd.r1/kitchen_dining.coffee_cup.01` represented by City Sample cup;
- `hssd.r1/kitchen_dining.pot.01` represented by R6 pot.

Reuse/reposition the exact 41 shells already representing static slots, delete
only the legacy bedroom-phone shell, and spawn exactly 16 missing shells. This
produces 57 HSSD shells plus the three dynamic slots with a smaller mutation
surface than delete-all/recreate-all. Cold reload validates exact rows and
before/after actor paths, not counts alone.

The three dynamic rows do not receive the standalone R2 shell transform. They
preserve the complete R6 semantic actor, collision proxy, PresentationMesh,
fit/envelope and attachment observations. For example, the sealed R6 bedroom
phone actor is at z=64 with a fitted presentation relative z near -4.999518;
the cup actor is at z=78 with fitted relative z near 3.448716. Moving those
actors to raw R2 shell z values would break pickup. The v5 receipt maps each
unchanged R6 presentation observation to its logical R2 slot and proves no
duplicate shell exists; it never recomputes the fit.

## Collision model

Visual meshes remain NoCollision. Collision has two deliberately separate
semantic layers:

- The standalone HSSD R2 source receipt must continue to expose all 19 hidden
  proxies as QueryOnly/Custom. It supplies semantic identity, component path,
  overlap and navigation binding evidence, not copied-map runtime mode/profile.
- The copied R6 map must preserve the exact 16 static-proxy projection: shoe
  bench, dining table, stove, coffee table and sofa are
  QueryAndPhysics/BlockAll; the remaining eleven are QueryOnly/Custom. All are
  hidden, non-simulating and Pawn/Visibility blocking. Exact instance IDs and
  the `0ed67682...082ed9` projection digest prevent distribution-preserving or
  coherent reseal drift.
- Three pickup proxies preserve complete R6 presentation, collision and pickup
  state independently of the static projection.

Twenty secondary objects receive deterministic QueryOnly box components
derived from pinned R2 bounds. Twenty-one details remain explicit NoCollision.
Each receipt records owner, extent, transform, mode, responses,
physics/nav/overlap flags and reloaded observation. Human walking remains the
promotion gate. No serialized JSON shape changes, so execution/plan/upgrade
remain v2; the unsuccessful v2 attempt `20260830d` is quarantined and every
execution pins the exact commandlet and materializer bytes.

## Six-room finish profile

The closed JSON profile references only existing materials and defines:

- per-room floor/wall/ceiling material paths;
- baseboard and door-trim segments;
- bathroom wet-zone segments;
- six layered fixture assemblies and exact R4 light bindings;
- fixed emissive/material bindings and component counts.

The fixture forge pins Blender 4.5.8 at SHA-256
`86b39e16cf8043a93de6b4ac5e23399d790f662c644573f600398a3c3bd121eb`
and 163,587,256 bytes, runs CPU-only with GPU devices disabled, and emits
exactly three GLBs: pendant (entry/kitchen), flush dome
(bedroom/bathroom) and linear panel (living/office). Each uses deterministic
procedural geometry and two opaque materials (brushed metal and opal
diffuser), with no external textures, cameras or lights. The host validates
one root scene, exact mesh/material/node names, no unsupported extensions,
origin/scale/orientation, finite closed bounds, mesh/material counts, nonblank
CPU previews and GLB bytes. Archetype and material names are globally unique so
UE import packages cannot collide. Outputs and previews are Git-external; only
source, recipe and digests enter Git.

The UE commandlet imports those fixed GLBs into one exact package namespace and
replaces the mesh on the six existing fixture actors without adding fixture
actors. No caller asset or transform override exists.

## Materializer and containment

`materialize_hssd_r2_citysample_live.py` performs:

1. deterministic zero-write preflight;
2. same-FD validation of R6, HSSD v4, namespace, scripts/profile;
3. fresh private attempt and exact R6 project copy;
4. fixed execution manifest and stripped environment;
5. bwrap `--unshare-net --unshare-pid`, `-nullrhi`, `-notraceserver`, no
   GPU/display/proxy/credentials;
6. commandlet save/cold reload;
7. residual process-group and stable-log closure;
8. exact static-tree delta containing only the map and the sealed fixture
   mesh/material package inventory;
9. scene, host and combined receipt publication;
10. immediate standalone current-byte revalidation.

All JSON rejects duplicates/non-finite values, uses canonical digests and exact
key sets, and compares booleans type-strictly. Execution binds parent receipt,
trees/maps, HSSD plan/projections, 42→57+3 actors, 108 preserved actors,
19/20/21 collision rows, finish inventory, scripts and isolation.

## Live launcher and rollback

The dedicated launcher adds a v5 combined-receipt validator while preserving
the byte/shape behavior of existing v2-v4 receipts. It admits only the new v5
receipt and constructs the
fixed R6 game command with the playable-home map,
`citysample_crowd_visual_demo_v1`, `-VistaHumanOperatedVisualDemo`, display
`:118`, GPU0, 1080p and safe transport/telemetry flags.

Rollout keeps R6 active through NullRHI. Before checkpoint, construct and
zero-write validate the exact R6 rollback launch from receipt
`6370e4e1...7648870`, the fixed v4 launcher and fixed working directory. The
current R6 unit is transient and is not assumed restartable by unit name. Stop
only R6 UE, verify it left GPU0, start R9 without restarting
Sunshine/Xvfb/input, run the checklist, and on failure recreate R6 through the
validated `systemd-run --user` command or contained direct launcher. No unit is
installed during source implementation.

## Test strategy

Pure CPU tests cover zero-write behavior, fixed source pins, namespace equality,
42→57+3 actor closure, pickup drift, 108 preserved actors, 19/20/21 collision,
six-room finish, deterministic fixture forge/GLB inspection, no overrides/
network/GPU/AI review, terminal/log/map/fixture drift, exact artifact mutation
and launcher command/rollback metadata.

Collision tests separately enforce the HSSD source 19×QueryOnly/Custom
contract and the R6 runtime 5×QueryAndPhysics/BlockAll plus
11×QueryOnly/Custom projection. They reject unknown/missing identities and
both directions of consistently resealed mode/profile drift at live UE,
commandlet-document and trusted host-validation boundaries.

Retained NullRHI evidence must show UE zero, cold reload, exact inventories,
map-plus-fixture delta, delayed current-byte validation and all acceptance
fields false.
Human review covers 12 views, five portals both ways, controls, pickups,
fixtures/exposure/collision and performance.

## Failure and tradeoffs

Failed attempts remain append-only and never stop R6. Live failure restores R6.
Query boxes improve walkability but need human tuning. Existing 256px HSSD
textures limit close-up realism; this pass improves completeness without
pretending to solve texture fidelity. A separate launcher duplicates a small
amount of code but avoids weakening sealed R6 contracts.
