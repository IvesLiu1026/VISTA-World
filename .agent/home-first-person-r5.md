# Home first-person body visibility R5

- Owner: Codex, solo implementer, 2026-09-08; no delegation.
- Request: empty hands visible at rest in first person, abdomen/lower body/feet visible when looking down, with natural transitions into existing interactions.
- Base: completed R4 4355a35bfd7ba87379548d51f591f9d90d316441.
- Branch/worktree: codex/vista-home-first-person-r5, /data/sysx/vista-world/worktrees/vista-home-first-person-r5.
- Owns: first-person presentation and pose code in unreal_plugins/VistaPhotorealReview/** in this worktree; new tools/{runtime,ue,blender}/vista_home_first_person_r5/**; focused tests, docs/design/vista-home-first-person-r5/**, world_packs/vista_home_first_person_r5/**, this record.
- Outputs: fresh attempts in /data/sysx/vista-world/runs/vista-home-first-person-r5-20260908a.
- Must not touch: R3/R4 source or asset outputs; preserved demo, live project-x/build-n, Sunshine apps/config/auth/services/input or :119; R6/R23; ports 8000/8001; other worktrees; canonical event/action datasets; shared engine installation.
- Runtime ownership: isolated build and NullRHI validation only; bounded CPU Blender preview if needed. Preserve live service PIDs and avoid a second GPU scene while the user's demo remains active. No promotion without the user releasing the preserved demo.
- Validation: native compilation; empty/held/retracting and first/third pose behavior; projected hands/abdomen/legs/feet and transitions at several pitches; actual fitted body preview; existing required contract/compiler tests and focused regression; source/demo integrity.
- Handoff: docs/design/vista-home-first-person-r5/implementation.md and a hash-bound delivery manifest.
- Status: implementation complete in project-c/build-c; 35 existing tests and 12 native NullRHI scenarios passed. Three previews-d images passed posed-surface visibility checks and manual inspection. Preservation verified 2,318 demo files and 2,357 unchanged R4 Content files. Native GPU appearance, self-shadow, FPS and the full action suite remain pending; no live demo promotion.
