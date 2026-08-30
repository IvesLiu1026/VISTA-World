# Design: VISTA R8 UE 5.7 Authority Bootstrap R2

Status: Security revision in progress; root publication blocked
Updated: 2026-08-30
Depends on: requirements.md

## Decision

Use three independent immutable data authorities and one independently
published root execution bundle. Do not place host runtime or BuildPlugin below
the engine authority. This keeps each publication fresh and prevents a sealed
engine tree from later being mutated to satisfy a different contract.

## Components

### Engine publisher

A new R8 provisioner retains the R5 full pre/post tree hashing but adds:

- exact installed-script/helper identity checks;
- no-replace final rename through a small standard-library helper;
- explicit mount/device, hard-link, symlink, case-collision, and special-node
  rejection;
- exact parent-mode verification with no chmod; an engine receipt; and
- an audit/reconcile command that never removes or overwrites a final path.

### Host-runtime builder

The host-runtime builder treats fixed engine and BuildPlugin authorities plus
the source Python and bubblewrap as inputs. It parses ELF program/dynamic metadata with the
fixed root-owned `/usr/bin/readelf`, resolves needed sonames against a closed
set of system library directories, and recursively closes dependencies without
running target binaries.

The builder copies resolved bytes into their absolute-path-equivalent relative
destinations. Source symlink aliases become independent regular files so the
final runtime contains no link traversal. It also copies the fixed Python 3.10
standard library and a documented data allowlist. Minimal passwd/group/locale
configuration is generated rather than copied from sensitive host databases.

Before publication it emits a zero-write, independently frozen audit plan. The
manifest records destination path, source canonical path, source identity,
mode, size, and SHA-256. A content projection covers all payload directories and
files. Discovery is a `yhliu`-only operation from the committed checkout and
may run held/pinned `readelf`; it succeeds without `/root` traversal. Root
publication never runs discovery or a subprocess. The v2 receipt binds the
input pin, reviewed-plan pin, exact audit plan, root helper, stage-native
launcher, live interpreter, tool pins, and source authority digests.

### Sequential review and install roots

The sealed core cannot receive future runtime or bundle pins. Four independent
roots break that cycle:

```text
user runtime-input candidate -> root runtime-input
  -> user runtime plan + native launcher candidate -> root runtime-plan
  -> immutable host runtime
  -> user bundle-input + reviewed launch-r8 candidate -> root bundle-input
  -> user bundle plan + native launcher candidate -> root bundle-plan
  -> atomic root executor bundle/policy
```

User candidates are no-replace, exact-inventory `0555` directories, but remain
user-owned and therefore are review surfaces rather than root trust anchors.
After each candidate is frozen, a separate static one-shot stage installer is
built and independently reviewed. Its binary embeds the exact fixed candidate
and final paths, candidate file pins, installed helper/Python pins, operation,
and acknowledgement. At runtime it accepts only its install/reconcile operation
and exact acknowledgement. It opens and pins itself, Python, and the helper,
then uses held-fd `execveat` to enter the fixed standard-library helper with the
embedded reviewed pins; no caller path or pin is accepted.

The reviewed installer is not sudo-executed from the user candidate. The
initial sealed core contains a generic static transfer launcher as the first
trusted entry chain. It opens/pins its fixed self path, helper, and Python and
accepts only a four-value stage enum, human-transferred installer SHA/size, and
exact acknowledgement—never a path. Through held-Python `execveat` it enters a
bootstrap-only core-helper transfer operation, passing its inherited held-self
FD. The helper holds the fixed candidate FD and publishes one fresh root-owned
authority containing the binary and sealed transfer receipt. The receipt
cross-binds the external candidate pin, final installer pin/path, transfer
launcher, helper/Python, stage contract, and no-replace/reconcile claims. The
root-owned one-shot requires exact sibling inventory, binds `/proc/self/exe` to
the receipt installer pin, and carries its held-self FD across the next Python
exec; the helper revalidates that FD before any stage write.

The root helper takes the fixed stage lock, reopens all candidate inputs by
held FD, compares the transferred pins, verifies the closed documents and live
sealed inputs, copies to fresh same-filesystem staging, seals root:root modes,
and uses no-replace rename/fsync. Reconcile only audits/fsyncs an existing exact
root. A complete core/earlier-stage device/inode/mode/hash snapshot before and
after proves that later stages never append to or mutate earlier roots.

Reviewed-plan v2 is created only after its plan and native administrator binary
are complete, and binds both. The native administrator binary embeds the exact
installed helper and Python pins. Runtime and bundle publication launchers in
the plan roots accept only publish/reconcile plus the exact acknowledgement;
they accept no paths, pins, or hashes.

### Executor R2

The executor changes only the authority/bootstrap contract:

- root bundle and policy move from unknown R1 paths into one fresh atomic R2
  root authority;
- host runtime points to its independent payload;
- BuildPlugin points to its published payload and validates the adjacent
  manifest/receipt;
- the bundle inventory adds a static native `launch-r8-ue57`;
- production execution validates the live `/proc/self/exe` interpreter against
  the policy Python pin and required `sys.flags`.

The UE commandlet, archive validation, and negative acceptance claims remain
unchanged. The host bwrap launch is changed to the held immutable loader. Root
publication is corrected so post-rename durability uncertainty preserves the
final and uses reconcile-only handling.

### Root bundle/policy publisher

The reviewed publisher is installed root-owned at a fixed plan-root path and
independently hash checked before running. It reads only fixed authority paths
and fixed Git source records frozen in the bundle input. Root rehashes the
reviewed source bytes it will copy but does not execute Git or rehash/discover
the compiler/toolchain ledger.

It first emits a zero-write bundle/policy plan for independent literal review.
Only a matching reviewed plan may stage the four bundle files, canonical bundle
manifest, and external policy below one fresh root directory and publish that
directory with one no-replace rename.

The generated launcher is a reviewed static native ELF built by `yhliu` before
the bundle input root exists. Root copies its exact held bytes and never runs a
compiler. It opens the immutable
loader/Python and invokes the loader with held-fd `execveat`, loader `--argv0`
set to the immutable absolute Python path, a cleared environment, fixed flags,
and fixed executor path. It exposes only three closed operations: full
authority audit, the one policy-pinned execution, or reconcile-only durability
handling. It never relies on `PYTHONHOME` with isolated Python.

### Operation serialization

The independently reviewed bootstrap root owns four `0600`, single-link lock
files for engine, runtime, root bundle, and executor operations. Each privileged
operation validates its literal lock identity and obtains a nonblocking
exclusive `flock`. Engine source coordination separately requires the runtime
owner to attest that no writer is active; read-only UE use is not itself a
reason to stop R6, CAR, or Sunshine.

Root audit-plan derivation, stage install, publication, and reconcile take the
appropriate fixed nonblocking lock. User candidate/plan generation is
lock-free, read-only with respect to authorities, and cannot access `/root`.

## Publication Order

1. Commit implementation, review tooling, specs, and tests as HEAD A. The
   engine wrapper may still contain explicit fail-closed placeholders, but no
   core candidate may be built from HEAD A.
2. Run the complete read-only NFS engine projection, externally review its
   digest/count/byte evidence, and atomically freeze the externally pinned
   `engine-source-pin.json` review candidate. Obtain the runtime-owner
   quiescence acknowledgement; this workflow does not stop a service itself.
3. Substitute the final helper, engine-source-pin, and Python pins into the
   engine wrapper, rerun review, and commit every final source byte as HEAD B.
   Any later authority-helper edit invalidates the wrapper, generic transfer
   launcher, and core candidate; any parent-seal-helper edit invalidates its
   native launcher.
4. Build from exact HEAD B and freeze the static generic stage-transfer
   launcher, parent-seal helper/native pair, and BuildPlugin helper/admin pair.
   Then assemble the exact four-file core candidate and run
   `audit-core-bootstrap-review-inputs`, which is user-only and zero-write.
5. Independently review that canonical audit and use the separately reviewed
   one-shot root bootstrap to append four fresh immutable roots in this exact
   order: core, parent-seal, BuildPlugin-helper, BuildPlugin-admin. It copies
   prebuilt bytes and never compiles as root or creates a shared-authority
   child. Each rename is preserved; durability-unknown is reconcile-only and
   continuation is allowed only to the next absent root.
6. Run the root-owned parent-seal native one-shot against the exact initial
   `{blender-4.5.8-r1}` inventory. Resolve any durability-unknown state by exact
   reconcile before another child exists.
7. Verify `/data/vista-authorities` as root:root `0555`; publish BuildPlugin
   through exact `/usr/bin/env -i PATH=/usr/bin:/bin /usr/bin/bash` and the
   root-owned BuildPlugin admin. The helper live-binds its held admin FD and
   sealed receipt, then receipt v2 projects that exact admin authority,
   launcher, receipt, and bootstrap lineage for later live revalidation.
   User-owned/direct/shebang invocation and inherited
   `BASH_ENV` are forbidden. The publisher never chmod/fchmods the shared
   parent.
8. Publish the full engine authority with the externally reviewed source pin.
   The engine shell is likewise an explicit fixed `env -i` system-bash trust
   boundary, not a direct/shebang or pre-entry self-pin claim.
9. Atomically freeze the runtime-input user candidate. Emit the exact runtime
   plan, compile its stage-native launcher from the committed sealed-memfd C
   source, seal reviewed-plan v2 plus launcher, then build/review the two frozen
   one-shot installers. Install runtime-input, then runtime-plan; neither step
   requires a future bundle root. Publish only the exactly matching runtime.
10. Atomically freeze bundle input with the already user-built `launch-r8-ue57`.
   Emit bundle/policy core plan, compile/seal reviewed-plan v2 plus stage-native
   launcher, and build/review the two frozen one-shot installers. Install
   bundle-input, then bundle-plan, then publish the fresh atomic R2 authority.
11. Run the installed launcher in full zero-write authority-audit mode.
12. Run one fresh installed-launcher `--execute` attempt under NullRHI.
13. Audit final evidence and retain all later acceptance gates as false.

If an earlier stage fails, later stages do not run. A final-name collision is a
reconciliation event, not permission to replace or delete anything.

## Trust Boundaries

```text
reviewed root installer and static-launcher hashes
  -> immutable sequential input/plan authorities
  -> immutable engine / host-runtime / BuildPlugin authorities
  -> immutable R2 bundle + external policy
  -> held immutable loader/Python + held bwrap/authority descriptors
  -> isolated bwrap NullRHI commandlet
  -> validated canonical archive
  -> no-replace append-only evidence publication
```

The mutable worktree provides reviewed source bytes but never becomes runtime
authority. The external policy pins the bundle; the bundle does not authorize
itself.

## Failure Model

- Source drift during engine/runtime copying: pre/post digests differ; reject.
- Missing library or ambiguous soname: reject before publication.
- User candidate replacement after review: one-shot installer literal pin
  differs; reject before any authority write.
- Stage final collision: reject and use exact audit/reconcile; never replace.
- Compiler/Git/readelf availability during root publication: irrelevant by
  design; any attempted privileged subprocess is a contract failure.
- Secret/special/link node in runtime selection: reject.
- Parent or authority permission drift: reject; publishers never chmod the
  shared parent.
- Interpreter replacement after launcher verification: held-fd execution keeps
  the verified inode; executor additionally compares `/proc/self/exe` to policy.
- Host `PYTHONHOME`/stdlib fallback: impossible by contract; loader `--argv0`
  makes the immutable absolute Python path the prefix landmark, and executor
  rejects any host prefix/path/import origin.
- Partial final rename/fsync: report durability unknown and run audit; never
  blindly retry.
- UE failure/timeout/malformed archive: kill child group, retain the immutable
  invocation ledger, and require new approval/new namespace for retry.
- Rename succeeded but later fsync failed: retain final, report durability
  unknown, and allow only audit/reconcile.

## Validation

- Fake authority and fake ELF fixtures exercise publication and policy building.
- Tests cover secret-path rejection, link/special/hard-link/case collision,
  missing/ambiguous dependency, source drift, mode drift, stale R1 path, policy
  tamper, launcher inventory, live interpreter mismatch, missing `-I`/`-B`, and
  no-replace collision.
- Existing executor adversarial archive, sandbox, receipt, and publication tests
  remain green.

## Non-goals

No visual quality claim, runtime multiplayer proof, animation-quality approval,
R10 final proof, GPU render, service restart, public network exposure, or Git
storage of external authorities.
