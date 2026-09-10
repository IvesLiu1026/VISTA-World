---
name: vista-blender-ue-workflow
description: Build and validate VISTA indoor scenes, physical props, embodied interactions, and liquid prototypes with Blender Python and Unreal Engine. Use for reproducible 3D implementation or improving an existing VISTA environment; a research summary alone does not need this workflow.
---

# VISTA Blender / Unreal workflow

Produce runnable changes with visible and behavioral evidence. Generated concepts,
Blender renders, compiled plugins and interactive Unreal results are different
deliverables; identify which ones were actually checked.

## Start from the current version

Read project rules and `git status`. Identify the live demo's actual project,
map and plugin, then the separate writing worktree owned by this task. Reuse
verified source assets and scripts before rebuilding them. Existing user
authorization applies; this skill does not add an approval gate.

Use fresh output directories and source/hash receipts. Keep external meshes,
textures, Blender/UE binaries and generated media outside Git in this workspace.
Commit scripts, manifests and findings. Follow asset use scopes; human-review-only
content does not automatically become eligible model input or benchmark data.

## Choose the relevant work

- **Design, rooms, props or materials:** read [scene-assets.md](references/scene-assets.md).
- **A person, cameras, hands, object interactions or liquids:** read
  [motion-fluid.md](references/motion-fluid.md).
- **Local execution commands and source examples:** read
  [local-runbook.md](references/local-runbook.md). These paths are version-specific;
  inspect their existence and receipts before reuse.
- **Outdoor terrain, foliage, daylight and running/jumping:** read
  [alpine-outdoors.md](references/alpine-outdoors.md). Keep the existing indoor
  demo and validate collision-driven movement in the new project.

For a broad quality upgrade, complete one representative room and interaction
first. Check near/far views, both player perspectives, contact, state transitions
and frame time. An empty-room screenshot cannot validate picking up or pouring.

Before exporting, check units, origins, axes, UVs, material channels, hollow
vessels, rig weights and collision proxies as relevant. The bundled helper reads
GLB structure without Blender:

```sh
uv run python /absolute/skill/path/scripts/inspect_glb.py /absolute/asset.glb
```

It verifies GLB structure and embedded references and reports geometry, materials
and skins. It does not prove visual quality, dimensions, watertightness, collision
behavior or natural motion.

## Finish with evidence and limits

Run existing checks and focused tests for changed behavior. Import into an
isolated UE project, read back saved bindings and inspect a native render before
describing something as verified in Unreal. NullRHI cannot validate water/shaders.
For GPU tests, inspect the actual device, not just the requested adapter index.

Provide absolute links to review media, source and receipts as relevant. Record
visible defects and unfinished coupling. Do not describe interpolation as motion
capture, a cylinder as fluid, an active Niagara component as a conservation test,
or a scripted consequence as a validated counterfactual experiment.
