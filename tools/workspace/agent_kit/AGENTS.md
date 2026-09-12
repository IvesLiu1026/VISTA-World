# VISTA research workspace entrypoint

This directory contains three independent repositories and external scene data.
Start with `.agent/CURRENT_STATE.md`, `.agent/WORKFLOW.md` and
`.agent/ACTIVE_WORK.md`. Those describe this host; old absolute paths in imported
research notes and historical specs describe their original host only.

Use the applicable repository's `AGENTS.md` and `.agent/RULES.md` before editing.
Use `bin/uv` for Python and `bin/codex-vista` for a workspace-aware Codex session.
The home-level agent kit is a fallback; this workspace's current map takes priority
for paths and runtime ownership. Existing user authorization applies to its stated
scope; do not repeatedly request it because an old runbook says "confirm".

Repositories:

- `repos/VISTA-World`: world contracts, shared Unreal source and scene tooling.
- `repos/VISTA-Web`: scenario authoring, natural-language plan editing and audit UI.
- `repos/EgoArgus`: maintained benchmark/evaluation source, not the old anonymous release.

Use isolated `codex/` worktrees under `worktrees/` for source edits. VISTA-Web
integrates through `dev`; World uses `codex/vista-home-villa-integration`.
Production/main changes require the user's explicit deployment instruction.
Preserve unrelated changes; stage explicit files. Never casually delete `runs/`,
frozen releases, asset blobs or another task's files.

The stable demo and editable DEV scene share one explicitly owned VISTA game/input
slot. Selecting one replaces the other process. Only the runtime owner changes
that slot. Other users' Sunshine instances, desktops and GPU processes are outside
scope. Keep external assets and host-local runtime settings out of source Git.

Use scene contracts and reviewed typed adapters for experiments. Gold labels,
hidden scene state, seeds and review notes are not model observation inputs.
Do not turn demo-only licensed assets into training/evaluation data.

Skills are installed separately from OAuth/app connections. Read
`.agent/MCP_PLUGINS.md` before claiming a plugin is usable. Never copy or print
authentication stores, API tokens, paired-client secrets or private keys.

Before finishing, record the owned branch, modified files, tests, actual runtime,
remaining defects and next action in a new `.agent/handoffs/` document. Update
the active-work registry; preserve previous evidence rather than overwriting it.
