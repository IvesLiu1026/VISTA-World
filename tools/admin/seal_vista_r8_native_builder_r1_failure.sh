#!/usr/bin/env bash
# Seal the already-failed native-builder R1 as append-only evidence.
#
# This program is deliberately observational.  Its only persistent writes are
# its fixed /run lock and one fresh evidence child.  It does not reconcile any
# builder input, invoke a builder, or change systemd state.

set -euo pipefail
umask 077
IFS=$'\n\t'
export LC_ALL=C LANG=C PATH=/usr/sbin:/usr/bin:/sbin:/bin
unset BASH_ENV ENV CDPATH GLOBIGNORE PYTHONHOME PYTHONPATH

readonly SCHEMA='vista.r8-native-builder-r1-failure-seal/v1'
readonly LIVE_SELF='/root/seal-vista-r8-native-builder-r1-failure-83f180e0-20260901c.sh'
readonly LOCK_PATH='/run/lock/vista-r8-native-builder-r1-failure-seal-83f180e0-20260901c.lock'
# The authoritative seal lives below /root.  The candidate run's evidence
# directory is intentionally owned by the unprivileged operator; using a
# predictable child there would let that owner rename or substitute the child
# while this root process is writing it.  A user-visible copy can be derived
# only after this root-owned authority has closed.
readonly EVIDENCE_PARENT='/root'
readonly FINAL_NAME='vista-r8-native-builder-r1-failure-seal-b7ead170-83f180e0-20260901c'
readonly STAGING_NAME='.vista-r8-native-builder-r1-failure-seal-b7ead170-83f180e0-20260901c.staging'
readonly FINAL_PATH="${EVIDENCE_PARENT}/${FINAL_NAME}"
readonly STAGING_PATH="${EVIDENCE_PARENT}/${STAGING_NAME}"

readonly PHASE_A='vista-r8-native-builder-phase-a.service'
readonly PHASE_B='vista-r8-native-builder-phase-b.service'
readonly PHASE_A_INVOCATION='81d481f1eb764c60a737835b867fcb63'
readonly PHASE_A_START_MONOTONIC='675339972529'
readonly PHASE_A_EXIT_MONOTONIC='675341234136'
readonly FAILURE_TEXT='TRACE_PATH_DRIFT: trace host file[21]'

readonly TRUSTED_ROOT='/root/vista-r8-native-builder-bootstrap-r1'
readonly ROOT_INPUT='/root/vista-r8-native-builder-bootstrap-input-r1'
readonly LIBEXEC_ROOT='/usr/local/libexec/vista-r8-native-builder-r1'
readonly INPUT_ROOT='/etc/vista-r8-native-builder-r1'
readonly STATE_ROOT='/var/lib/vista-r8-native-builder-r1'
readonly BUILDER="${LIBEXEC_ROOT}/vista_r8_native_builder.py"
readonly BUNDLE="${INPUT_ROOT}/source.bundle"
readonly REQUEST="${INPUT_ROOT}/phase-a-request.json"
readonly PHASE_A_UNIT="/etc/systemd/system/${PHASE_A}"
readonly PHASE_B_UNIT="/etc/systemd/system/${PHASE_B}"

readonly BOOTSTRAP_SHA256='26442b12d9a8da3614831232772983a5b6b7860f8a415511c8a381aca68c4cd4'
readonly BOOTSTRAP_BYTES='36759'
readonly BUILDER_SHA256='9b6c4b587456de26e9c20560d5eb62d09982e73e1e6cb9493dbf663b521fa441'
readonly BUILDER_BYTES='211353'
readonly BUNDLE_SHA256='abd3c562ad5b975919aab3a6b0420f5326bd802774dda6e74a0db99d78b95387'
readonly BUNDLE_BYTES='3329251'
readonly REQUEST_SHA256='b5ce8dc8b558ee62f92247c97a5daa169ec83e3864fa388f6088aad3aa3a904f'
readonly REQUEST_BYTES='2483604'
readonly PHASE_A_UNIT_SHA256='f3acaf39ad92fe2bc70680c9f7e0d8ab1e1f68f68553ebd4a74137c0cf939520'
readonly PHASE_A_UNIT_BYTES='1858'
readonly PHASE_B_UNIT_SHA256='1e65b23e2ae857b88d3b488a63cfcba3d6462c265ff3b4d3b33da046b9f96035'
readonly PHASE_B_UNIT_BYTES='2143'
readonly REQUEST_V4_RECORD_SHA256='d368db55dc50b90822dda55d2c1ad5b2a8cdabaf8b9ba7aac61e50832f4fd476'
readonly REQUEST_V4_RECORD_BYTES='1895'
readonly FAILED_SEALER='/root/seal-vista-r8-native-builder-r1-failure-83f180e0.failed-journal-boot-descriptor-20260901a.sh'
readonly FAILED_SEALER_SHA256='518e9ecbf2f37d9bb70069e334a0e4ab5125cf6a8a756abd28be31aaa1641c90'
readonly FAILED_SEALER_BYTES='31883'
readonly FAILED_SEALER_LOCK='/run/lock/vista-r8-native-builder-r1-failure-seal-83f180e0.lock'
readonly FAILED_EMPTY_LOCK_SEALER='/root/seal-vista-r8-native-builder-r1-failure-83f180e0.failed-empty-lock-metadata-20260901b.sh'
readonly FAILED_EMPTY_LOCK_SEALER_SHA256='109dbc378343c0309198d2c43b0772e124201609554440c63d80dc1c9b7101ba'
readonly FAILED_EMPTY_LOCK_SEALER_BYTES='33118'
readonly FAILED_EMPTY_LOCK_SEALER_LOCK='/run/lock/vista-r8-native-builder-r1-failure-seal-83f180e0-20260901.lock'
readonly FAILED_EMPTY_JOURNAL_SEALER='/root/seal-vista-r8-native-builder-r1-failure-83f180e0.failed-empty-phase-b-journal-metadata-20260901c.sh'
readonly FAILED_EMPTY_JOURNAL_SEALER_SHA256='640f72e4d66176bcc1e73412abcafdc57d5252060ce26beea59f61db9ffdeb7e'
readonly FAILED_EMPTY_JOURNAL_SEALER_BYTES='34299'
readonly FAILED_EMPTY_JOURNAL_SEALER_LOCK='/run/lock/vista-r8-native-builder-r1-failure-seal-83f180e0-20260901b.lock'
readonly EMPTY_SHA256='e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
readonly R1_BUILDER_UID='997'
readonly R1_BUILDER_GID='997'
readonly R1_PHASE_A_LOCK_FD='11'
readonly R1_PHASE_B_LOCK_FD='12'

readonly TRUSTED_INVENTORY=$'bootstrap_vista_r8_native_builder.sh\nsystemd\nsystemd/vista-r8-native-builder-phase-a.service\nsystemd/vista-r8-native-builder-phase-b.service\nvista_r8_native_builder.py'
readonly INPUT_INVENTORY=$'phase-a-request.json\nsource.bundle'
readonly LIBEXEC_INVENTORY='vista_r8_native_builder.py'
readonly STATE_INVENTORY=$'phase-a-slot\nphase-a-slot/.build.lock\nphase-b-slot\nphase-b-slot/.build.lock'

STAGING_OWNED='false'
PUBLISHED='false'
TRAVERSAL_SEQUENCE='0'
TRAVERSAL_LIST=''

fail() {
  printf '%s\n' "VISTA R8 R1 failure sealer: $*" >&2
  exit 126
}

cleanup() {
  local status="$?"
  if [[ "${STAGING_OWNED}" == 'true' && "${PUBLISHED}" == 'false' ]]; then
    /usr/bin/rm -rf --one-file-system -- "${STAGING_PATH}" || status=125
  fi
  exit "${status}"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

sha256_of() {
  /usr/bin/sha256sum -- "$1" | /usr/bin/cut -d' ' -f1
}

verify_live_self() {
  local path_identity held_identity held_sha
  path_identity="$(/usr/bin/stat -Lc '%d:%i:%a:%u:%g:%h:%s' -- "${LIVE_SELF}")" || \
    fail 'cannot inspect live sealer path'
  held_identity="$(/usr/bin/stat -Lc '%d:%i:%a:%u:%g:%h:%s' -- "${SELF_HELD}")" || \
    fail 'cannot inspect held sealer identity'
  held_sha="$(sha256_of "${SELF_HELD}")" || fail 'cannot hash held sealer'
  [[ "${path_identity}" == "${SELF_IDENTITY}" && \
    "${held_identity}" == "${SELF_IDENTITY}" && \
    "${held_sha}" == "${SELF_SHA256}" ]] || fail 'live sealer changed'
}

assert_directory() {
  local path="$1" mode="$2" uid="$3" gid="$4" label="$5"
  [[ -d "${path}" && ! -L "${path}" ]] || fail "${label} is not a directory"
  [[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g' -- "${path}")" == \
    "directory|${mode}|${uid}|${gid}" ]] || fail "${label} metadata differs"
}

assert_closed_file_metadata() {
  local path="$1" mode="$2" uid="$3" gid="$4" label="$5"
  [[ -f "${path}" && ! -L "${path}" ]] || fail "${label} is not closed regular"
  [[ "$(/usr/bin/stat -Lc '%a|%u|%g|%h' -- "${path}")" == \
    "${mode}|${uid}|${gid}|1" ]] || fail "${label} metadata differs"
}

assert_file() {
  local path="$1" mode="$2" uid="$3" gid="$4" sha="$5" bytes="$6" label="$7"
  assert_closed_file_metadata "${path}" "${mode}" "${uid}" "${gid}" "${label}"
  [[ "$(/usr/bin/stat -Lc '%s' -- "${path}")" == "${bytes}" ]] || \
    fail "${label} size differs"
  [[ "$(sha256_of "${path}")" == "${sha}" ]] || fail "${label} SHA-256 differs"
}

assert_empty_file() {
  local path="$1" mode="$2" uid="$3" gid="$4" label="$5"
  assert_file "${path}" "${mode}" "${uid}" "${gid}" "${EMPTY_SHA256}" 0 "${label}"
}

assert_lock_file() {
  local path="$1"
  [[ -f "${path}" && ! -L "${path}" ]] || fail "build lock differs: ${path}"
  [[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h|%s' -- "${path}")" == \
    "regular empty file|600|${R1_BUILDER_UID}|${R1_BUILDER_GID}|1|0" ]] || \
    fail "build lock metadata differs: ${path}"
}

verify_held_r1_lock() {
  local path="$1" fd="$2" expected_id="$3" label="$4" path_id held_id held_metadata
  assert_lock_file "${path}"
  path_id="$(/usr/bin/stat -Lc '%d:%i' -- "${path}")" || fail "cannot stat ${label} path"
  held_id="$(/usr/bin/stat -Lc '%d:%i' -- "/proc/$$/fd/${fd}")" || \
    fail "cannot stat held ${label}"
  held_metadata="$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h|%s' -- "/proc/$$/fd/${fd}")" || \
    fail "cannot inspect held ${label}"
  [[ "${path_id}" == "${expected_id}" && "${held_id}" == "${expected_id}" ]] || \
    fail "${label} inode binding differs"
  [[ "${held_metadata}" == \
    "regular empty file|600|${R1_BUILDER_UID}|${R1_BUILDER_GID}|1|0" ]] || \
    fail "held ${label} metadata differs"
}

secure_reexec_with_r1_build_locks() {
  local marker="${VISTA_R8_R1_LOCK_GUARD-}"
  if [[ "${marker}" == "${R1_PHASE_A_LOCK_FD}:${R1_PHASE_B_LOCK_FD}" ]]; then
    unset VISTA_R8_R1_LOCK_GUARD
    /usr/bin/flock -n "${R1_PHASE_A_LOCK_FD}" || fail 'R1 Phase A build lock is held'
    /usr/bin/flock -n "${R1_PHASE_B_LOCK_FD}" || fail 'R1 Phase B build lock is held'
    return
  fi
  [[ ! -v VISTA_R8_R1_LOCK_GUARD ]] || fail 'unexpected R1 lock-guard marker'

  # Bash redirections cannot express O_NOFOLLOW without also leaving a race.
  # Re-exec through a tiny trusted opener so both pre-existing locks are opened
  # read-only, non-creating, non-blocking, and no-follow.  The fixed descriptors
  # and their flock ownership survive exec into a fresh Bash process.
  exec /usr/bin/python3 -c '
import fcntl
import os
import stat
import sys


def die(message):
    print(f"VISTA R8 R1 lock guard: {message}", file=sys.stderr)
    raise SystemExit(126)


live_self, phase_a, phase_b, uid_text, gid_text, fd_a_text, fd_b_text = sys.argv[1:]
uid = int(uid_text)
gid = int(gid_text)
targets = (int(fd_a_text), int(fd_b_text))
paths = (phase_a, phase_b)
opened = []
flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
for path in paths:
    try:
        fd = os.open(path, flags)
    except OSError as error:
        die(f"secure non-creating open failed for {path}: {error}")
    opened.append(fd)
    held = os.fstat(fd)
    try:
        named = os.lstat(path)
    except OSError as error:
        die(f"cannot rebind {path}: {error}")
    if not stat.S_ISREG(held.st_mode):
        die(f"lock is not regular: {path}")
    if (
        stat.S_IMODE(held.st_mode) != 0o600
        or held.st_uid != uid
        or held.st_gid != gid
        or held.st_nlink != 1
        or held.st_size != 0
        or (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino)
    ):
        die(f"lock metadata or inode binding differs: {path}")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        die(f"lock is already held for {path}: {error}")

for source, target in zip(opened, targets, strict=True):
    os.dup2(source, target, inheritable=True)
    os.set_inheritable(target, True)
for source in opened:
    if source not in targets:
        os.close(source)
for path, target in zip(paths, targets, strict=True):
    held = os.fstat(target)
    try:
        named = os.lstat(path)
    except OSError as error:
        die(f"cannot close-gate {path}: {error}")
    if (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino):
        die(f"lock changed before re-exec: {path}")

environment = {
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "VISTA_R8_R1_LOCK_GUARD": f"{targets[0]}:{targets[1]}",
}
os.execve("/usr/bin/bash", ["/usr/bin/bash", live_self], environment)
' "${LIVE_SELF}" \
    "${STATE_ROOT}/phase-a-slot/.build.lock" \
    "${STATE_ROOT}/phase-b-slot/.build.lock" \
    "${R1_BUILDER_UID}" "${R1_BUILDER_GID}" \
    "${R1_PHASE_A_LOCK_FD}" "${R1_PHASE_B_LOCK_FD}"
}

assert_inventory() {
  local root="$1" expected="$2" observed
  observed="$(/usr/bin/find -P "${root}" -xdev -mindepth 1 -printf '%P\n' | /usr/bin/sort)" || \
    fail "cannot enumerate ${root}"
  [[ "${observed}" == "${expected}" ]] || fail "inventory differs: ${root}"
}

assert_r1_filesystem() {
  assert_directory "${TRUSTED_ROOT}" 555 0 0 'trusted R1 root'
  assert_directory "${TRUSTED_ROOT}/systemd" 555 0 0 'trusted R1 systemd root'
  assert_inventory "${TRUSTED_ROOT}" "${TRUSTED_INVENTORY}"
  assert_file "${TRUSTED_ROOT}/bootstrap_vista_r8_native_builder.sh" 500 0 0 \
    "${BOOTSTRAP_SHA256}" "${BOOTSTRAP_BYTES}" 'trusted R1 bootstrap'
  assert_file "${TRUSTED_ROOT}/vista_r8_native_builder.py" 400 0 0 \
    "${BUILDER_SHA256}" "${BUILDER_BYTES}" 'trusted R1 builder'
  assert_file "${TRUSTED_ROOT}/systemd/${PHASE_A}" 400 0 0 \
    "${PHASE_A_UNIT_SHA256}" "${PHASE_A_UNIT_BYTES}" 'trusted R1 Phase A unit'
  assert_file "${TRUSTED_ROOT}/systemd/${PHASE_B}" 400 0 0 \
    "${PHASE_B_UNIT_SHA256}" "${PHASE_B_UNIT_BYTES}" 'trusted R1 Phase B unit'

  assert_directory "${ROOT_INPUT}" 700 0 0 'root R1 input'
  assert_inventory "${ROOT_INPUT}" "${INPUT_INVENTORY}"
  assert_file "${ROOT_INPUT}/source.bundle" 400 0 0 \
    "${BUNDLE_SHA256}" "${BUNDLE_BYTES}" 'root R1 source bundle'
  assert_file "${ROOT_INPUT}/phase-a-request.json" 400 0 0 \
    "${REQUEST_SHA256}" "${REQUEST_BYTES}" 'root R1 Phase A request'

  assert_directory "${LIBEXEC_ROOT}" 555 0 0 'installed R1 libexec root'
  assert_inventory "${LIBEXEC_ROOT}" "${LIBEXEC_INVENTORY}"
  assert_file "${BUILDER}" 444 0 0 "${BUILDER_SHA256}" "${BUILDER_BYTES}" \
    'installed R1 builder'
  assert_directory "${INPUT_ROOT}" 555 0 0 'installed R1 input root'
  assert_inventory "${INPUT_ROOT}" "${INPUT_INVENTORY}"
  assert_file "${BUNDLE}" 444 0 0 "${BUNDLE_SHA256}" "${BUNDLE_BYTES}" \
    'installed R1 source bundle'
  assert_file "${REQUEST}" 444 0 0 "${REQUEST_SHA256}" "${REQUEST_BYTES}" \
    'installed R1 Phase A request'
  assert_file "${PHASE_A_UNIT}" 644 0 0 "${PHASE_A_UNIT_SHA256}" \
    "${PHASE_A_UNIT_BYTES}" 'installed R1 Phase A unit'
  assert_file "${PHASE_B_UNIT}" 644 0 0 "${PHASE_B_UNIT_SHA256}" \
    "${PHASE_B_UNIT_BYTES}" 'installed R1 Phase B unit'

  assert_directory "${STATE_ROOT}" 555 0 0 'installed R1 state root'
  assert_directory "${STATE_ROOT}/phase-a-slot" 711 997 997 'R1 Phase A slot'
  assert_directory "${STATE_ROOT}/phase-b-slot" 711 997 997 'R1 Phase B slot'
  assert_lock_file "${STATE_ROOT}/phase-a-slot/.build.lock"
  assert_lock_file "${STATE_ROOT}/phase-b-slot/.build.lock"
  assert_inventory "${STATE_ROOT}" "${STATE_INVENTORY}"
  [[ ! -e "${STATE_ROOT}/phase-a-slot/published" && \
    ! -L "${STATE_ROOT}/phase-a-slot/published" ]] || fail 'R1 Phase A publication exists'
  [[ ! -e "${STATE_ROOT}/phase-b-slot/published" && \
    ! -L "${STATE_ROOT}/phase-b-slot/published" ]] || fail 'R1 Phase B publication exists'
}

capture_manager() {
  local unit="$1" output="$2"
  /usr/bin/systemctl show --no-pager \
    -p MainPID -p ControlPID -p Result -p NRestarts \
    -p ExecMainStartTimestampMonotonic -p ExecMainExitTimestampMonotonic \
    -p ExecMainCode -p ExecMainStatus -p ProcSubset -p Names -p LoadState \
    -p ActiveState -p SubState -p FragmentPath -p DropInPaths -p UnitFileState \
    -p ActiveEnterTimestampMonotonic -p Job -p NeedDaemonReload \
    -p ConditionResult -p InvocationID -- "${unit}" >"${output}" || \
    fail "cannot capture manager state: ${unit}"
}

property_value() {
  local file="$1" key="$2" count
  count="$(/usr/bin/awk -F= -v key="${key}" '$1 == key { count++ } END { print count + 0 }' "${file}")"
  [[ "${count}" == '1' ]] || fail "manager property count differs: ${key}"
  /usr/bin/awk -F= -v key="${key}" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' "${file}"
}

assert_property() {
  local file="$1" key="$2" expected="$3" observed
  observed="$(property_value "${file}" "${key}")" || \
    fail "cannot read unique manager property: ${key}"
  [[ "${observed}" == "${expected}" ]] || \
    fail "manager ${key} differs in ${file}"
}

assert_manager_state() {
  local a="$1" b="$2"
  assert_property "${a}" LoadState loaded
  assert_property "${a}" ActiveState failed
  assert_property "${a}" SubState failed
  assert_property "${a}" Result exit-code
  assert_property "${a}" UnitFileState static
  assert_property "${a}" FragmentPath "${PHASE_A_UNIT}"
  assert_property "${a}" Names "${PHASE_A}"
  assert_property "${a}" DropInPaths ''
  assert_property "${a}" Job ''
  assert_property "${a}" MainPID 0
  assert_property "${a}" ControlPID 0
  assert_property "${a}" NRestarts 0
  assert_property "${a}" ExecMainStartTimestampMonotonic "${PHASE_A_START_MONOTONIC}"
  assert_property "${a}" ExecMainExitTimestampMonotonic "${PHASE_A_EXIT_MONOTONIC}"
  assert_property "${a}" ExecMainCode 1
  assert_property "${a}" ExecMainStatus 2
  assert_property "${a}" ActiveEnterTimestampMonotonic 0
  assert_property "${a}" InvocationID "${PHASE_A_INVOCATION}"
  assert_property "${a}" ProcSubset all
  assert_property "${a}" NeedDaemonReload no
  assert_property "${a}" ConditionResult yes

  assert_property "${b}" LoadState loaded
  assert_property "${b}" ActiveState inactive
  assert_property "${b}" SubState dead
  assert_property "${b}" Result success
  assert_property "${b}" UnitFileState static
  assert_property "${b}" FragmentPath "${PHASE_B_UNIT}"
  assert_property "${b}" Names "${PHASE_B}"
  assert_property "${b}" DropInPaths ''
  assert_property "${b}" Job ''
  assert_property "${b}" MainPID 0
  assert_property "${b}" ControlPID 0
  assert_property "${b}" NRestarts 0
  assert_property "${b}" ExecMainStartTimestampMonotonic 0
  assert_property "${b}" ExecMainExitTimestampMonotonic 0
  assert_property "${b}" ExecMainCode 0
  assert_property "${b}" ExecMainStatus 0
  assert_property "${b}" ActiveEnterTimestampMonotonic 0
  assert_property "${b}" InvocationID ''
  assert_property "${b}" ProcSubset all
  assert_property "${b}" NeedDaemonReload no
  assert_property "${b}" ConditionResult no
}

encode() { printf '%s' "$1" | /usr/bin/base64 -w0; }

compact_journal_boot_id() {
  local boot_id="$1" compact
  [[ "${boot_id}" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || \
    return 1
  compact="${boot_id//-/}"
  [[ "${compact}" =~ ^[0-9a-f]{32}$ ]] || return 1
  printf '%s' "${compact}"
}

emit_record() {
  local path="$1" metadata kind sha='-' target='-' encoded_path
  metadata="$(/usr/bin/stat -c '%F|%a|%u|%g|%h|%s|%d|%i|%y|%z' -- "${path}")" || \
    fail "cannot stat discovery path: ${path}"
  if [[ -L "${path}" ]]; then
    kind='symlink'
    target="$(/usr/bin/readlink -- "${path}")" || fail "cannot read symlink: ${path}"
    target="$(encode "${target}")" || fail "cannot encode symlink target: ${path}"
  elif [[ -f "${path}" ]]; then
    kind='regular'
    sha="$(sha256_of "${path}")" || fail "cannot hash discovery file: ${path}"
  elif [[ -d "${path}" ]]; then
    kind='directory'
  else
    kind='special'
  fi
  encoded_path="$(encode "${path}")" || fail "cannot encode discovery path: ${path}"
  printf '%s\t%s\t%s\t%s\t%s\n' "${encoded_path}" "${kind}" "${metadata}" "${sha}" "${target}"
}

fresh_traversal_list() {
  TRAVERSAL_SEQUENCE="$((TRAVERSAL_SEQUENCE + 1))"
  TRAVERSAL_LIST="${STAGING_PATH}/.traversal-${TRAVERSAL_SEQUENCE}.nul"
  [[ ! -e "${TRAVERSAL_LIST}" && ! -L "${TRAVERSAL_LIST}" ]] || \
    fail "traversal list collided: ${TRAVERSAL_LIST}"
  ( set -o noclobber; : >"${TRAVERSAL_LIST}" ) 2>/dev/null || \
    fail "cannot create traversal list: ${TRAVERSAL_LIST}"
  [[ -f "${TRAVERSAL_LIST}" && ! -L "${TRAVERSAL_LIST}" ]] || \
    fail "traversal list is not regular: ${TRAVERSAL_LIST}"
}

emit_tree() {
  local root="$1" path list count='0'
  fresh_traversal_list
  list="${TRAVERSAL_LIST}"
  if ! /usr/bin/find -P "${root}" -xdev -print0 | /usr/bin/sort -z >"${list}"; then
    fail "cannot materialize traversal for ${root}"
  fi
  while IFS= read -r -d '' path; do
    emit_record "${path}"
    count="$((count + 1))"
  done <"${list}"
  [[ "${count}" -gt 0 ]] || fail "traversal is empty: ${root}"
  /usr/bin/rm -f -- "${list}" || fail "cannot remove owned traversal list: ${list}"
}

capture_installed_inventory() {
  local output="$1" root
  {
    printf '%s\n' 'path_base64\tkind\tstat(F|mode|uid|gid|nlink|size|dev|inode|mtime_full|ctime_full)\tsha256\tsymlink_target_base64'
    for root in "${TRUSTED_ROOT}" "${ROOT_INPUT}" "${LIBEXEC_ROOT}" "${INPUT_ROOT}" "${STATE_ROOT}"; do
      emit_tree "${root}"
    done
    emit_record "${PHASE_A_UNIT}"
    emit_record "${PHASE_B_UNIT}"
  } >"${output}"
}

capture_root_history() {
  local output="$1" path roots_list count='0'
  fresh_traversal_list
  roots_list="${TRAVERSAL_LIST}"
  if ! /usr/bin/find -P /root -xdev -mindepth 1 -maxdepth 1 \
      \( -name 'vista-r8-native-builder-bootstrap-r1*' \
      -o -name 'vista-r8-native-builder-bootstrap-input-r1*' \
      -o -name 'vista-r8-native-builder-*-20260831*.sh' \
      -o -name 'seal-vista-r8-native-builder-r1-failure-*.sh' \
      -o -name '.vista-r8-native-builder-bootstrap-r1*' \
      -o -name '.vista-r8-native-builder-bootstrap-input-r1*' \) \
      -print0 | /usr/bin/sort -z >"${roots_list}"; then
    fail 'cannot materialize R1 root-history selection'
  fi
  {
    printf '%s\n' 'path_base64\tkind\tstat(F|mode|uid|gid|nlink|size|dev|inode|mtime_full|ctime_full)\tsha256\tsymlink_target_base64'
    while IFS= read -r -d '' path; do
      emit_tree "${path}"
      count="$((count + 1))"
    done <"${roots_list}"
    emit_record "${FAILED_SEALER_LOCK}"
    emit_record "${FAILED_EMPTY_JOURNAL_SEALER_LOCK}"
  } >"${output}"
  [[ "${count}" -gt 0 ]] || fail 'R1 root history selection is empty'
  /usr/bin/rm -f -- "${roots_list}" || fail 'cannot remove owned root-history list'
}

assert_required_history() {
  local path
  for path in \
    '/root/vista-r8-native-builder-bootstrap-r1.failed-22dfa1c4-20260831a' \
    '/root/vista-r8-native-builder-bootstrap-r1.failed-c963c44e-procsubset-pid-20260831a' \
    '/root/vista-r8-native-builder-bootstrap-r1.failed-b7ead170-recovery-partial-20260831a' \
    '/root/vista-r8-native-builder-recovery-b7ead170-20260831b.sh' \
    '/root/vista-r8-native-builder-recovery-b7ead170-20260831c.sh' \
    '/root/vista-r8-native-builder-recovery-b7ead170-20260831d.sh' \
    "${FAILED_SEALER}" "${FAILED_EMPTY_LOCK_SEALER}" \
    "${FAILED_EMPTY_JOURNAL_SEALER}"; do
    [[ -e "${path}" || -L "${path}" ]] || fail "required append-only R1 history is absent: ${path}"
  done
  [[ ! -e '/root/vista-r8-native-builder-bootstrap-r1.failed-b7ead170-recovery-partial-20260831b' && \
    ! -L '/root/vista-r8-native-builder-bootstrap-r1.failed-b7ead170-recovery-partial-20260831b' ]] || \
    fail 'successful recovery unexpectedly left its failure slot'
  assert_file "${FAILED_SEALER}" 500 0 0 "${FAILED_SEALER_SHA256}" \
    "${FAILED_SEALER_BYTES}" 'prior failed journal sealer'
  assert_file "${FAILED_EMPTY_LOCK_SEALER}" 500 0 0 \
    "${FAILED_EMPTY_LOCK_SEALER_SHA256}" "${FAILED_EMPTY_LOCK_SEALER_BYTES}" \
    'prior failed empty-lock-metadata sealer'
  assert_file "${FAILED_EMPTY_JOURNAL_SEALER}" 500 0 0 \
    "${FAILED_EMPTY_JOURNAL_SEALER_SHA256}" "${FAILED_EMPTY_JOURNAL_SEALER_BYTES}" \
    'prior failed empty-phase-b-journal-metadata sealer'
  assert_empty_file "${FAILED_SEALER_LOCK}" 600 0 0 'prior failed journal sealer lock'
  assert_empty_file "${FAILED_EMPTY_JOURNAL_SEALER_LOCK}" 600 0 0 \
    'prior failed empty-phase-b-journal-metadata sealer lock'
  [[ ! -e "${FAILED_EMPTY_LOCK_SEALER_LOCK}" && \
    ! -L "${FAILED_EMPTY_LOCK_SEALER_LOCK}" ]] || \
    fail 'prior empty-lock-metadata sealer unexpectedly created its fresh lock'
}

capture_cgroups() {
  local output="$1" unit events
  : >"${output}"
  for unit in "${PHASE_A}" "${PHASE_B}"; do
    events="/sys/fs/cgroup/system.slice/${unit}/cgroup.events"
    if [[ -e "${events}" ]]; then
      /usr/bin/grep -qx 'populated 0' "${events}" || fail "unit cgroup is populated: ${unit}"
      printf '%s\tpresent\tpopulated 0\n' "${unit}" >>"${output}"
    else
      printf '%s\tabsent\n' "${unit}" >>"${output}"
    fi
  done
}

[[ "${EUID}" -eq 0 ]] || fail 'root EUID is required'
[[ "$#" -eq 0 ]] || fail 'arguments are forbidden'
[[ "$0" == "${LIVE_SELF}" && -f "${LIVE_SELF}" && ! -L "${LIVE_SELF}" ]] || \
  fail 'live sealer path differs'
[[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h' -- "${LIVE_SELF}")" == \
  'regular file|500|0|0|1' ]] || fail 'live sealer metadata differs'
exec {SELF_FD}<"${LIVE_SELF}"
readonly SELF_FD
SELF_HELD="/proc/$$/fd/${SELF_FD}"
SELF_IDENTITY="$(/usr/bin/stat -Lc '%d:%i:%a:%u:%g:%h:%s' -- "${SELF_HELD}")" || \
  fail 'cannot bind held sealer identity'
SELF_SHA256="$(sha256_of "${SELF_HELD}")" || fail 'cannot hash held sealer'
SELF_BYTES="$(/usr/bin/stat -Lc '%s' -- "${SELF_HELD}")" || fail 'cannot size held sealer'
readonly SELF_HELD SELF_IDENTITY SELF_SHA256 SELF_BYTES
verify_live_self
secure_reexec_with_r1_build_locks
R1_PHASE_A_LOCK_ID="$(/usr/bin/stat -Lc '%d:%i' -- "/proc/$$/fd/${R1_PHASE_A_LOCK_FD}")" || \
  fail 'cannot bind R1 Phase A build lock'
R1_PHASE_B_LOCK_ID="$(/usr/bin/stat -Lc '%d:%i' -- "/proc/$$/fd/${R1_PHASE_B_LOCK_FD}")" || \
  fail 'cannot bind R1 Phase B build lock'
readonly R1_PHASE_A_LOCK_ID R1_PHASE_B_LOCK_ID
assert_r1_filesystem
assert_required_history
verify_held_r1_lock "${STATE_ROOT}/phase-a-slot/.build.lock" \
  "${R1_PHASE_A_LOCK_FD}" "${R1_PHASE_A_LOCK_ID}" 'R1 Phase A build lock'
verify_held_r1_lock "${STATE_ROOT}/phase-b-slot/.build.lock" \
  "${R1_PHASE_B_LOCK_FD}" "${R1_PHASE_B_LOCK_ID}" 'R1 Phase B build lock'

if [[ ! -e "${LOCK_PATH}" && ! -L "${LOCK_PATH}" ]]; then
  ( set -o noclobber; : >"${LOCK_PATH}" ) 2>/dev/null || fail 'cannot create fixed seal lock'
  /usr/bin/chown root:root -- "${LOCK_PATH}"
  /usr/bin/chmod 0600 -- "${LOCK_PATH}"
fi
[[ -f "${LOCK_PATH}" && ! -L "${LOCK_PATH}" ]] || fail 'fixed seal lock is not regular'
[[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h|%s' -- "${LOCK_PATH}")" == \
  'regular empty file|600|0|0|1|0' ]] || fail 'fixed seal lock metadata differs'
exec {LOCK_FD}<>"${LOCK_PATH}"
readonly LOCK_FD
/usr/bin/flock -n "${LOCK_FD}" || fail 'another R1 failure seal owns the fixed lock'

[[ "$(/usr/bin/readlink -e -- "${EVIDENCE_PARENT}")" == "${EVIDENCE_PARENT}" ]] || \
  fail 'evidence parent canonical path differs'
assert_directory "${EVIDENCE_PARENT}" 700 0 0 'fixed evidence parent'
exec {EVIDENCE_FD}<"${EVIDENCE_PARENT}"
readonly EVIDENCE_FD
EVIDENCE_IDENTITY="$(/usr/bin/stat -Lc '%d:%i:%F:%a:%u:%g' -- "${EVIDENCE_PARENT}")"
readonly EVIDENCE_IDENTITY
[[ ! -e "${FINAL_PATH}" && ! -L "${FINAL_PATH}" ]] || fail 'final evidence already exists'
[[ ! -e "${STAGING_PATH}" && ! -L "${STAGING_PATH}" ]] || fail 'staging evidence already exists'
trap '' HUP INT TERM
/usr/bin/mkdir -m 0700 -- "/proc/self/fd/${EVIDENCE_FD}/${STAGING_NAME}" || fail 'cannot create fresh staging'
STAGING_OWNED='true'
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
/usr/bin/chown root:root -- "${STAGING_PATH}"
assert_directory "${STAGING_PATH}" 700 0 0 'fresh evidence staging'

assert_r1_filesystem
assert_required_history
verify_held_r1_lock "${STATE_ROOT}/phase-a-slot/.build.lock" \
  "${R1_PHASE_A_LOCK_FD}" "${R1_PHASE_A_LOCK_ID}" 'R1 Phase A build lock'
verify_held_r1_lock "${STATE_ROOT}/phase-b-slot/.build.lock" \
  "${R1_PHASE_B_LOCK_FD}" "${R1_PHASE_B_LOCK_ID}" 'R1 Phase B build lock'
assert_r1_filesystem

BOOT_ID="$(/usr/bin/tr -d '\n' </proc/sys/kernel/random/boot_id)"
[[ "${BOOT_ID}" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || \
  fail 'boot ID differs'
JOURNAL_BOOT_ID="$(compact_journal_boot_id "${BOOT_ID}")" || \
  fail 'cannot derive compact journal boot ID'
readonly JOURNAL_BOOT_ID
printf '%s\n' "${BOOT_ID}" >"${STAGING_PATH}/boot-id.txt"

capture_manager "${PHASE_A}" "${STAGING_PATH}/phase-a.systemctl-show.txt"
capture_manager "${PHASE_B}" "${STAGING_PATH}/phase-b.systemctl-show.txt"
assert_manager_state "${STAGING_PATH}/phase-a.systemctl-show.txt" \
  "${STAGING_PATH}/phase-b.systemctl-show.txt"

/usr/bin/journalctl --no-pager --quiet --boot="${JOURNAL_BOOT_ID}" \
  "_SYSTEMD_INVOCATION_ID=${PHASE_A_INVOCATION}" -u "${PHASE_A}" \
  --output=short-iso-precise >"${STAGING_PATH}/phase-a.journal.txt" || \
  fail 'cannot capture R1 Phase A journal'
/usr/bin/grep -Fq -- "${FAILURE_TEXT}" "${STAGING_PATH}/phase-a.journal.txt" || \
  fail 'exact R1 Phase A failure is absent from its invocation journal'
/usr/bin/journalctl --no-pager --quiet --boot="${JOURNAL_BOOT_ID}" -u "${PHASE_B}" \
  --output=short-iso-precise >"${STAGING_PATH}/phase-b.journal.txt" || \
  fail 'cannot capture R1 Phase B journal'

/usr/bin/install -o root -g root -m 0600 -- "${PHASE_A_UNIT}" \
  "${STAGING_PATH}/phase-a.unit"
/usr/bin/install -o root -g root -m 0600 -- "${PHASE_B_UNIT}" \
  "${STAGING_PATH}/phase-b.unit"

/usr/bin/jq -e -cS \
  '{request_schema:.schema,phase:.phase,status:.status,accepted:.accepted,claims:.claims,trace_contract_schema:.trace_contract.schema,host_file_count:(.trace_contract.host_files|length),host_file_index:21,host_file:.trace_contract.host_files[21],event_count_policies:.trace_contract.event_count_policies}' \
  "${REQUEST}" >"${STAGING_PATH}/request-v4-record.json" || fail 'cannot capture request v4 record'
assert_file "${STAGING_PATH}/request-v4-record.json" 600 0 0 \
  "${REQUEST_V4_RECORD_SHA256}" "${REQUEST_V4_RECORD_BYTES}" 'request v4 record'

capture_installed_inventory "${STAGING_PATH}/r1-installed-inventory.tsv"
capture_root_history "${STAGING_PATH}/root-history-inventory.tsv"
capture_cgroups "${STAGING_PATH}/cgroup-status.txt"

{
  printf '%s  %s\n' "${BOOTSTRAP_SHA256}" '/root/vista-r8-native-builder-bootstrap-r1/bootstrap_vista_r8_native_builder.sh'
  printf '%s  %s\n' "${BUILDER_SHA256}" "${BUILDER}"
  printf '%s  %s\n' "${BUNDLE_SHA256}" "${BUNDLE}"
  printf '%s  %s\n' "${REQUEST_SHA256}" "${REQUEST}"
  printf '%s  %s\n' "${PHASE_A_UNIT_SHA256}" "${PHASE_A_UNIT}"
  printf '%s  %s\n' "${PHASE_B_UNIT_SHA256}" "${PHASE_B_UNIT}"
} >"${STAGING_PATH}/r1-installed-pins.sha256"
printf '%s  %s\n' "${SELF_SHA256}" "${LIVE_SELF}" >"${STAGING_PATH}/self-pin.sha256"

{
  printf '%s\n' "schema=${SCHEMA}"
  printf '%s\n' 'status=sealed-failed-closed'
  printf '%s\n' 'r1_source_commit=b7ead1700e7c81f623759eed3ff28360c65ea92d'
  printf '%s\n' "boot_id=${BOOT_ID}"
  printf '%s\n' "phase_a_unit=${PHASE_A}"
  printf '%s\n' "phase_a_invocation_id=${PHASE_A_INVOCATION}"
  printf '%s\n' "phase_a_failure=${FAILURE_TEXT}"
  printf '%s\n' 'phase_a_result=exit-code'
  printf '%s\n' 'phase_a_published=false'
  printf '%s\n' 'phase_b_started=false'
  printf '%s\n' 'phase_b_published=false'
  printf '%s\n' 'request_schema=vista.r8-native-builder-request/v2'
  printf '%s\n' 'trace_contract_schema=vista.r8-native-builder-trace-contract/v4'
  printf '%s\n' 'trace_host_file_index=21'
  printf '%s\n' 'production_native_output=false'
  printf '%s\n' 'r2_activation_authorized=false'
  printf '%s\n' "sealer_sha256=${SELF_SHA256}"
  printf '%s\n' "sealer_size=${SELF_BYTES}"
} >"${STAGING_PATH}/manifest.txt"

# Close gate: the source evidence and manager snapshot must still be exact.
assert_r1_filesystem
assert_required_history
verify_held_r1_lock "${STATE_ROOT}/phase-a-slot/.build.lock" \
  "${R1_PHASE_A_LOCK_FD}" "${R1_PHASE_A_LOCK_ID}" 'R1 Phase A build lock'
verify_held_r1_lock "${STATE_ROOT}/phase-b-slot/.build.lock" \
  "${R1_PHASE_B_LOCK_FD}" "${R1_PHASE_B_LOCK_ID}" 'R1 Phase B build lock'
[[ "$(/usr/bin/tr -d '\n' </proc/sys/kernel/random/boot_id)" == "${BOOT_ID}" ]] || \
  fail 'boot changed during failure sealing'
capture_manager "${PHASE_A}" "${STAGING_PATH}/.phase-a.close"
capture_manager "${PHASE_B}" "${STAGING_PATH}/.phase-b.close"
/usr/bin/cmp -s -- "${STAGING_PATH}/phase-a.systemctl-show.txt" "${STAGING_PATH}/.phase-a.close" || \
  fail 'R1 Phase A manager state changed during sealing'
/usr/bin/cmp -s -- "${STAGING_PATH}/phase-b.systemctl-show.txt" "${STAGING_PATH}/.phase-b.close" || \
  fail 'R1 Phase B manager state changed during sealing'
/usr/bin/rm -f -- "${STAGING_PATH}/.phase-a.close" "${STAGING_PATH}/.phase-b.close"
verify_live_self
[[ "$(/usr/bin/stat -Lc '%d:%i:%F:%a:%u:%g' -- "${EVIDENCE_PARENT}")" == \
  "${EVIDENCE_IDENTITY}" ]] || fail 'evidence parent changed'

readonly -a EVIDENCE_FILES=(
  'boot-id.txt' 'cgroup-status.txt' 'manifest.txt' 'phase-a.journal.txt'
  'phase-a.systemctl-show.txt' 'phase-a.unit' 'phase-b.journal.txt'
  'phase-b.systemctl-show.txt' 'phase-b.unit' 'r1-installed-inventory.tsv'
  'r1-installed-pins.sha256' 'request-v4-record.json' 'root-history-inventory.tsv'
  'self-pin.sha256'
)
EXPECTED_EVIDENCE_INVENTORY="$(
  printf '%s\n' "${EVIDENCE_FILES[@]}" 'receipt.sha256' | /usr/bin/sort
)"
readonly EXPECTED_EVIDENCE_INVENTORY
for name in "${EVIDENCE_FILES[@]}"; do
  [[ -f "${STAGING_PATH}/${name}" && ! -L "${STAGING_PATH}/${name}" ]] || \
    fail "evidence file differs: ${name}"
  /usr/bin/chown root:root -- "${STAGING_PATH}/${name}"
  /usr/bin/chmod 0444 -- "${STAGING_PATH}/${name}"
  /usr/bin/sync -f "${STAGING_PATH}/${name}"
done
(
  cd "${STAGING_PATH}"
  for name in "${EVIDENCE_FILES[@]}"; do /usr/bin/sha256sum -- "${name}"; done
) >"${STAGING_PATH}/receipt.sha256"
/usr/bin/chown root:root -- "${STAGING_PATH}/receipt.sha256"
/usr/bin/chmod 0444 -- "${STAGING_PATH}/receipt.sha256"
/usr/bin/sync -f "${STAGING_PATH}/receipt.sha256"
/usr/bin/chmod 0555 -- "${STAGING_PATH}"
assert_directory "${STAGING_PATH}" 555 0 0 'closed evidence staging'
assert_inventory "${STAGING_PATH}" "${EXPECTED_EVIDENCE_INVENTORY}"
for name in "${EVIDENCE_FILES[@]}" 'receipt.sha256'; do
  assert_closed_file_metadata "${STAGING_PATH}/${name}" 444 0 0 \
    "closed evidence file: ${name}"
done
(
  cd "${STAGING_PATH}" &&
  /usr/bin/sha256sum -c -- receipt.sha256 >/dev/null
) || fail 'closed evidence receipt does not verify'
/usr/bin/sync -f "${STAGING_PATH}"
/usr/bin/sync -f "${EVIDENCE_PARENT}"

[[ ! -e "${FINAL_PATH}" && ! -L "${FINAL_PATH}" ]] || fail 'final evidence collided before publish'
trap '' HUP INT TERM
/usr/bin/mv -T --no-clobber -- "/proc/self/fd/${EVIDENCE_FD}/${STAGING_NAME}" \
  "/proc/self/fd/${EVIDENCE_FD}/${FINAL_NAME}" || fail 'no-replace evidence publish failed'
STAGING_OWNED='false'
PUBLISHED='true'
[[ ! -e "${STAGING_PATH}" && ! -L "${STAGING_PATH}" && \
  -d "${FINAL_PATH}" && ! -L "${FINAL_PATH}" ]] || fail 'no-replace evidence publish did not close'
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
assert_directory "${FINAL_PATH}" 555 0 0 'published R1 failure evidence'
assert_inventory "${FINAL_PATH}" "${EXPECTED_EVIDENCE_INVENTORY}"
for name in "${EVIDENCE_FILES[@]}" 'receipt.sha256'; do
  assert_closed_file_metadata "${FINAL_PATH}/${name}" 444 0 0 \
    "published evidence file: ${name}"
done
(
  cd "${FINAL_PATH}" &&
  /usr/bin/sha256sum -c -- receipt.sha256 >/dev/null
) || fail 'published evidence receipt does not verify'
/usr/bin/sync -f "${FINAL_PATH}"
/usr/bin/sync -f "${EVIDENCE_PARENT}"

FINAL_MANIFEST_SHA256="$(sha256_of "${FINAL_PATH}/manifest.txt")" || \
  fail 'cannot hash published manifest'
FINAL_RECEIPT_SHA256="$(sha256_of "${FINAL_PATH}/receipt.sha256")" || \
  fail 'cannot hash published receipt'
readonly FINAL_MANIFEST_SHA256 FINAL_RECEIPT_SHA256
printf '%s\n' "VISTA_R8_R1_FAILURE_SEALED=${FINAL_PATH}"
printf '%s  %s\n' "${FINAL_MANIFEST_SHA256}" "${FINAL_PATH}/manifest.txt"
printf '%s  %s\n' "${FINAL_RECEIPT_SHA256}" "${FINAL_PATH}/receipt.sha256"
