# HSSD six-room scene assembler

This directory contains two separate assemblers:

- `assembler.py` / `blender_worker.py` retain the earlier one-room R5 review
  path.
- `forge.py` / `six_room_blender_worker.py` are the six-room R2 placement
  remediation path over the sealed R7 materialization described here.

The six-room forge is private, non-commercial research tooling. HSSD GLBs,
Blender files, renders, and receipts stay outside Git. It does not download
assets, call a model API, start Unreal, or promote Blender visuals to runtime
interaction authority.

## Dry run

Dry run is the default and writes nothing:

```bash
PYTHONPATH=. uv run python -m \
  tools.blender.vista_playable_home_hssd_scene.forge \
  --license-accept CC-BY-NC-4.0
```

It revalidates the sealed R7 HSSD materialization (26 normalized GLBs and 26
asset receipts), its exact profile/scene-plan/placement digests, the checked-in
six-room `HouseSpec`, and the pinned Blender and builder bytes. It then applies
17 fixed transform-policy overrides. There is no caller-provided placement
override. The emitted plan contains:

- 26 prototype imports and 60 linked-instance placements;
- room-local and world-space rotated AABBs;
- explicit floor, surface, and wall-edge support records;
- a before/after protected portal-approach ledger;
- every retained R1 semantic proxy and its visual alignment delta;
- review-only secondary AABB proxies or explicit detail-no-collision policies;
- explicit visual-contact and collision policies;
- the unchanged external source/license authority and remaining review blockers.

The deterministic R2 transform layer reduces protected portal conflict
assignments from 10 to 0, collision-blocking overlap pairs from 1 to 0, semantic
proxy deltas over 0.10 m from 2 to 0, and hard geometric support outliers from
7 to 2. All 60 rotated AABBs remain inside their six rooms. The bathroom faucet
still lacks a derivable fixture surface, and the office ladder stays aligned to
its retained semantic proxy instead of inventing a wall anchor. Separately,
all 18 wall-edge items remain `review_pending`: proximity to a room boundary is
not wall-fixture authority. The 20 secondary AABB policies also remain review
candidates until a separate Unreal collision receipt exists. Chair/table and
soft-dressing AABB contacts likewise remain review-pending; they do not block
this deterministic transform-remediation step, but no visual or physics review
is claimed.

This is placement remediation, not runtime proof. It does not promote the
scene to accepted visual evidence, playable collision, Unreal runtime, or
GTA-quality status; all such claims remain false.

## Explicit Blender execution

Execution requires a fresh absolute directory outside every Git worktree and
outside the sealed source run:

```bash
PYTHONPATH=. uv run python -m \
  tools.blender.vista_playable_home_hssd_scene.forge \
  --license-accept CC-BY-NC-4.0 \
  --execute \
  --output-root /absolute/external/append-only/attempt
```

Only the fixed Blender 4.5.8 worker can run. Caller-selected scripts, asset
subsets, network URLs, proxy variables, credentials, and GPU devices are not
forwarded. The worker revalidates the complete plan and source materialization
again before importing anything.

Execution requires Linux sealed memory files. The host supports both Python's
native `os.memfd_create` and a fail-closed libc fallback for uv-managed Python
builds that omit the Python wrapper; both paths require all four immutable file
seals before Blender starts.

On success, the external attempt contains:

```text
build-plan.json
blender.log
scene/scene-review.glb
scene/scene-source.blend
render/living-room-player-eye.png
render/overview.png
artifact-receipt.json
inspection-receipt.json
scene-build-result.json
scene-complete.json
```

Each HSSD GLB is imported once. Placements share mesh and material datablocks;
prototype objects, cameras, lights, and hidden proxies are excluded from the
review GLB. The `.blend` retains the R1 proxies for inspection. A terminal
result remains `assembled_rendered_review_pending` and `accepted=false` until
separate human visual review and Unreal collision/runtime evidence exist.
