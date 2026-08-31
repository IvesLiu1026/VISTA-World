# MakeHuman CC0 R15 detail-action UE import

This lane turns the already generated, round-trip-verified R15 FBXs into 18
fresh UE assets: nine `AnimSequence` packages and nine typed-notify
`AnimMontage` packages. It is isolated from R8 and writes only under:

```text
/Game/VISTA/MakeHumanCC0/R15/DetailActions
```

It does not modify or restart the current live project, Sunshine, Pixel
Streaming, or a GPU service. A successful import is still development-only,
unaccepted, and nonpromotable until runtime and human-motion review pass.

## Pinned source authority

The host and commandlet both pin the same immutable source attempt:

```text
/data/sysx/vista-world/runs/vista-action-world-r1/
  makehuman-cc0-detail-actions-r15-source-r1-20260901b
```

- worker receipt SHA-256:
  `6e0eee885f50c9eb8d62de544ec6e4c021c19f5ff84dbc3e43794787ff4b0189`
- worker receipt size: `17089` bytes
- worker receipt content digest:
  `107a32156ac12422e0899dfac4503518adac1b9a8ce78dde8d79e96ac39847a8`
- plan content digest:
  `424830fc53f6d5a7f01dc1e26a371a7fa147e016174b45c0b25df1b72fcd2ea9`
- profile content digest:
  `fb88d2cdfe810226d84b9111cbe99ad7c13842cab0e60c4af48354fe5bc02384`

The nine FBX SHA-256 and size pins are compiled into
`makehuman_cc0_detail_actions_r15_contract.py` and independently repeated in
the sandbox commandlet. The import fails before mutation if any byte differs.

## 1. Read-only preflight

From the VISTA-World checkout:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. uv run python -m \
  tools.ue.vista_playable_home.run_makehuman_cc0_detail_actions_r15_import \
  plan \
  --attempt-name makehuman-cc0-detail-actions-r15-ue57-dev-r1-20260901a
```

Before a fresh plugin package exists, the expected status is:

```text
blocked_pending_fresh_compiled_plugin_authority
```

Planning performs no writes and never launches Unreal.

## 2. Build a fresh plugin package

The package must be built from the reviewed commit that contains
`VistaPlayableHomeCc0R15DetailActionLibrary`. Use a new append-only output path;
do not reuse the prior R6 or pre-R15 BuildPlugin package.

```bash
/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Build/BatchFiles/RunUAT.sh \
  BuildPlugin \
  -Plugin="$PWD/unreal_plugins/VistaPlayableHome/VistaPlayableHome.uplugin" \
  -Package=/data/sysx/vista-world/runs/vista-action-world-r1/\
playable-actions-r2-plugin-build-r15-20260901a \
  -TargetPlatforms=Linux
```

Locate the packaged `VistaPlayableHome` directory, then record its exact tree
projection without changing it:

```bash
PLUGIN_ROOT=/data/sysx/vista-world/runs/vista-action-world-r1/\
playable-actions-r2-plugin-build-r15-20260901a/HostProject/Plugins/VistaPlayableHome

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. uv run python - "$PLUGIN_ROOT" <<'PY'
import json
import sys
from pathlib import Path

from tools.ue.vista_playable_home import build_home

tree = build_home.snapshot_tree(Path(sys.argv[1]), "fresh R15 BuildPlugin")
print(json.dumps({
    "root": str(Path(sys.argv[1]).resolve()),
    "tree_sha256": tree.sha256,
    "file_count": tree.file_count,
    "total_bytes": tree.total_bytes,
}, indent=2, sort_keys=True))
PY
```

The runner also requires both editor modules and rejects a plugin path inside a
worktree. If the packaged layout differs, pass the directory that directly
contains `VistaPlayableHome.uplugin`.

## 3. Re-run the read-only plan with all plugin pins

Substitute the four values printed above:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. uv run python -m \
  tools.ue.vista_playable_home.run_makehuman_cc0_detail_actions_r15_import \
  plan \
  --attempt-name makehuman-cc0-detail-actions-r15-ue57-dev-r1-20260901a \
  --plugin-root "$PLUGIN_ROOT" \
  --plugin-tree-sha256 '<TREE_SHA256>' \
  --plugin-file-count '<FILE_COUNT>' \
  --plugin-total-bytes '<TOTAL_BYTES>'
```

Expected status:

```text
ready_for_cpu_only_dev_import
```

Review the 18-item inventory and every input pin before execution.

## 4. Execute the isolated CPU-only import

Execution creates a fresh attempt by copying the sealed R3 MakeHuman character
project and fresh compiled plugin. Bubblewrap unshares the network, and Unreal
runs with `-nullrhi`, memory DDC, no renderer, and no GPU assignment.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. uv run python -m \
  tools.ue.vista_playable_home.run_makehuman_cc0_detail_actions_r15_import \
  execute \
  --attempt-name makehuman-cc0-detail-actions-r15-ue57-dev-r1-20260901a \
  --plugin-root "$PLUGIN_ROOT" \
  --plugin-tree-sha256 '<TREE_SHA256>' \
  --plugin-file-count '<FILE_COUNT>' \
  --plugin-total-bytes '<TOTAL_BYTES>' \
  --acknowledgement \
  'I acknowledge this CPU-only R15 CC0 UE import is development-only, unaccepted, nonpromotable, and requires runtime and human-motion review.'
```

The terminal host manifest is written only after the commandlet proves:

- exactly nine animation-only sequences bound to the existing R6 skeleton;
- exactly 53 bone tracks and zero root-transform delta;
- root motion disabled and locked to the reference pose after cold reload;
- exactly nine one-iteration default-slot montages;
- rotary power contact at frame 24 and on/off completion at frame 60;
- button contact at frame 24 and press completion at frame 54;
- cabinet handle contact at frame 26 and open/close completion at frame 66;
- chair contact at frame 54, sit completion at frame 78, seated-idle cycle
  completion at frame 54, and stand completion at frame 78;
- pour tilt contact at frame 36 and completion at frame 84;
- cold reload of exactly 18 new packages;
- byte-identical pre-existing R3 content.

The source receipt also remains pinned to `runtime_execution_authorized=false`,
`human_reviewed=false`, and `accepted=false`. The seated-idle FBX is a verified
loop source, but this import intentionally authors a one-iteration montage;
runtime code must explicitly repeat it while the actor remains seated.

Any partial namespace remains quarantined in its unique attempt. Never reuse
that attempt name after a failure.

## Remaining runtime gates

UE import completion does not make the motions playable by itself. The next
separate change must bind the nine montages into the runtime animation
component and action executor, then prove target-aware rotary/button/cabinet,
sit/idle/stand, and two-object pour semantics. That stage needs a new compiled
plugin/project derivative and a human-operated Sunshine playtest; it must not
overwrite the current live R6 rollback or treat this import receipt as runtime
or human-motion acceptance.
