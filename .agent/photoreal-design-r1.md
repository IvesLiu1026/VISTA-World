# Photoreal design reference session — 2026-09-06

- Agent: Codex, current VISTA design task.
- Branch: `codex/vista-photoreal-design-r1`.
- Worktree: `/data/sysx/vista-world/worktrees/vista-photoreal-design-r1`.
- Base: `936d86d50aa1cc281fcbe4d91287db935fcc1f51` (R23 checkpoint).
- Owns: `docs/design/vista-photoreal-r1/**`, `tools/design/build_photoreal_reference_layout.py`, this file.
- Scope: six room concept sheets, three kitchen object reference sheets, a deterministic nominal layout, and an implementation brief.
- Runtime ownership (2026-09-06 user follow-up): user explicitly requested completed modeling and a Sunshine-accessible result. This authorizes the local Blender/UE build, GPU1 preview, and a new Sunshine review entry. Preserve the existing GPU0 demos and their project files. GPU1 handles Blender rendering; live UE presentation uses GPU0 because GPU1 cannot present to Xvfb. Use fresh append-only output directories under `/data/sysx/vista-world/runs/vista-photoreal-design-r1/`.
- Additional owned paths: `tools/blender/vista_photoreal_r1/**`, `tools/ue/vista_photoreal_r1/**`, `tools/runtime/vista_photoreal_r1/**`, `unreal_plugins/VistaPhotorealReview/**`, and related review documentation. Own only the new review service/window; coordinate any Sunshine application-list reload after checkpointing its current configuration.
- Preserve: existing world packs, runtime code, accepted receipts, third-party assets, other worktrees and all datasets.
- Image authorization: user requested GPT Image 2 room and object design references in this task. Built-in image tool only; no Higgsfield, OpenRouter or user API-key billing invoked.
- Visual references are original generated concepts, not measurements, meshes, PBR texture maps, or proof of multi-view geometric consistency.
- Validation: verify layout against the pinned source, parse XML/JSON, inspect generated images and record actual file hashes/dimensions.
- Handoff: `docs/design/vista-photoreal-r1/README.md`.
- Kitchen checkpoint: all six room and three object sheets saved; kitchen, pot, mug and articulated fridge modeled and imported. See `docs/design/vista-photoreal-r1/implementation.md`. Preserve this accepted standalone project and its evidence.
- Completed follow-up: connected six-room home under `home-r1-20260906a`, accepted geometry `model-b`, final UE `project-g`, live profile `sunshine-review-profile-g.json`. Own the same source/documentation paths and only the named photoreal home/kitchen review units. Sunshine Home entry is installed and reloaded; Home and its input relay are active on `:119`, GPU0. GPU1 rendered Blender previews. Existing R23/R6 processes and standalone kitchen project are preserved. No remote generation/API spending. See `home-implementation.md` and its manifest for 31 passing checks, 29 native screenshots, collision/door/flight validation and limitations.
