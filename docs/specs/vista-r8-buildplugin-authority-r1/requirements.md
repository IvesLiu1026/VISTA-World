# Requirements: VISTA R8 BuildPlugin Authority R1

Status: Approved
Updated: 2026-08-30

## Problem

The reviewed UE 5.7 BuildPlugin output used by the R8 animation lane currently
exists only as a mutable, user-owned development tree. Git source and a
successful BuildPlugin run do not make those executable plugin bytes an
immutable execution authority. A same-UID process can replace files between
review and copy unless the publisher holds every reviewed source inode and
publishes through a distinct root-owned boundary.

## Goals

- Independently bind the complete fixed development package at
  `/data/sysx/vista-world/runs/vista-action-world-r1/vista-r8-ue-animation-buildplugin-dev-20260830c`.
- Provide one reviewed root-side helper that can publish that exact package to
  a fresh, immutable authority below `/data/vista-authorities`.
- Close source namespace/content TOCTOU by holding every source file and
  directory descriptor from validation through copy and post-copy revalidation.
- Produce canonical, machine-verifiable inventory and publication receipts.
- Place the finalized helper SHA-256 in a separate reviewed runbook so the
  helper does not self-authorize or create a recursive hash dependency.
- Keep checkout execution read-only; administrator installation and publication
  remain explicit future actions.

## Non-goals

- Building or loading the plugin, invoking UE/UHT/UBT, or proving runtime use.
- Publishing the R8 Blender artifacts or a sealed UE execution authority.
- Changing the R8 importer, commandlet, runtime plugin, R5 projection, services,
  external attempt C, or any Git-tracked executable input outside this lane.
- Claiming animation quality, interaction success, photorealism, GTA quality,
  Manny/MetaHuman/CitySample use, or production acceptance.
- Updating an existing authority in place or deleting a failed/old authority.

## Assumptions

- Approval for this requirements/design/task slice is inherited from the prior
  approved VISTA production spec and the current continuation request.
- Linux supplies `renameat2(RENAME_NOREPLACE)`, `O_NOFOLLOW`, directory FDs,
  `fsync`, and `/usr/bin/python3.10` with its reviewed fixed pin.
- An administrator separately reviews and installs this helper at its literal
  root-owned path before publication, then verifies the installed bytes against
  the independently obtained runbook literal. Checkout-generated metadata never
  grants root authority.
- Attempt C is input evidence only; this lane never modifies it.

## Requirements

### R1 — Exact fixed input

WHEN the helper audits the development package THEN it SHALL require the fixed
absolute source path, exactly 241 regular single-link files, 32 directories
including the root, 51,661,522 file bytes, no links or special entries, and the
complete canonical inventory digest
`cad2d8f0481934cc1565c3cad0dbad041d293795cf31ea420a6a646d8c2b46b2`.

Acceptance notes:
- The normalized package projection SHALL equal
  `69153cd676ac35579115d1be9c8ced7d86c70beab7f8adb681ad7b8d373ae48e`.
- Inventory SHALL bind every relative path, source mode, size, and file SHA-256;
  projection SHALL use the same path/content algorithm consumed by the R8 UE
  materializer.
- Case-insensitive collisions, unsafe relative names, hard links, symlinks,
  sockets, devices, and FIFOs SHALL be rejected.

### R2 — Critical executable pins

WHEN the complete inventory is valid THEN the helper SHALL also require exact
mode, size, and SHA-256 pins for `VistaPlayableHome.uplugin`,
`Binaries/Linux/UnrealEditor.modules`, and the two named Editor module `.so`
files.

Acceptance notes:
- The modules JSON SHALL be strict JSON and map only `VistaPlayableHome` and
  `VistaPlayableHomeEditor` to the two pinned `.so` basenames.
- The uplugin SHALL be strict JSON and declare the two expected Runtime/Editor
  modules and engine version `5.7.0`.

### R3 — Held-descriptor source authority

WHEN source validation starts THEN the helper SHALL open the source root,
every directory, and every file with `O_NOFOLLOW`, retain all descriptors until
copy and final validation complete, and copy payload bytes only from held file
descriptors.

Acceptance notes:
- Pre-open stat, held-FD stat, content hash, post-copy held-FD stat, fixed-root
  pathname identity, and directory namespace/identity SHALL all agree.
- Mutation, replacement, rename, addition, removal, truncation, growth, or
  source mode drift SHALL fail closed before publication.

### R4 — Installed root execution boundary

IF publication is requested THEN the helper SHALL refuse unless effective UID
is root and the helper is the exact root-owned, single-link, mode `0500` file
`/root/vista-r8-buildplugin-authority-r1/vista_r8_buildplugin_authority.py`,
executed by the pinned root-owned `/usr/bin/python3.10` in isolated, no-bytecode
mode with user site disabled.

Acceptance notes:
- Every existing helper/interpreter ancestor SHALL be root-owned and not group-
  or world-writable.
- Running `--publish` from a worktree, copied user path, alternate Python, or as
  a non-root user SHALL fail before opening a staging output.
- A held `/proc/self/exe` FD, its inode, size, and SHA-256 SHALL exactly match the
  separately opened pinned interpreter path; `sys.executable` alone is not an
  execution-authority proof.
- `--audit-source` SHALL remain zero-write and usable from the checkout.

### R5 — Fresh immutable publication

WHEN all gates pass and the administrator supplies the exact acknowledgement
THEN the helper SHALL copy into a fresh private staging directory, normalize all
payload and metadata files to root:root `0444` and all directories to root:root
`0555`, audit the finished tree, fsync files/directories, and atomically publish
to `/data/vista-authorities/vista-r8-ue-animation-buildplugin-r1` using
`renameat2(RENAME_NOREPLACE)`.

Acceptance notes:
- The authority parent SHALL already be root-owned, mode `0555`, and have safe
  root-owned non-writable ancestry.
- Existing final destination or unavailable no-replace rename SHALL fail; there
  is no overwrite fallback.
- Staging SHALL never be treated as an authority. A failed staging tree may be
  removed only after its root-owned identity is revalidated.
- If rename succeeds but the authority-parent fsync fails, the helper SHALL emit
  stable `BUILDPLUGIN_AUTHORITY_PUBLISHED_DURABILITY_UNKNOWN`, preserve the
  possible final tree, forbid a blind publish retry, and provide a root-gated
  reconciliation path that re-audits and fsyncs the published authority.

### R6 — Canonical evidence and bounded claims

WHEN an audit or publication succeeds THEN the helper SHALL emit canonical JSON
that records the complete inventory/manifest seals, critical pins, fixed source
and destination, helper/interpreter bindings, policy gates, and explicit
negative runtime/quality claims.

Acceptance notes:
- `manifest.json` SHALL contain the complete 273-entry source inventory and
  destination modes. `receipt.json` SHALL bind the canonical manifest and
  payload projection with a content digest.
- Publication may assert only that this BuildPlugin authority was freshly and
  immutably published; it SHALL not assert that UE imported, loaded, or executed
  it.
- Dry-run output SHALL use `accepted:false` and SHALL not imply authority exists.
- Dry-run SHALL observe whether the final path exists, label it unvalidated, and
  pass a closed report validator that rejects missing/extra fields or digest
  drift.

### R7 — Pure verification

WHEN this lane is reviewed THEN CPU-only tests SHALL cover exact audit,
critical-pin mismatch, unsafe tree entries, regular-file-to-FIFO open races,
TOCTOU/replacement, held-FD copy, live interpreter mismatch, worktree/non-root
refusal, immutable modes, canonical evidence, existing-target refusal,
post-rename fsync uncertainty/reconciliation, and no-replace publication without
executing root, UE, Blender, GPU, or network operations.

## Edge Cases

- Empty or non-UTF-8 path components, newline/NUL path ambiguity, and case-fold
  collisions are rejected rather than normalized.
- A source change that is later restored still changes inode/ctime or held
  namespace identity and is rejected.
- Source regular-file opens include `O_NONBLOCK`, so a same-UID swap to a FIFO
  cannot hang the root publisher between stat and open.
- A valid aggregate projection with a changed source mode is rejected by the
  complete inventory digest.
- A partial authority, stale staging directory, or pre-existing final path is
  never reused.
- Metadata write or fsync failure leaves no accepted final authority.
- Parent-fsync failure after rename is the exception to “no final”: the final
  name may exist but remains durability-unknown until reconciliation succeeds.

## Open Questions

- None for implementation. The eventual administrator may accept or decline
  the one fresh publication after separately verifying the reviewed helper SHA.

## Approval

- Requested by: VISTA owner (continuation request)
- Approved by: VISTA owner; inherited from the previously approved spec and
  explicit continuation authorization
- Date: 2026-08-30
