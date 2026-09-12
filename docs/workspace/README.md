# Portable VISTA research workspace

The research workspace separates clean source checkouts, reusable scene content,
editable Unreal projects, published papers, and disposable execution state. It
can coexist with a running demo release. None of the workspace commands stop,
restart, or reconfigure Sunshine, Unreal, input permissions, or another process.

```text
workspace/
  repos/          VISTA-World, VISTA-Web, EgoArgus (independent shallow Git repos)
  papers/         version-pinned PDF, source archive, extracted TeX, SHA256 manifest
  assets/sha256/  one immutable blob per unique file content
  scenes/        versioned scene manifests referring to shared blobs
  projects/      independent editable projects materialized on demand
  hosts/         host-local settings; never put credentials here
  manifests/     source revisions and transfer provenance
  cache/         rebuildable caches, separate from source and assets
  runs/          append-only evidence, compiled plans and results
  state/         local operational state
```

Keep large video datasets, checkpoints and backups in the user's approved NAS
space. NAS filesystem free space is shared capacity, not a personal quota. Do not
copy another user's files or follow source NAS symlinks during migration.

## Initialize and import scene packs

Run these from the VISTA-World repository. All arguments are explicit: the helper
does not contain a machine address, release date, workspace location or scene ID.

```sh
uv run --no-project python tools/workspace/workspace.py --root /PATH/workspace init
uv run --no-project python tools/workspace/workspace.py --root /PATH/workspace \
  import-catalog --catalog /PATH/release/catalog.json --sha256 CATALOG_SHA256
uv run --no-project python tools/workspace/workspace.py --root /PATH/workspace status --verify
uv run --no-project python tools/workspace/workspace.py --root /PATH/workspace \
  materialize --scene SCENE_VERSION --project NEW_EDITABLE_PROJECT
```

The importer checks the source inventory and each file's digest before publishing
its scene manifest. Source payloads and the live demo stay untouched. Repeat
imports of identical content reuse verified blobs. A changed scene needs a new
version ID. Existing projects are never overwritten. Interrupted imports may
leave verified, unreferenced blobs; retry is safe and no automatic garbage
collection is performed. A partially materialized project is retained for
inspection; retry with a new project ID.

Blobs are copied into the store before becoming read-only. Materialization uses
copy-on-write reflinks when supported, independent copies otherwise. Editable
projects never share a writable inode with either the blob store or the original
release. Deduplication reduces the new store size; it does **not** reclaim disk
space occupied by preserved historical releases. Editable projects and `.git`
objects also take space and must be included in actual disk accounting.

## Source repositories and papers

`tools/workspace/snapshot_repo.py` builds a clean shallow checkout at an exact
commit using local Git objects. It never reads dirty source files or copies the
source Git configuration, keys, hooks, environments or caches. Supply a public,
credential-free GitHub origin and write the receipt outside the checkout. Use
VISTA-Web's accepted `dev` revision and VISTA-World's accepted environment
integration revision. EgoArgus should use the lab's maintained release repository,
not the historical anonymous review scaffold.

The sparse worktree omits legacy research notes, external symlinks, generated
logs and local environment files. The shallow Git objects still contain tracked
files from that upstream commit: this is a development checkout, **not a secrets
scrubber or a redacted public distribution**. Review the selected tree for
credentials before transferring it. No complete source history is copied.
Each repo keeps its own branch and dependency environment. Existing remote
authentication must be configured separately by the user when a future Git push
needs it; migration does not copy SSH keys or tokens.

`paper_snapshot.py --arxiv VERSION --output NEW_DIRECTORY` downloads both the
published PDF and corresponding TeX source with a version and file digests. It
extracts regular source files only and does not run TeX or source scripts.
Uncommitted local drafts are preserved at the source machine. The paper library
is for research context; it is not part of a model's prediction input.

## Extension boundaries

- **VISTA-World:** shared world contracts, scene compiler, Unreal plugins,
  interaction/event runtime and runtime adapters.
- **Scene packs:** room layout, object placement, material/assets references,
  scene-specific events, and versioned engine/build requirements.
- **VISTA-Web:** scenario authoring, natural-language plan editing and audit UI;
  integrate through an explicit adapter, rather than importing its database or
  webserver into Unreal.
- **EgoArgus:** evaluation inputs, modality conditions and scoring; inference
  receives only the authorized observation/dialogue projection. Gold labels,
  seeds, hidden scene state and post-hoc reviews stay out of prediction inputs.
- **Host/runtime adapters:** engine discovery, GPU/display, input and streaming.
  Keep each host's bindings outside source and scene content. Only a tested
  adapter may activate a scene; merely materializing it does not validate runtime.

Add a scene by producing a new versioned catalog entry and importing it into the
existing store. Reuse the relevant shared plugin source from `repos/VISTA-World`;
build it against the scene's recorded engine build before replacing binaries in
an editable project. The `Source/` and `Binaries/` inside an imported payload are
historical build inputs, not the common-core source of truth. Do not overwrite a
live payload or blindly apply the newest plugin to an older scene revision.

This change provides the storage/source/workspace boundary. It does not claim
that all historical character implementations have been merged into one plugin,
that a generic NL-to-motion API is complete, or that demo content is accepted for
sealed evaluation. Shared behavioral refactors and VISTA/EgoArgus adapters need
their own typed contracts and runtime tests. The existing validated GPU/display
restrictions remain in force; two installed GPUs do not imply two accepted
interactive streams.

## Development checks

In `repos/VISTA-World`:

```sh
uv sync --frozen
PYTHONPATH=tools uv run python -m unittest \
  tools.tests.test_vista_playable_home_contracts \
  tools.tests.test_vista_playable_home_compiler \
  tools.tests.test_research_workspace -v
```

Compile a scene plan into `runs/`, never into a frozen asset pack. Preserve run
evidence; caches can be rebuilt but should only be removed during explicit
maintenance when no active process owns them. Source/code migration does not
start web services, download evaluation videos, train a model or make API calls.
