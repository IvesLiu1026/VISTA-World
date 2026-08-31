# MakeHuman CC0 R14 detail-action UE import

This lane turns the already generated, round-trip-verified R14 FBXs into six
fresh UE assets: three `AnimSequence` packages and three typed-notify
`AnimMontage` packages. It is isolated from R8 and writes only under:

```text
/Game/VISTA/MakeHumanCC0/R14/DetailActions
```

It does not modify or restart the current live project, Sunshine, Pixel
Streaming, or a GPU service. A successful import is still development-only,
unaccepted, and nonpromotable until runtime and human-motion review pass.

## Pinned source authority

The host and commandlet both pin the same immutable source attempt:

```text
/data/sysx/vista-world/runs/vista-action-world-r1/
  makehuman-cc0-detail-actions-r14-candidate-20260901a
```

- worker receipt SHA-256:
  `b142912fcf9d8a195c173d60064992b2f323c9208b467109af817134c26e3ed3`
- worker receipt content digest:
  `afe84bfaf120006c99e44c2f05531d759f538e193b03889a88334f752c6f2a12`
- profile content digest:
  `eccf9da1ca7283efc08cffabe1d52ba020578e3d7c04d423cb2356f25b320d43`

The three FBX SHA-256 and size pins are compiled into
`makehuman_cc0_detail_actions_r14_contract.py` and independently repeated in
the sandbox commandlet. The import fails before mutation if any byte differs.

## 1. Read-only preflight

From the VISTA-World checkout:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. uv run python -m \
  tools.ue.vista_playable_home.run_makehuman_cc0_detail_actions_r14_import \
  plan \
  --attempt-name makehuman-cc0-detail-actions-r14-ue57-dev-r1-20260901a
```

Before a fresh plugin package exists, the expected status is:

```text
blocked_pending_fresh_compiled_plugin_authority
```

Planning performs no writes and never launches Unreal.

## 2. Build a fresh plugin package

The package must be built from the reviewed commit that contains
`VistaPlayableHomeCc0DetailActionLibrary`. Use a new append-only output path;
do not reuse the prior R6 or pre-R14 BuildPlugin package.

```bash
/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Build/BatchFiles/RunUAT.sh \
  BuildPlugin \
  -Plugin="$PWD/unreal_plugins/VistaPlayableHome/VistaPlayableHome.uplugin" \
  -Package=/data/sysx/vista-world/runs/vista-action-world-r1/\
playable-actions-r2-plugin-build-r14-20260901a \
  -TargetPlatforms=Linux
```

Locate the packaged `VistaPlayableHome` directory, then record its exact tree
projection without changing it:

```bash
PLUGIN_ROOT=/data/sysx/vista-world/runs/vista-action-world-r1/\
playable-actions-r2-plugin-build-r14-20260901a/HostProject/Plugins/VistaPlayableHome

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. uv run python - "$PLUGIN_ROOT" <<'PY'
import json
import sys
from pathlib import Path

from tools.ue.vista_playable_home import build_home

tree = build_home.snapshot_tree(Path(sys.argv[1]), "fresh R14 BuildPlugin")
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
  tools.ue.vista_playable_home.run_makehuman_cc0_detail_actions_r14_import \
  plan \
  --attempt-name makehuman-cc0-detail-actions-r14-ue57-dev-r1-20260901a \
  --plugin-root "$PLUGIN_ROOT" \
  --plugin-tree-sha256 '<TREE_SHA256>' \
  --plugin-file-count '<FILE_COUNT>' \
  --plugin-total-bytes '<TOTAL_BYTES>'
```

Expected status:

```text
ready_for_cpu_only_dev_import
```

Review the six-item inventory and every input pin before execution.

## 4. Execute the isolated CPU-only import

Execution creates a fresh attempt by copying the sealed R3 MakeHuman character
project and fresh compiled plugin. Bubblewrap unshares the network, and Unreal
runs with `-nullrhi`, memory DDC, no renderer, and no GPU assignment.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. uv run python -m \
  tools.ue.vista_playable_home.run_makehuman_cc0_detail_actions_r14_import \
  execute \
  --attempt-name makehuman-cc0-detail-actions-r14-ue57-dev-r1-20260901a \
  --plugin-root "$PLUGIN_ROOT" \
  --plugin-tree-sha256 '<TREE_SHA256>' \
  --plugin-file-count '<FILE_COUNT>' \
  --plugin-total-bytes '<TOTAL_BYTES>' \
  --acknowledgement \
  'I acknowledge this CPU-only R14 CC0 UE import is development-only, unaccepted, nonpromotable, and requires runtime and human-motion review.'
```

The terminal host manifest is written only after the commandlet proves:

- exactly three animation-only sequences bound to the existing R6 skeleton;
- exactly 53 bone tracks and zero root-transform delta;
- exactly three non-looping default-slot montages;
- open/close handle-contact and completion notifies at the specified frames;
- inspect completion at frame 88;
- cold reload of exactly six new packages;
- byte-identical pre-existing R3 content.

Any partial namespace remains quarantined in its unique attempt. Never reuse
that attempt name after a failure.

## Remaining runtime gates

UE import completion does not make the motions playable by itself. The next
separate change must bind these three montages into the runtime animation
component and action executor, then prove open/close/inspect contact semantics
against the articulated fridge and held-object interaction. That stage needs a
new compiled plugin/project derivative and a human-operated Sunshine playtest;
it must not overwrite the current live R6 rollback.
