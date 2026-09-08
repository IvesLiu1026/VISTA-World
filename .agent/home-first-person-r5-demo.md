# Isolated R5 Sunshine demo

- Owner: Codex, solo implementer, 2026-09-08.
- Authorization: user explicitly requested an isolated playable demo of R5 while retaining the original demo. This extends the earlier R5 implementation-only scope to installing its app entry, selecting the Home runtime, native GPU review and Sunshine app reload.
- Worktree/branch: /data/sysx/vista-world/worktrees/vista-home-first-person-r5, codex/vista-home-first-person-r5.
- Owns: tools/runtime/vista_home_first_person_r5/{launch_demo.py,smoke_demo.py,test_launch_demo.py} and focused tests; the R5 worktree's shared review launcher DDC allowlist; docs/design/vista-home-first-person-r5/demo.md; world_packs/vista_home_first_person_r5/demo.json; this record.
- Runtime ownership: one selected Home process/input relay on :119; a new VISTA Home R5 Sunshine app and its isolated runtime/profile/cache; Sunshine service reload for the new entry. Original app definitions remain identical. Use the existing revision-aware Home service slot so R3 and R5 cannot compete for input/GPU at once.
- Preserve: R3/R4 project assets and original source worktrees, R3 launch profile and backup, all unrelated Sunshine entries, credentials/auth, R6/R23, production/8000/8001 and canonical datasets.
- Outputs: fresh /data/sysx/vista-world/runs/vista-home-first-person-r5-demo-20260908a.
- Validation: launcher safeguards, separate runtime paths, native GPU hands/downward body/Tab/grab/drop and room entry checks, R3 rollback launch then R5 selection, original project/app integrity.
- Status: VISTA Home R5 is installed, native GPU initialized and selected by Moonlight (app ID 1722879117). 14 launcher/ownership tests passed; 2,318 R3 source/backup files and six original app definitions are unchanged. Native keyboard smoke was interrupted by concurrent client input and is not a pass; live receipts record successful cup pickup and placement. Automated inputs stopped and the user's R5 control is retained. Full GPU body-view/action acceptance and native R3 rollback remain pending.
- Handoff: docs/design/vista-home-first-person-r5/demo.md, run live-confirmation.json and preservation.json; no automatic reset, switch or further input after handoff.
