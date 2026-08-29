# VISTA Human Visual Package and PSO Runbook

Status: host-side foundation only

Source milestone: sealed City Sample/HSSD human visual R3

Runtime ownership: none in this change

This lane turns the sealed R3 editor project into a future Linux Development
package with a human-recorded Vulkan PSO cache. The checked-in tools currently
plan and verify the lane. They do not materialize a project, run Unreal/UAT,
launch a GPU process, create an external attempt, or inspect pixels.

## Fixed source and boundary

The only accepted source is:

- combined receipt SHA-256:
  `91dfaa32e1efc66747c93dc7e891e4ab4ed6c80aca08178fae11af9018544d5d`
- combined content digest:
  `588858a72f12287a7e46232cc0a97433e762c0ba04a374567095eb525ae9c298`
- provider: `citysample_crowd_visual_demo_v1`
- map:
  `/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome`
- engine: UE `5.7.3`, changelist `50162420`
- platform/configuration/shader format:
  `Linux` / `Development` / `SF_VULKAN_SM6`

The legal scope is an exact closed object, not a free-form note:

- private, noncommercial research only;
- Epic/UE-only content entitlement confirmed;
- no source UAsset redistribution;
- all external assets remain outside Git;
- MetaHuman/City Sample presentation is human-operated only;
- excluded from the VISTA dataset and database;
- excluded from AI/VLM training, testing, evaluation, and review.

No agent or VLM may drive the capture traversal, consume pixels, sign visual
acceptance, or convert this human-only lane into dataset evidence. Text logs,
hashes, command plans, and process-free receipt verification remain allowed.

## Package-only plugin projection

The R3 source descriptor is accepted as source evidence even though it still
enables editor tools. It must never be packaged unchanged. A disposable project
projection has exactly these enabled project plugins:

1. `VistaPlayableHome`
2. `HairStrands`
3. `MassGameplay`
4. `RigLogic`
5. `SunPosition`

It must explicitly disable:

- `PythonScriptPlugin`
- `EditorScriptingUtilities`
- `Interchange`
- `AndroidFileServer`

An unknown enabled project plugin is a terminal refusal. Transitive runtime
dependencies are not implicit permission: the materializer must emit the
canonical `final-cook/plugin-closure-receipt.json` and sidecar. The receipt must
prove `DisableEnginePluginsByDefault=true`, an exact Game/Linux/Development
resolved closure, no unknown plugin, and the exact descriptor bytes. The final
receipt verifier refuses the package when any of that evidence is absent.

There is no hard-coded transitive closure. Both planning and final receipt
verification scan the actual project and pinned UE 5.7.3 `.uplugin` descriptor
graph, hash every reachable descriptor, apply Game/Linux/Development platform,
target, configuration, and optional-reference rules, then derive the closure.
The closure receipt is evidence only: changing its reported plugin list cannot
change the independently derived result.

Both disposable projects are independently anchored to sealed R3 through
`seed-cook/source-projection-manifest.json` and
`final-cook/source-projection-manifest.json`. The verifier enumerates every R3
static project file and every projected `.uproject`, Config, Content, Plugins,
and Source/code file, recording
relative path, mode, size, SHA-256, device, inode, and link count through an
FD-bound seal. Every source and projected file must have one safe link, and a
projected file must never share its device/inode pair with its source; every
non-transformed file must still be an exact byte copy. In particular,
`Plugins/VistaPlayableHome/VistaPlayableHome.uplugin` must match sealed R3
bytes; a modified plugin cannot authorize itself by regenerating the closure or
final receipt. The only approved deltas are:

- exact replacement of the `.uproject` descriptor;
- one exact PSO block appended to sealed `Config/DefaultEngine.ini`;
- creation of exact `Config/DefaultGame.ini` PSO settings.

Any other missing, additional, changed, hardlinked, symlinked, or path-replaced
static file is refused. The seed receipt and the human-capture receipt each bind
the seed manifest and independently rederive it before acceptance, so a seed
project changed after cook cannot become capture input. Verification and
launch-plan publication rederive these
identity and content pins rather than trusting destination-reported evidence.
The manifest, closure, and final receipt bind each other by their actual receipt
hashes.

This matters because the real graph is substantially larger than the project
roots. For example, HairStrands reaches Niagara, GeometryCache, DeformerGraph,
Dataflow, and ComputeFramework; MassGameplay reaches ZoneGraph,
ZoneGraphAnnotations, SmartObjects, StateTree, and DataValidation; RigLogic and
IKRig reach ControlRig and FullBodyIK; and MetaHumanCharacter has a broad
transitive graph. In the pinned engine, Niagara's unrestricted dependency on
`PythonScriptPlugin` conflicts with this lane's denylist. MetaHuman dependencies
also reach denied editor plugins, and one reachable descriptor currently has a
malformed target restriction. The planner therefore correctly refuses the real
R3 graph today. Do not cook until a reviewed plugin/dependency projection or a
pinned UBT target receipt resolves those conflicts without weakening policy.
Plugin-reference `HasExplicitPlatforms=true` follows UE 5.7 UBT semantics:
`PlatformAllowList` itself must include `Linux`; `SupportedTargetPlatforms`
cannot substitute. Applicable circular dependencies are rejected with the
complete DFS recursion-stack chain, matching UBT's circular-dependency meaning.

## Stable-key contract

The package projection must add the closed settings emitted by
`stable_key_config_contract()`:

- `bShareMaterialShaderCode=True`;
- `NeedsShaderStableKeys=True`;
- shader format is only `SF_VULKAN_SM6`;
- pipeline file cache enabled;
- runtime PSO precaching enabled;
- full Development validation enabled;
- normal packaged runs do not log PSOs;
- the cache file is `VistaPlayableHome`, game version `1`, sorted by first use.

The capture command temporarily enables `-logpso`,
`r.ShaderPipelineCache.LogPSO=1`, and bound-PSO saving. The final launch plan
contains none of those capture switches.

## Receipt DAG

```text
sealed_r3_source
  -> seed_cook
  -> human_capture
  -> expand
  -> final_cook
  -> final_package_receipt
```

Every node has a distinct closed schema, canonical JSON receipt, SHA-256
sidecar, explicit parent receipt pins, and append-only terminal failures.

| Node | Required evidence | Executor boundary |
|---|---|---|
| `seed_cook` | sealed R3→seed projection manifest, Linux Development archive, and at least one nonempty `.shk` | authorized UAT operator |
| `human_capture` | reverified seed projection edge, nonempty `*.rec.upipelinecache`, and signed coverage ledger | human operator only |
| `expand` | nonempty `VistaPlayableHome_SF_VULKAN_SM6.spc` and log with nonzero PSOs/stable keys | authorized commandlet operator |
| `final_cook` | new archive and exact canonical baked-cache basename | authorized UAT operator |
| `final_package_receipt` | complete archive rehash plus source/PSO receipt pins | host-side verifier |

Zero matches, empty output, rejected PSOs, stale stable keys, a failed command,
or a broken receipt edge is terminal failure. Do not relabel or overwrite that
attempt; create a new `attempt-*` after diagnosis.

Every stage uses one fixed subtree of the same protected, canonical, fresh
`attempt-*`; arbitrary paths and symlinks are refused:

```text
attempt-*/
  seed-cook/       # seed project+projection manifest, UAT/archive/.shk, receipts
  pso-capture/     # isolated user cache, .rec.upipelinecache, ledger, log, receipt
  expand/          # .spc, log, receipt+sidecar
  final-cook/      # final project/input .spc, closure, archive/cooked cache, receipts
```

The final verifier reopens every stage receipt and sidecar, recomputes every
parent SHA edge and exact argv hash, rehashes tools/logs and all PSO artifacts,
then recomputes the archive. A plausible standalone final JSON is insufficient.

Logs are stage-specific semantic evidence, not opaque blobs. Seed and final UAT
logs require `BUILD SUCCESSFUL` immediately followed by the terminal
`AutomationTool exiting with ExitCode=0 (Success)` summary and reject
failure/error/crash signatures anywhere, including `Cook completed with
errors.`, `No stable keys found.`, or `No PSOs were saved.` before an otherwise
successful footer. A benign count such as `0 PSOs rejected` is not itself a
zero-output contradiction. Human capture requires a whole-word nonzero native
`Saved <n> PSOs` line and terminal clean engine exit; `NotSaved`, `No PSOs
saved.`, rejection/discard text, nonzero exit, cook failure, fatal error, or
segfault refuses the receipt. Expand separately binds
the exact `.rec.upipelinecache` glob and exact `.shk` glob, requires nonzero
matches, unique stable-key count, loaded PSO count, and a native nonzero
binary-PSO write line naming the exact `.spc` output. Zero matches/counts, every
rejected/rejecting/rejection spelling, `No stable keys found.`, obsolete/bad
PSOs, loading errors, missing/not-written/zero summaries, empty inputs, crash
text, success followed by failure, or a wrong path fails. The exact output write
summary must be the terminal non-whitespace record.
The final cooked cache basename is exactly
`VistaPlayableHome_SF_VULKAN_SM6.stable.upipelinecache`; arbitrary glob matches
are not accepted.

## Generate the dry-run plans

Choose a new absolute `attempt-*` path that does not exist. The following only
validates inputs; it prints canonical JSON only after the plugin graph is
conflict-free. Against current R3 it is expected to refuse at descriptor-graph
preflight without creating the attempt. Shell redirection would be an explicit
operator write and is intentionally not performed by the tools.

```bash
cd /home/yhliu/VISTA-World

PYTHONPATH=. uv run python \
  tools/ue/vista_playable_home/human_visual_package_receipt.py \
  --combined-receipt \
  /data/sysx/vista-world/runs/vista-action-world-r1/citysample-human-demo-r3-20260829/human-visual-demo-combined-receipt.json \
  --run-uat \
  /mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Build/BatchFiles/RunUAT.sh \
  --editor-cmd \
  /mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Binaries/Linux/UnrealEditor-Cmd \
  --attempt-root \
  /data/sysx/vista-world/runs/vista-action-world-r1/human-package-pso-r1/attempt-001
```

Use the same arguments with `human_visual_pso_seed.py` to emit the complete
capture/expand/final-cook DAG and all closed argv arrays:

```bash
PYTHONPATH=. uv run python \
  tools/ue/vista_playable_home/human_visual_pso_seed.py \
  --combined-receipt \
  /data/sysx/vista-world/runs/vista-action-world-r1/citysample-human-demo-r3-20260829/human-visual-demo-combined-receipt.json \
  --run-uat \
  /mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Build/BatchFiles/RunUAT.sh \
  --editor-cmd \
  /mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Binaries/Linux/UnrealEditor-Cmd \
  --attempt-root \
  /data/sysx/vista-world/runs/vista-action-world-r1/human-package-pso-r1/attempt-001
```

Both CLIs intentionally expose no `--execute`, `--launch`, `--apply`, or free
argument passthrough. The returned UAT and Unreal commandlet argv arrays are
future operator inputs after runtime ownership and external-write approval.
Each invocation reopens and hashes the pinned `/usr/bin/bwrap` bytes and size;
the packaged-launch planner repeats that check while building its plan. Merely
recording a declared constant without checking installed bytes does not pass.
It also reloads the canonical final receipt, every sidecar and DAG node, and all
archive bytes immediately before emitting a launch plan. If anything changed
after `load_inputs`, planning fails; `archive_rehashed_during_plan=true` is only
emitted after that second verification succeeds.

## Authorized future execution sequence

This section is an acceptance checklist, not authorization to execute it.

1. Assign one owner for UE/UAT/GPU `0`, display `:118`, and the new external
   attempt. Confirm the current Sunshine/UE owner has handed those resources
   over.
2. Resolve the currently reported descriptor-graph conflicts through reviewed
   source/plugin changes or pinned UBT evidence. Do not disable this graph gate,
   remove a denylist entry, or hand-author a smaller closure in a receipt.
3. Materialize fresh seed and final project copies only at
   `seed-cook/project` and `final-cook/project`, without modifying R3. Copy only
   the receipt-pinned payload, replace both descriptors with the exact
   package-only projection, and apply the stable-key config exactly.
   Generate both source-projection manifests from sealed R3 and the materialized
   seed/final projects; do not copy hashes from the destination into source
   fields. Reverify the seed manifest before sealing both seed cook and capture.
4. Recompute the disposable project tree and source receipt immediately before
   invoking the plan's `seed_cook.argv` with `shell=False` and a sanitized
   environment.
5. Seal UAT success, the complete seed archive, and all `.shk` files. A process
   exit code alone is not a receipt.
6. Launch the seed package only through the plan's isolated human-capture argv.
   A human traverses all six rooms and exercises walk, sprint, jump, crouch,
   pickup, and drop. Close the pipeline cache cleanly before sealing the capture.
7. Seal every recorded `.rec.upipelinecache` and the human coverage ledger.
   Screenshots are neither required nor accepted by the host-side verifier.
8. Run the exact expand argv. Require nonzero loaded recorded PSOs, nonzero
   stable keys, no rejected/obsolete input, and a nonempty
   `expand/VistaPlayableHome_SF_VULKAN_SM6.spc` output.
9. Copy those exact verified bytes to the fixed final-project pipeline-cache
   input path, seal both records, and generate the exact resolved-plugin closure
   receipt. Then run the exact full `final_cook.argv`. Do not use iterative
   cooking, skip-cook, or reuse the seed archive.
10. Prove the final cook baked a nonempty
   `VistaPlayableHome_SF_VULKAN_SM6.stable.upipelinecache`. Seal the final archive
   and write `final-cook/human-visual-final-package-receipt.json` plus its exact
   sidecar.
11. Run `human_visual_packaged_launch.py --package-receipt ...` to re-hash the
    archive and emit the fixed `:118`/GPU `0`/1920x1080 launch plan. Actual launch
    still belongs to the runtime owner.

## Persistent packaged cache

The final launch plan derives this namespace solely from the final package
receipt SHA-256:

```text
/data/sysx/vista-world/cache/human-visual-packaged/<receipt-sha256>/
  ddc/
  user/
    xdg-cache/
    xdg-config/
    xdg-data/
```

Every directory must be a real, non-symlink directory owned by the launching
EUID with exact mode `0700`. The dry-run planner names these paths but never
creates them. A future launcher must revalidate the final receipt and entire
archive immediately before process creation.

## Acceptance gates

Promotion remains false until all of these have independently closed:

- every receipt DAG edge is content-hash bound;
- archive and fixed launcher/executable/pak pins re-hash exactly;
- stable keys, recorded cache, expanded `.spc`, and baked cache are nonempty;
- all six rooms and fixed interaction set are present in the human ledger;
- a human accepts visuals and interactions in Moonlight/Sunshine;
- 1920x1080 at 100% screen percentage on GPU `0`;
- median frame rate at least 55 fps;
- 1% low at least 30 fps;
- p95 frame time at most 25 ms;
- no stall over one second;
- no new PSO hitch after the warm pass;
- archive tree is unchanged after smoke;
- no agent/VLM/pixel-review or VISTA dataset/database path was used.

The plan and receipts keep these claims false by default: runtime visual
acceptance, interaction acceptance, photoreal character acceptance, GTA-level
quality, PSO acceptance, and performance acceptance.

## Failure handling

- Source hash/content drift: stop; do not silently adopt a newer R3 project.
- Unknown or enabled editor plugin: stop before materialization/cook.
- Existing or symlinked attempt path: choose a fresh append-only attempt.
- Tool/Build.version mismatch: stop; do not substitute another UE install.
- Empty `.shk` or recorded cache: retain the failed attempt and repeat in a new
  attempt after correcting stable-key config or human coverage.
- Expand zero-match/rejection: retain logs and inputs; never weaken the gate.
- Final archive or artifact drift: do not launch.
- Human visual rejection or missed performance gate: preserve the package as
  rejected evidence; its claims remain false.

## Source files and validation

- `tools/ue/vista_playable_home/human_visual_package_receipt.py`
- `tools/ue/vista_playable_home/human_visual_pso_seed.py`
- `tools/runtime/vista_playable_home/human_visual_packaged_launch.py`

Focused validation:

```bash
PYTHONPATH=. uv run pytest -q \
  tools/tests/test_vista_playable_home_human_visual_package_receipt.py \
  tools/tests/test_vista_playable_home_human_visual_pso_seed.py \
  tools/tests/test_vista_playable_home_human_visual_packaged_launch.py

uv run ruff format --check \
  tools/ue/vista_playable_home/human_visual_package_receipt.py \
  tools/ue/vista_playable_home/human_visual_pso_seed.py \
  tools/runtime/vista_playable_home/human_visual_packaged_launch.py \
  tools/tests/test_vista_playable_home_human_visual_package_receipt.py \
  tools/tests/test_vista_playable_home_human_visual_pso_seed.py \
  tools/tests/test_vista_playable_home_human_visual_packaged_launch.py

uv run ruff check <the same six Python files>
git diff --check
```
