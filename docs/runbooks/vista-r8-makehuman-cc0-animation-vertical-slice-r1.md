# VISTA R8 MakeHuman CC0 animation vertical slice

## Outcome and boundary

R8 stage 1 closes the source-motion gap without treating restricted or
unreviewed animation as VISTA-cleared. It authors five numeric, project-owned
candidate clips directly on the existing 53-bone MakeHuman rig:

| Clip | Frames / FPS | Loop | UE typed-notify contract |
| --- | ---: | --- | --- |
| `idle` | 0–60 / 30 | yes | none |
| `walk` | 0–30 / 30 | yes | none |
| `run` | 0–20 / 30 | yes | none |
| `mug_pickup_countertop` | 0–60 / 30 | no | frame 34 `vista_pickup_contact`; frame 59 `vista_pickup_completed` |
| `mug_place_countertop` | 0–60 / 30 | no | frame 34 `vista_drop_release`; frame 59 `vista_drop_completed` |

All clips are in-place and prohibit root motion. The profile declares numeric
project-authored keyframes and explicitly excludes motion derived from UE
mannequins, MetaHuman, City Sample, SimWorld, or motion-capture payloads. The
MakeHuman character source and motion recipe are declared `CC0-1.0`; external
FBX, Blend, Unreal packages, logs, and receipts remain outside Git.

This stage does **not** claim UE animation import, montage-notify authoring,
runtime interaction, motion quality, photorealism, or GTA-level quality.

## Bound source evidence

- Blender character source:
  `makehuman-cc0-smoke-r6/vista_cc0_hero.blend`, 26,919,627 bytes,
  SHA-256 `c502ae47ab07d4622bb716f01febfa8df76b2f714260c331dc4eed8e08f1d222`.
- Character worker receipt content digest:
  `3d3e9dda132289ff9a2897dd114d5d20f02b2567b6304d2009c5176d70aa01fb`.
- UE 5.7 character import R3 host receipt content digest:
  `f5a09afe52e7e97792b99e08f2b38a78bfcbfb99fe9f0bee6627b468acbf9a46`.
- UE R3 project projection SHA-256:
  `b8a116993c3f1d7a9cae6fb93f1fe247e973c92d2ab90e564993cb406d7f40f0`.
- Blender 4.5.8 executable SHA-256:
  `86b39e16cf8043a93de6b4ac5e23399d790f662c644573f600398a3c3bd121eb`.
- Official Blender 4.5.8 Linux x64 archive:
  `https://download.blender.org/release/Blender4.5/blender-4.5.8-linux-x64.tar.xz`,
  377,902,300 bytes, SHA-256
  `8cc3997ca2148a43187ca625f150b41bd3ef7c2991988725a34b46cbf25ba82f`.

Blender is not execution authority at its user-owned download path. R8 requires
the complete distribution to be provisioned at the fixed administrator-owned
authority root:

```text
/data/vista-authorities/blender-4.5.8-r1/
  distribution/
  distribution-manifest.json
```

Every directory, regular file, and relative non-escaping symlink is present in
the canonical manifest. The audit recomputes both the content-tree and full
security-tree digests, supplements the tree seal with the exact Blender binary
pin, and requires `/`, `/data`, `/data/vista-authorities`, the authority root,
the distribution, manifest, and every tree entry to be root-owned and not
group/world-writable. The bundled Python used to launch the sandbox wrapper is
also sealed by the tree manifest and recorded in the build plan.

The R3 UE receipt proves the own skeleton, skeletal mesh, physics asset, exact
53 bones, and post-exit project seal. It deliberately leaves
`animation_verified`, `interaction_verified`, and `runtime_verified` false.

## Reproduction

### Closed root bootstrap

No root authority is created from a manifest computed at installation time.
The user-side builder `tools/admin/vista_r8_publisher_bundle.py` first verifies
literal SHA-256 and byte-count pins for the ten reviewed publisher files. It
then writes, with `O_EXCL`, one minimal canonical USTAR containing those ten
regular files plus the canonical `publisher-files.sha256`. Member order,
headers, uid/gid, modes, mtime, padding, and the two terminating zero blocks
are fixed. The reviewed bundle is exactly 192,512 bytes with SHA-256
`a3ef15b22b0b0323409b937de275e2cb0d8f4a566e446074751612fc9eea408e`.

The standalone bootstrap `tools/admin/vista_r8_root_bootstrap.py` is not a
bundle member. An administrator must verify its literal reviewed pin before
and after installing it at:

```text
/root/vista-r8-root-bootstrap-r1/vista_r8_root_bootstrap.py
```

The reviewed bootstrap is currently 40,499 bytes with SHA-256
`4ad88e13267fccb0ba0f876dd5f2d6d275eb2ac2cd2b9a5d4732579f5a649be0`.
It accepts only the fixed `/tmp` bundle and official Blender archive paths,
opens each once with `O_NOFOLLOW`, requires a regular single-link inode, and
holds and revalidates the same descriptors through staging. It independently
pins the bundle, every member, the publisher manifest, the official archive,
and `/usr/bin/python3.10`.

Both `/root` trees are fully staged and audited before dirfd-relative
`renameat2(RENAME_NOREPLACE)` publication:

```text
/root/vista-r8-blender-authority-r1
/root/vista-r8-cc0-animation-publisher-r1
```

The two trees contain byte-identical root-install receipts. A third identical
activation receipt is atomically published under the fixed bootstrap root only
after both peer trees, `/data/vista-published/vista-action-world-r1`, and their
directory entries are fsynced. The Blender helper and publisher each require
the exact peer trees and all three receipts. A first-name-only or otherwise
partial install is inert; the bootstrap never automatically deletes a final
name after it becomes visible. `ROOT_BOOTSTRAP_PARTIAL_INSTALL` requires
administrator review/quarantine before any recovery attempt.

The commands below intentionally use literal pins and `set -euo pipefail`.
Nothing dynamically hashes a checkout and then treats that caller-generated
value as root authority. Execute the complete block in one Bash process; do
not resume at a later root command after any failed gate:

```bash
/usr/bin/bash -eu -o pipefail <<'VISTA_R8_ROOT_BOOTSTRAP'

ARCHIVE=/tmp/blender-4.5.8-linux-x64.tar.xz &&
BUNDLE=/tmp/vista-r8-cc0-animation-publisher-r1.ustar &&
BOOTSTRAP_SRC=tools/admin/vista_r8_root_bootstrap.py &&
BOOTSTRAP_DST=/root/vista-r8-root-bootstrap-r1/vista_r8_root_bootstrap.py &&
BOOTSTRAP_SHA=4ad88e13267fccb0ba0f876dd5f2d6d275eb2ac2cd2b9a5d4732579f5a649be0 &&
BUNDLE_SHA=a3ef15b22b0b0323409b937de275e2cb0d8f4a566e446074751612fc9eea408e &&

/usr/bin/test ! -e "$ARCHIVE" &&
/usr/bin/test ! -e "$BUNDLE" &&
/usr/bin/curl --fail --location \
  https://download.blender.org/release/Blender4.5/blender-4.5.8-linux-x64.tar.xz \
  --output "$ARCHIVE" &&
printf '%s  %s\n' \
  8cc3997ca2148a43187ca625f150b41bd3ef7c2991988725a34b46cbf25ba82f \
  "$ARCHIVE" | /usr/bin/sha256sum -c - &&
/usr/bin/test "$(/usr/bin/stat -c %s "$ARCHIVE")" = 377902300 &&

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. uv run python -m \
  tools.admin.vista_r8_publisher_bundle build &&
printf '%s  %s\n' "$BUNDLE_SHA" "$BUNDLE" | /usr/bin/sha256sum -c - &&
/usr/bin/test "$(/usr/bin/stat -c %s "$BUNDLE")" = 192512 &&

printf '%s  %s\n' "$BOOTSTRAP_SHA" "$BOOTSTRAP_SRC" | /usr/bin/sha256sum -c - &&
/usr/bin/test "$(/usr/bin/stat -c %s "$BOOTSTRAP_SRC")" = 40499 &&
/usr/bin/sudo /usr/bin/test ! -e /root/vista-r8-root-bootstrap-r1 &&
/usr/bin/sudo /usr/bin/install -d -o root -g root -m 0700 \
  /root/vista-r8-root-bootstrap-r1 &&
/usr/bin/sudo /usr/bin/install -o root -g root -m 0500 \
  "$BOOTSTRAP_SRC" "$BOOTSTRAP_DST" &&
printf '%s  %s\n' "$BOOTSTRAP_SHA" "$BOOTSTRAP_DST" \
  | /usr/bin/sudo /usr/bin/sha256sum -c - &&
/usr/bin/sudo /usr/bin/test \
  "$(/usr/bin/sudo /usr/bin/stat -c '%s:%u:%g:%a' "$BOOTSTRAP_DST")" \
  = '40499:0:0:500' &&

/usr/bin/sudo /usr/bin/env -i \
  PATH=/usr/bin:/bin \
  PYTHONNOUSERSITE=1 \
  /usr/bin/python3.10 -I -B "$BOOTSTRAP_DST" install \
  --acknowledgement \
  'I acknowledge one fresh root install of the reviewed R8 authority bundle.'
VISTA_R8_ROOT_BOOTSTRAP
```

The installed Blender helper then performs the separate safe extraction into
`/data/vista-authorities/blender-4.5.8-r1`. The archive parser rejects absolute
or traversing names, duplicates, hardlinks, devices/FIFOs, oversized payloads,
and escaping or dangling symlinks. Its `/data` manifest binds the official
archive, exact installed helper, publisher bundle, and paired install receipt.
It publishes only a fresh sibling staging tree with
`renameat2(RENAME_NOREPLACE)`:

```bash
/usr/bin/bash -eu -o pipefail <<'VISTA_R8_BLENDER_AUTHORITY'

HELPER=/root/vista-r8-blender-authority-r1/vista_blender_authority.py &&
/usr/bin/sudo /usr/bin/env -i \
  PATH=/usr/bin:/bin \
  PYTHONNOUSERSITE=1 \
  /usr/bin/python3.10 -I -B "$HELPER" prepare \
  --acknowledgement \
  'I acknowledge one root-owned fresh Blender 4.5.8 authority provision.' &&
/usr/bin/sudo /usr/bin/env -i \
  PATH=/usr/bin:/bin \
  PYTHONNOUSERSITE=1 \
  /usr/bin/python3.10 -I -B "$HELPER" audit
VISTA_R8_BLENDER_AUTHORITY
```

Retain the canonical audit JSON in administrator records. External archives,
the Blender distribution, publisher bundle, root receipts, and generated
manifests remain outside Git. This repository intentionally does not execute
any command in this section.

### Plan and candidate execution

Read-only deterministic plan (fail-closed with
`IMMUTABLE_BLENDER_AUTHORITY_REQUIRED` until the authority above exists):

```bash
PYTHONPATH=. uv run python -m \
  tools.animation.vista_playable_home_cc0.vertical_slice
```

The worktree command is audit/dry-run only. Even `sudo` against the worktree is
rejected. After review, invoke the fixed publisher with a minimal environment
and the exact acknowledgement:

The supervisor has no user-site or third-party schema dependency. It pins the
reviewed profile-schema bytes and applies the closed key/type/range/regex/const
contract with the Python standard library, avoiding the host's older
`jsonschema` package under isolated Python.

```bash
/usr/bin/sudo /usr/bin/env -i \
  PATH=/usr/bin:/bin \
  PYTHONNOUSERSITE=1 \
  /usr/bin/python3.10 -I -B \
  /root/vista-r8-cc0-animation-publisher-r1/tools/animation/vista_playable_home_cc0/vertical_slice.py \
  --execute \
  --output-root \
  /data/vista-published/vista-action-world-r1/makehuman-cc0-animation-r8-<fresh-slug> \
  --execution-acknowledgement \
  'I acknowledge one offline pinned-Blender CC0 animation candidate build; outputs stay outside Git and UE/runtime/human acceptance remain pending.'
```

The root supervisor uses bubblewrap with private user/network namespaces and
no GPU device binding, then drops the sandbox command to dedicated UID/GID
`65534`. Blender can write only to `/vista/work`, a sandbox-private tmpfs; no
host artifact, evidence, or output directory is writable or visible in the
sandbox. Before any output directory is created, the host reconstructs the
complete plan from the fixed source-character, UE-import, immutable Blender
tree, bubblewrap, worker/Git, sealed-wrapper/Git, output, and gate authorities.
A caller-resealed path or record is not execution authority.

The attempt path must be exactly one direct child of the fixed, root-owned
`/data/vista-published/vista-action-world-r1` run parent. Nested parents,
symlink aliases, lexical traversal, and caller-selected intermediate
directories are rejected before the host resolves such a parent or creates
any attempt output. The publisher audits the fixed run parent and its complete
ancestor chain; it never delegates pathname authority to a nested directory.

The host opens and holds the exact bubblewrap, Blender, bundled wrapper-Python,
source Blend, worker, and wrapper inodes while checking their sizes and SHA-256
values. It copies the plan, source Blend, worker, and wrapper into write-sealed
memfds; bubblewrap exposes only those snapshots through `--ro-bind-data`.
Critical executables are mounted from held descriptors with `--ro-bind-fd`.
The wrapper sends Blender logs only on stderr and, after independently checking
the worker exit, receipt, and six artifacts, emits exactly one deterministic
USTAR archive on stdout. The host applies hard stdout/stderr byte limits,
rejects malformed, missing, duplicate, linked, traversing, oversized, unknown,
or non-canonical archive members, validates every artifact from captured bytes,
and only then publishes those bytes with `O_EXCL` under the root-owned,
non-writable `/data/vista-published` hierarchy. Every published file is
root:root `0444`; every directory is root:root `0555`. Pre-existing or
concurrently fabricated host artifacts are never candidate authority. Held
inode identities and the complete host authority are revalidated after the
child exits and before publication.

## Append-only development evidence

All attempts are preserved under
`/data/sysx/vista-world/runs/vista-action-world-r1/`:

| Attempt | Result |
| --- | --- |
| `makehuman-cc0-animation-r8-candidate-20260829a` | Correct fail-closed: loop check evaluated the last active action rather than each named action. |
| `makehuman-cc0-animation-r8-candidate-20260829b` | Correct fail-closed: FBX validation used `ignore_leaf_bones=true`, which omitted terminal bones on round-trip. Five FBXs and one Blend remain quarantined. |
| `makehuman-cc0-animation-r8-candidate-20260829c` | First sealed five-FBX round-trip candidate with exact 53-bone closure. |
| `makehuman-cc0-animation-r8-candidate-20260829d` | Independent repeat exposed expected Blender FBX/Blend metadata-level byte drift. |
| `makehuman-cc0-animation-r8-candidate-20260829e` | Sealed candidate with exact source↔round-trip bone mapping and normalized semantic-pose digests. |
| `makehuman-cc0-animation-r8-candidate-20260829f` | Independent semantic-repeat candidate. All five semantic-pose digests exactly match attempt E. |

Blender's binary FBX and Blend exports contain time, file ID, and absolute
native-file metadata, so E/F binary SHA-256 values intentionally differ. The
normalized round-trip pose digests are byte-identical across E/F:

| Clip | Semantic pose SHA-256 |
| --- | --- |
| `idle` | `b48636e1167251befa33b87992c2fd58158bd0388d4b9796e7e9a00476a2e28f` |
| `walk` | `bbc2164b20f6f8bb3ef09933158bb29e66a5b11093b845a1c2d59f4a1ca6f562` |
| `run` | `e1b2bc07cdf123a64a316923f3457c67705db2c051f52e4a253657ea948a2fd4` |
| `mug_pickup_countertop` | `e36e92a40740c48935378cc75512fd39f104c4e9c77f632d97ddbbc9baa97062` |
| `mug_place_countertop` | `bc4645ef9ee0855f0881607f6133931a093bbe4b214dbc6f260ce987d4774587` |

Attempt E host receipt:
`makehuman-cc0-animation-r8-candidate-20260829e/host-receipt.json`.
Its current status is
`candidate_sealed_pending_git_pin_ue_import_runtime_and_human_review`; this is
expected because this worktree was intentionally not committed during the
candidate run. E/F also predate the closed host-authority and immutable-FD
snapshot repair, so they remain development evidence only. They must not be
promoted; root should execute a fresh attempt only after review and commit.

## Required next UE 5.7 import commandlet

The next implementation must use a fresh copy/projection of the sealed R3 UE
project and must remain offline and append-only. It needs these closed gates:

1. Require a post-review R8 host receipt whose worker and wrapper are bound to
   the exact root-owned publisher manifest. Refuse attempts E/F as final import
   authority because they predate this publisher boundary.
2. Revalidate all five FBX byte seals, the five semantic-pose digests, the
   identity mapping of all 53 source/round-trip bones, and the exact R3 skeleton
   package:
   `/Game/VISTA/MakeHumanCC0/R6/SK_VISTA_CC0_Hero_R6_Skeleton`.
3. Configure Interchange as animation-only: `import_animations=true`,
   `import_only_animations=true`, skeletal/static mesh import false, material
   and texture import false, and the existing MakeHuman skeleton required.
   Any newly created skeleton, mesh, material, or texture is terminal failure.
4. Import exactly five `AnimSequence` packages under one project-owned CC0 R8
   namespace. Validate skeleton identity, 30 FPS timing, expected duration,
   idle/walk/run loop policy, and zero root-transform delta after cold reload.
5. Create pickup/place montages from the two mug sequences. Add only
   `UVistaAnimationSignalNotify` instances with the exact typed signals above.
   At 30 FPS, the intended times are 34/30 and 59/30 seconds; the receipt must
   also retain the integer frame authority so floating-point time is not the
   source of truth.
6. Save and cold-reload every sequence and montage, inventory exact package
   paths/classes/file SHA-256 values, and prove the source project projection
   changed only in the allowed CC0 R8 animation namespace.
7. Keep acceptance false until a dedicated-server plus two-client interaction
   proof observes Free→Held→Placed with contact/release/completion notifies and
   rollback behavior. Locomotion additionally needs a MakeHuman-compatible
   animation blueprint/blendspace before it is called runtime-ready.

No retargeter, UE mannequin animation, MetaHuman/City Sample animation, legacy
SimWorld animation, caller-selected script, arbitrary object path, or caller
supplied notify name may enter this commandlet.

## Validation

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. uv run pytest -q \
  tools/tests/test_vista_r8_root_bootstrap.py \
  tools/tests/test_vista_playable_home_makehuman_cc0_animation_vertical_slice.py
ruff check \
  tools/admin/vista_blender_authority.py \
  tools/admin/vista_r8_publisher_bundle.py \
  tools/admin/vista_r8_root_bootstrap.py \
  tools/animation/vista_playable_home_cc0 \
  tools/blender/vista_playable_home_makehuman_cc0_animation \
  tools/tests/test_vista_r8_root_bootstrap.py \
  tools/tests/test_vista_playable_home_makehuman_cc0_animation_vertical_slice.py
ruff format --check \
  tools/admin/vista_blender_authority.py \
  tools/admin/vista_r8_publisher_bundle.py \
  tools/admin/vista_r8_root_bootstrap.py \
  tools/animation/vista_playable_home_cc0 \
  tools/blender/vista_playable_home_makehuman_cc0_animation \
  tools/tests/test_vista_r8_root_bootstrap.py \
  tools/tests/test_vista_playable_home_makehuman_cc0_animation_vertical_slice.py
git diff --check
```
