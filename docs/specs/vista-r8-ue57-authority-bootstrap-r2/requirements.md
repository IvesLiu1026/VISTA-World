# Requirements: VISTA R8 UE 5.7 Authority Bootstrap R2

Status: Dedicated-builder source milestone complete; privileged activation blocked
Updated: 2026-08-31
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
/root/vista-r8-native-builder-bootstrap-r1/
  bootstrap_vista_r8_native_builder.sh
  vista_r8_native_builder.py
  systemd/
    vista-r8-native-builder-phase-a.service
    vista-r8-native-builder-phase-b.service

/root/vista-r8-native-builder-bootstrap-input-r1/
  source.bundle
  phase-a-request.json
  phase-b-request.json              # appended only after closed phase A

/usr/local/libexec/vista-r8-native-builder-r1/
  vista_r8_native_builder.py

/etc/vista-r8-native-builder-r1/
  source.bundle
  phase-a-request.json
  phase-b-request.json              # appended only after closed phase A

/etc/systemd/system/
  vista-r8-native-builder-phase-a.service
  vista-r8-native-builder-phase-b.service

/var/lib/vista-r8-native-builder-r1/
  phase-a-slot/
    .build.lock
    published/
      artifacts/
      manifests/
      parent-seal-candidate/
      manifest.json
  phase-b-slot/
    .build.lock
    published/
      initial-bootstrap-candidate/
      initial-bootstrap-installer/
      manifests/
      manifest.json

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

/root/vista-r8-ue57-initial-bootstrap-r1/
  bootstrap-r8-ue57-initial-authorities
  vista_r8_ue57_initial_bootstrap.py
  input-pin.json
  .bootstrap.lock

/root/vista-r8-ue57-initial-bootstrap-installer-r1/
  install-reconcile-r8-ue57-initial-bootstrap

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

### R1a. Dedicated native-builder bootstrap

- Production native artifacts SHALL be built only by the locked system account
  `vista-r8-builder`, whose UID and primary GID are exactly `997`, home is
  `/nonexistent`, shell is `/usr/sbin/nologin`, password is locked, and
  supplementary groups are empty. Neither `/etc/subuid` nor `/etc/subgid`
  may contain an entry for that account or any range containing numeric ID 997.
  Every inactive bootstrap operation SHALL also reject any live process whose
  real/effective/saved/fs UID, GID, or supplementary groups contain numeric
  ID 997, including an orphan process that predates account creation.
- The finite root trust ceremony SHALL begin from the exact, independently
  pinned, root-owned `0555`
  `/root/vista-r8-native-builder-bootstrap-r1` inventory shown above. The
  bootstrap script may only install or exactly reconcile the inactive
  framework, append the Phase A inputs, or append the Phase B request. It SHALL
  NOT reload, enable, start, or execute either service or builder.
- The installed builder SHALL be the exact root-owned `0444`
  `/usr/local/libexec/vista-r8-native-builder-r1/vista_r8_native_builder.py`
  and SHALL run only through the pinned `/usr/bin/python3.10 -I -B`. The source
  bundle and canonical requests SHALL be root-owned `0444` regular,
  single-link files below `/etc/vista-r8-native-builder-r1`; no worktree,
  `yhliu`-owned candidate, caller path, or first-seen source is a production
  build input.
- The source bundle SHALL be an exact Git bundle bound to one full source
  commit. Each phase request SHALL be canonical, closed-schema JSON that pins
  that bundle, commit, complete required Git-blob inventory, builder, service
  unit, compiler, linker/toolchain inputs, readelf, Python, flags, bindings,
  output names, and phase lineage. Any unknown key, duplicate key, NaN,
  symlink, metadata drift, hash drift, non-HEAD blob, missing source, extra
  source, or tool alias SHALL fail closed.
- The request SHALL bind one exhaustive `strace` contract for every actual
  Python-startup, Git, compiler, and `readelf` invocation. That contract SHALL
  include exact successful regular-file pins and component chains, searched
  directory identities, failed-search state, runtime mapped-file
  device/inode/path/byte bindings, and the exact pre-run private-scratch
  inventory. Unknown, unfinished, restart, state-changing-cwd, unresolved
  relative, deleted-mapping, unbound `/proc/<pid>`, implicit alias, or
  unmodelled file syscall results SHALL fail closed. Successful scratch
  mutations SHALL remain beneath the held invocation root; transient leaves
  require matching create/delete trace evidence, and every two-path mutation
  SHALL validate both endpoints. A raw `..` component beneath invocation
  scratch SHALL be rejected before lexical normalization. A raw `..` in a
  host-tool path is accepted only when its complete requested and canonical
  component chains are root-owned, non-writable, held, and cross-bound to the
  tracer's resolved target. Exact procfs startup/source probes are finite
  tokens tied to `self` or the emitting trace tree; they are not host-input
  wildcards. `/dev/null` is the sole non-scratch writable endpoint, and only
  exact `O_RDWR` with the explicitly modelled non-mutating `O_CLOEXEC` flag is
  accepted.
- WHEN Git's process tree performs one or more exact successful
  `openat(O_RDONLY|O_CLOEXEC)` operations on
  `/sys/devices/system/cpu/online`, planner and replay SHALL canonicalize only
  that event's positive multiplicity to one. The endpoint SHALL remain an
  exact held root-owned read-only host-file authority with pinned bytes and
  component metadata. A different path, syscall, outcome, or open-flag set
  SHALL retain ordinary exact multiplicity; no sysfs prefix rule is permitted.
  Trace v4 SHALL carry exactly one closed `event_count_policies` entry binding
  this rule to `git:fetch`, and both producer and independent consumer SHALL
  reject a missing, additional, reordered, or changed policy projection.
- WHEN an observed read-only tool invocation reads a kernel virtual sysctl,
  the trace contract SHALL accept only the literal and canonical
  `/proc/sys/vm/overcommit_memory` as a distinct finite host authority. Its
  value SHALL be stream-read despite `st_size == 0`, SHALL be exactly one of
  `0\n`, `1\n`, or `2\n`, and SHALL be bound by exact byte count and SHA-256.
  The endpoint SHALL remain a root:root `0644`, single-link regular file opened
  only with `O_RDONLY|O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK`; its path, mode, owner,
  device, inode, and all other stable metadata SHALL remain exact before and
  after replay and during independent authority review.
- WHEN either native-builder service validates the finite kernel-virtual
  authority, its procfs namespace SHALL keep the exact non-process endpoint
  visible with `ProcSubset=all`, SHALL retain `ProtectProc=invisible`, and
  SHALL retain `ProtectKernelTunables=yes` so `/proc/sys` remains read-only.
  `ProcSubset=pid` is forbidden because it removes `/proc/sys` from the
  service view.
- The finite sysctl component chain MAY omit only the volatile link count of
  its exact `/proc` ancestor under one synthesized, schema-defined policy. It
  SHALL retain every other `/proc` component field and every field for `/`,
  `/proc/sys`, `/proc/sys/vm`, and the endpoint. The request cannot select or
  extend this policy. Any other `/proc` or `/proc/sys` path, alias, traversal,
  symlink, write-capable open, malformed value, content drift, inode drift,
  component drift, or orphan profile reference SHALL fail zero-publication and
  production replay. No prefix, glob, or generic procfs-host-input allowlist is
  permitted.
- The unprivileged Phase A request planner SHALL be observation-only: it SHALL
  run in fresh private temporary roots, emit only canonical request bytes, and
  assert `observation_only=true` and `production_native_output=false`. Cleanup
  failure SHALL not yield a successful request. Production replay SHALL
  revalidate the same held host inputs and exact trace profile; the rehearsal
  binary or its observations are never production artifacts.
- The only writable builder state SHALL be
  `/var/lib/vista-r8-native-builder-r1`. Its root is root:root `0555`;
  `phase-a-slot` and `phase-b-slot` are `997:997 0711`; each slot contains
  one `997:997 0600` `.build.lock`; and each final authority is the fresh
  no-replace `slot/published` root. Phase A SHALL NOT write Phase B, and Phase
  B SHALL have only read access to the closed Phase A root plus write access to
  its own slot.
- The two units SHALL be fixed root-owned systemd oneshots with
  `User=Group=vista-r8-builder`, empty supplementary/capability sets,
  `PrivateNetwork=yes`, `ProtectSystem=strict`, `ProtectHome=yes`,
  `PrivateDevices=yes`, `PrivateTmp=yes`, `UMask=0077`, closed device and
  address-family policy, namespace restrictions, a closed environment, fixed
  paths, and phase-specific `ReadWritePaths`. They SHALL remain inactive until
  a separate privileged activation approval.
- Every native job SHALL extract its exact committed C blob from the held Git
  bundle, place it in a sealed memfd, compile it twice in fresh scratch paths
  with the exact frozen flags (including explicit `-x c`), and require
  byte-identical output and identical static-ELF inspection. A result with
  `PT_INTERP`, `PT_DYNAMIC`, dynamic dependencies, build drift, tool drift,
  or metadata drift SHALL not publish.
- The production builder SHALL verify its runtime identity only from kernel
  UID/GID/group state and an exact `/proc/self/status` projection before trace
  snapshotting. Account name, home, shell, password lock, subordinate-ID, and
  orphan-process policy remain root-bootstrap invariants; production SHALL not
  perform a late `pwd`/`grp` NSS lookup that could load an untraced provider.
- Every job SHALL emit a closed canonical job manifest binding request, bundle,
  commit, source blob, bindings, flags, environment, canonical tool paths and
  pins, both build observations, output pin/mode, static-ELF result, builder
  identity, and negative network/worktree/user-candidate claims. Each phase
  SHALL emit one closed aggregate manifest whose exact inventory pins every
  artifact and job manifest. All directories and files are fsynced before a
  kernel no-replace promotion; an existing final is reconcile/audit-only.

#### R1a.1 Phase A

- Phase A SHALL contain exactly three deterministic native jobs:
  `transfer-r8-ue57-stage-installer`,
  `launch-vista-authority-parent-seal`, and
  `bootstrap-r8-ue57-initial-authorities`.
- In addition to the three artifacts and their manifests, Phase A SHALL assemble
  the exact builder-owned `parent-seal-candidate`:
  `vista_authority_parent_seal.py:0444` and
  `launch-vista-authority-parent-seal:0555`. Its helper must equal the exact
  committed blob and its launcher must equal the Phase A native artifact.
- The authority administrator SHALL accept Phase A only through standard-library
  canonical JSON, held-FD, path/owner/mode/link/inventory, SHA-256, request,
  source-bundle, source-commit, job-manifest, and static-ELF validation. It SHALL
  keep Phase A descriptors open while comparing core and parent-seal review
  material and SHALL NOT invoke a local compiler, `readelf`, Bubblewrap, a
  user namespace, or a `yhliu` production build.

#### R1a.2 Phase B

- Phase B SHALL be requested only after the complete Phase A authority validates.
  Its root-owned canonical request SHALL embed the independently derived,
  canonical core review audit and the complete initial-bootstrap input document,
  and SHALL cross-bind both documents to the Phase A manifest, job provenance,
  launcher/helper/Python pins, exact Git bundle/commit/blobs, fixed four-root
  sequence, and acknowledgements.
- Phase B SHALL reuse, byte for byte, Phase A's installed-builder pin, source
  bundle pin, commit, seven-blob inventory, tools/toolchain ledger, runtime-map
  sets, and trace-v4 contract; only its fixed service-unit binding and job may
  differ. Derivation SHALL re-read the exact Phase A request and manifest and
  prove manifest-to-request pin lineage. Later Phase B authority review SHALL
  hold both Phase A documents while revalidating those same common fields and
  the Phase B `phase_inputs.phase_a` manifest pin/content digest.
- Phase B SHALL assemble the exact builder-owned three-file
  `initial-bootstrap-candidate`:
  `bootstrap-r8-ue57-initial-authorities:0555`,
  `vista_r8_ue57_initial_bootstrap.py:0444`, and
  `input-pin.json:0444`. It SHALL then build twice and publish the sole
  `install-reconcile-r8-ue57-initial-bootstrap:0555` installer. No
  `yhliu`-owned candidate may be read.
- The Phase B aggregate and candidate/job manifests SHALL bind the embedded
  documents, Phase A provenance, all three candidate pins/modes, installer pin,
  exact inventory, deterministic double-build, static-ELF result, and negative
  network/worktree/user-candidate claims. The authority administrator SHALL
  rederive the expected request independently and validate the published files
  through held descriptors before any separate manual root ceremony.

#### R1a.3 Initial four-root installation

- Only after independent review of Phase B may the finite manual root ceremony
  copy the sole installer into the exact root-owned `0500`, sole-inventory
  installer authority. The mutable worktree, builder slot, and builder-owned
  candidate SHALL never be sudo-executed directly.
- Fresh installer execution SHALL hold and revalidate all three candidate
  files, create the exact root-owned `0555` initial-bootstrap authority through
  private same-filesystem staging and no-replace rename, install launcher and
  helper as `0500`, install the input document as `0444`, and create one
  single-link zero-byte root:root `0600` lock. Installer reconcile is
  candidate-free and fsync-only; it never creates, deletes, renames, or chmods.
- The installed launcher SHALL embed no self or input-document hash. It opens
  and hashes its held live self, proves the canonical input document binds that
  observation plus its compiled helper/Python pins, takes the nonblocking lock,
  and enters held Python with `execveat`, `-I -B`, a closed environment, and
  held launcher/helper/input/Python/lock descriptors.
- Its public CLI SHALL be exactly one operation plus its literal
  acknowledgement. Operations are `publish-initial-authorities`,
  `reconcile-initial-authorities`, and `resume-initial-authorities`; no caller
  path, pin, candidate, final root, or stage is accepted.
- The installer and initial-bootstrap helper retain the existing fixed-path,
  held-FD, no-subprocess, no-network, no-replace, full-fsync, collision,
  durability-unknown, and candidate-free reconcile contracts. Installed state
  remains the five-state prefix automaton `EXACT^k ABSENT^(4-k)` for
  `k=0..4`: core, parent-seal, BuildPlugin-helper, BuildPlugin-admin.
- Publish is permitted only from the empty prefix. Reconcile is candidate-free
  and permitted only for a nonempty exact prefix. Resume first reconciles a
  nonempty incomplete prefix and then holds every fixed Phase B candidate
  component before appending the remaining roots. Gaps, mutation, aliases,
  extra entries, owner/mode/link drift, or a changed earlier root fail closed.
- Before the first publish/resume write, the helper SHALL open every fixed
  candidate component with `O_NOFOLLOW|O_NONBLOCK`, reject special, sparse,
  oversized, multi-link, wrong-owner, wrong-mode, missing, or extra files, and
  retain every descriptor. It revalidates all candidates and the immutable
  prefix before and after each transition, including the shared BuildPlugin
  candidate between helper and administrator publication.
- Each root SHALL use a private direct child below held `/root`, held-FD copy,
  root ownership/modes, file and directory fsync, no-replace promotion, final
  reopen/rehash, and held `/root` fsync. Cleanup first proves a staging name
  still binds the held staging inode and can never mutate a promoted final.
- Every successful rename is irreversible. A post-rename error preserves the
  final inode, reports durability unknown, and permits only exact
  reconcile/resume; no failure path deletes, repairs, chmods, replaces, or
  republishes an installed root.
- The deterministic BuildPlugin admin receipt and direct-first-use fsync rules
  remain unchanged: the initial helper, parent-seal helper, core helper, and
  BuildPlugin helper each live-open, hash, fsync, and revalidate their complete
  installed roots and held `/root` before the first downstream mutation.

### R1b. Deferred sequential runtime and bundle authorities

- Runtime and bundle input/plan pins SHALL remain outside the sealed core and use
  the four fresh flat authorities shown above. The exact candidate inventories,
  reviewed-plan schemas, operation locks, no-future-root ordering, held-FD
  transfer, no-replace publication, candidate-free reconcile, immutable
  earlier-root snapshots, BuildPlugin lineage, and zero privileged subprocess
  contracts remain unchanged.
- Runtime input inventory is exactly `{input-pin.json}`; bundle input inventory
  is exactly `{input-pin.json, launch-r8-ue57}`; runtime and bundle plan
  inventories are each exactly
  `{reviewed-plan-pin.json, publish-reconcile-r8-ue57}`. Reviewed-plan schema v2
  binds the canonical plan SHA/size/content digest and exact administrator
  launcher SHA/size.
- Each later stage SHALL have a distinct static one-shot installer whose closed
  recipe binds fixed candidate/final paths, all candidate pins and modes,
  installed helper/Python pins, operation, and literal acknowledgement. It
  accepts only install or reconcile for its frozen stage and never accepts a
  caller path or pin. A user-owned review surface is never executed through
  sudo; only a separately transferred root-owned installer may mutate a stage.
- The sealed core's generic transfer launcher remains the only installer
  transfer primitive. It accepts only the four-value stage enum, externally
  reviewed installer SHA/size, and exact transfer acknowledgement; it accepts
  no path. The core helper holds the fixed candidate and publishes the exact
  root-owned installer plus transfer receipt, which cross-binds candidate and
  final pins/paths, launcher, helper/Python, stage operation/acknowledgement,
  no-replace, and reconcile-only claims.
- The BuildPlugin helper authority remains exact root:root `0555` with its sole
  helper `0500`. Its administrator authority remains exact root:root `0555`
  with `{publish-reconcile-buildplugin:0500, receipt.json:0444}`. Receipt v2,
  held administrator FD, live helper/interpreter/launcher binding,
  `admin_launcher_fd_required:true`, `launcher_receipt_live_bound:true`, and
  `downstream_live_fsync_required:true` remain mandatory for all consumers.
- `/root/vista-r8-ue57-stage-installers-r1` remains root:root `0700` only so its
  four fixed child authorities can be appended by no-replace. Each child is
  root:root `0555` with exactly
  `{install-reconcile-r8-ue57-stage:0500, receipt.json:0444}`. No child is ever
  appended internally, replaced, repaired, or deleted.
- Stage ordering remains: runtime input requires no future root; runtime plan
  requires runtime input; bundle input requires both runtime roots; bundle plan
  requires bundle input. Each operation snapshots the sealed core and every
  earlier stage by device/inode/owner/mode/link/size/hash and proves them
  unchanged. Root install, publish, and reconcile execute no Git, compiler,
  assembler, linker, `readelf`, `ldd`, toolchain discovery, or other subprocess.
- Production recipes for `launch-r8-ue57`, the runtime and bundle
  administrator launchers, and the four stage installers have not yet been
  added to the dedicated builder. Until each recipe and its closed manifests are
  approved, every corresponding production candidate entry point SHALL fail
  with `DEDICATED_BUILDER_AUTHORITY_REQUIRED` before writing or compiling.
  Test-only compile helpers may remain, but they are not production authority.
- No native production artifact may be compiled by `yhliu`, root, an
  interactive shell, Bubblewrap, a user namespace, or an ad hoc service.
  Adding later recipes is a new reviewed source milestone and does not authorize
  bootstrap installation, service activation, candidate execution, root
  publication, or T7.

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
- Interpreted scope for this milestone: implement, locally validate, review,
  commit, and push the fresh BuildPlugin and sealed UE authority source. Root
  bootstrap, builder activation, authority publication, and UE execution each
  remain separately gated after the committed bundle/request is reviewed.
- Date: 2026-08-30
