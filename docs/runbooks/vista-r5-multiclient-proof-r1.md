# R5 multi-client functional proof

This lane is designed to prove the R5 cup transaction in one UE 5.7.3 Editor
process containing one dedicated-server PIE world and two real `NM_Client` PIE
worlds. Runtime uses `-nullrhi` in one private
`bubblewrap --unshare-all` namespace; no GPU device is exposed.

No UE, UBT, UAT, PIE, GPU, engine copy, or privileged command was run while
authoring this harness. Runtime and compile claims remain pending.

## Current hard blocker: immutable Engine authority

The supervisor intentionally fails even dry-run with
`IMMUTABLE_ENGINE_AUTHORITY_REQUIRED` until an administrator provisions and
audits this fixed authority:

```text
/data/vista-authorities/ue-5.7.3-r1/
├── engine/
└── engine-full-tree-manifest.json
```

The authority and every ancestor through `/` must be root-owned, unavailable
for writes by the invoking user, and not group/world writable. The manifest is
canonical and contains the complete directory/file inventory, full file
hashes, metadata, a content digest, and one content-tree root digest. The
supervisor checks the complete inventory and metadata plus critical UE,
CQTest, UBT, dotnet, and runtime hashes. The critical hashes are supplemental;
they are not described as complete Engine closure.

The reviewed bootstrap inputs in a Git checkout are:

```text
tools/runtime/vista_playable_home/provision_immutable_engine_authority.sh
tools/runtime/vista_playable_home/r5_engine_authority_admin.py
```

Neither checkout file is executable authority. The provisioner refuses to run
from a worktree and accepts only the independently verified copies installed
under `/root/vista-r5-engine-authority-r1/`. Use these exact final source
hashes; stop immediately if either check fails.

### Stage 1: verify checkout bytes, then install

Run from the repository root. This stage verifies the two checkout inputs
independently, installs copies owned by root, and makes the fixed bootstrap
directory non-writable before use.

```bash
EXPECTED_SCRIPT=f46f5aa5cd0e1a084d6548812da2bd2aa9c7bf9d801fab10f7d0c07f601e9849
EXPECTED_HELPER=4ca08f3f88ab7249255ebc9c551d725efa888a8527fe6b1b2d8a02acf395259e
CHECKOUT_SCRIPT=tools/runtime/vista_playable_home/provision_immutable_engine_authority.sh
CHECKOUT_HELPER=tools/runtime/vista_playable_home/r5_engine_authority_admin.py

printf '%s  %s\n' "$EXPECTED_SCRIPT" "$CHECKOUT_SCRIPT" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_HELPER" "$CHECKOUT_HELPER" | sha256sum -c -

sudo install -d -o root -g root -m 0755 /root/vista-r5-engine-authority-r1
sudo install -o root -g root -m 0555 "$CHECKOUT_SCRIPT" \
  /root/vista-r5-engine-authority-r1/provision_immutable_engine_authority.sh
sudo install -o root -g root -m 0555 "$CHECKOUT_HELPER" \
  /root/vista-r5-engine-authority-r1/r5_engine_authority_admin.py
sudo chmod 0555 /root/vista-r5-engine-authority-r1
```

### Stage 2: verify installed bytes, then execute only the installed script

Do not execute the checkout script. Recheck both installed copies against the
independent expected hashes after installation, inspect their ownership and
modes, and only then execute the fixed installed path.

```bash
EXPECTED_SCRIPT=f46f5aa5cd0e1a084d6548812da2bd2aa9c7bf9d801fab10f7d0c07f601e9849
EXPECTED_HELPER=4ca08f3f88ab7249255ebc9c551d725efa888a8527fe6b1b2d8a02acf395259e
INSTALLED_ROOT=/root/vista-r5-engine-authority-r1
INSTALLED_SCRIPT=$INSTALLED_ROOT/provision_immutable_engine_authority.sh
INSTALLED_HELPER=$INSTALLED_ROOT/r5_engine_authority_admin.py

printf '%s  %s\n' "$EXPECTED_SCRIPT" "$INSTALLED_SCRIPT" \
  | sudo sha256sum -c -
printf '%s  %s\n' "$EXPECTED_HELPER" "$INSTALLED_HELPER" \
  | sudo sha256sum -c -
sudo stat -c '%n %U:%G %a %F' \
  "$INSTALLED_ROOT" "$INSTALLED_SCRIPT" "$INSTALLED_HELPER"
sudo "$INSTALLED_SCRIPT"
```

At startup the installed script independently refuses every other path,
checks `/`, `/root`, its fixed directory, itself, and its helper for root
ownership, non-symlink canonical identity, and non-group/world-writable modes.
It also pins and rechecks the helper SHA-256 before any Engine operation. The
script contains no `sudo`, refuses an existing final authority, rejects source
symlinks, hashes source before and after copy, compares destination content,
applies root ownership and read-only modes, then performs an atomic final
rename. It copies roughly the full UE tree and therefore must only be run by
an administrator after reviewing the script and capacity. Codex did not
execute it.

The script prints `ENGINE_MANIFEST_SHA256` and `ENGINE_TREE_ROOT_DIGEST`.
Those exact values must be reviewed, pinned in
`r5_multiclient_proof.py`, and included in a newly generated trusted projection
commit before dry-run can succeed.

## Trusted source and sandbox boundary

The supervisor accepts no caller-selected engine, project, plugin, CQTest
binary, Unreal executable, wrapper, or prebuilt proof module. It requires:

- exact Git `HEAD` blobs listed by `r5_trusted_projection.json`;
- the repository-owned minimal `VistaR5Proof` project and complete plugin
  source projection;
- the fixed immutable Engine authority and pinned full-tree root;
- a controlled UBT build whose module descriptors, Engine `BuildId`, ELF
  outputs, hashes, source, input, launch, and Engine provenance are closed
  before runtime.

Project/plugin sources, the trusted runtime wrapper, and controlled build
outputs are sealed anonymous files mounted with `--ro-bind-data`. The sandbox
does not bind host `/`; it projects only required system runtime directories,
the immutable Engine root, sealed inputs, and output-specific mounts.

## Private receipt and Automation authority

The Unreal test cannot write a host evidence path. Inside the namespace it can
only atomically close this fixed path on a private, non-host-bound tmpfs:

```text
/vista-private/r5-multiclient-proof-receipt.json
```

A Git-tracked sealed wrapper launches Unreal, redirects all Unreal output to
diagnostic stderr, then reads that private receipt and
`/vista-private/automation-report/index.json`. It emits exactly one canonical
base64 envelope marker on stdout only when:

- Unreal exits zero;
- the report contains exactly the requested test;
- the requested full test path has `Success` state;
- succeeded is exactly one, and warnings, errors, failures, not-run, and
  in-process counts are zero;
- the private receipt is a passed v3 receipt.

The host captures stdout directly, rejects missing, duplicate, malformed, or
oversized markers, revalidates both captured byte strings, then and only then
writes evidence with `O_EXCL`. A pre-created filesystem receipt and any log
substring have no authority.

## Fresh attempt and dry-run

After the Engine authority pins and Git projection are committed, create a
fresh empty directory outside the repository:

```bash
ATTEMPT_ROOT=/absolute/path/r5-proof-$(date -u +%Y%m%d%H%M%S)-0001
mkdir -m 700 "$ATTEMPT_ROOT"

uv run python tools/runtime/vista_playable_home/r5_multiclient_proof.py \
  --attempt-root "$ATTEMPT_ROOT" \
  --attempt-id r5-proof-$(date -u +%Y%m%d%H%M%S)-0001 \
  --timeout-seconds 900
```

Dry-run performs validation and prints the launch plan without creating
`proof-output`. Attempts are append-only and must never be reused.

## Authorized execution

Only after reviewing the dry-run plan:

```bash
uv run python tools/runtime/vista_playable_home/r5_multiclient_proof.py \
  --attempt-root "$ATTEMPT_ROOT" \
  --attempt-id r5-proof-$(date -u +%Y%m%d%H%M%S)-0001 \
  --timeout-seconds 900 \
  --execute
```

Accepted evidence is written under `proof-output/`:

- `input-manifest.json`
- `launch-plan.json`
- `build-provenance.json`
- `build.log` and `runtime.log` (diagnostic only)
- `evidence/r5-multiclient-proof-receipt.json`
- `evidence/automation-report/index.json`
- `evidence/proof-acceptance.json`

## Proof boundary

An accepted receipt cross-binds Git, projection, input, launch, and controlled
build provenance. It checks six replicated checkpoints, one server plus two
clients, Free/Held/Placed/Drop state, inventory, attachment, collision,
transform and velocity, command replay/collision, and post-contact rollback.

The Event claim is deliberately narrow: it proves only that ResetEvent rejects
while an action is active. The receipt records identical before/after
`ActiveEventId`, `EventStatus`, `SessionGeneration`, public goal, terminal
condition, and that `HasActiveAction` remains true immediately after rejection.
The test then explicitly cancels the action for cleanup. It does not claim that
an accepted reset safely quiesces or cancels arbitrary active actions.

For moving `free_after_drop`, the replicated contact-time transform remains
bit-exact across worlds; the post-tick live transform is only required to be
finite. Collision, simulation state, and requested velocities remain exact.
