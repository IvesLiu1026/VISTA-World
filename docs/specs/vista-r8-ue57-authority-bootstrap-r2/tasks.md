# Tasks: VISTA R8 UE 5.7 Authority Bootstrap R2

Status: Dedicated-builder source milestone complete; privileged activation and T7 blocked
Updated: 2026-08-31
Depends on: requirements.md, design.md

## Safety Rules

- Source work occurs only on `codex/vista-r9-six-room-finish-r1`.
- Root bootstrap, account/unit installation, systemd reload/enable/start, builder
  execution, candidate execution, UE, engine copying, or authority publication
  requires a separate explicit approval after source review.
- Do not touch GPU0/GPU1, CAR, Sunshine, Xvfb `:118`, input relay, ports, R6
  service, production port `8000`, existing R8 publication, or candidate h.
- Runtime artifacts are append-only and stay outside Git.
- Stage only named files for one logical change. Wrapper pins may change only
  in the separately reviewed final-repin substage after all pinned source bytes
  are frozen; this change records that reviewed repin, not a silent placeholder
  substitution.

## Task List

- [x] T1. Freeze the dedicated-builder requirements and design (R1, R1a, R1b,
  R9, R10)
  - Replace the obsolete `yhliu + Bubblewrap/user-namespace` production native
    build design with the fixed UID/GID 997 dedicated builder.
  - Record root-owned Git bundle and Phase A/B requests, two inactive hardened
    oneshots, fixed writable slots, deterministic double builds, closed
    manifests, held-FD authority validation, and deferred late recipes.
  - Preserve separate Engine/Host Runtime/BuildPlugin authorities, the R2
    bundle/live-interpreter contract, append-only publication, and all later
    human/runtime/GTA gates.
  - Completion evidence: the three approved SDD documents describe the same
    Phase A/B boundary and blocked rollout status.

- [ ] T2. Align and harden the executor authority contract (R4-R8)
  - Keep the fixed R2 bundle/policy, host-runtime, and BuildPlugin paths.
  - Bind BuildPlugin manifest and closed receipt-v2 admin-publication lineage;
    reject omission, old schema, unknown keys, tamper, or rebinding.
  - Validate immutable live `/proc/self/exe`, Python prefix/path/import
    origins, zero-write authority audit, and exact attempt/ledger behavior.
  - Preserve renamed finals on durability uncertainty and reconcile only.
  - Completion evidence: focused executor policy, launcher, receipt, archive,
    sandbox, and no-replace tests pass.

- [ ] T3. Close Engine and Host Runtime authority tooling (R1, R2, R3)
  - Retain the complete externally reviewed engine projection, fixed source pin,
    no-replace publisher, and candidate-free reconcile.
  - Retain the allowlisted ELF/runtime closure, no-`ldd` resolution ledger,
    generated non-secret `/etc`, manifest/receipt, and independent audit plan.
  - Keep engine and runtime publications independent and require the
    runtime-owner no-writer acknowledgement.
  - Completion evidence: source-only fake-authority/ELF tests and independent
    projection review pass before any root action.

- [ ] T4. Close Root Bundle and deferred sequential-authority tooling (R1b,
  R4-R7)
  - Retain the atomic R2 bundle/policy publisher, four operation locks,
    reviewed-plan schemas, four fresh input/plan roots, held-FD transfer,
    immutable earlier-root snapshots, and no-future-root ordering.
  - Add approved dedicated-builder recipes for `launch-r8-ue57`, runtime and
    bundle administrator launchers, and all four stage installers.
  - Until those recipes exist, require every production entry point to return
    `DEDICATED_BUILDER_AUTHORITY_REQUIRED` before any write or compile.
  - Completion evidence: each later artifact has two byte-identical builds,
    static-ELF proof, a closed job manifest, aggregate inventory, and authority
    administrator tests. This task is intentionally incomplete in the current
    milestone.

- [x] T5a. Implement the dedicated-builder source milestone (R1a, R10)
  - Add the fixed locked `vista-r8-builder:997:997` account contract with
    `/nonexistent`, `/usr/sbin/nologin`, no supplementary groups, and no
    subordinate-ID entry or range containing 997; reject every inactive
    ceremony while any orphan/live process carries UID, GID, or group 997.
  - Add the root-reviewed three-operation bootstrap, root-owned installed
    builder/inputs, root:root `0555` state root, `997:997 0711` phase slots,
    and `0600` phase locks without starting services.
  - Add the two fixed `PrivateNetwork` oneshots with pinned Python, closed
    environment, `UMask=0077`, strict protection, and phase-specific writable
    paths.
  - Add strict canonical requests, exact Git-bundle/blob extraction, symlink-safe
    held tool validation, sealed source memfds, twice-built byte identity,
    static-ELF checks, full durability, and closed job/phase manifests.
  - Add the observation-only Phase A request planner and exhaustive trace-v2
    contract: exact per-invocation event/search/scratch prestate, mapped-file
    device/inode/path/byte closure, resolved two-path mutation endpoints, and
    fail-closed replay against held host inputs. Reject scratch raw `..`
    before normalization; require immutable pinned host chains plus resolved
    targets for GCC host `..`; close exact procfs tokens and `/dev/null`
    `O_RDWR[|O_CLOEXEC]`; and avoid production NSS lookups.
  - Phase A emits the three launchers and exact
    `parent-seal-candidate/{vista_authority_parent_seal.py:0444,launch-vista-authority-parent-seal:0555}`.
  - Phase B consumes only closed Phase A plus its root-owned request embedding
    canonical core audit and initial input, then emits the exact builder-owned
    three-file initial candidate and sole twice-built installer.
  - Phase B reuses the exact Phase A builder/bundle/commit/blob/tool/runtime/
    trace contract and validates Phase A request-to-manifest lineage both at
    zero-write derivation and later with both documents held during audit.
  - The authority administrator validates builder authorities with
    standard-library held-FD/hash/schema/static-ELF logic and performs no local
    production compilation. Initial-helper provenance consumes Phase B, and
    late native production entry points fail closed.
  - Completion evidence: source, unit, bootstrap, helper, test, and runbook
    changes exist. Two zero-publication planner/replay runs over one ephemeral
    exact bundle produced byte-identical canonical request bytes; no root,
    systemd, production builder phase, candidate publication, or UE action is
    included in this completion.

- [ ] T5b. Freeze and independently review builder inputs (R1a, R10)
  - Run the complete focused and related R8 source suite, Ruff/format/compile,
    shell syntax, static systemd-unit verification, and `git diff --check`.
  - Obtain an independent security review with no P0/P1 blocker.
  - Freeze the final source commit, exact root-owned Git bundle candidate,
    canonical Phase A request, bootstrap, builder, and unit hashes/sizes.
  - Confirm wrapper pins in a separate final-repin substage. The current source
    candidate pins the reviewed authority administrator, engine source pin, and
    live Python bytes; any later source change invalidates that repin.
  - Completion evidence: a reviewed hash ledger, exact committed source, and
    the canonical bundle/request regenerated from that commit. Independent
    source review and repin are complete, but this task remains open until the
    commit exists and its exact bundle/request are frozen. This task does not
    install or execute anything.

- [ ] T6a. Install the inactive builder framework and close Phase A (R1a)
  - Through the finite root ceremony, install or exactly reconcile only the
    pinned framework and Phase A inputs.
  - Confirm both units are inactive/empty and the bootstrap did not reload,
    enable, start, or execute them.
  - Under a separate activation approval, run Phase A exactly once and validate
    its complete held-FD authority and parent-seal candidate.
  - Completion evidence: closed Phase A manifest and independent audit. **Not
    executed; blocked on T5b and privileged approval.**

- [ ] T6b. Close Phase B and install the initial four-root bootstrap (R1, R1a)
  - Independently derive/review the Phase B request from closed Phase A, append
    it through the inactive bootstrap, and separately approve one Phase B run.
  - Validate the three-file candidate, sole installer, embedded documents,
    job/candidate/aggregate manifests, and Phase A lineage with held FDs.
  - Copy only the independently reviewed sole installer into its fixed root
    authority, then install/reconcile the launcher/helper/input/lock and
    publish/resume only the exact four-root prefix.
  - Never execute a worktree or builder-owned candidate directly with sudo.
  - Completion evidence: exact prefix audit and durability receipts. **Not
    executed; blocked on T6a and separate privileged approvals.**

- [ ] T6c. Publish BuildPlugin and Engine authorities (R1-R4)
  - Seal the exact initial shared-parent inventory through the root-owned
    parent-seal chain and reconcile before adding a child.
  - Publish BuildPlugin only through the reviewed root helper/admin pair, then
    publish the engine only against the external source pin.
  - Completion evidence: immutable authority manifests/receipts and live-fsync
    audits. **Not executed; blocked on T6b.**

- [ ] T6d. Publish Host Runtime and atomic R2 executor authorities (R1b, R3-R7)
  - Complete T4's missing dedicated-builder recipes first.
  - Freeze/install runtime input and plan, publish the exact runtime, then
    freeze/install bundle input and plan and publish the atomic R2 root.
  - Completion evidence: all four immutable stage roots, runtime receipt, R2
    bundle/policy receipt, and zero-write installed audit. **Blocked by design
    on T4 and T6c.**

- [ ] T7. Execute one fresh NullRHI attempt (R7-R10)
  - Require installed `--audit-authorities` with zero blockers/writes.
  - Create and seal the one-invocation ledger before child launch.
  - Execute only the policy-fixed fresh attempt and acknowledgement without
    GPU/network/display/service resources.
  - Record CPU/RAM/disk budget and runtime-owner no-writer acknowledgement.
  - Completion evidence: append-only invocation and attempt evidence with all
    later acceptance claims still false. **Unexecuted and blocked on T6d plus
    separate execution approval.**

- [ ] T8. Audit, document, commit, and push (R9, R10)
  - Verify nine UAssets, typed notifies, manifests, receipts, modes, ownership,
    final negative claims, and append-only final name after T7.
  - Update the runbook and task evidence with exact source/root hashes and
    approved deviations.
  - Commit one reviewed logical change and push the collaboration branch.

## Phase Gates

- The completed source milestone authorizes no root/bootstrap/systemd/builder/
  candidate/UE execution.
- Every activation, finite root trust ceremony, authority publication, and T7
  remains a separate explicit gate.
- Human visual/motion acceptance remains a separate explicit gate.
- Dedicated-server/two-client interaction remains a separate explicit gate.
- R10 T7 remains a separate explicit gate.
- GTA-level or photoreal-character claims remain false in this phase.
