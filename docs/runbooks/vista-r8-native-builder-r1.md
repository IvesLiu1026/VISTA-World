# VISTA R8 Native Builder R1

Status: source correction complete; inactive c963 framework retained as evidence;
inputs and both build phases not executed
Updated: 2026-08-31

## Purpose and claim boundary

This boundary moves the four static R8 bootstrap builds out of the `yhliu`
review identity and into one fixed, locked, nologin system identity. It does not
make a user-owned binary trusted and it does not publish any `/root` execution
authority. It only creates two closed builder outputs for later held-FD review
by the `yhliu`-only authority administrator.

The native builder:

- runs as `vista-r8-builder` with UID/GID `997:997` and no supplementary
  groups, subordinate-ID ranges, password login, interactive shell, or other
  live process carrying numeric UID/GID/group 997;
- reads only a root-owned Git bundle and canonical request documents below
  `/etc/vista-r8-native-builder-r1`;
- has no persistent host write path outside its phase-specific slot (systemd
  private `/tmp` and the nested build sandbox scratch are ephemeral);
- resolves every source blob from the request's exact Git commit;
- compiles each static output twice in fresh scratch and requires the two byte
  streams to match;
- emits closed canonical job and phase manifests; and
- runs through one of two hardened `PrivateNetwork=yes` oneshot units.

`accepted` remains `false`. These outputs do not prove UE import, runtime
animation, human visual quality, two-client behavior, or GTA-level quality.

## Fixed identity and filesystem layout

```text
/root/vista-r8-native-builder-bootstrap-r1/       root:root 0555
  bootstrap_vista_r8_native_builder.sh            root:root 0500
  vista_r8_native_builder.py                      root:root 0400
  systemd/                                        root:root 0555
    vista-r8-native-builder-phase-a.service       root:root 0400
    vista-r8-native-builder-phase-b.service       root:root 0400

/root/vista-r8-native-builder-bootstrap-input-r1/ root:root 0700
  source.bundle                                   root:root 0400
  phase-a-request.json                            root:root 0400
  # appended only after phase A review:
  phase-b-request.json                            root:root 0400

/usr/local/libexec/vista-r8-native-builder-r1/    root:root 0555
  vista_r8_native_builder.py                      root:root 0444

/etc/vista-r8-native-builder-r1/                  root:root 0555
  source.bundle                                   root:root 0444
  phase-a-request.json                            root:root 0444
  # appended only after phase A review:
  phase-b-request.json                            root:root 0444

/var/lib/vista-r8-native-builder-r1/              root:root 0555
  phase-a-slot/                                   997:997 0711
    .build.lock                                   997:997 0600
    published/                                    997:997 0555
  phase-b-slot/                                   997:997 0711
    .build.lock                                   997:997 0600
    published/                                    997:997 0555

/etc/systemd/system/
  vista-r8-native-builder-phase-a.service         root:root 0644
  vista-r8-native-builder-phase-b.service         root:root 0644
```

The `0711` slot mode is deliberate. It does not let `yhliu` list or read
private build scratch, but it permits traversal to the named `published/`
authority after the builder has closed it. Phase A can write only its slot.
Phase B can write only its slot and receives Phase A's `published/` tree as a
read-only path. The Phase B unit has `After=phase-a` but not `Requires=phase-a`:
it must never restart Phase A while consuming an already closed manifest.
Both units use `UMask=0077`; the builder explicitly assigns the reviewed
`0444`/`0555` modes only while closing publication output.

The traced toolchain inventory uses a separately pinned `strace` and permits
only the additional `ptrace` syscall in the service allow-list. The units
still have empty capability bounding and ambient sets: neither the builder nor
the tracer receives `CAP_SYS_PTRACE`, a supplementary group, network access,
or any relaxation of the other process/filesystem hardening.

Before any root installation, the unprivileged `--plan-phase-a-request` mode
runs each Python-startup, Git, compiler, and `readelf` invocation in fresh
private scratch. It emits canonical request bytes only; its claims remain
`observation_only=true` and `production_native_output=false`. Trace contract v3
pins successful host files and path-component chains, directory searches,
negative search results, runtime mapped-file device/inode/path/bytes, and each
invocation's exact pre-run scratch inventory. Production accepts only the same
closed event multiset. Unknown or unfinished results, cwd changes, deleted
mappings, unbound process paths, implicit aliases, and unresolved scratch
mutation lifecycles fail closed. Transient Git symlinks are allowed only when
both semantic endpoints resolve below the held scratch root and the link is
subsequently deleted. Scratch-scoped raw `..` is rejected before
normalization; host GCC `..` is retained only with a complete root-owned,
non-writable component chain and matching `-yy` canonical result. Finite
`/proc/self` or trace-tree procfs probes are exact tokens rather than durable
host directories. Exact `/dev/null` with `O_RDWR` and optional `O_CLOEXEC` is
the only non-scratch mutating-open endpoint.

The one finite procfs host authority is the literal and canonical
`/proc/sys/vm/overcommit_memory`. It is not a `/proc/sys` allowlist. The
planner and both replay validators require root:root `0644`, one link, an exact
device/inode and complete endpoint component, a read-only no-follow descriptor,
and stream-pinned bytes equal to exactly `0\n`, `1\n`, or `2\n` even though
procfs reports size zero. Trace v3 synthesizes one closed
`proc-root-nlink-volatile-v1` record for that endpoint's `/proc` ancestor: only
the volatile `nlink` is omitted. Path, mode, owner, device, inode, mtime, and
ctime remain pinned there, and all metadata remains pinned for `/`,
`/proc/sys`, `/proc/sys/vm`, and the endpoint. Any other procfs path, alias,
traversal, symlink, write flag, malformed value, or replay drift offered as a
durable host input fails closed; the earlier exact process-local proc tokens
remain finite trace events rather than durable host authorities.

Both native-builder units therefore set `ProcSubset=all` so that the exact
non-process procfs endpoint remains visible inside the service mount namespace.
They retain `ProtectProc=invisible` to hide other-user process details and
`ProtectKernelTunables=yes` to keep `/proc/sys` read-only. `ProcSubset=pid` is
not a compatible hardening substitute here: it hides `/proc/sys` entirely and
would make the required trace-v3 authority impossible to validate.

The root bootstrap verifies the fixed account record, lock state,
subordinate-ID exclusion, and absence of numeric-997 processes. Production
builder startup does not repeat `pwd`/`grp` NSS lookups: it verifies kernel
real/effective/saved UID/GID, supplementary groups, and the exact
`/proc/self/status` identity projection before running traced work.

## Inputs and closed schemas

Both requests use `vista.r8-native-builder-request/v2`, canonical JSON with a
terminal newline and a valid `content_digest`. Each request binds:

- the literal phase and fixed installed builder path, mode, owner, SHA-256, and
  size;
- the fixed bundle path and exact bundle pin;
- one 40-hex Git commit and the exact seven source-blob pins;
- the pinned Python, Git, compiler, readelf, and complete toolchain ledger;
- the ordered job specifications, literal flags, helper/input bindings, and
  output names; and
- the no-network, dedicated-identity, double-build, fixed-write-root claims.

Phase A contains exactly these jobs:

1. `stage-transfer-launcher`;
2. `parent-seal-launcher`; and
3. `initial-bootstrap-launcher`.

Phase B contains only `initial-bootstrap-installer`. Its request additionally
binds the reviewed Phase A root-manifest pin/content digest, the canonical core
review audit, and the canonical initial-bootstrap input. The fresh
`vista_r8_ue57_initial_bootstrap.py` Git blob must match the helper provenance
in those embedded documents; stale helper provenance is rejected.
It must also carry Phase A's builder pin, bundle/commit/seven-blob inventory,
tools/toolchain ledger, runtime-map sets, and trace-v3 contract without change.
The zero-write derivation re-reads Phase A's request and manifest and validates
their pin edge. The later authority audit opens and retains both documents
while repeating that comparison against the installed Phase B request.

Phase output schemas are:

- `vista.r8-native-builder-phase-a-manifest/v1`;
- `vista.r8-native-builder-phase-b-manifest/v1`; and
- `vista.r8-native-builder-job-manifest/v1` for every individual build.

Every job manifest records two identical reproduction pins. The phase
manifest closes the exact relative inventory and repeats the request, Git
bundle/commit, source, tool, and job lineage.

## Finite trusted-source ceremony

Do not run the checkout copy of the bootstrap with `sudo`. First obtain the
four independently reviewed source pins from a separate review channel. Copy
only those reviewed bytes into the exact `/root` source tree above, apply the
listed owner/modes, and verify the conveyed SHA-256 and sizes again. Do not
derive an `EXPECTED` value from the mutable checkout in the same root command.

The bootstrap script itself is part of that independent record. Before its
first invocation, compare the separately conveyed SHA-256 and byte size against
the exact fixed path
`/root/vista-r8-native-builder-bootstrap-r1/bootstrap_vista_r8_native_builder.sh`.
The script's live-self check proves stable path/inode/metadata/bytes during an
operation, but deliberately does not self-authorize a digest derived from
itself.

At runtime the bootstrap requires its canonical live path, exact source-root
inventories, root ownership, single-link files, and the modes above. It opens
and retains descriptors for its live self, builder, and both unit sources. All
copies and final revalidation use those held descriptors. A second path,
symlink, extra file, hard-link alias, or source drift fails closed. Fresh file
copies use a no-clobber rename and synchronize the containing filesystem before
and after promotion; an existing exact destination is audit-only.

The input candidate root is separate because Phase B cannot be frozen until
the Phase A manifest exists. Before the Phase A input operation its exact
inventory is `{source.bundle, phase-a-request.json}`. After Phase A is closed
and reviewed, root may append only `phase-b-request.json`; the exact inventory
then contains all three files.

## Three closed bootstrap operations

Run the installed trusted bootstrap only through fixed system Bash with an
empty environment. Values in angle brackets are independently conveyed,
lowercase SHA-256/decimal-size literals; they are not shell substitutions from
the mutable checkout.

### 1. Install or reconcile the inactive framework

```bash
sudo /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin \
  /usr/bin/bash \
  /root/vista-r8-native-builder-bootstrap-r1/bootstrap_vista_r8_native_builder.sh \
  install-framework \
  <builder-sha256> <builder-size> \
  <phase-a-unit-sha256> <phase-a-unit-size> \
  <phase-b-unit-sha256> <phase-b-unit-size> \
  'I acknowledge installation or exact reconciliation of the fixed inactive VISTA R8 native-builder framework without starting a service or build.'
```

This is the only operation that may create the fixed account/group, libexec
root, empty input root, state root, slots, locks, and inactive units. A
name/UID/GID collision, unlocked password, supplementary group, subordinate-ID
mapping under the account name, any delegated subuid/subgid numeric interval
containing ID 997, any live process whose real/effective/saved/fs UID/GID or
supplementary group contains 997, unexpected inventory, active unit, or
populated service cgroup aborts the operation. The process-identity scan runs
before mutation and again at operation close, so an orphan numeric identity
cannot be reconciled into this trust boundary. Existing exact bytes reconcile;
no existing file is replaced.

Every operation performs a read-only systemd provenance gate before accepting
the framework, and the framework plus operation-close checks require the exact
installed fragments at `/etc/systemd/system`. The gate scans the complete
standard system-unit search roots (including control, transient, attached,
generator, local-vendor, vendor, and compatibility roots), rejects a custom
PID-1 `SYSTEMD_UNIT_PATH`, any shadow fragment or mask, unit-specific,
dash-prefix, or global `service.d` drop-in, alias or linked-unit symlink, and
every `*.wants` or `*.requires` entry for either builder unit. If PID 1 already
has a unit loaded, `systemctl show` must report the exact fragment path, empty
`DropInPaths`, the canonical name only, no reverse wants/requires, and a
non-enabled (`static` or `disabled`) unit-file state. This inspection does not
reload the manager or start, enable, link, or mask anything.

Immediately before printing success, every operation repeats the complete
framework verification after the final service-quiescence, numeric-identity,
and held-source checks. It then revalidates the operation's exact installed
input inventory and pins, both slot inventories, and the required absence or
closed state of each phase publication. Phase B retains held descriptors for
the candidate bundle and Phase A request as well as its new request, and the
close gate binds all three installed inputs back to those held bytes. The
close gate is the last fallible operation before the success message; a
concurrent privileged mutation is a failed bootstrap operation, not a
successful reconciliation. This final gate remains read-only and never
reloads or executes either service.

### 2. Append or reconcile Phase A inputs

```bash
sudo /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin \
  /usr/bin/bash \
  /root/vista-r8-native-builder-bootstrap-r1/bootstrap_vista_r8_native_builder.sh \
  install-phase-a-inputs \
  <source-bundle-sha256> <source-bundle-size> \
  <phase-a-request-sha256> <phase-a-request-size> \
  'I acknowledge fresh append or exact reconciliation of the reviewed VISTA R8 native-builder source bundle and phase A request without starting a build.'
```

This operation accepts no caller path. It opens only the two fixed input
candidate files, requires their exact root ownership/mode/inventory, and
appends only the fixed `/etc` destinations. An interrupted one-file prefix may
be resumed with the same pins. A gap, mismatch, extra entry, Phase A final, or
Phase B final is rejected.

After an independent installed-file/unit audit, an administrator may run one
`systemctl daemon-reload` and explicitly start only the Phase A unit. Neither
action is performed by the bootstrap or by this source-development lane.

### 3. Append or reconcile the Phase B request

First let Phase A finish and become inactive, verify its closed manifest and
all three deterministic outputs, create/review the canonical Phase B request,
and append that request to the fixed root input candidate. Then run:

```bash
sudo /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin \
  /usr/bin/bash \
  /root/vista-r8-native-builder-bootstrap-r1/bootstrap_vista_r8_native_builder.sh \
  install-phase-b-request \
  <phase-b-request-sha256> <phase-b-request-size> \
  'I acknowledge fresh append or exact reconciliation of the reviewed VISTA R8 native-builder phase B request after closed phase A publication without starting a build.'
```

The bootstrap requires an inactive/empty service cgroup, the exact installed
framework and Phase A input prefix, a `997:997 0555` Phase A publication with
the closed top-level inventory, and a still-fresh Phase B slot containing only
its lock. It then appends only the fixed root-owned Phase B request. The Phase
B builder performs the cryptographic/schema cross-binding before compiling.

After a second independent audit, the administrator may explicitly start only
the Phase B unit. Again, the bootstrap never starts or enables it.

## Closed outputs and review

Phase A final inventory is exactly:

```text
phase-a-slot/published/
  artifacts/
    transfer-r8-ue57-stage-installer
    launch-vista-authority-parent-seal
    bootstrap-r8-ue57-initial-authorities
  manifests/
    stage-transfer-launcher.json
    parent-seal-launcher.json
    initial-bootstrap-launcher.json
  parent-seal-candidate/
    vista_authority_parent_seal.py
    launch-vista-authority-parent-seal
  manifest.json
```

The parent-seal candidate is part of the same closed Phase A authority. The
helper is the exact Git-bundle blob (`0444`) and the launcher is the exact
twice-built Phase A artifact (`0555`); both are owned by `997:997` and are
sealed into the aggregate inventory. The initial-bootstrap sequence consumes
this fixed builder-owned directory directly. There is no parallel
`yhliu`-owned parent-seal native candidate and no `/data/...` fallback.

Phase B final inventory is exactly the closed aggregate described by its
manifest:

```text
phase-b-slot/published/
  initial-bootstrap-candidate/
  initial-bootstrap-installer/
  manifests/
  manifest.json
```

The `yhliu`-only authority administrator must open the known files through
held descriptors, validate owner/mode/link/inventory, canonical schemas,
content digests, request pins, Git lineage, source/helper provenance, two-build
equality, and static-ELF evidence. It consumes only these builder artifacts; it
does not compile a local `yhliu` candidate. The generic stage-transfer bytes
used in the core review candidate likewise come directly from Phase A; the
obsolete standalone stage-transfer review path is not a prerequisite.

## Failure and recovery rules

- Never delete, replace, chmod, or rebuild a `published/` final in place.
- A final collision is an audit event, not permission to rerun a compiler.
- The bootstrap never overwrites an installed source or request. Exact bytes
  reconcile; any mismatch stops.
- A Phase A input interruption may resume only its valid append-only prefix
  with the same reviewed pins.
- Do not install Phase B until Phase A is inactive, its cgroup is empty, and
  its complete manifest has passed independent review.
- Do not add either service to a target, enable it, or configure automatic
  restart. Both phases are explicit finite administrator actions.

## Source and zero-publication validation

The implementation lane may run only static checks:

```bash
/usr/bin/bash -n tools/admin/bootstrap_vista_r8_native_builder.sh
systemd-analyze verify \
  tools/admin/systemd/vista-r8-native-builder-phase-a.service \
  tools/admin/systemd/vista-r8-native-builder-phase-b.service
uv run pytest -q tools/tests/test_vista_r8_native_builder_bootstrap.py
uv run ruff check tools/tests/test_vista_r8_native_builder_bootstrap.py
git diff --check
```

In addition to the static suite, the unprivileged observation-only planner was
run twice over one ephemeral exact Git bundle after the trace-v3 correction.
Both runs completed observation and cold replay for all 27 invocation profiles
and emitted byte-identical canonical request bytes
(`1a14f2af3e574e6c13ed15f08f2c5a958c992d95eac3f33d8ceed8749593c490`,
2,435,395 bytes). These request bytes explicitly retain
`observation_only=true` and `production_native_output=false`; the ephemeral
bundle and outputs were removed after comparison. This host's two runs did not
emit the finite sysctl access, so the exact authority was correctly absent
rather than admitted as an orphan; focused planner, contract, held-open, and
revalidation tests exercise both its accepted literal form and its closed
negative matrix.

No root mutation was executed during the initial authoring pass. Subsequent
reviewed ceremonies preserved the failed 22dfa bootstrap source as evidence,
then installed the c963 fixed-identity account and framework without daemon
reload, enablement, or service start. A pre-start review found the incompatible
`ProcSubset=pid` namespace boundary, so Phase A inputs were not installed and
neither builder phase ever ran. Both units remained inactive/dead, both
`published/` roots remained absent, and no candidate publication or UE action
resulted from that framework. The corrected framework requires a newly pinned,
independently reviewed replacement ceremony; the c963 installation and all
c963 bundle/request pins are historical evidence only.
