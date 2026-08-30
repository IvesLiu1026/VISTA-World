# Tasks: VISTA R8 UE 5.7 Authority Bootstrap R2

Status: In progress
Updated: 2026-08-30
Depends on: requirements.md, design.md

## Safety Rules

- Source work occurs only on `codex/vista-r9-six-room-finish-r1`.
- Root, UE, engine copying, or authority publication is forbidden until T1-T5
  pass and the exact installed scripts receive independent approval.
- Do not touch GPU0/GPU1, CAR, Sunshine, Xvfb `:118`, input relay, ports, R6
  service, production port `8000`, existing R8 publication, or candidate h.
- Runtime artifacts are append-only and stay outside Git.
- Stage only the named files for this logical change.

## Task List

- [ ] T1. Freeze revised R2 requirements and design
  - Record separate Engine/Host Runtime/BuildPlugin authorities.
  - Record fresh R2 root paths and live-interpreter contract.
  - Preserve later human/runtime/GTA gates.

- [ ] T2. Align and harden executor authority contract
  - Change fixed R2 bundle/policy, host-runtime, and BuildPlugin paths.
  - Bind BuildPlugin manifest and closed receipt v2 admin-publication lineage;
    reject v1, omitted, unknown, tampered, or rebound admin bindings.
  - Add launcher to bundle/policy.
  - Validate immutable live `/proc/self/exe`, Python prefix/path/import origins.
  - Add full zero-write authority audit and exact attempt/ledger contract.
  - Preserve renamed finals on durability uncertainty and add reconcile-only.

- [ ] T3. Implement R8 engine and host-runtime authority tooling
  - Add full immutable engine publisher with no-replace reconciliation.
  - Add allowlisted ELF/runtime closure builder, manifest, receipt, and audit.
  - Require externally reviewed engine and runtime audit-plan literals.
  - Keep engine and runtime publications independent.
  - Generate runtime input and plan candidates only as `yhliu`; bind the full
    per-object ELF resolution ledger without `ldd`.
  - Publish fresh runtime input/plan roots through separately reviewed one-shot
    installers; never append to the sealed core.

- [ ] T4. Implement root bundle/policy bootstrap tooling
  - Generate atomic R2 root authority with four-file bundle, static native
    held-fd launcher, and external policy.
  - Pin all data/code/runtime authorities and publication receipts.
  - Add zero-write audit and exact installed-root execution contract.
  - Install and validate the four fixed root-owned operation locks.
  - Build `launch-r8-ue57` and the plan administrator launchers only as
    `yhliu`; privileged paths copy exact held binaries and run no toolchain.
  - Seal reviewed-plan v2 with its native launcher pin, then use fresh
    bundle-input/bundle-plan one-shot installers with external literal pins.
  - Bind host-runtime receipt v2 and root-policy v3 publication provenance.
  - Build/review the generic static stage-transfer launcher as `yhliu`; include
    it in the exact initial core bootstrap and use it as the sole installer
    transfer root entry.

- [ ] T5. Close CPU-only tests and independent source review
  - Commit review tooling with fail-closed wrapper placeholders as HEAD A.
  - Run/review the full engine projection and freeze the externally pinned
    engine-source-pin candidate before finalizing the wrapper.
  - Substitute final helper/source-pin/Python pins, rerun review, and commit
    the complete final source set as HEAD B, including the strict BuildPlugin
    helper/admin contract that requires the shared parent already be `0555`.
  - From HEAD B only, build/freeze the generic transfer, parent-seal,
    BuildPlugin helper/admin, and exact core candidates; run the canonical
    zero-write core-bootstrap audit.
  - Run focused and related R8 tests, Ruff/format/compile/shell/diff checks.
  - Obtain independent security review with no P0/P1 blockers.
  - Record exact source/root helper hashes.
  - Cover the four-stage sequence/no-future-root matrix, external pin mismatch,
    exact inventory/link/mode/owner rejection, collision/reconcile/durability,
    core/earlier-root identity preservation, root subprocess/toolchain bombs,
    and user candidate generation with `/root` access bombed.

- [ ] T6a. Publish reviewed BuildPlugin and Engine authorities
  - Verify the externally reviewed engine source-pin candidate, final HEAD B,
    all frozen user candidates, and sealed zero-write core audit before any
    privileged bootstrap step.
  - Then use the separately reviewed
    one-shot bootstrap to append only fresh core, parent-seal,
    BuildPlugin-helper, and BuildPlugin-admin roots in that order. It copies
    prebuilt bytes, never compiles as root, and preserves every rename; an
    uncertain step reconciles before proceeding to the next absent root.
  - Seal the exact initial shared-parent inventory with the separate reviewed
    parent-seal one-shot; finish any reconcile before another child exists.
  - Invoke only the already reviewed, root-owned BuildPlugin admin/helper pair;
    it requires parent `0555` and never chmod/fchmods it. Re-audit and publish.
  - Publish full UE engine against the committed source pins.

- [ ] T6b. Freeze and publish host-runtime authority
  - Freeze runtime-input and runtime-plan candidates; build and independently
    review their two one-shot installers and exact embedded pins.
  - Install the fresh runtime-input root, then runtime-plan root.
  - Publish only an exact matching immutable runtime.

- [ ] T6c. Freeze and publish atomic R2 root authority
  - Freeze bundle-input and bundle-plan candidates; build and independently
    review their two one-shot installers and exact embedded pins.
  - Install the fresh bundle-input root, then bundle-plan root.
  - Publish one directory containing `bundle/` and sibling `policy.json`.

- [ ] T7. Execute fresh NullRHI attempt
  - Installed `--audit-authorities` has zero blockers/writes.
  - Create and seal the one-invocation ledger before child launch.
  - Execute only the fixed fresh attempt and exact acknowledgement.
  - Do not consume GPU/network/display/service resources.
  - Record CPU/RAM/disk budget and runtime-owner no-writer acknowledgement.

- [ ] T8. Audit, document, commit, and push
  - Verify nine UAssets, typed notifies, manifests, receipts, modes, ownership,
    final negative claims, and append-only final name.
  - Update runbook/task evidence.
  - Commit one reviewed logical change and push the collaboration branch.

## Phase Gates

- Human visual/motion acceptance remains a separate explicit gate.
- Dedicated-server/two-client interaction remains a separate explicit gate.
- R10 T7 remains a separate explicit gate.
- GTA-level or photoreal-character claims remain false in this phase.
