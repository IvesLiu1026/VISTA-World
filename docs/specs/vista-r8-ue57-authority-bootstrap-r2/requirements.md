# Requirements: VISTA R8 UE 5.7 Authority Bootstrap R2

Status: Security revision in progress; root publication blocked
Updated: 2026-08-30
Owner: Codex integrator

## Problem

The R8 Blender animation publication and reviewed BuildPlugin development
package exist, but the production UE executor still cannot run safely. The
current executor points at an obsolete BuildPlugin location, the immutable UE
engine and host-runtime authorities do not exist, and there is no independently
reviewed publisher for the root executor bundle, external policy, or live
Python interpreter launcher.

The older R5 engine provisioner is not sufficient for this phase. It publishes
and seals an engine-only authority. Adding the R8 host runtime below that sealed
directory afterwards would violate the immutable-authority contract.

## Scope

This phase must:

1. keep the full UE engine, normalized host runtime, and BuildPlugin as three
   separate immutable authorities;
2. align the production executor with the published BuildPlugin payload;
3. publish a versioned root-owned R2 executor bundle and external policy;
4. bind the privileged executor to the live Python interpreter that actually
   started the process;
5. permit one fresh CPU-only, network-isolated NullRHI import attempt after all
   source tests and independent reviews pass; and
6. publish append-only evidence that remains explicitly unaccepted for runtime,
   two-client, photoreal-character, and human-motion-quality claims.

This phase does not perform a visual render, use a GPU, modify Sunshine, stop an
existing UE service, claim GTA-level quality, or satisfy R10/human review.

## Fixed Authority Layout

```text
/root/vista-r8-ue57-authority-r2/
  vista_r8_ue57_authority_admin.py
  provision_vista_r8_ue57_engine.sh
  transfer-r8-ue57-stage-installer
  engine-source-pin.json
  .engine.lock
  .runtime.lock
  .bundle.lock
  .executor.lock

/root/vista-authority-parent-seal-r1/
  launch-vista-authority-parent-seal
  vista_authority_parent_seal.py

/root/vista-r8-buildplugin-authority-r1/
  vista_r8_buildplugin_authority.py

/root/vista-r8-buildplugin-admin-r1/
  publish-reconcile-buildplugin
  receipt.json

/data/vista-authorities/ue-5.7.3-r1/
  engine/
  engine-full-tree-manifest.json
  receipt.json

/data/vista-authorities/vista-r8-ue57-host-runtime-r1/
  payload/
    etc/
    lib/
    lib64/
    usr/bin/python3.10
    usr/lib/
    usr/share/
  manifest.json
  receipt.json

/data/vista-authorities/vista-r8-ue-animation-buildplugin-r1/
  payload/
  manifest.json
  receipt.json

/root/vista-r8-ue57-runtime-input-r1/
  input-pin.json

/root/vista-r8-ue57-runtime-plan-r1/
  reviewed-plan-pin.json
  publish-reconcile-r8-ue57

/root/vista-r8-ue57-bundle-input-r1/
  input-pin.json
  launch-r8-ue57

/root/vista-r8-ue57-bundle-plan-r1/
  reviewed-plan-pin.json
  publish-reconcile-r8-ue57

/root/vista-r8-ue57-stage-installers-r1/
  runtime-input/{install-reconcile-r8-ue57-stage,receipt.json}
  runtime-plan/{install-reconcile-r8-ue57-stage,receipt.json}
  bundle-input/{install-reconcile-r8-ue57-stage,receipt.json}
  bundle-plan/{install-reconcile-r8-ue57-stage,receipt.json}

/root/vista-r8-ue57-executor-r2/
  policy.json
  bundle/
    makehuman_cc0_animation_runtime_executor.py
    makehuman_cc0_animation_runtime_sandbox_wrapper.py
    makehuman_cc0_animation_runtime_commandlet.py
    launch-r8-ue57
    bundle-manifest.json

/data/vista-published/vista-action-world-r1/
  .makehuman-cc0-animation-ue57-r1-20260830a.invocation.json
```

Unknown or partial R1 root bundle/policy paths are never reused or repaired.

## Functional Requirements

### R1. Fresh, immutable publication

- Each final authority name must be absent before publication.
- Staging is a fresh direct child on the same filesystem.
- Final promotion uses kernel no-replace semantics and fsyncs the final and
  parent directories.
- Final directories are root:root `0555`; final regular files are root:root
  `0444` or `0555` only when executable.
- Symlinks, hard-link aliases, special nodes, case-fold collisions, and
  unsupported mount/device crossings are rejected.
- A durability-unknown result is reconciled by audit; publication is never
  blindly retried or deleted.
- The shared `/data/vista-authorities` parent must already be root:root `0555`;
  publishers verify it and never relax or rewrite its mode.
- The reviewed bootstrap installer creates fixed single-link root:root `0600`
  `.engine.lock`, `.runtime.lock`, `.bundle.lock`, and `.executor.lock` files
  below `/root/vista-r8-ue57-authority-r2`. Engine publish/reconcile,
  runtime plan/publish/reconcile, root-bundle plan/publish, and installed
  audit/execute/reconcile respectively take a nonblocking exclusive `flock`.
  These coordination files are outside the atomic R2 execution-authority
  inventory and cannot be caller-selected.
- The separate fixed `vista_authority_parent_seal.py` helper plus its reviewed
  one-shot launcher is the only bootstrap allowed to seal
  `/data/vista-authorities` from root:root `0755` to `0555`. Its reviewed initial
  child inventory is exactly `{blender-4.5.8-r1}`. It securely reopens and binds
  the parent and child device/inode/type inventory before and after
  `fchmod`/`fsync`. Any durability-unknown result must finish exact
  audit/reconcile while no new child exists. Only afterwards may the regenerated
  BuildPlugin publisher create its fixed child; BuildPlugin, engine, and runtime
  publishers require exact `0555` and never call chmod/fchmod on the parent.

### R1a. Sequential input and plan authorities

- Bootstrap uses a two-commit trust sequence. HEAD A contains reviewed tooling
  and may retain explicit wrapper placeholders; core generation is forbidden.
  The full engine projection is then externally reviewed and its exact source
  pin candidate frozen. Final helper/source-pin/Python literals are substituted
  into the wrapper and all final source bytes are committed as HEAD B. Transfer,
  parent-seal, BuildPlugin, and core candidates must all equal HEAD B.
- `audit-core-bootstrap-review-inputs` is `yhliu`-only and zero-write. It rejects
  any placeholder or zero pin, missing engine source pin, non-HEAD source,
  incomplete/aliased candidate inventory, non-static native launcher, or
  cross-candidate helper/Python mismatch. Root cannot run this review command.
- A separately reviewed downstream one-shot consumes the audit's externally
  reviewed pin and publishes the fixed roots in append-only prefix order:
  core, parent-seal, BuildPlugin-helper, BuildPlugin-admin. It never rolls back
  or deletes a renamed root; durability-unknown is exact reconcile-only before
  continuing to the next absent root.
- Runtime and bundle input/plan pins are never appended below the already
  sealed core bootstrap authority. They use the four fresh, flat authorities
  shown above; every root has an exact inventory and is published once.
- The unprivileged review identity is exactly `yhliu` (UID `1000021`, primary
  GID `1000001`). It performs Git proof, `readelf` discovery, compiler/toolchain
  discovery, and both native builds from the committed checkout. It cannot
  traverse `/root` and does not publish an authority.
- Runtime input candidate inventory is exactly `{input-pin.json}`. Bundle input
  candidate inventory is exactly `{input-pin.json, launch-r8-ue57}`. Runtime
  and bundle plan candidates are each exactly
  `{reviewed-plan-pin.json, publish-reconcile-r8-ue57}`.
- Reviewed-plan schema v2 binds the canonical plan SHA/size/content digest and
  exact native administrator launcher SHA/size. The launcher is built only
  after the plan and frozen input exist, from the committed C blob through a
  sealed memfd, with helper/Python pins embedded.
- A user-owned `0555` candidate is not itself a root trust anchor. For each of
  the four stages, a distinct reviewed one-shot native installer is built only
  after that candidate exists. Its compile-time literals bind the fixed
  candidate/final paths, candidate file SHA/size values, installed helper and
  Python SHA/size values, operation, and exact acknowledgement. Runtime accepts
  no caller path or pin; it exposes only install or reconcile for that frozen
  stage.
- The user-built one-shot is never executed through `sudo` from its mutable
  candidate path. The sealed core helper is the fixed transfer primitive: its
  bootstrap-only transfer command accepts only the externally reviewed
  installer SHA/size and exact acknowledgement, opens and holds the fixed
  candidate, and atomically publishes the corresponding immutable two-file
  installer authority above. Transfer receipt v1 pins the candidate/final
  installer, fixed paths, core helper/live Python, stage operations/acks, and
  no-replace/reconcile-only claims. The root-owned one-shot validates that
  exact sibling receipt and passes its inherited held-self FD to the helper.
- The initial reviewed core includes a separate static generic transfer
  launcher. This is the first trusted entry chain: it pins/reopens its fixed
  core path, helper, and Python before executing anything; accepts only the
  four-value stage enum, externally reviewed candidate SHA/size, and exact
  transfer acknowledgement; and passes a held-self FD to the generic helper
  transfer command. It accepts no path. The engine shell wrapper is not reused
  for sequential stage transfer.
- The BuildPlugin helper authority is root:root `0555` with exact sole helper
  mode `0500`. Its separate admin authority is root:root `0555` with exact
  `{publish-reconcile-buildplugin:0500, receipt.json:0444}`. The generated shell
  is invoked only by fixed `env -i` system bash, holds its own FD, and passes it
  to the helper. Privileged helper operations require an FD opened and passed
  by a trusted root process and live-validate the immutable receipt, self
  inode/bytes, helper/Python pins, and bootstrap provenance before any
  BuildPlugin write; this is an invocation requirement, not a claim that root
  cannot construct an equivalent FD. Published BuildPlugin receipt v2 carries
  the exact closed `admin_publication` lineage and all later consumers reject
  v1, omission, unknown keys, tamper, or rebinding. Root-side consumers also
  require the exact one-file BuildPlugin helper authority, live-rehash its
  single-link `0500` helper against the publisher pin, and cross-bind the
  publisher interpreter to the independently live-rehashed policy Python pin.
- `/root/vista-r8-ue57-stage-installers-r1` remains root:root `0700` solely so
  the four fixed child authorities can be added with no-replace. Each child is
  root:root `0555` with the exact two-file inventory shown above. Every later
  transfer snapshots and preserves all earlier child inode/bytes/modes; no
  child is ever appended, replaced, repaired, or deleted.
- The held root helper compares those independently transferred pins, validates
  exact candidate inventory/owner/modes/single links, copies through held FDs,
  rehashes before and after, publishes with no-replace and full fsync, and
  reopens the exact root inventory. A collision is reconcile-only; no root is
  repaired, replaced, or deleted.
- Every later install/reconcile snapshots the sealed core plus every earlier
  stage root by device/inode/mode/owner/link count/size/hash and proves those
  snapshots unchanged. Runtime input requires no future plan/bundle root;
  runtime plan requires runtime input; bundle input requires both runtime
  roots; bundle plan requires bundle input. No future-root gate is allowed.
- Root install/publish/reconcile paths execute no Git, `readelf`, GCC, cc1,
  assembler, linker, specs discovery, `ldd`, or other subprocess. They consume
  only fixed sealed documents and component-held source bytes.

### R2. Engine authority

- The only source is the fixed canonical
  `/mnt/NAS2/yhliu/UE_5.7.3_prebuilt` tree.
- A complete read-only source projection is produced first; its tree digest,
  canonical manifest SHA/content digest, complete path/type/source-mode/size/
  SHA inventory, file/directory counts, total bytes, and critical files are
  independently reviewed and committed before root publication. Root
  publication compares against those external pins and therefore does not
  promote a first-seen mutable NFS tree.
- The source is fully hashed before and after copying and both observations must
  match the committed projection pins.
- Copying occurs only after the runtime owner confirms a checkpoint/quiescent
  window with no writer to the mutable source. A read-only UE consumer may
  remain active; this phase does not itself stop or restart the existing demo
  service.
- The final manifest covers every engine directory and byte, including mode,
  owner, size, and SHA-256.
- A sealed engine receipt binds the reviewed source manifest pins, publisher,
  interpreter, pre/post source projections, final projection, and critical
  engine identity.
- Critical files include `UnrealEditor-Cmd`, `UnrealEditor.modules`, and
  `Build.version` and are pinned again in the root policy.
- The authority contains no host-runtime subdirectory.

### R3. Normalized host-runtime authority

- Host runtime is a separate allowlisted publication, not a copy of host `/`.
- It contains only the runtime loader/shared-library closure required by the
  fixed Python interpreter, bubblewrap, UE engine ELF files, and BuildPlugin
  ELF files;
  Python 3.10 standard library; explicitly documented locale/font/runtime data;
  and minimal generated non-secret `/etc` records.
- Source symlinks are resolved to regular files under closed destination names;
  final payload contains no symlinks.
- `/etc/shadow`, credentials, SSH material, home directories, `/root`, sockets,
  device nodes, display/audio sockets, GPU/DRI/NVIDIA nodes, package caches, and
  mutable logs are forbidden.
- Every copied source is opened without following an unreviewed path component,
  byte-hashed before and after copying, and recorded in a manifest/receipt.
- The ELF resolver uses parsed `PT_INTERP`/`DT_NEEDED` metadata and a closed
  system-library search map; it does not execute `ldd` on engine/plugin files.
- Before root publication, a zero-write audit plan records the exact ELF seed
  set, dependency graph, ordered search/RPATH/RUNPATH decisions, resolved
  symlink aliases, generated `/etc` bytes, data allowlist, source/tool pins, and
  final projection. Its literal digest is independently reviewed and committed;
  publication must match it and may not trust a first-seen host closure.
- Every ELF object has a closed metadata and deterministic resolution record:
  exact interpreter/NEEDED/SONAME/RPATH/RUNPATH, `$ORIGIN` expansion, ordered
  closed-default search directories, not-found decisions, selected canonical
  regular-file identity/pin, and resolution-to-graph binding. Root only
  rehashes these reviewed object/source records; it never reruns `readelf`.

### R4. BuildPlugin binding

- The executor consumes exactly
  `/data/vista-authorities/vista-r8-ue-animation-buildplugin-r1/payload`.
- It additionally pins and validates the publication manifest and receipt,
  rather than trusting only a payload tree projection.
- Descriptor modules, BuildId, two editor binaries, full projection, ownership,
  modes, manifest, and receipt must all bind to the same publication.
- The authority root inventory is exactly `payload/`, `manifest.json`, and
  `receipt.json`; no unbound sibling is allowed.

### R5. Root bundle and policy

- A separately hash-reviewed administrator helper is the only publisher for the
  R2 root authority. `bundle/` and its non-cyclic sibling `policy.json` are
  staged and promoted together through one no-replace rename.
- The bundle manifest contains exactly executor, wrapper, commandlet, and
  launcher records.
- The external policy pins the exact approved attempt and invocation-ledger
  path, bundle manifest/files, immutable Python/loader, bwrap, engine manifest/
  receipt/tree/critical files, host-runtime manifest/receipt/payload,
  BuildPlugin manifest/receipt/payload, R3 receipt/project, and fresh R8
  receipt/FBXs.
- The policy is canonical, closed-schema JSON and is not its own trust anchor.
- A zero-write bundle/policy audit plan exposes every literal pin for independent
  review before the root publisher may create the final R2 authority.
- No caller-supplied path, hash, count, UE argument, FBX list, or authority root
  is accepted by the production launcher.
- Host-runtime receipt schema v2 binds the root-owned runtime input pin,
  reviewed-plan pin, exact audit-plan bytes/content digest, core helper, runtime
  plan native launcher, and live Python. Root-policy schema v3 binds the
  analogous bundle publication provenance plus launcher source/compiler-driver/
  toolchain-ledger/output provenance. Installed execution rehashes all four
  stage roots and cross-binds these records on every operation.

### R6. Live interpreter binding

- `launch-r8-ue57` is a reviewed statically linked native ELF, not a shebang
  script. Its compiler/source/output pins are part of the reviewed bootstrap.
- The launcher opens the immutable host-runtime loader and Python once and uses
  held-descriptor `execveat(..., AT_EMPTY_PATH)` to start that loader with the
  immutable library search paths. The loader's reviewed `--argv0` is the
  immutable absolute Python path while the executable bytes remain the held
  Python FD. Python therefore derives its immutable prefix before importing the
  executor even under `-I -B`; the design does not rely on `PYTHONHOME`, which
  isolated mode ignores.
- Before any production write, the executor opens `/proc/self/exe`, hashes the
  live executable, and proves device/inode/size identity with the policy-pinned
  immutable host-runtime Python path.
- The executor requires isolated mode, disabled user site, disabled bytecode
  writes, a fixed safe environment, root EUID, fixed `sys.prefix/base_prefix`,
  a closed `sys.path`, imported stdlib origins only below immutable runtime or
  bundle, and its fixed R2 bundle path.

### R7. Sandbox invariants

- Bubblewrap remains fixed to `--unshare-all`, a private tmpfs work tree, sealed
  memfd inputs, and read-only Engine/Host Runtime/BuildPlugin mounts.
- Host-side bubblewrap is invoked through the held immutable runtime loader and
  library closure, never through a mutable host ELF interpreter.
- UE launches only `UnrealEditor-Cmd` with `-nullrhi`, `-nosound`, unattended
  flags, and the fixed reviewed commandlet.
- No host `/`, repository, output tree, network namespace, display socket,
  audio socket, `/dev/dri`, or NVIDIA device is mounted.
- The phase owns no GPU, port, Sunshine, Xvfb, input relay, or existing UE
  service lifecycle.
- Every live run records its CPU/RAM/disk budget and runtime-owner
  acknowledgement; the fixed sandbox still exposes no GPU/display/network even
  if host GPUs are busy.

### R8. One append-only attempt

- Production policy, native launcher, and executor all pin exactly
  `makehuman-cc0-animation-ue57-r1-20260830a`; production launcher accepts no
  caller-supplied attempt name or path.
- Installed `--audit-authorities` loads and fully validates every authority with
  zero writes. Execute repeats the same validation in the same process.
- Immediately before child launch, root creates the fixed direct-child
  invocation ledger with `O_EXCL`, seals it `0444`, and fsyncs it and the
  existing `0555` parent. The ledger remains after success or failure and
  permanently consumes this one invocation. A failure requires new user
  approval and a new attempt namespace.
- All held authorities are revalidated after child exit and before no-replace
  publication.
- A failed attempt cannot promote a final directory.
- If final rename succeeds but a later fsync fails, the final is preserved and
  reported durability-unknown. A root-gated reconcile path only revalidates and
  fsyncs; it never deletes, replaces, or republishes.

### R9. Evidence and claims

- Successful evidence must bind nine generated UAssets, five FBXs, typed notify
  frames/signals, engine/build/plugin/runtime projections, bundle/policy, child
  archive, and commandlet/host receipts.
- Output remains `accepted:false`.
- `runtime_interaction_verified`, `dedicated_server_two_client_verified`,
  `human_motion_quality_accepted`, `photoreal_character_accepted`, and
  `gta_level_quality` remain false.

### R10. Verification and review

- Source changes pass focused adversarial tests, related R8 regressions, Ruff,
  formatting, compilation, shell syntax, and `git diff --check`.
- At least one independent security reviewer must approve source and exact root
  scripts before privileged publication.
- Exact root helper/script hashes and acknowledgements are recorded before use.
- No privileged execution occurs from `/tmp` or a worktree; only independently
  hash-checked root-owned installed copies may run.

## Approval

- User approval: `批准！幫我做到好`
- Interpreted scope: implement and execute the already described fresh
  BuildPlugin plus sealed UE animation authority phase, while preserving later
  runtime/human/GTA acceptance gates.
- Date: 2026-08-30
