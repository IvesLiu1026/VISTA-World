---
name: vista-workspace-handoff
description: Continue work in a migrated VISTA research workspace, resolve repo and scene ownership, and hand off verified development state. Use for VISTA workspace migration or continuation, not general server administration.
---

# Continue a VISTA workspace

Find the ancestor directory containing `workspace.json` and `bin/vista-workspace`.
Read its `AGENTS.md`, `.agent/CURRENT_STATE.md`, `.agent/WORKFLOW.md` and the target
repo's instructions. If launched directly in a repo, the workspace is normally
two parents above it. Resolve paths from the workspace, not historical source
host paths in old notes.

Keep three boundaries distinct: clean source repositories, immutable shared scene
assets, and independently editable projects. `bin/vista-workspace status --verify`
checks stored content. It does not validate new behavior or native rendering.

For 3D work, use `vista-blender-ue-workflow` when available and its target-host
runbook. For model evaluation, use `vista-remote-eval-runbook` when available;
observe the inference/oracle boundary. Otherwise use the repository's explicit
commands and contracts. Existing user authorization persists within its scope.

Before selecting a Sunshine scene, inspect the active runtime owner. Stable and
DEV entries share the VISTA slot; selecting one changes the displayed game.
Do not interrupt another task or assume the second GPU supports interactive
presentation. Inspect the actual project and process after launch.

Before claiming agent-tool continuity, verify discovered skills and initialized
MCP servers. A copied plugin cache is not an authenticated connection. Use the
workspace's MCP/plugin status ledger and preserve target login credentials.

End with a new handoff: branch, owned paths, changed behavior, checks, live runtime,
evidence locations and unfinished work. Preserve old runs and source drafts.
