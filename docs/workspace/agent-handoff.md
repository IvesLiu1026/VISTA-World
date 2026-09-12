# Agent continuity and Sunshine development entry

The workspace now has an explicit agent entrypoint, a versioned handoff skill,
and an editable-scene selector for the existing VISTA streaming slot. Previously
only committed repository rules/specs and clean source snapshots were copied;
user skills and MCP/plugin runtime discovery were not yet synchronized.

## Entry points

Start a new agent session with `WORKSPACE/bin/codex-vista`. With no arguments it
opens at the workspace root, puts workspace tools on PATH, and preserves the
target's existing Codex authentication and model preferences. It does not copy
source-host authentication stores, conversations, session databases or API keys.

Read `WORKSPACE/AGENTS.md`, `.agent/CURRENT_STATE.md`, `.agent/WORKFLOW.md` and
`.agent/ACTIVE_WORK.md`. `.agent/SPEC_INDEX.md` links to the three repositories'
tracked planning documents; `.agent/MCP_PLUGINS.md` distinguishes installed
plugins, accessible apps, initialized MCP tools and pending authentication.
Use repo-specific instructions after the workspace overview.

The target has workspace-local Codex CLI **0.153.4**, Blender **4.5.8 LTS**
and Node.js **22.22.2** with npm.
The existing global CLI was left available. Fourteen user skills were installed,
with previous skill directories backed up outside discovery. Five system-skill
reference copies remain in the portable kit; the CLI supplies its system skills.
The installed Blender/UE workflow routes the migrated host to current workspace
paths and marks older source-host examples as historical references.

## Sunshine integration

`VISTA Villa DEV` is an additional application entry. It runs the independently
editable `alpine-villa-dev-r1` project, not the frozen R3 payload. Existing
`Desktop`, `VISTA Alpine Villa R3` and `VISTA World` entries are preserved.

`dev_stream.py` takes an explicit workspace, project and host profile. The private
`hosts/sunshine.local.json` binds the reviewed adapter files by digest and names
the existing VISTA-owned game/input slot and display. Host settings are not in
the source repository. No machine address, fixed release date or absolute
original-host directory is embedded in the new selector.

The selector checks the host profile, adapter digests, supported GPU, project
and matching Unreal build before stopping a process. It inventories current
edited files and writes a new payload receipt with each run. Re-selecting the
same project and payload keeps the current game. Selecting modified content
relaunches it. Stream disconnect leaves the scene running; selecting the stable
R3 entry returns to the original release. Stable and DEV entries share one
interactive slot and cannot be used simultaneously.

Development runs and shader caches go under workspace `runs/` and `cache/unreal/`.
The existing selection pointer is updated only for compatibility with the shared
slot; its `runtime_location` identifies workspace development logs. This lane
remains human development, not sealed model evaluation. GPU 1 presentation is
still not accepted.

## Verified on the target, 2026-09-12

- Fourteen installed user skills were discovered, including `nlplab-admin`,
  `vista-blender-ue-workflow` and `vista-workspace-handoff`; discovery reported
  **zero skill errors**. The complete discovered local/system/plugin-skill set
  contained 29 entries at the time of the check.
- The existing account exposed 11 accessible apps, including GitHub, Higgsfield,
  Figma, Canva, Google Drive, Notion, Slack and SciSpace.
- The app MCP initialized **451 tools**. The OpenAI documentation MCP initialized
  **5 tools** without requiring authentication. These are discovery checks, not
  paid generation tests or blanket permission to write to external services.
- Sepia **0.9.0** was installed through its public marketplace pinned to source
  commit `c6d914f14884e4777d2a5093cf318ead6e967854`.
- The Cloudflare API MCP reports **not logged in** and zero tools. Its OAuth flow
  must be completed by the account owner when that integration is needed. Other
  account app connections were reused; no credentials were migrated.
- Blender factory-startup/background Python executed successfully. No Blender
  GPU render was run during installation.
- DEV native rendering and first/third-person switching were visually inspected.
  The active UE process's project path points into the editable workspace, and
  NVIDIA process inspection confirms physical **GPU 0**.
- Keyboard delivery was exercised through the pinned Sunshine virtual keyboard,
  guarded relay and XTEST, rather than only injecting directly into the window.
- The preserved stable R3 native launch and return to DEV were checked. Selecting
  unchanged DEV content again preserved its process identity.

The original lighting and character limitations remain visible; this migration
does not claim new photorealism or animation fixes. At handoff, Windows Moonlight
pairing/client verification is a separate outstanding user step. The VISTA
Sunshine instance initially had no administrator credentials or paired clients;
no default administrator password was created.

## Future maintenance

Keep source revisions, skill-file digests and tool versions in `manifests/`.
New skills should be self-contained and validated before installation. Back up
existing skill directories before replacement, and do not duplicate the same
skill into multiple discovery roots. Do not copy plugin cache metadata as a
substitute for installation or OAuth; verify runtime discovery after updates.

Official references: [local MCP configuration](https://learn.chatgpt.com/docs/extend/mcp),
[skill discovery](https://learn.chatgpt.com/docs/build-skills), and
[plugin installation and authentication](https://learn.chatgpt.com/docs/plugins).
