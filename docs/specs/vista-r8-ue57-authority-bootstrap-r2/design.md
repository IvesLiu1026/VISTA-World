# Design: VISTA R8 UE 5.7 Authority Bootstrap R2

Status: Fresh native-builder R2 namespace source complete; privileged activation blocked
Updated: 2026-08-31
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

### Dedicated native builder

Production native compilation moves out of the interactive `yhliu` session and
into one fixed, locked system identity:

```text
root-reviewed Git bundle + Phase A request
  -> inactive PrivateNetwork phase-A oneshot as UID/GID 997
  -> closed Phase A authority
  -> stdlib held-FD authority audit
  -> root-reviewed Phase B request embedding core audit + initial input
  -> inactive PrivateNetwork phase-B oneshot as UID/GID 997
  -> closed Phase B candidate + sole installer
```

The account is exactly `vista-r8-builder:997:997`, with locked password,
`/nonexistent` home, `/usr/sbin/nologin`, no supplementary groups, and no
subordinate-ID name or numeric range. Each inactive bootstrap operation scans
the live process table before mutation and at close, rejecting any process
whose UID/GID fields or supplementary groups contain 997; this also closes the
fresh-account orphan-numeric-ID case. This removes the former dependency on
`yhliu`, Bubblewrap, `newuidmap`, and delegated user namespaces for production
native builds.

The bootstrap trust ceremony begins from the exact root-owned
`/root/vista-r8-native-builder-bootstrap-r2` inventory. Its script has three
closed append/reconcile operations: install the inactive framework, install the
source bundle plus Phase A request, and install the Phase B request after Phase A
closes. It pins and holds its live self, builder, both unit files, and supplied
inputs; verifies exact owners, modes, links, hashes, account records, empty unit
cgroups, and append-only inventories; fsyncs every installed file and parent;
and never reloads, enables, starts, or executes systemd or the builder. One
fixed root-owned zero-byte `0600` `.bootstrap.lock` is part of that inventory;
the script validates and holds it with nonblocking `flock` for the complete
operation and rebinds every canonical trusted-source path to its held inode at
the final close gate.
Before creating an identity or target, a zero-write gate accepts only a wholly
absent group/user plus fresh five-path target set, an already exact group/user
plus fresh targets, or an exact identity plus complete framework reconciliation.
Any identity collision or partial/dirty framework is evidence, not a resumable
installation prefix.

The root-owned builder is installed as `0444` below
`/usr/local/libexec/vista-r8-native-builder-r2`. Root-owned `0444` inputs
live below `/etc/vista-r8-native-builder-r2`. The state root
`/var/lib/vista-r8-native-builder-r2` is root:root
`0555`; its two `997:997 0711` phase slots are the only writable locations
and each owns one `0600` lock. A phase creates private scratch below its own
slot and promotes exactly one fresh `published` directory with
`renameat2(RENAME_NOREPLACE)` and full file/directory/slot fsync.

Both systemd units are fixed oneshots running pinned
`/usr/bin/python3.10 -I -B` with `PrivateNetwork`, strict filesystem/home/
device/process protections, no capabilities or supplementary groups,
`UMask=0077`, a closed environment, and phase-specific read/write paths. Phase
B can read the closed Phase A publication but cannot write it. Neither unit is
enabled or started by source implementation or bootstrap installation.
Both units explicitly make the five failed R1 trusted/input/install/state roots
inaccessible. The R1 filesystem and manager failure state remain append-only
evidence and are neither an input nor a reconciliation target for R2.
Other approved `r1`-suffixed engine, host-runtime, BuildPlugin, parent-seal,
stage, attempt, and evidence authorities are separate versioned contracts, not
members of the failed native-builder namespace, and are intentionally retained.

For every job the builder validates its held executable, request, service unit,
source bundle, Git, compiler, readelf, and full toolchain ledger. It extracts
only the request's exact committed blobs from the root-owned bundle, seals the C
source in a memfd, and compiles twice in fresh scratch directories with frozen
flags and environment. It rejects any byte or static-ELF inspection difference.
Each output and canonical job manifest is single-link, closed-inventory, hashed,
fsynced, and bound by the aggregate phase manifest.

The toolchain ledger is produced by a zero-publication, unprivileged Phase A
planner using the separately pinned `strace`. Each concrete Python, Git (and
its children), compiler, and `readelf` run contributes a canonical multiset of
closed file-syscall events, successful regular-file and directory identities,
negative searches, exact private-scratch prestate, and mapped-file
device/inode/path/byte bindings. Production validates and holds those same
inputs before replay. Cwd-changing syscalls and unknown/unfinished result
forms are rejected; scratch mutations require traced create/delete lifecycle
and resolved endpoints beneath the held invocation root. Scratch-scoped raw
`..` is rejected before normalization. GCC's root-owned host paths containing
`..` are retained lexically only when their complete immutable component chain
and `-yy` resolved target agree. Exact procfs component probes use finite
trace-tree tokens instead of treating `/proc` metadata as durable host input.
The only external write-like open modeled by the observed contract is exact
`/dev/null` with `O_RDWR` and, optionally, `O_CLOEXEC`.

The `git:fetch` process tree has one observed multiplicity variation: the
exact successful `openat` of `/sys/devices/system/cpu/online` with
`O_RDONLY|O_CLOEXEC` occurs two or three times without changing its output.
Both planner and replay canonicalize only that exact event's positive
multiplicity to one. Trace v5 carries one exact `event_count_policies` entry
that binds the rule to `git:fetch`; producer and independent consumer require
that complete singleton projection. The file remains held and pinned by exact
root-owned, read-only bytes and component metadata. No other path, syscall,
outcome, or flag set receives this normalization.

Trace contract v5 retains the v4 event-count policy and finite kernel-virtual
host authority for the exact literal and canonical
`/proc/sys/vm/overcommit_memory`; this is not a procfs prefix rule. Planner
assembly recognizes no alias, traversal, symlink, or second sysctl. It opens
the endpoint read-only with
`O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK`, requires root:root `0644` with one link, and
stream-reads the value because procfs reports `st_size == 0`. Only `0\n`,
`1\n`, or `2\n` is valid, and the request records the resulting exact size and
SHA-256 together with its schema-defined stable component projection.

The v5 component-chain schema synthesizes its fixed
`proc-chain-mount-metadata-volatile-v2` policy only for the four exact procfs
records `/proc`, `/proc/sys`, `/proc/sys/vm`, and the endpoint. A systemd
`ProtectProc=invisible` mount namespace may change `device`, `inode`, `mtime`,
and `ctime` for every one of those records, so those four fields are omitted
from their cross-namespace contract shape. `/proc` also omits its volatile
process-count-sensitive `nlink`; the other three retain exact `nlink`. `/`
retains the ordinary complete metadata shape, and every procfs record still
pins path, kind, mode, owner, and the absence of symlinks.
The planner, production held-input opener, before/after replay revalidator, and
independent authority administrator derive this policy from the exact endpoint
path rather than trusting a request field. Because the endpoint inode is absent
from the cross-namespace contract projection, both production and independent
review close file/directory and bind aliases again from actual held-open
device/inode identities inside their current namespace. Any special-policy
record elsewhere, any other procfs host input, or any endpoint/content/component
mismatch fails closed. The Phase A and Phase B service namespaces use
`ProcSubset=all` so that this one non-process procfs endpoint remains visible,
while `ProtectProc=invisible` and `ProtectKernelTunables=yes` continue to hide
other-user process details and make kernel tunables read-only. A `pid`-only
procfs subset is incompatible with this contract because it removes
`/proc/sys` from the service view.

Profile coverage and orphan accounting are extended symmetrically:
the finite host record must have at least one exact successful read-only open
event in a referencing profile, every such event must have that host record,
and neither tracer nor builder runtime-map sets may absorb it as coverage.

The inactive root bootstrap owns the account-record invariants (locked
password, nologin shell, nonexistent home, subordinate-ID exclusion, and no
live numeric-997 process). Once started, the production builder deliberately
uses only kernel UID/GID/group calls plus `/proc/self/status`; it performs no
`pwd`/`grp` lookup after the runtime-map snapshot boundary, so lazy NSS loading
cannot create an unbound mapped dependency.

### Phase A and authority audit

Phase A has exactly three jobs: the generic stage-transfer launcher, parent-seal
launcher, and initial-bootstrap launcher. It also assembles the exact
`parent-seal-candidate` from the committed helper `0444` and the
builder-produced launcher `0555`. The closed aggregate inventory contains
only the artifacts, per-job manifests, parent candidate, and aggregate manifest.

The authority administrator no longer compiles or invokes `readelf` for
production review. It uses only Python standard-library canonical JSON parsing,
held descriptors, SHA-256, owner/mode/link/inventory checks, request and source
lineage checks, and an internal ELF program-header parser. All Phase A
descriptors remain held while core and parent candidate bytes are compared.
Mutation, aliasing, unknown schema keys, mismatched Git blobs, dynamic ELF
segments, or job/aggregate-manifest drift fails before any later request exists.

### Phase B and initial four-root bootstrap

After the complete Phase A authority validates, the administrator independently
derives a canonical Phase B request. That root-owned request embeds both the
canonical core review audit and the complete initial-bootstrap input document,
and cross-binds them to the exact Phase A manifest, source bundle/commit/blobs,
launcher/helper/Python pins, four-root sequence, and acknowledgements. Phase B
accepts no `yhliu` candidate.

The derivation does not discover a second toolchain contract. It copies the
exact Phase A builder pin, bundle/commit/blob inventory, tools ledger, runtime
map sets, and trace-v5 bytes, while replacing only the fixed systemd-unit
binding and job. It re-reads Phase A's request and manifest and validates their
pin edge before emitting bytes. Publication review repeats this comparison
with both Phase A documents held, so request/manifest mutation or a coherently
resealed Phase B tool/trace substitution fails before candidate acceptance.

Phase B copies the exact Phase A initial launcher, writes the committed helper
and canonical input document, and thereby assembles this exact builder-owned
candidate:

```text
initial-bootstrap-candidate/
  bootstrap-r8-ue57-initial-authorities  0555
  vista_r8_ue57_initial_bootstrap.py     0444
  input-pin.json                         0444
```

It then performs the same twice-built deterministic static process for the sole
`install-reconcile-r8-ue57-initial-bootstrap` installer. Candidate, installer,
job, candidate, and aggregate manifests bind every byte and lineage edge. The
administrator rederives the expected Phase B request and validates the
publication with held descriptors before any manual root action.

The existing initial installation protocol remains unchanged after this trust
boundary. A finite independently pinned root ceremony may copy only the sole
installer to the sole-inventory root installer authority. The builder-owned
candidate is never directly sudo-executed. The installer publishes the fixed
launcher/helper/input/lock authority, and the helper models installed roots as:

```text
0: ----
1: C---
2: CP--
3: CPH-
4: CPHA
```

Here `C`, `P`, `H`, and `A` are core, parent-seal, BuildPlugin-helper,
and BuildPlugin-admin. Every other combination is a gap. Publish starts only
from state 0; reconcile is candidate-free for states 1-4; resume first
reconciles states 1-3 and only then holds all fixed Phase B candidate inputs.
Each no-replace rename is an irreversible checkpoint; post-rename failures
preserve the final inode and require reconcile/resume.

### Deferred sequential review and install roots

Runtime input/plan and bundle input/plan remain four separate immutable roots
with their existing locks, exact inventories, reviewed-plan schemas, transfer
receipts, held-FD copy, earlier-root snapshots, no-future-root ordering,
no-replace promotion, and candidate-free reconcile contracts.

Their native production prerequisites are intentionally unavailable in this
milestone. Recipes for `launch-r8-ue57`, runtime/bundle administrator
launchers, and all four stage installers must be added to the dedicated builder
before those roots can be frozen. Until then their production entry points
return `DEDICATED_BUILDER_AUTHORITY_REQUIRED` before any write or compile.
Test-only compile helpers are not production authority.

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

The generated launcher will be a reviewed static native ELF produced by a
future dedicated-builder recipe before the bundle input root exists. Until that
recipe exists, its production entry point fails closed with
`DEDICATED_BUILDER_AUTHORITY_REQUIRED`. Root will copy its exact held bytes and
never run a compiler. The launcher opens the immutable
loader/Python and invokes the loader with held-fd `execveat`, loader `--argv0`
set to the immutable absolute Python path, a cleared environment, fixed flags,
and fixed executor path. It exposes only three closed operations: full
authority audit, the one policy-pinned execution, or reconcile-only durability
handling. It never relies on `PYTHONHOME` with isolated Python.

### Operation serialization

The fresh native-builder R2 bootstrap root owns its own `0600`, single-link
zero-byte operation lock. Every one of its three inactive install/reconcile
operations holds that lock from trusted-source opening through the terminal
close-state gate. The independently reviewed authority bootstrap root owns four
additional `0600`, single-link lock files for engine, runtime, root bundle, and executor operations. Each privileged
operation validates its literal lock identity and obtains a nonblocking
exclusive `flock`. Engine source coordination separately requires the runtime
owner to attest that no writer is active; read-only UE use is not itself a
reason to stop R6, CAR, or Sunshine.

Root audit-plan derivation, stage install, publication, and reconcile take the
appropriate fixed nonblocking lock. User candidate/plan generation is
lock-free, read-only with respect to authorities, and cannot access `/root`.

## Publication Order

1. **Source milestone — complete, non-privileged.** The dedicated builder,
   bootstrap installer, two inactive systemd units, Phase A/B request and
   manifest contracts, held-FD authority validation, initial helper provenance,
   fail-closed late entry points, tests, and documentation exist in the
   collaboration worktree. This status does not assert a final Git commit,
   root-owned bundle/request, installed account, installed unit, service run,
   builder output, root authority, or UE attempt.
2. Freeze the final reviewed source commit and independently create/check the
   exact Git bundle and canonical Phase A request. Copy only the independently
   pinned bootstrap inventory and Phase A input inventory to their fixed
   root-owned trust roots. **Not executed.**
3. Run only the bootstrap's `install-framework` and
   `install-phase-a-inputs` operations. Verify account/GID/subordinate-ID,
   files, slots, locks, units, and inactive empty cgroups. Do not reload, enable,
   or start either unit as part of installation. **Not executed; separate root
   approval required.**
4. After an independent request/unit/hash review, explicitly start the Phase A
   oneshot once. Validate the closed Phase A manifest, all three twice-built
   static artifacts, the three job manifests, and the exact parent-seal
   candidate with the standard-library held-FD authority audit. A collision or
   ambiguous publication becomes audit/reconcile, never replacement.
   **Not executed.**
5. Derive and independently review the canonical Phase B request only from the
   closed Phase A authority. Require it to embed the exact core review audit and
   initial input document. Append it through
   `install-phase-b-request` while both units remain inactive. **Not executed.**
6. With a fresh explicit activation approval, start the Phase B oneshot once.
   Independently rederive its request and validate the exact three-file initial
   candidate, sole twice-built installer, job/candidate/aggregate manifests, and
   Phase A lineage through held descriptors. **Not executed.**
7. Perform the separate finite manual trust ceremony for the sole installer,
   then install/reconcile the root-owned initial launcher/helper/input/lock and
   publish/resume the exact four-root prefix. Never execute a mutable worktree
   or builder-owned candidate directly with sudo. **Not executed.**
8. Run the root-owned parent-seal one-shot against exactly
   `{blender-4.5.8-r1}`, reconcile any durability-unknown result before another
   child exists, and publish BuildPlugin only through the reviewed root-owned
   helper/admin chain. **Not executed.**
9. Publish the full engine authority only against the externally reviewed
   source projection and fixed source pin. **Not executed.**
10. Add and approve dedicated-builder recipes for `launch-r8-ue57`, the
    runtime/bundle administrator launchers, and the four stage installers.
    Until this new source milestone closes, every corresponding production
    generator remains `DEDICATED_BUILDER_AUTHORITY_REQUIRED`. **Blocked by
    design.**
11. After those recipes close, freeze and install runtime-input/runtime-plan,
    publish the matching host runtime, then freeze and install
    bundle-input/bundle-plan and publish the atomic R2 executor authority.
    **Blocked on step 10 and all earlier authorities.**
12. Run the installed launcher in full zero-write authority-audit mode.
    **Blocked.**
13. Run one fresh installed-launcher NullRHI attempt and then audit the
    append-only evidence while retaining all later acceptance gates as false.
    **T7 is unexecuted and blocked.**

If an earlier stage fails, later stages do not run. A final-name collision is a
reconciliation event, not permission to replace or delete anything.

## Trust Boundaries

```text
root-reviewed Git bundle + canonical Phase A request
  -> pinned builder + PrivateNetwork UID/GID 997 Phase A
  -> held-FD-validated closed Phase A manifests and artifacts
  -> canonical Phase B request embedding core audit + initial input
  -> pinned builder + PrivateNetwork UID/GID 997 Phase B
  -> held-FD-validated initial candidate + sole installer
  -> independently reviewed root installer and static-launcher hashes
  -> immutable sequential input/plan authorities
  -> immutable engine / host-runtime / BuildPlugin authorities
  -> immutable R2 bundle + external policy
  -> held immutable loader/Python + held bwrap/authority descriptors
  -> isolated bwrap NullRHI commandlet
  -> validated canonical archive
  -> no-replace append-only evidence publication
```

The mutable worktree provides reviewed source bytes but never becomes runtime
or native-build authority. The root-owned Git bundle and canonical requests
authorize only their closed builder phases; neither a systemd unit nor a
builder output authorizes its own activation or root installation. The external
executor policy pins the runtime bundle; the runtime bundle does not authorize
itself.

## Failure Model

- Source drift during engine/runtime copying: pre/post digests differ; reject.
- Builder identity, subordinate-ID, input owner/mode/link, service-unit, tool,
  or Git-bundle drift: reject before compile.
- First/second native build mismatch or dynamic ELF segment: reject without a
  phase publication.
- Phase A mutation while the administrator compares core/parent materials:
  held-FD revalidation fails; do not derive Phase B.
- Embedded Phase B audit/input differs from independent derivation: reject
  before accepting any candidate or installer.
- A late native production entry point has no approved builder recipe: return
  `DEDICATED_BUILDER_AUTHORITY_REQUIRED` before write or compile.
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

- Static source tests cover the fixed 997 account, `/nonexistent`/nologin and
  no-subordinate-ID rules; exact bootstrap inventories and modes; three
  append-only bootstrap operations; inactive units; PrivateNetwork hardening;
  phase-specific writable slots; and forbidden root/home/network access.
- Builder tests cover strict canonical requests, exact Git blobs, symlink-safe
  pinned tools, sealed source memfds, two byte-identical builds, static ELF,
  closed job/phase manifests, no-replace publication, Phase A parent candidate,
  Phase B embedded-document lineage, and absence of worktree/user-candidate
  production inputs.
- Authority tests cover standard-library held-FD/hash/schema/static-ELF
  validation, namespace and file mutation, independent Phase B rederivation,
  initial-helper provenance, and fail-closed late recipes without a local
  production compiler path.
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
