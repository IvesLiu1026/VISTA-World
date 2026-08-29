# Requirements: VISTA R8 Sealed UE Executor R1

Status: Approved for implementation
Updated: 2026-08-30

## Problem

The reviewed R8 source lane can author five CC0 MakeHuman motions and the UE
commandlet can describe the exact nine animation assets, but no authority may
currently execute that commandlet. The development engine, R3 project,
BuildPlugin output and Git checkout are writable pathnames. Launching UE from
those paths would allow same-UID replacement, network access, GPU exposure and
host-output forgery between validation and publication.

## Goals

- Add one fail-closed, CPU-only UE 5.7 animation-import execution lane.
- Bind the full immutable engine, R3 project, fresh R8 FBXs, reviewed
  BuildPlugin package, commandlet, wrapper and executor into one manifest.
- Run UE with NullRHI in a private bubblewrap namespace with no network or GPU.
- Treat logs and exit code as diagnostics, never as success proof.
- Publish only a validated R3-plus-nine-assets project through a fresh,
  immutable, append-only boundary.
- Keep every claim narrower than runtime, interaction, human-motion,
  photorealism or GTA-quality acceptance.

## Non-goals

- Provisioning the administrator-owned engine, Blender, R8 or BuildPlugin
  authorities in this source change.
- Running Unreal, Blender, a GPU job or changing the live Sunshine stack.
- Accepting the quarantined R8 attempts E/F.
- Adding caller-selected scripts, projects, plugins, FBXs, engines or output
  paths.
- Modifying the R5 proof runner or its trusted projection.
- Promoting imported assets to a packaged gameplay or human-review milestone.

## Assumptions

- Target runtime is UE 5.7.3 on Linux x86_64.
- `/usr/bin/bwrap`, Linux sealed memfds and user namespaces are available.
- A later reviewed root bootstrap will install the executor bundle and publish
  the required immutable authorities at fixed paths.
- The existing R3 receipt/project and R8 materializer contracts remain the
  source of truth for the skeleton, mesh, clips and nine-asset inventory.

## Requirements

### R1. Worktree execution is never authority

WHEN the executor runs from a Git checkout THEN it SHALL provide deterministic
zero-write planning only and SHALL reject execution before creating an attempt.

Acceptance notes:
- The CLI exposes no engine, project, plugin, FBX, script or binary override.
- Missing or partial authority pins are reported as closed blockers.
- A root-installed exact executor/wrapper/commandlet bundle is required for
  execution.

### R2. Every executable and input byte is cross-bound

WHEN an execution plan is admitted THEN the system SHALL validate an immutable
full-engine manifest, exact R3 project, fresh root-published R8 receipt and five
FBXs, reviewed root-owned BuildPlugin tree, bwrap binary, executor, wrapper,
commandlet and execution manifest.

Acceptance notes:
- Engine validation includes the complete inventory, manifest digest, tree
  digest, BuildId and critical UE binaries.
- BuildPlugin validation includes the full normalized tree, descriptor,
  `UnrealEditor.modules` BuildId and both fixed module binaries.
- Every held input is revalidated immediately before launch and after child
  exit.
- Symlinks, writable authority paths, owner/mode drift, unknown files and
  partial pin sets fail closed.

### R3. UE executes without host, network or GPU authority

WHEN the sandbox starts THEN it SHALL use bubblewrap with all namespaces
unshared, an empty environment, UID/GID 65534, a private `/tmp`, private work
tree, new `/dev` and `/proc`, and no network or GPU device exposure.

Acceptance notes:
- UE always receives `-nullrhi`, `-nosound`, `-unattended` and the fixed Python
  commandlet.
- The sandbox cannot see the repository, mutable NAS engine path, host output
  directory, credentials, proxy variables, display sockets or Sunshine.
- Engine and BuildPlugin authorities are read-only; R3, R8, manifests, wrapper
  and commandlet are write-sealed memfd snapshots.

### R4. The execution command and manifest are closed

WHEN a plan is built THEN it SHALL contain one canonical execution manifest and
one fixed Unreal command derived only from reviewed constants.

Acceptance notes:
- The execution manifest binds every authority digest and the exact expected
  nine-asset delta.
- Asset namespaces, skeleton, frame counts, notify frames and root-motion gates
  remain identical to the approved R8 materializer/commandlet contracts.
- The project is assembled inside the private sandbox, never in a caller-owned
  host directory.

### R5. Success crosses the sandbox only as validated bytes

WHEN UE exits successfully THEN the sandbox wrapper SHALL independently verify
the commandlet result and emit exactly one bounded canonical USTAR on stdout.

Acceptance notes:
- UE logs are emitted only on stderr.
- The archive contains exactly nine new UAssets plus the commandlet receipt and
  result; no base-project copy, link, special file or extra member is allowed.
- Missing/duplicate/traversing/non-canonical/oversized members, a nonzero child
  exit or a zero exit without valid receipts are rejected.
- The host revalidates schemas, content digests, bindings, gates and exact R3
  delta from captured bytes.

### R6. Publication is fresh, immutable and non-promotional

WHEN all post-exit checks pass THEN the root-installed executor SHALL publish
one fresh direct child below the fixed root-owned parent using no-replace and
fsync semantics.

Acceptance notes:
- Directories finish root:root `0555`; files finish root:root `0444`.
- Existing paths are never overwritten or reused.
- The host receipt binds engine, R3, R8, plugin, sandbox transport and output.
- `accepted` remains false and runtime, interaction, human-quality,
  photorealism and GTA claims remain false.

### R7. Failure and timeout leave no candidate

IF validation, launch, timeout, archive parsing, post-exit revalidation or
publication fails THEN the system SHALL terminate the child process group,
close all held descriptors and leave no final published name.

Acceptance notes:
- A same-UID mutation during planning, execution or publication is detected.
- Traceback text plus exit zero is not success.
- Partial staging remains private and is never renamed to the final name.

### R8. The lane is reviewable without privileged execution

WHEN this source slice is reviewed THEN its fake-authority tests SHALL exercise
planning, sandbox construction, memfd seals, archive rejection, TOCTOU,
publication and negative claims without launching UE or requiring root/GPU.

## Edge Cases

- Engine or plugin BuildId agrees in one file but differs in another.
- An authority directory is replaced after its manifest is checked.
- UE returns zero but emits no receipt, an invalid receipt or extra assets.
- The archive contains duplicate normalized paths, links, device nodes or a
  valid-looking receipt bound to different FBXs.
- Publication target appears concurrently after preflight.
- Timeout occurs after UE wrote valid private bytes but before wrapper closure.

## Open Questions

- Exact production authority pins remain intentionally unset until independent
  root provisioning and review.
- The first real run will determine whether the bounded stdout archive limit
  needs adjustment; changing it requires a reviewed source revision.

## Approval

- Requested by: yhliu
- Approved by: user messages `批准 spec，開始執行`, subsequent execution
  authorizations, and `請你繼續做我們可以做的部分`
- Date: 2026-08-30
