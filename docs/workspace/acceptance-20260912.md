# Dual RTX 5090 workspace acceptance — 2026-09-12

Scope: a new private development workspace beside the accepted demo releases.
No game, display, input or Sunshine service was restarted. All four service
process identities and active states matched the initial read-only audit.

## Source and paper inventory

| Component | Pinned version | Verified |
| --- | --- | --- |
| VISTA-World | `f3ad1d7ed376010ac3c058e600e01e24f41e79ab` | clean checkout; initial snapshot plus fast-forward launcher update |
| VISTA-Web | `f6b6586f42b0af0820ff4bce36b6e3ce259d8ca9` (`dev`) | clean checkout |
| NYCU-NLP-Lab/EgoArgus | `4837908b2291c3aae31e8ca1999ef9313d62f175` | clean checkout; maintained release repo |
| VISTA paper | [2605.10579v2](https://arxiv.org/abs/2605.10579v2) | PDF, source archive and extracted source; 21 file hashes |
| EgoArgus paper | [2608.25561v1](https://arxiv.org/abs/2608.25561v1) | PDF, source archive and extracted source; 22 file hashes |

Original dirty source files and local paper drafts stayed on the original host.
Source transfer used Git objects at pinned commits and credential-free origins;
it did not copy local Git configuration, authentication or complete history.
Credential-pattern matches in the selected source trees were reviewed; remaining
matches were test placeholders. Sparse worktrees omit generated logs, legacy
research notes, local env files and external symlinks. Tracked data remain in the
shallow Git object database; this is not a redacted public export.

## Asset and development validation

- Seven scenes imported from catalog SHA256
  `0ad1548e0dba0a786f3273521c2038e8af1bfeabc65da7c9dd5409a4b75d118b`.
- All **14,132** source file entries checked; unique asset contents reverified
  after import. Existing release payloads were not rewritten.
- New store: **5,621,354,053 logical bytes**, versus **13,276,824,154 bytes**
  across the seven scene inventories.
- `alpine-villa-dev-r1`: **3,556** verified files in an independently editable
  project. The materializer's tests prove edits cannot change shared blobs or
  the source release; existing editable projects cannot be overwritten.
- **36 tests passed on both source and target:** 28 contract/compiler tests and
  8 workspace regression tests. Target used a fresh, project-local Python 3.12
  environment installed with the frozen lockfile.
- Scene compiler emitted build-plan content digest
  `8cc3d758aa85f0c57a7db5c308c184ce2499515e4ff0fac0210953240751ff17`.
- The workspace-local `bin/vista-workspace status` command executed successfully.
  Its uv executable is an independent copy of the previously verified tool;
  there is no release date or original-host path in the launcher.

## Target disk accounting

Decimal GB/TB, measured after transfer and validation. These are a point-in-time
snapshot; unrelated workloads can change them.

| Item | Size |
| --- | ---: |
| Local filesystem total | 982.24 GB |
| Local filesystem available after this task | 596.36 GB |
| New workspace actual allocation | 9.91 GB |
| Shared asset store actual allocation | 5.63 GB |
| Editable Villa actual allocation | 3.85 GB |
| Three repositories, including World venv | 0.279 GB |
| Papers | 0.017 GB |
| All migrated files, including preserved demo/releases | 24.45 GB |
| NAS available, initial audit | 5.55 TB shared |
| NAS2 available, initial audit | 61.39 TB shared |

NAS availability is filesystem capacity, not a personal storage quota. No NAS
mount configuration, shared model cache or another user's files were changed.
No old snapshots were deleted, so the deduplicated store does not represent
space reclaimed from the original releases.

## Acceptance limits

This validates portable source/storage organization and the CPU contract/compiler
development environment. The editable Villa was **not** launched or rebuilt;
the existing validated native demo remains active. No new Moonlight client
verification is claimed. GPU 1 interactive presentation remains unaccepted.
VISTA-Web dependencies/services and EgoArgus GPU inference dependencies, model
weights and videos are not deployed by this source migration. Paper sources were
not recompiled. Existing repo licenses and asset usage boundaries still apply.

The workspace supports adding/versioning scene packs without copying all shared
assets. Full character-runtime consolidation and typed VISTA/EgoArgus research
adapters remain separate implementation work; this receipt does not claim them.
