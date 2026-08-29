# Requirements: VISTA HSSD R2 UE Composition R1

Status: Approved for implementation
Updated: 2026-08-30

## Problem

The private-research UE Phase-2 candidate already imports all 26 HSSD visual
assets and composes 60 actors, but it is bound to the original R1 transforms.
The reviewed R2 Blender plan removes avoidable portal conflicts, blocking AABB
overlaps and semantic-proxy alignment violations. Unreal must consume that exact
sealed placement authority in a fresh diagnostic candidate without weakening
the existing material, collision, proxy or acceptance gates.

## Goals

- Bind the exact external R2 Blender plan from
  `hssd-six-room-scene-r5-20260830t030529/build-plan.json` by path, bytes,
  SHA-256 and canonical content digest.
- Reuse the existing sealed Phase-1 HSSD UE namespace and its 26 imported
  StaticMesh assets; do not reimport or alter licensed source GLBs.
- Compose exactly 60 visual-only HSSD actors, ten per room, at the R2 world
  transforms while retaining exactly 19 semantic proxy authorities.
- Preserve all explicit R2 blockers: two hard support outliers, 18 wall-fixture
  reviews and 20 secondary collision candidates without UE authority.
- Produce a fresh append-only, NullRHI UE candidate and closed receipts.

## Non-goals

- Claiming visual acceptance, playable collision, full material fidelity,
  human presence, interaction proof, photorealism or GTA-level quality.
- Solving the washer active transmission plus clear-coat material bridge.
- Modifying the live R6 demo, Sunshine, HSSD source run, prior UE attempts or
  public Git with external HSSD binaries.
- Replacing semantic proxies with HSSD meshes or granting secondary dressing
  collision authority.

## Requirements

### R1 — Exact R2 plan authority

The host and commandlet SHALL validate the fixed R2 plan SHA-256, byte count,
schema, canonical content digest, source profile/scene digests, 17 transform
overrides, all 17 exact target transforms and canonical support, proxy, portal,
portal-clearance and contact ledger projections. Missing, extra, merely
shape-valid, resealed or caller-selected plan bytes SHALL fail before UE
execution or publication.
Pinned JSON SHALL be hashed and parsed from the same `O_NOFOLLOW` file
descriptor; attempt-local inputs SHALL be revalidated immediately before UE and
again before terminal publication.

### R2 — Closed placement projection

The R2 placement set SHALL contain the same 60 instance, room, asset,
interaction and semantic-target identities as the pinned R1 source; only the
fixed transform projection may differ. The composed result SHALL contain ten
actors per room and exactly 19 semantic targets.

### R3 — Existing safety authority remains unchanged

Every HSSD actor SHALL remain a visual shell with `NoCollision`, no physics,
no overlap events and no navigation contribution. The existing R1 semantic
proxy SHALL remain the sole query authority and SHALL retain the Phase-2 repair,
save and cold-reload gates. Each visual-shell actor receipt SHALL use a closed
field set and bind the deterministic persistent-level actor path plus the exact
`/Script/Engine.StaticMeshActor` class; additional positive or negative claim
fields are forbidden.

### R4 — Honest unresolved blockers

The execution and terminal receipts SHALL bind the R2 remediation ledger and
keep the faucet, ladder, 18 wall fixtures and 20 secondary collision candidates
review-pending. Zero portal/AABB/proxy-threshold counts do not imply complete
playability.

### R5 — Isolated append-only execution

Apply SHALL require the existing explicit non-promotable material-conflict
acknowledgement, copy the sealed Phase-1 project to one fresh direct child,
execute UE 5.7.3 with NullRHI/no network, save/reload the map and never mutate
the live runtime or any prior attempt.

No network SHALL mean a pinned Bubblewrap `--unshare-net` OS namespace in
addition to UE transport flags. The final scene and host receipts SHALL bind
that isolation contract. Concurrent transient mutation by another process with
the same Unix UID is outside this lane's threat model; persistent drift is
detected by the pre/post execution revalidation.

### R6 — Pure reviewability

CPU-only tests SHALL cover exact plan binding, identity-preserving transform
projection, drift rejection, dry-run zero-write behavior, terminal receipt
binding and all negative claims without running UE, Blender, GPU or network.

## Approval

- Requested by: yhliu
- Approved by: previously approved VISTA Action World T10 spec and explicit
  continuation request `那請你繼續做我們可以做的部分`
- Date: 2026-08-30
