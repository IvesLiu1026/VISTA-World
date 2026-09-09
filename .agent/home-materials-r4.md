# Home material fidelity R4 and retained demo

- Owner: Codex, solo implementer, 2026-09-08. No delegated agents.
- User request: keep today's working Home demo available for imminent operation; develop more realistic textured surfaces using suitable SimWorld + VISTA asset references.
- Base: verified Home R3 fc68a26236f53245b242283097576e93fa9a61c4.
- Worktree: /data/sysx/vista-world/worktrees/vista-home-materials-r4, branch codex/vista-home-materials-r4.
- Owns: new tools/{blender,ue,runtime}/vista_home_materials_r4/**, world_packs/vista_home_materials_r4/**, focused tests, docs/design/vista-home-materials-r4/** and this ownership record.
- Asset outputs: /data/sysx/vista-world/runs/vista-home-materials-r4-20260908a; demo backup: /data/sysx/vista-world/home/demo-r3-20260908.
- Must not touch: R3 source checkout, live project-x/build-n, Sunshine apps/config/auth/services/input, :119 camera or input, production 8000, review 8001, other live R6/R23 projects, canonical event/action datasets, and other sessions' work.
- Runtime: preserve all existing game/service PIDs. No second GPU UE scene during the user's demo. Local asset preparation and CPU-only previews with bounded worker count; separate NullRHI authoring project where feasible.
- Inputs: read-only existing SimWorld + VISTA donor manifests/materials and native evidence. Preserve donor provenance and use restrictions. The retained catalog has wood/wool but lacks suitable wall/cotton surfaces; add a small explicit set of free CC0 maps from official Poly Haven downloads. No paid model/image/video generation or uploads.
- Validation: source and demo hashes; per-part geometry/bounds/topology preservation; UV/material coverage and map colorspaces; inspect CPU-rendered material previews; required contract/compiler checks; native import in an isolated project if feasible without GPU use.
- Handoff: docs/design/vista-home-materials-r4/implementation.md and the new run's delivery receipt.
- Status: complete material-authoring handoff. Selected project-e imported and saved with NullRHI; verify-saved-e.json passed for 207 slots, 21 connected photo material graphs, 18 textures and two character meshes. All 2,318 live demo and backup files match the lock; Sunshine app and service PIDs/start times unchanged. Six CPU Blender previews inspected. 35 required/focused tests passed. Native GPU appearance, full action replay and FPS acceptance remain pending; R3 remains the only Home demo entry.
