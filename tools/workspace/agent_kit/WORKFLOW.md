# Continue development on the target host

## Enter

Run `bin/vista-workspace status`, inspect `.agent/ACTIVE_WORK.md`, then choose the
repository for the task. Run `git status --short --branch` in it. Source checkout
pins are in `manifests/`; an inventory is not permission to rewrite another task.
Read the nearest repository instructions. Historical spec checkboxes describe
their recorded revision, not proof that the current DEV build passed those tests.

The migration used shallow repositories. Fetch the required integration ref before
creating a worktree. Do not assume `main` is the accepted environment development
branch. Keep each repository's history separate and never force-update a dirty
checkout merely to match an upstream branch.

```sh
# From repos/VISTA-World; use a fresh task slug.
git fetch origin codex/vista-home-villa-integration
git worktree add ../../worktrees/TASK -b codex/TASK FETCH_HEAD
```

For VISTA-Web, use its `dev` branch instead. For EgoArgus, base a topic branch on
the maintained release's accepted revision; no model run is implied by checkout.
Declare owned paths and runtime ownership before writing. Use subagents only
when the current user/instructions authorize delegation.

## Build and review a scene

Use `bin/vista-workspace materialize --scene SCENE --project NEW_PROJECT` to create
an independent edit target. `assets/sha256` and historical release payloads are
reference inputs, not editing directories. Modify common Unreal source in the
World worktree, then build against the scene's recorded UE build into a fresh
package. Copy only reviewed build outputs into the editable project.

Select the DEV Sunshine entry to view that project. The launcher inventories the
current edited payload and stores its hash manifest with the run. Re-selecting
unchanged content resumes the same game; changed payloads start a new run. Ending
the Moonlight stream leaves the scene running. Use the original stable demo entry
to return to the frozen scene.

Blender geometry/material exports, compiled C++, native UE rendering, virtual
keyboard/mouse delivery, and the Windows Moonlight view are distinct checks.
After meaningful changes inspect first and third person, movement/contact, object
state, relevant liquids and frame time. Record what was actually verified.
No GPU 1 interactive presentation acceptance is implied by its presence.

## Validate and hand off

World baseline checks:

```sh
uv sync --frozen
PYTHONPATH=tools uv run python -m unittest \
  tools.tests.test_vista_playable_home_contracts \
  tools.tests.test_vista_playable_home_compiler -v
git diff --check
```

Add focused tests for changed behavior. VISTA-Web frontend edits require
`npm run build` in its frontend directory; development uses 8001 and does not
modify production 8000. Model/API calls and dataset writes use the existing
task's explicit authorization; otherwise prepare the concrete run before asking.

Record branch/commit, source scene, payload digest, native evidence, known defects
and next step in `.agent/handoffs/`. Commit named source files, open/review a PR
against the appropriate integration branch, and merge only within authorization.
Do not include binary assets, generated media, runtime logs or credentials in Git.
