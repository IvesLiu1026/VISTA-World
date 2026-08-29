# Design: VISTA R8 Sealed UE Executor R1

Status: Approved for implementation
Updated: 2026-08-30
Depends on: requirements.md and the approved R8 animation runbook

## Summary

Implement a new executor and a sandbox wrapper without changing the existing
R8 materializer, commandlet or R5 proof lane. A checkout may validate and
produce a deterministic dry plan, but only a later root-installed exact bundle
with all authority pins can execute. The child sees immutable inputs and a
private work tree; success returns as one validated USTAR rather than through a
host-writable output mount.

## Architecture and Flow

1. The host executor validates its fixed root-installed identity and all
   authority manifests.
2. It opens and holds bwrap, engine/plugin authority roots and every input file.
3. R3 files, five R8 FBXs, execution JSON, wrapper and commandlet are copied to
   fully write-sealed memfds.
4. The executor builds one fixed bubblewrap command. Engine and BuildPlugin
   roots are mounted read-only; sealed files are mounted through
   `--ro-bind-data`; `/vista/work` and `/tmp` are private tmpfs.
5. The wrapper reconstructs the R3 project in `/vista/work`, installs the
   reviewed plugin, launches fixed `UnrealEditor-Cmd` with NullRHI and captures
   UE diagnostics on stderr.
6. After UE exits, the wrapper validates the commandlet result, nine UAssets and
   unchanged R3 base, then emits one canonical USTAR on stdout.
7. The host applies byte and time limits, parses the archive, repeats all
   semantic checks, revalidates held authorities and publishes through a
   root-only staging directory and no-replace rename.

## Interfaces and Contracts

New modules:

- `makehuman_cc0_animation_runtime_executor.py`
  - zero-write `build_plan()` and CLI;
  - full authority validation;
  - immutable snapshot and bwrap command construction;
  - bounded child supervision and USTAR validation;
  - root-only immutable publication.
- `makehuman_cc0_animation_runtime_sandbox_wrapper.py`
  - fixed manifest and path contract;
  - private R3/plugin assembly;
  - fixed UE invocation;
  - commandlet receipt/result validation;
  - canonical archive emission.

The CLI accepts only a closed attempt name, dry-run by default and the exact
execution acknowledgement for `--execute`. It accepts no authority path,
engine path, script path, plugin path, FBX list or arbitrary UE argument.

Schemas are versioned separately for the host plan, execution manifest,
sandbox result envelope and host receipt. Existing R8 materializer schemas are
consumed but not changed.

## Authority Model

- Full engine: fixed `/data/vista-authorities/ue-5.7.3-r1`, root-owned manifest
  and complete tree pins.
- BuildPlugin: a later fixed root-owned publication copied from the reviewed
  BuildPlugin C package and pinned by complete normalized projection.
- R8 motion: one fresh root-published attempt; E/F remain permanently denied.
- R3: exact receipt and 24-file project projected into sealed memfds.
- Code: executor, wrapper and commandlet must match a later root-installed
  bundle manifest; checkout execution is denied.
- Transport: fixed `/usr/bin/bwrap` opened and launched through its held file
  descriptor.

Constants stay unset until independent review. Tests monkeypatch complete fake
authorities; production code never treats a caller-computed digest as authority.

## Sandbox Layout

```text
/vista/engine                 immutable full engine ro-bind
/vista/plugin                 immutable BuildPlugin ro-bind
/vista/input/execution.json   sealed memfd
/vista/input/r3/**            sealed memfds
/vista/input/r8/*.fbx         sealed memfds
/vista/input/commandlet.py    sealed memfd
/vista/input/wrapper.py       sealed memfd
/vista/work                   private tmpfs
/tmp                          private tmpfs
```

No host `/`, repository, output directory, display socket, audio socket,
network namespace, DRI or NVIDIA device is mounted.

## Data and Publication

The wrapper archive inventory is closed to eleven regular files: nine UAssets,
one commandlet result and one commandlet receipt. The host receipt is created
outside the sandbox only after archive and authority revalidation.

Publication reconstructs the exact R3 project plus nine new files in a private
root-owned sibling staging tree. It writes with `O_EXCL`, fsyncs files and
directories, applies final immutable modes, then publishes with a no-replace
rename. No failed path is promoted.

## Failure Handling

- Preflight failures are zero-write.
- Child timeout kills the process group and rejects all output.
- Stdout/stderr limits stop the child and fail closed.
- Nonzero exit, malformed archive, receipt mismatch, authority drift or
  concurrent final-name creation prevents publication.
- Logs remain diagnostics and never change acceptance state.

## Testing Strategy

- Pure fake-authority tests for every ownership, mode, symlink, inventory,
  digest and BuildId gate.
- Command-shape tests proving unshare-all, NullRHI, private tmpfs and absence of
  GPU/network/host-output mounts.
- Linux memfd seal assertions.
- Fake-child tests for exit/log/archive combinations and timeout cleanup.
- Adversarial USTAR tests for duplicate, traversal, links, special files,
  extra/missing assets and receipt cross-binding.
- Fake root-publication tests for fresh direct child, modes, no-overwrite,
  fsync sequencing and negative claims.
- No real UE, Blender, GPU, service or root action in this source slice.

## File Plan

- Add the two executor/wrapper modules above.
- Add `tools/tests/test_vista_playable_home_makehuman_cc0_animation_runtime_executor.py`.
- Update `docs/runbooks/vista-r8-ue-animation-runtime-r1.md` only after the
  implementation passes review.
- Do not edit the R5 runner/projection or existing R8 materializer/commandlet in
  the first slice.

## Rollout and Observability

1. Land and independently review the CPU-only source slice.
2. Provision and review the full engine, BuildPlugin and fresh R8 authorities.
3. Install the exact executor bundle under root and fill pins in a separate
   reviewed commit.
4. Run dry plan and inspect the exact bwrap command/manifest.
5. Authorize one append-only real commandlet attempt.
6. Keep imported output `accepted:false`; runtime and human review remain later
   lanes.

## Traceability

- R1 -> checkout identity gate and closed CLI
- R2 -> authority validators and held-input revalidation
- R3 -> bwrap command and mount allowlist
- R4 -> canonical execution manifest
- R5 -> wrapper and USTAR parser
- R6 -> root publication helper and host receipt
- R7 -> supervisor cleanup and post-exit checks
- R8 -> fake-authority/adversarial test suite

## Approval

- Requested by: yhliu
- Approved by: prior approved VISTA Action World/R8 execution direction and
  explicit continuation on 2026-08-30
- Date: 2026-08-30
