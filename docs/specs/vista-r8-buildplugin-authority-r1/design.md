# Design: VISTA R8 BuildPlugin Authority R1

Status: Approved
Updated: 2026-08-30
Depends on: requirements.md

## Summary

One standalone standard-library Python helper has two modes. Checkout
`--audit-source` opens and validates the fixed attempt C tree without writing.
Installed-root `--publish` repeats the same validation, retains every source
descriptor, copies only from those descriptors into fresh staging, seals a
canonical manifest and receipt, revalidates both source and destination, fsyncs,
and publishes with Linux no-replace rename.

## Architecture and Flow

1. **Fixed contract.** Constants pin the source/destination, aggregate counts,
   package projection, complete inventory digest, four critical files, helper
   install location, and isolated Python interpreter.
2. **Descriptor walk.** Open the fixed source root as a no-follow directory FD.
   Recursively enumerate by directory FD; open every child directory and file
   relative to its held parent. Reject unsafe names/types/links/collisions.
   Retain all FDs in `HeldTree`.
3. **Validation.** Hash every held file, form deterministic directory/file
   records, require the complete pins, and strictly validate uplugin/modules
   semantics from held bytes.
4. **Audit mode.** Emit a canonical zero-write report and close all FDs.
   Observe the final pathname without validating it and validate the report's
   exact closed schema before emitting it.
5. **Publication gate.** Before any output, require root, the literal installed
   helper and isolated interpreter, exact acknowledgement, safe ancestry, a
   fresh destination, and a safe authority parent. Bind a held
   `/proc/self/exe` descriptor and hash/inode to the pinned Python pathname.
6. **Staging.** Create a fresh root-only staging root. Recreate the exact
   directory projection. Copy file bytes only from held FDs through `O_EXCL`
   destination FDs while recomputing source seals. Write canonical manifest and
   receipt, normalize ownership/modes, and fsync each file.
7. **Double audit.** Revalidate held source file/directory identities and names;
   independently walk staging and require exact payload plus metadata bytes and
   root ownership/modes.
8. **Publish.** Fsync deepest-first, call `renameat2(RENAME_NOREPLACE)` between
   held safe parent FDs, fsync the authority parent, and emit the already sealed
   receipt. No overwrite/update path exists. If the final parent fsync fails
   after rename, return `PUBLISHED_DURABILITY_UNKNOWN`, retain the possible final
   tree, and require the reconciliation action to re-audit and fsync it.
9. **External trust anchor.** The finalized helper hash lives only in the
   separately reviewed runbook. The administrator obtains that literal from the
   reviewed commit/channel, installs the helper, and verifies the root-owned
   installed file after installation. This closes checkout precheck-to-install
   races without making the helper recursively hash itself.

## Interfaces and Contracts

CLI:

```text
/usr/bin/python3.10 -I -B tools/admin/vista_r8_buildplugin_authority.py \
  --audit-source

/usr/bin/python3.10 -I -B \
  /root/vista-r8-buildplugin-authority-r1/vista_r8_buildplugin_authority.py \
  --publish \
  --acknowledgement "I acknowledge one fresh publication of the reviewed VISTA R8 UE 5.7 BuildPlugin authority."

# Only after BUILDPLUGIN_AUTHORITY_PUBLISHED_DURABILITY_UNKNOWN:
/usr/bin/python3.10 -I -B \
  /root/vista-r8-buildplugin-authority-r1/vista_r8_buildplugin_authority.py \
  --reconcile-published \
  --acknowledgement "I acknowledge reconciliation of the existing VISTA R8 UE 5.7 BuildPlugin authority without republishing it."
```

Production CLI paths are not caller-selectable. Tests use internal `Contract`
objects and temporary roots; this cannot bypass the root gate in `main()` or
`publish_fixed_authority()`.

Fixed authority layout:

```text
/data/vista-authorities/vista-r8-ue-animation-buildplugin-r1/
  payload/          # exact BuildPlugin tree; dirs 0555, files 0444
  manifest.json     # canonical full inventory and destination modes; 0444
  receipt.json      # canonical publication receipt; 0444
```

Canonical package projection algorithm is the R8 materializer contract: compact
JSON records for every directory (`kind`, `path`) and file (`kind`, `path`,
`sha256`, `size_bytes`), sorted by `(path, kind)`, each prefixed with an unsigned
eight-byte big-endian byte length, then SHA-256.

Canonical full inventory is newline-terminated compact sorted-key JSON of a
list containing all sorted directory records followed by all sorted file
records. Directory records bind `source_mode`; file records bind
`source_mode`, bytes, and SHA-256. The published manifest adds fixed
`authority_mode` values without changing the pinned source inventory record.

## Data Model and Migration

- `Contract`: immutable fixed paths, aggregate pins, inventory/projection pins,
  critical-file pins, and resource bounds.
- `HeldDirectory`: relative path, FD, and full stat identity.
- `HeldFile`: relative path, FD, stat identity, source mode, size, and SHA-256.
- `HeldTree`: owns all descriptors; context-manager close is mandatory.
- Manifest schema: `vista.r8-buildplugin-authority-manifest/v1`.
- Receipt schema: `vista.r8-buildplugin-authority-receipt/v1`.

There is no migration or in-place update. Rollback is to decline publication
or leave the new authority unused. Removal of a published authority is outside
this helper and requires a separate administrator decision.

## File Plan

- `docs/specs/vista-r8-buildplugin-authority-r1/{requirements,design,tasks}.md`
- `tools/admin/vista_r8_buildplugin_authority.py`
- `tools/tests/test_vista_r8_buildplugin_authority.py`
- `docs/runbooks/vista-r8-buildplugin-authority-r1.md`

## Failure Handling

- All validation errors carry stable `BUILDPLUGIN_AUTHORITY_*` codes.
- Root/install/ack/source/parent/freshness gates run before staging creation.
- Copy and destination validation failures close descriptors and remove only the
  fresh staging inode created by this invocation, after identity/type/owner
  checks. The final destination is never removed.
- `renameat2` absence or any non-`EEXIST` failure aborts without fallback.
- An `EEXIST`/`ENOTEMPTY` result is reported as a non-fresh authority.
- A parent-fsync error after successful rename is not ordinary rollback: final
  existence is unknown/durability-unknown, staging cleanup is skipped, and the
  only supported next action is root-gated reconciliation, never `--publish`.

## Testing Strategy

- Generate small fake contracts entirely under pytest `tmp_path`.
- Exercise descriptor walk and canonical calculations against regular trees.
- Mutate names/content/modes and replace pathnames between validation/copy to
  prove fail-closed behavior and held-FD provenance.
- Swap a stat-observed regular source to a FIFO immediately before open and prove
  `O_NONBLOCK` causes deterministic rejection rather than blocking.
- Bind and mismatch the live `/proc/self/exe` inode/hash against a fake pinned
  interpreter.
- Monkeypatch only the root/install gate for the private staging primitive;
  separately prove public publication always invokes the closed gate.
- Replace `renameat2` with a test no-replace primitive for pure temporary-tree
  success, collision, parent-fsync uncertainty, and reconciliation tests; static
  checks retain the production syscall.
- Run focused pytest, Ruff, compileall/AST, and owned-path diff checks only.

## Rollout and Observability

1. Merge/review source only.
2. Administrator verifies the final helper SHA independently, installs it to the
   exact root path, re-verifies the installed file against that same literal,
   and invokes audit first.
3. Administrator optionally performs one fresh publish.
4. A later, separate change may pin `payload/` in the R8 materializer only after
   inspecting the root receipt and re-running the exact projection audit.

The receipt deliberately records runtime and quality claims as false. There is
no service restart, port, secret, network, CI, or GPU impact.

## Traceability

- R1 -> fixed `Contract`, descriptor inventory, projection/inventory validators
- R2 -> critical pin table plus strict uplugin/modules validators
- R3 -> `HeldTree`, FD-relative walk/copy, pre/post identity validation
- R4 -> installed helper/interpreter/ancestry gate and CLI refusal tests
- R5 -> fresh staging, mode normalization, fsync, `renameat2` no-replace,
  durability-unknown state, and reconciliation
- R6 -> canonical manifest/receipt, closed audit validation, bounded claims
- R7 -> fake-tree focused and negative tests

## Open Questions

- None. Administrator publication remains intentionally external to this lane.

## Approval

- Requested by: VISTA owner (continuation request)
- Approved by: VISTA owner; inherited approval
- Date: 2026-08-30
