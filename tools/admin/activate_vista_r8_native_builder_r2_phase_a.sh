#!/usr/bin/env bash
# One-shot activation ceremony for only VISTA R8 native-builder R2 Phase A.
# Phase B is deliberately never started.  Any post-reload or post-start failure
# is preserved with an append-only root-owned receipt and is never retried.

set -euo pipefail
umask 077
IFS=$'\n\t'
export LC_ALL=C LANG=C PATH=/usr/sbin:/usr/bin:/sbin:/bin
unset BASH_ENV ENV CDPATH GLOBIGNORE PYTHONHOME PYTHONPATH

readonly LIVE_SELF='/root/activate_vista_r8_native_builder_r2_phase_a-83f180e0-20260901b.sh'
readonly COMMIT='83f180e03935bcc7994962ec95f2d8c8027f405d'
readonly PHASE_A='vista-r8-native-builder-r2-phase-a.service'
readonly PHASE_B='vista-r8-native-builder-r2-phase-b.service'
readonly TRUSTED_ROOT='/root/vista-r8-native-builder-bootstrap-r2'
readonly TRUSTED_SYSTEMD="${TRUSTED_ROOT}/systemd"
readonly GLOBAL_LOCK="${TRUSTED_ROOT}/.bootstrap.lock"
readonly INPUT_CANDIDATE='/root/vista-r8-native-builder-bootstrap-input-r2'
readonly LIBEXEC_ROOT='/usr/local/libexec/vista-r8-native-builder-r2'
readonly INPUT_ROOT='/etc/vista-r8-native-builder-r2'
readonly STATE_ROOT='/var/lib/vista-r8-native-builder-r2'
readonly PHASE_A_UNIT="/etc/systemd/system/${PHASE_A}"
readonly PHASE_B_UNIT="/etc/systemd/system/${PHASE_B}"
readonly PHASE_A_FINAL="${STATE_ROOT}/phase-a-slot/published"
readonly PHASE_B_FINAL="${STATE_ROOT}/phase-b-slot/published"
readonly RECEIPT_FINAL='/root/vista-r8-native-builder-r2-phase-a-receipt-83f180e0-20260901b'
readonly RECEIPT_STAGING='/root/.vista-r8-native-builder-r2-phase-a-receipt-83f180e0-20260901b.staging'
readonly OUTER_LOCK='/run/lock/vista-r8-native-builder-r2-activate-83f180e0-20260901b.lock.d'

readonly FAILED_ACTIVATOR_ORIGINAL='/root/activate_vista_r8_native_builder_r2_phase_a.sh'
readonly FAILED_ACTIVATOR='/root/activate_vista_r8_native_builder_r2_phase_a.failed-pre-mutation-manager-loaded-83f180e0-20260901a.sh'
readonly FAILED_ACTIVATOR_SHA256='40dababde27afadcf2c701e5671aeb21a9d0be39a279d83dcda203dff4504fb9'
readonly FAILED_ACTIVATOR_BYTES='46128'
readonly FAILED_RECEIPT_FINAL='/root/vista-r8-native-builder-r2-phase-a-receipt-83f180e0-20260831a'
readonly FAILED_RECEIPT_STAGING='/root/.vista-r8-native-builder-r2-phase-a-receipt-83f180e0-20260831a.staging'
readonly FAILED_OUTER_LOCK='/run/lock/vista-r8-native-builder-r2-activate-83f180e0-20260831a.lock.d'

readonly R1_SEAL='/root/vista-r8-native-builder-r1-failure-seal-b7ead170-83f180e0-20260901c'
readonly R1_SEALER='/root/seal-vista-r8-native-builder-r1-failure-83f180e0-20260901c.sh'
readonly R1_SEALER_SHA256='c418918f6907d595895fb8139bae3576741799bc7e789b2b8751ed5a1d1b163d'
readonly R1_SEALER_BYTES='35026'
readonly R1_PHASE_A='vista-r8-native-builder-phase-a.service'
readonly R1_PHASE_B='vista-r8-native-builder-phase-b.service'
readonly R1_STATE_ROOT='/var/lib/vista-r8-native-builder-r1'
readonly R1_BUILDER_UID='997'
readonly R1_BUILDER_GID='997'
readonly R1_PHASE_A_LOCK_FD='11'
readonly R1_PHASE_B_LOCK_FD='12'
readonly R1_STATE_INVENTORY=$'phase-a-slot\nphase-a-slot/.build.lock\nphase-b-slot\nphase-b-slot/.build.lock'
readonly R1_SEAL_INVENTORY=$'boot-id.txt\ncgroup-status.txt\nmanifest.txt\nphase-a.journal.txt\nphase-a.systemctl-show.txt\nphase-a.unit\nphase-b.journal.txt\nphase-b.systemctl-show.txt\nphase-b.unit\nr1-installed-inventory.tsv\nr1-installed-pins.sha256\nreceipt.sha256\nrequest-v4-record.json\nroot-history-inventory.tsv\nself-pin.sha256'
readonly R1_RECEIPT_NAMES=$'boot-id.txt\ncgroup-status.txt\nmanifest.txt\nphase-a.journal.txt\nphase-a.systemctl-show.txt\nphase-a.unit\nphase-b.journal.txt\nphase-b.systemctl-show.txt\nphase-b.unit\nr1-installed-inventory.tsv\nr1-installed-pins.sha256\nrequest-v4-record.json\nroot-history-inventory.tsv\nself-pin.sha256'

readonly BOOTSTRAP_SHA256='da51dfe7bef6495f3cc659d78de0795e3fd99404a17daaa5bcdea32795255084'
readonly BOOTSTRAP_BYTES='41247'
readonly BUILDER_SHA256='abc072477e5a10265405d1cc4d44c0f629142bb652beafc861080751fa7d59e7'
readonly BUILDER_BYTES='212992'
readonly PHASE_A_SHA256='1a07936c9d3e5a157c6e3b13353c54cb2e8dbb3af26f06673b56a0f6b2a3d8f3'
readonly PHASE_A_BYTES='2162'
readonly PHASE_B_SHA256='403bf91313539edf78b840f3a3342d9270c2b503b03f6a6ce32d0ac9127ccd75'
readonly PHASE_B_BYTES='2450'
readonly BUNDLE_SHA256='54ba5e0ae512fa9661ccec04ee245de6510d343ae21445f8f169b239fd557533'
readonly BUNDLE_BYTES='3301129'
readonly REQUEST_SHA256='fb8e99428b4e7cb043c96591f73d413500834667f263eeec3f3c70af66f318e0'
readonly REQUEST_BYTES='2483438'
readonly EXPECTED_TRUSTED=$'.bootstrap.lock\nbootstrap_vista_r8_native_builder_r2.sh\nsystemd\nsystemd/vista-r8-native-builder-r2-phase-a.service\nsystemd/vista-r8-native-builder-r2-phase-b.service\nvista_r8_native_builder.py'
readonly EXPECTED_INPUT=$'phase-a-request.json\nsource.bundle'
readonly EXPECTED_STATE_PRE=$'phase-a-slot\nphase-a-slot/.build.lock\nphase-b-slot\nphase-b-slot/.build.lock'
readonly EXPECTED_PHASE_A=$'artifacts\nartifacts/bootstrap-r8-ue57-initial-authorities\nartifacts/launch-vista-authority-parent-seal\nartifacts/transfer-r8-ue57-stage-installer\nmanifest.json\nmanifests\nmanifests/initial-bootstrap-launcher.json\nmanifests/parent-seal-launcher.json\nmanifests/stage-transfer-launcher.json\nparent-seal-candidate\nparent-seal-candidate/launch-vista-authority-parent-seal\nparent-seal-candidate/vista_authority_parent_seal.py'
readonly RECEIPT_FILES=$'activation-self-pin.sha256\nfailed-activation-self-pin.sha256\nmanifest.txt\nphase-a-manifest.sha256\nphase-a-publication-inventory.txt\nphase-a.journal.txt\npost-start-validation.txt\nr1-after-reload-state.txt\nr1-after-reload.systemctl-show.txt\nr1-after-start-state.txt\nr1-after-start.systemctl-show.txt\nr1-before-reload-state.txt\nr1-seal-tree.sha256\nr2-after-reload.systemctl-show.txt\nr2-after-start.systemctl-show.txt\nr2-before-reload.systemctl-show.txt\nstart-exit.txt\nsystemd-analyze.txt'

fail() { printf '%s\n' "VISTA R8 R2 Phase A activation: $*" >&2; exit 126; }
sha256_of() { /usr/bin/sha256sum -- "$1" | /usr/bin/cut -d' ' -f1; }
assert_absent() { [[ ! -e "$1" && ! -L "$1" ]] || fail "fresh path exists: $1"; }

MUTATION_BEGUN='false'
RECEIPT_PUBLISHED='false'
OUTER_LOCK_OWNED='false'
RECEIPT_STAGING_OWNED='false'
cleanup() {
  local status="$?"
  if [[ "${MUTATION_BEGUN}" == 'false' && "${RECEIPT_PUBLISHED}" == 'false' ]]; then
    [[ "${RECEIPT_STAGING_OWNED}" != 'true' || \
      ( ! -e "${RECEIPT_STAGING}" && ! -L "${RECEIPT_STAGING}" ) ]] || \
      /usr/bin/rm -rf --one-file-system -- "${RECEIPT_STAGING}"
    if [[ "${OUTER_LOCK_OWNED}" == 'true' && \
      -f "${OUTER_LOCK}/r1-seal-tree.sha256" && ! -L "${OUTER_LOCK}/r1-seal-tree.sha256" ]]; then
      /usr/bin/rm -f -- "${OUTER_LOCK}/r1-seal-tree.sha256" || status=125
    fi
    [[ "${OUTER_LOCK_OWNED}" != 'true' || ! -d "${OUTER_LOCK}" || -L "${OUTER_LOCK}" ]] || \
      /usr/bin/rmdir -- "${OUTER_LOCK}" 2>/dev/null || status=125
  fi
  exit "${status}"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

assert_directory() {
  local path="$1" mode="$2" uid="$3" gid="$4"
  [[ -d "${path}" && ! -L "${path}" ]] || fail "directory differs: ${path}"
  [[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g' -- "${path}")" == "directory|${mode}|${uid}|${gid}" ]] || fail "directory metadata differs: ${path}"
}
assert_closed_file_metadata() {
  local path="$1" mode="$2" uid="$3" gid="$4"
  [[ -f "${path}" && ! -L "${path}" ]] || fail "file differs: ${path}"
  [[ "$(/usr/bin/stat -Lc '%a|%u|%g|%h' -- "${path}")" == \
    "${mode}|${uid}|${gid}|1" ]] || fail "file metadata differs: ${path}"
}
assert_file() {
  local path="$1" mode="$2" uid="$3" gid="$4" sha="$5" size="$6"
  assert_closed_file_metadata "${path}" "${mode}" "${uid}" "${gid}"
  [[ "$(/usr/bin/stat -Lc '%s' -- "${path}")" == "${size}" ]] || fail "file size differs: ${path}"
  [[ "$(sha256_of "${path}")" == "${sha}" ]] || fail "file pin differs: ${path}"
}
verify_failed_activation_history() {
  assert_file "${FAILED_ACTIVATOR}" 500 0 0 \
    "${FAILED_ACTIVATOR_SHA256}" "${FAILED_ACTIVATOR_BYTES}"
  assert_absent "${FAILED_ACTIVATOR_ORIGINAL}"
  assert_absent "${FAILED_RECEIPT_FINAL}"
  assert_absent "${FAILED_RECEIPT_STAGING}"
  assert_absent "${FAILED_OUTER_LOCK}"
}
verify_live_self() {
  local path_id held_id metadata
  path_id="$(/usr/bin/stat -Lc '%d:%i' -- "${LIVE_SELF}")" || fail 'cannot stat live activation'
  held_id="$(/usr/bin/stat -Lc '%d:%i' -- /proc/$$/fd/8)" || fail 'cannot stat held activation'
  metadata="$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h|%s' -- /proc/$$/fd/8)" || fail 'cannot inspect held activation'
  [[ "${path_id}" == "${held_id}" && "${path_id}" == "${LIVE_SELF_ID}" ]] || fail 'live activation identity changed'
  [[ "${metadata}" == "regular file|500|0|0|1|${LIVE_SELF_BYTES}" ]] || fail 'held activation metadata differs'
  [[ "$(sha256_of /proc/$$/fd/8)" == "${LIVE_SELF_SHA256}" ]] || fail 'live activation bytes changed'
}
assert_inventory() {
  local root="$1" expected="$2" observed
  observed="$(/usr/bin/find -P "${root}" -xdev -mindepth 1 -printf '%P\n' | /usr/bin/sort)" || fail "cannot inventory ${root}"
  [[ "${observed}" == "${expected}" ]] || fail "inventory differs: ${root}"
}
manager_document() {
  /usr/bin/systemctl show --no-pager -p MainPID -p ControlPID -p Result -p NRestarts \
    -p ExecMainStartTimestampMonotonic -p ExecMainExitTimestampMonotonic \
    -p ExecMainCode -p ExecMainStatus -p ProcSubset -p Id -p Names -p LoadState \
    -p ActiveState -p SubState -p FragmentPath -p DropInPaths -p UnitFileState \
    -p WantedBy -p RequiredBy -p Job -p NeedDaemonReload -p ConditionResult \
    -p InvocationID -- "$1"
}
property() {
  local document="$1" key="$2" count line
  if ! count="$(/usr/bin/awk -F= -v key="${key}" '$1 == key {n++} END {print n+0}' <<<"${document}")"; then
    printf '%s' "__VISTA_INVALID_PROPERTY_${key}__"
    return 126
  fi
  if [[ "${count}" != 1 ]]; then
    printf '%s' "__VISTA_INVALID_PROPERTY_${key}__"
    return 126
  fi
  if ! line="$(/usr/bin/awk -F= -v key="${key}" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' <<<"${document}")"; then
    printf '%s' "__VISTA_INVALID_PROPERTY_${key}__"
    return 126
  fi
  printf '%s' "${line}"
}
file_property() {
  local file="$1" key="$2" count
  if ! count="$(/usr/bin/awk -F= -v key="${key}" '$1 == key {n++} END {print n+0}' "${file}")"; then
    printf '%s' "__VISTA_INVALID_FILE_PROPERTY_${key}__"
    return 126
  fi
  if [[ "${count}" != 1 ]]; then
    printf '%s' "__VISTA_INVALID_FILE_PROPERTY_${key}__"
    return 126
  fi
  if ! /usr/bin/awk -F= -v key="${key}" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "${file}"; then
    printf '%s' "__VISTA_INVALID_FILE_PROPERTY_${key}__"
    return 126
  fi
}
capture_pair() {
  local first second
  first="$(manager_document "$1")" || return 1
  second="$(manager_document "$2")" || return 1
  printf '%s\n\n%s\n' "${first}" "${second}" >"$3"
}

assert_r1_state_filesystem() {
  assert_directory "${R1_STATE_ROOT}" 555 0 0
  assert_directory "${R1_STATE_ROOT}/phase-a-slot" 711 997 997
  assert_directory "${R1_STATE_ROOT}/phase-b-slot" 711 997 997
  assert_inventory "${R1_STATE_ROOT}" "${R1_STATE_INVENTORY}"
  [[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h|%s' -- "${R1_STATE_ROOT}/phase-a-slot/.build.lock")" == \
    'regular empty file|600|997|997|1|0' ]] || fail 'R1 Phase A build lock differs'
  [[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h|%s' -- "${R1_STATE_ROOT}/phase-b-slot/.build.lock")" == \
    'regular empty file|600|997|997|1|0' ]] || fail 'R1 Phase B build lock differs'
}

verify_held_r1_lock() {
  local path="$1" fd="$2" expected_id="$3" label="$4" path_id held_id metadata
  path_id="$(/usr/bin/stat -Lc '%d:%i' -- "${path}")" || fail "cannot stat ${label} path"
  held_id="$(/usr/bin/stat -Lc '%d:%i' -- "/proc/$$/fd/${fd}")" || \
    fail "cannot stat held ${label}"
  metadata="$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h|%s' -- "/proc/$$/fd/${fd}")" || \
    fail "cannot inspect held ${label}"
  [[ "${path_id}" == "${expected_id}" && "${held_id}" == "${expected_id}" ]] || \
    fail "${label} inode binding differs"
  [[ "${metadata}" == \
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
    "${R1_STATE_ROOT}/phase-a-slot/.build.lock" \
    "${R1_STATE_ROOT}/phase-b-slot/.build.lock" \
    "${R1_BUILDER_UID}" "${R1_BUILDER_GID}" \
    "${R1_PHASE_A_LOCK_FD}" "${R1_PHASE_B_LOCK_FD}"
}

verify_r1_build_lock_bindings() {
  verify_held_r1_lock "${R1_STATE_ROOT}/phase-a-slot/.build.lock" \
    "${R1_PHASE_A_LOCK_FD}" "${R1_PHASE_A_LOCK_ID}" 'R1 Phase A build lock'
  verify_held_r1_lock "${R1_STATE_ROOT}/phase-b-slot/.build.lock" \
    "${R1_PHASE_B_LOCK_FD}" "${R1_PHASE_B_LOCK_ID}" 'R1 Phase B build lock'
}

r1_state_seal_projection() {
  local path encoded count line
  for path in "${R1_STATE_ROOT}" "${R1_STATE_ROOT}/phase-a-slot" \
    "${R1_STATE_ROOT}/phase-a-slot/.build.lock" "${R1_STATE_ROOT}/phase-b-slot" \
    "${R1_STATE_ROOT}/phase-b-slot/.build.lock"; do
    encoded="$(printf '%s' "${path}" | /usr/bin/base64 -w0)" || return 1
    count="$(/usr/bin/awk -F '\t' -v key="${encoded}" '$1 == key {n++} END {print n+0}' \
      "${R1_SEAL}/r1-installed-inventory.tsv")" || return 1
    [[ "${count}" == 1 ]] || return 1
    line="$(/usr/bin/awk -F '\t' -v key="${encoded}" '$1 == key {print; exit}' \
      "${R1_SEAL}/r1-installed-inventory.tsv")" || return 1
    printf '%s\n' "${line}"
  done
}

r1_state_current_projection() {
  local path encoded metadata kind sha
  assert_r1_state_filesystem
  for path in "${R1_STATE_ROOT}" "${R1_STATE_ROOT}/phase-a-slot" \
    "${R1_STATE_ROOT}/phase-a-slot/.build.lock" "${R1_STATE_ROOT}/phase-b-slot" \
    "${R1_STATE_ROOT}/phase-b-slot/.build.lock"; do
    encoded="$(printf '%s' "${path}" | /usr/bin/base64 -w0)" || return 1
    metadata="$(/usr/bin/stat -c '%F|%a|%u|%g|%h|%s|%d|%i|%y|%z' -- "${path}")" || return 1
    if [[ -d "${path}" && ! -L "${path}" ]]; then
      kind='directory'; sha='-'
    elif [[ -f "${path}" && ! -L "${path}" ]]; then
      kind='regular'; sha="$(sha256_of "${path}")" || return 1
    else
      return 1
    fi
    printf '%s\t%s\t%s\t%s\t-\n' "${encoded}" "${kind}" "${metadata}" "${sha}"
  done
}

assert_r1_state_matches_seal() {
  local sealed current
  sealed="$(r1_state_seal_projection)" || fail 'cannot project sealed R1 state inventory'
  current="$(r1_state_current_projection)" || fail 'cannot project current R1 state inventory'
  [[ "${current}" == "${sealed}" ]] || fail 'live R1 state differs from sealed failure evidence'
}

r1_state_document() {
  local relative path metadata
  assert_r1_state_filesystem
  for relative in . phase-a-slot phase-a-slot/.build.lock phase-b-slot phase-b-slot/.build.lock; do
    if [[ "${relative}" == . ]]; then path="${R1_STATE_ROOT}"; else path="${R1_STATE_ROOT}/${relative}"; fi
    metadata="$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h|%s|%d|%i|%y|%z' -- "${path}")" || \
      return 1
    printf '%s|%s\n' "${relative}" "${metadata}"
  done
}

capture_r1_state() {
  local document
  document="$(r1_state_document)" || return 1
  printf '%s\n' "${document}" >"$1"
}

assert_r1_state_matches() {
  local baseline="$1" expected observed
  expected="$(/usr/bin/cat -- "${baseline}")" || fail 'cannot read R1 state baseline'
  observed="$(r1_state_document)" || fail 'cannot inspect live R1 state'
  [[ "${observed}" == "${expected}" ]] || fail 'live R1 state changed from activation baseline'
}

assert_r1_vector() {
  local a b
  verify_r1_build_lock_bindings
  assert_r1_state_filesystem
  assert_r1_state_matches_seal
  a="$(manager_document "${R1_PHASE_A}")"; b="$(manager_document "${R1_PHASE_B}")"
  [[ "$(property "${a}" Id)|$(property "${a}" Names)|$(property "${a}" LoadState)|$(property "${a}" ActiveState)|$(property "${a}" SubState)" == \
    "${R1_PHASE_A}|${R1_PHASE_A}|loaded|failed|failed" ]] || fail 'R1 Phase A state vector differs'
  [[ "$(property "${a}" FragmentPath)|$(property "${a}" DropInPaths)|$(property "${a}" UnitFileState)|$(property "${a}" WantedBy)|$(property "${a}" RequiredBy)|$(property "${a}" Job)" == \
    "/etc/systemd/system/${R1_PHASE_A}||static|||" ]] || fail 'R1 Phase A provenance differs'
  [[ "$(property "${a}" ProcSubset)|$(property "${a}" NeedDaemonReload)|$(property "${a}" NRestarts)|$(property "${a}" MainPID)|$(property "${a}" ControlPID)" == \
    'all|no|0|0|0' ]] || fail 'R1 Phase A quiescence differs'
  [[ "$(property "${a}" Result)|$(property "${a}" ConditionResult)|$(property "${a}" ExecMainCode)|$(property "${a}" ExecMainStatus)" == \
    'exit-code|yes|1|2' ]] || fail 'R1 Phase A result differs'
  [[ "$(property "${a}" ExecMainStartTimestampMonotonic)|$(property "${a}" ExecMainExitTimestampMonotonic)|$(property "${a}" InvocationID)" == \
    '675339972529|675341234136|81d481f1eb764c60a737835b867fcb63' ]] || fail 'R1 Phase A execution differs'
  [[ "$(property "${b}" Id)|$(property "${b}" Names)|$(property "${b}" LoadState)|$(property "${b}" ActiveState)|$(property "${b}" SubState)" == \
    "${R1_PHASE_B}|${R1_PHASE_B}|loaded|inactive|dead" ]] || fail 'R1 Phase B state vector differs'
  [[ "$(property "${b}" FragmentPath)|$(property "${b}" DropInPaths)|$(property "${b}" UnitFileState)|$(property "${b}" WantedBy)|$(property "${b}" RequiredBy)|$(property "${b}" Job)" == \
    "/etc/systemd/system/${R1_PHASE_B}||static|||" ]] || fail 'R1 Phase B provenance differs'
  [[ "$(property "${b}" ProcSubset)|$(property "${b}" NeedDaemonReload)|$(property "${b}" NRestarts)|$(property "${b}" MainPID)|$(property "${b}" ControlPID)" == \
    'all|no|0|0|0' ]] || fail 'R1 Phase B quiescence differs'
  [[ "$(property "${b}" Result)|$(property "${b}" ConditionResult)|$(property "${b}" ExecMainCode)|$(property "${b}" ExecMainStatus)|$(property "${b}" ExecMainStartTimestampMonotonic)|$(property "${b}" ExecMainExitTimestampMonotonic)|$(property "${b}" InvocationID)" == \
    'success|no|0|0|0|0|' ]] || fail 'R1 Phase B never-started vector differs'
}

assert_r2_never_started() {
  local unit="$1" doc
  doc="$(manager_document "${unit}")"
  [[ "$(property "${doc}" Id)|$(property "${doc}" Names)|$(property "${doc}" LoadState)|$(property "${doc}" ActiveState)|$(property "${doc}" SubState)|$(property "${doc}" FragmentPath)|$(property "${doc}" DropInPaths)|$(property "${doc}" UnitFileState)|$(property "${doc}" WantedBy)|$(property "${doc}" RequiredBy)|$(property "${doc}" Job)" == "${unit}|${unit}|loaded|inactive|dead|/etc/systemd/system/${unit}||static|||" ]] || fail "R2 manager provenance differs: ${unit}"
  [[ "$(property "${doc}" ProcSubset)|$(property "${doc}" NeedDaemonReload)|$(property "${doc}" NRestarts)|$(property "${doc}" MainPID)|$(property "${doc}" ControlPID)|$(property "${doc}" ExecMainStartTimestampMonotonic)|$(property "${doc}" ExecMainExitTimestampMonotonic)|$(property "${doc}" ExecMainCode)|$(property "${doc}" ExecMainStatus)|$(property "${doc}" InvocationID)" == 'all|no|0|0|0|0|0|0|0|' ]] || fail "R2 unit was started: ${unit}"
  [[ "$(property "${doc}" Result)|$(property "${doc}" ConditionResult)" == 'success|no' ]] || fail "R2 never-started result differs: ${unit}"
  assert_absent "/sys/fs/cgroup/system.slice/${unit}"
}

assert_r2_pre_reload_pristine() {
  local unit="$1" doc load_state unit_file_state
  doc="$(manager_document "${unit}")"
  load_state="$(property "${doc}" LoadState)" || fail "R2 pre-reload LoadState is unreadable: ${unit}"
  unit_file_state="$(property "${doc}" UnitFileState)" || fail "R2 pre-reload UnitFileState is unreadable: ${unit}"
  case "${load_state}" in
    not-found)
      [[ "$(property "${doc}" Id)|$(property "${doc}" Names)|$(property "${doc}" ActiveState)|$(property "${doc}" SubState)|$(property "${doc}" FragmentPath)|$(property "${doc}" DropInPaths)|$(property "${doc}" WantedBy)|$(property "${doc}" RequiredBy)|$(property "${doc}" Job)" == "${unit}|${unit}|inactive|dead|||||" ]] || fail "R2 pre-reload not-found provenance differs: ${unit}"
      case "${unit_file_state}" in '' | static) ;; *) fail "R2 pre-reload not-found UnitFileState differs: ${unit}" ;; esac
      ;;
    loaded)
      [[ "$(property "${doc}" Id)|$(property "${doc}" Names)|$(property "${doc}" ActiveState)|$(property "${doc}" SubState)|$(property "${doc}" FragmentPath)|$(property "${doc}" DropInPaths)|$(property "${doc}" UnitFileState)|$(property "${doc}" WantedBy)|$(property "${doc}" RequiredBy)|$(property "${doc}" Job)" == "${unit}|${unit}|inactive|dead|/etc/systemd/system/${unit}||static|||" ]] || fail "R2 pre-reload loaded provenance differs: ${unit}"
      ;;
    *) fail "R2 pre-reload LoadState differs: ${unit}" ;;
  esac
  [[ "$(property "${doc}" ProcSubset)|$(property "${doc}" NeedDaemonReload)|$(property "${doc}" NRestarts)|$(property "${doc}" MainPID)|$(property "${doc}" ControlPID)|$(property "${doc}" ExecMainStartTimestampMonotonic)|$(property "${doc}" ExecMainExitTimestampMonotonic)|$(property "${doc}" ExecMainCode)|$(property "${doc}" ExecMainStatus)|$(property "${doc}" InvocationID)" == 'all|no|0|0|0|0|0|0|0|' ]] || fail "R2 pre-reload unit was started: ${unit}"
  [[ "$(property "${doc}" Result)|$(property "${doc}" ConditionResult)" == 'success|no' ]] || fail "R2 pre-reload result differs: ${unit}"
  assert_absent "/sys/fs/cgroup/system.slice/${unit}"
}

verify_r1_seal() {
  local name receipt_names manifest assertion manifest_keys sealed_boot current_boot
  assert_directory "${R1_SEAL}" 555 0 0
  assert_inventory "${R1_SEAL}" "${R1_SEAL_INVENTORY}"
  for name in ${R1_SEAL_INVENTORY}; do
    assert_closed_file_metadata "${R1_SEAL}/${name}" 444 0 0
  done
  receipt_names="$(/usr/bin/awk 'NF == 2 && $1 ~ /^[0-9a-f]{64}$/ && $2 !~ /^\// {print $2}' "${R1_SEAL}/receipt.sha256" | /usr/bin/sort)"
  [[ "${receipt_names}" == "${R1_RECEIPT_NAMES}" ]] || fail 'R1 seal receipt name inventory differs'
  (cd "${R1_SEAL}" && /usr/bin/sha256sum -c -- receipt.sha256 >/dev/null) || fail 'R1 seal receipt does not verify'
  [[ "$(/usr/bin/head -n1 "${R1_SEAL}/manifest.txt")" == 'schema=vista.r8-native-builder-r1-failure-seal/v1' ]] || fail 'R1 seal schema differs'
  manifest="$(/usr/bin/cat "${R1_SEAL}/manifest.txt")"
  manifest_keys="$(/usr/bin/cut -d= -f1 "${R1_SEAL}/manifest.txt" | /usr/bin/sort)"
  [[ "${manifest_keys}" == $'boot_id\nphase_a_failure\nphase_a_invocation_id\nphase_a_published\nphase_a_result\nphase_a_unit\nphase_b_published\nphase_b_started\nproduction_native_output\nr1_source_commit\nr2_activation_authorized\nrequest_schema\nschema\nsealer_sha256\nsealer_size\nstatus\ntrace_contract_schema\ntrace_host_file_index' ]] || fail 'R1 seal manifest key inventory differs'
  for assertion in \
    'status=sealed-failed-closed' \
    'r1_source_commit=b7ead1700e7c81f623759eed3ff28360c65ea92d' \
    'phase_a_invocation_id=81d481f1eb764c60a737835b867fcb63' \
    'phase_a_failure=TRACE_PATH_DRIFT: trace host file[21]' \
    'phase_a_result=exit-code' 'phase_a_published=false' \
    'phase_b_started=false' 'phase_b_published=false' \
    'request_schema=vista.r8-native-builder-request/v2' \
    'trace_contract_schema=vista.r8-native-builder-trace-contract/v4' \
    'trace_host_file_index=21' 'production_native_output=false' \
    'r2_activation_authorized=false' "sealer_sha256=${R1_SEALER_SHA256}" \
    "sealer_size=${R1_SEALER_BYTES}"; do
    [[ "$(/usr/bin/grep -Fxc -- "${assertion}" <<<"${manifest}")" == 1 ]] || fail "R1 seal manifest assertion differs: ${assertion}"
  done
  assert_file "${R1_SEALER}" 500 0 0 "${R1_SEALER_SHA256}" "${R1_SEALER_BYTES}"
  [[ "$(/usr/bin/cat "${R1_SEAL}/self-pin.sha256")" == "${R1_SEALER_SHA256}  ${R1_SEALER}" ]] || fail 'R1 sealer self pin differs'
  /usr/bin/grep -Fq 'TRACE_PATH_DRIFT: trace host file[21]' "${R1_SEAL}/phase-a.journal.txt" || fail 'R1 journal failure marker differs'
  [[ "$(file_property "${R1_SEAL}/phase-a.systemctl-show.txt" Result)|$(file_property "${R1_SEAL}/phase-a.systemctl-show.txt" ExecMainStatus)|$(file_property "${R1_SEAL}/phase-a.systemctl-show.txt" InvocationID)|$(file_property "${R1_SEAL}/phase-a.systemctl-show.txt" ExecMainStartTimestampMonotonic)|$(file_property "${R1_SEAL}/phase-a.systemctl-show.txt" ExecMainExitTimestampMonotonic)" == 'exit-code|2|81d481f1eb764c60a737835b867fcb63|675339972529|675341234136' ]] || fail 'sealed R1 Phase A manager evidence differs'
  [[ "$(file_property "${R1_SEAL}/phase-b.systemctl-show.txt" Result)|$(file_property "${R1_SEAL}/phase-b.systemctl-show.txt" ExecMainStartTimestampMonotonic)|$(file_property "${R1_SEAL}/phase-b.systemctl-show.txt" InvocationID)" == 'success|0|' ]] || fail 'sealed R1 Phase B manager evidence differs'
  [[ "$(sha256_of "${R1_SEAL}/phase-a.unit")" == 'f3acaf39ad92fe2bc70680c9f7e0d8ab1e1f68f68553ebd4a74137c0cf939520' ]] || fail 'sealed R1 Phase A unit differs'
  [[ "$(sha256_of "${R1_SEAL}/phase-b.unit")" == '1e65b23e2ae857b88d3b488a63cfcba3d6462c265ff3b4d3b33da046b9f96035' ]] || fail 'sealed R1 Phase B unit differs'
  [[ "$(sha256_of "${R1_SEAL}/request-v4-record.json")" == 'd368db55dc50b90822dda55d2c1ad5b2a8cdabaf8b9ba7aac61e50832f4fd476' ]] || fail 'sealed R1 request record differs'
  (cd / && /usr/bin/sha256sum -c -- "${R1_SEAL}/r1-installed-pins.sha256" >/dev/null) || fail 'live R1 installed pins differ from seal'
  sealed_boot="$(/usr/bin/cat "${R1_SEAL}/boot-id.txt")"
  current_boot="$(/usr/bin/tr -d '\n' </proc/sys/kernel/random/boot_id)"
  [[ "${sealed_boot}" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ && "${sealed_boot}" == "${current_boot}" ]] || fail 'R1 seal boot identity differs'
}

r1_seal_tree_digest() {
  local name metadata sha
  for name in ${R1_SEAL_INVENTORY}; do
    metadata="$(/usr/bin/stat -Lc '%a:%u:%g:%h:%s:%d:%i' -- "${R1_SEAL}/${name}")" || return 1
    sha="$(sha256_of "${R1_SEAL}/${name}")" || return 1
    printf '%s\0%s\0%s\0' "${name}" "${metadata}" "${sha}"
  done | /usr/bin/sha256sum | /usr/bin/cut -d' ' -f1
}

verify_r2_disk() {
  assert_directory "${TRUSTED_ROOT}" 555 0 0; assert_directory "${TRUSTED_SYSTEMD}" 555 0 0
  assert_inventory "${TRUSTED_ROOT}" "${EXPECTED_TRUSTED}"
  assert_file "${TRUSTED_ROOT}/bootstrap_vista_r8_native_builder_r2.sh" 500 0 0 "${BOOTSTRAP_SHA256}" "${BOOTSTRAP_BYTES}"
  assert_file "${TRUSTED_ROOT}/vista_r8_native_builder.py" 400 0 0 "${BUILDER_SHA256}" "${BUILDER_BYTES}"
  assert_file "${TRUSTED_SYSTEMD}/${PHASE_A}" 400 0 0 "${PHASE_A_SHA256}" "${PHASE_A_BYTES}"
  assert_file "${TRUSTED_SYSTEMD}/${PHASE_B}" 400 0 0 "${PHASE_B_SHA256}" "${PHASE_B_BYTES}"
  [[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h|%s' -- "${GLOBAL_LOCK}")" == 'regular empty file|600|0|0|1|0' ]] || fail 'R2 global lock differs'
  [[ "$(/usr/bin/stat -Lc '%d:%i' -- "${GLOBAL_LOCK}")" == "${GLOBAL_LOCK_ID}" && \
    "$(/usr/bin/stat -Lc '%d:%i' -- /proc/$$/fd/10)" == "${GLOBAL_LOCK_ID}" ]] || fail 'R2 global lock binding differs'
  assert_directory "${INPUT_CANDIDATE}" 700 0 0; assert_inventory "${INPUT_CANDIDATE}" "${EXPECTED_INPUT}"
  assert_file "${INPUT_CANDIDATE}/source.bundle" 400 0 0 "${BUNDLE_SHA256}" "${BUNDLE_BYTES}"
  assert_file "${INPUT_CANDIDATE}/phase-a-request.json" 400 0 0 "${REQUEST_SHA256}" "${REQUEST_BYTES}"
  assert_directory "${LIBEXEC_ROOT}" 555 0 0; assert_inventory "${LIBEXEC_ROOT}" 'vista_r8_native_builder.py'
  assert_file "${LIBEXEC_ROOT}/vista_r8_native_builder.py" 444 0 0 "${BUILDER_SHA256}" "${BUILDER_BYTES}"
  assert_directory "${INPUT_ROOT}" 555 0 0; assert_inventory "${INPUT_ROOT}" "${EXPECTED_INPUT}"
  assert_file "${INPUT_ROOT}/source.bundle" 444 0 0 "${BUNDLE_SHA256}" "${BUNDLE_BYTES}"
  assert_file "${INPUT_ROOT}/phase-a-request.json" 444 0 0 "${REQUEST_SHA256}" "${REQUEST_BYTES}"
  assert_file "${PHASE_A_UNIT}" 644 0 0 "${PHASE_A_SHA256}" "${PHASE_A_BYTES}"
  assert_file "${PHASE_B_UNIT}" 644 0 0 "${PHASE_B_SHA256}" "${PHASE_B_BYTES}"
  assert_directory "${STATE_ROOT}" 555 0 0; assert_directory "${STATE_ROOT}/phase-a-slot" 711 997 997; assert_directory "${STATE_ROOT}/phase-b-slot" 711 997 997
  assert_inventory "${STATE_ROOT}" "${EXPECTED_STATE_PRE}"
  [[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h|%s' -- "${STATE_ROOT}/phase-a-slot/.build.lock")" == 'regular empty file|600|997|997|1|0' ]] || fail 'R2 Phase A lock differs'
  [[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h|%s' -- "${STATE_ROOT}/phase-b-slot/.build.lock")" == 'regular empty file|600|997|997|1|0' ]] || fail 'R2 Phase B lock differs'
  assert_absent "${PHASE_A_FINAL}"; assert_absent "${PHASE_B_FINAL}"
}

validate_request() {
  /usr/bin/python3.10 -I -B - "${INPUT_ROOT}/phase-a-request.json" <<'PY'
import hashlib, json, pathlib, sys
p = pathlib.Path(sys.argv[1]); d = json.loads(p.read_bytes())
if d.get("schema") != "vista.r8-native-builder-request/v2" or d.get("phase") != "phase-a": raise SystemExit(2)
if d.get("source_commit") != "83f180e03935bcc7994962ec95f2d8c8027f405d": raise SystemExit(2)
if d.get("trace_contract", {}).get("schema") != "vista.r8-native-builder-trace-contract/v5": raise SystemExit(2)
if d.get("source_bundle", {}).get("path") != "/etc/vista-r8-native-builder-r2/source.bundle": raise SystemExit(2)
if d.get("builder", {}).get("path") != "/usr/local/libexec/vista-r8-native-builder-r2/vista_r8_native_builder.py": raise SystemExit(2)
if d.get("claims", {}).get("write_root") != "/var/lib/vista-r8-native-builder-r2" or d["claims"].get("network_access") is not False: raise SystemExit(2)
projected=dict(d); observed=projected.pop("content_digest", None)
raw=json.dumps(projected, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()+b"\n"
if observed != hashlib.sha256(raw).hexdigest(): raise SystemExit(2)
pol=[]
for r in d["trace_contract"].get("host_files", []):
  for x in r.get("component_chain", []):
    if "metadata_policy" in x: pol.append((r.get("path"),x.get("path"),x["metadata_policy"]))
paths=["/proc","/proc/sys","/proc/sys/vm","/proc/sys/vm/overcommit_memory"]
if pol != [("/proc/sys/vm/overcommit_memory",x,"proc-chain-mount-metadata-volatile-v2") for x in paths]: raise SystemExit(2)
PY
}

verify_phase_a_publication() {
  local path
  assert_directory "${PHASE_A_FINAL}" 555 997 997
  assert_inventory "${PHASE_A_FINAL}" "${EXPECTED_PHASE_A}"
  for path in artifacts manifests parent-seal-candidate; do assert_directory "${PHASE_A_FINAL}/${path}" 555 997 997; done
  for path in artifacts/bootstrap-r8-ue57-initial-authorities artifacts/launch-vista-authority-parent-seal artifacts/transfer-r8-ue57-stage-installer parent-seal-candidate/launch-vista-authority-parent-seal; do
    [[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h' -- "${PHASE_A_FINAL}/${path}")" == 'regular file|555|997|997|1' ]] || fail "Phase A executable differs: ${path}"
  done
  for path in manifest.json manifests/initial-bootstrap-launcher.json manifests/parent-seal-launcher.json manifests/stage-transfer-launcher.json parent-seal-candidate/vista_authority_parent_seal.py; do
    [[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h' -- "${PHASE_A_FINAL}/${path}")" == 'regular file|444|997|997|1' ]] || fail "Phase A document differs: ${path}"
  done
  assert_absent "${PHASE_B_FINAL}"
  /usr/bin/python3.10 -I -B - "${PHASE_A_FINAL}/manifest.json" <<'PY'
import hashlib, json, pathlib, sys
p=pathlib.Path(sys.argv[1]); raw=p.read_bytes(); d=json.loads(raw)
if json.dumps(d, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()+b"\n" != raw: raise SystemExit(2)
projected=dict(d); observed=projected.pop("content_digest", None)
canonical=json.dumps(projected, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()+b"\n"
if observed != hashlib.sha256(canonical).hexdigest(): raise SystemExit(2)
if d.get("schema") != "vista.r8-native-builder-phase-a-manifest/v1" or d.get("phase") != "phase-a": raise SystemExit(2)
PY
}

seal_receipt() {
  local outcome="$1" start_exit="$2" invocation="$3" digest name expected manifest_sha digest_ledger
  printf '%s\n' "${start_exit}" >"${RECEIPT_STAGING}/start-exit.txt"
  if [[ -f "${PHASE_A_FINAL}/manifest.json" && ! -L "${PHASE_A_FINAL}/manifest.json" ]]; then
    manifest_sha="$(sha256_of "${PHASE_A_FINAL}/manifest.json")" || fail 'cannot hash Phase A manifest for receipt'
    printf '%s  %s\n' "${manifest_sha}" "${PHASE_A_FINAL}/manifest.json" >"${RECEIPT_STAGING}/phase-a-manifest.sha256"
    /usr/bin/find -P "${PHASE_A_FINAL}" -xdev -mindepth 1 -printf '%P\n' | \
      /usr/bin/sort >"${RECEIPT_STAGING}/phase-a-publication-inventory.txt" || \
      fail 'cannot inventory Phase A publication for receipt'
  else
    printf '%s\n' 'absent' >"${RECEIPT_STAGING}/phase-a-manifest.sha256"
    printf '%s\n' 'absent' >"${RECEIPT_STAGING}/phase-a-publication-inventory.txt"
  fi
  digest_ledger="${RECEIPT_STAGING}/.content-digest-input.sha256"
  assert_absent "${digest_ledger}"
  (set -o noclobber; : >"${digest_ledger}") 2>/dev/null || \
    fail 'cannot create activation digest ledger'
  for name in ${RECEIPT_FILES}; do
    [[ "${name}" == manifest.txt ]] && continue
    (cd "${RECEIPT_STAGING}" && /usr/bin/sha256sum -- "${name}") >>"${digest_ledger}" || \
      fail "cannot hash activation receipt input: ${name}"
  done
  digest="$(sha256_of "${digest_ledger}")" || fail 'cannot hash activation digest ledger'
  /usr/bin/rm -f -- "${digest_ledger}" || fail 'cannot remove activation digest ledger'
  {
    printf '%s\n' 'schema=vista.r8-native-builder-r2-phase-a-activation-receipt/v1'
    printf '%s\n' "status=${outcome}" "source_commit=${COMMIT}" "start_exit=${start_exit}" "phase_a_invocation_id=${invocation}"
    printf '%s\n' 'phase_b_started=false' 'network_access=false' 'production_native_output=false'
    printf '%s\n' "journal_capture_exit=${JOURNAL_CAPTURE_EXIT}" "activator_sha256=${LIVE_SELF_SHA256}" "activator_size=${LIVE_SELF_BYTES}"
    printf '%s\n' 'prior_activation_status=pre-mutation-failed-manager-loaded' \
      "prior_activator_sha256=${FAILED_ACTIVATOR_SHA256}" \
      "prior_activator_size=${FAILED_ACTIVATOR_BYTES}"
    printf '%s\n' "r1_seal_tree_sha256=${R1_SEAL_TREE_SHA256}" "content_digest=${digest}"
  } >"${RECEIPT_STAGING}/manifest.txt"
  expected="$(printf '%s\n' ${RECEIPT_FILES} receipt.sha256 | /usr/bin/sort)"
  for name in ${RECEIPT_FILES}; do /usr/bin/chown root:root -- "${RECEIPT_STAGING}/${name}"; /usr/bin/chmod 0444 -- "${RECEIPT_STAGING}/${name}"; /usr/bin/sync -f "${RECEIPT_STAGING}/${name}"; done
  (
    cd "${RECEIPT_STAGING}" || exit 1
    for name in ${RECEIPT_FILES}; do /usr/bin/sha256sum -- "${name}" || exit 1; done
  ) >"${RECEIPT_STAGING}/receipt.sha256" || fail 'cannot hash activation receipt files'
  /usr/bin/chown root:root -- "${RECEIPT_STAGING}/receipt.sha256"; /usr/bin/chmod 0444 -- "${RECEIPT_STAGING}/receipt.sha256"; /usr/bin/sync -f "${RECEIPT_STAGING}/receipt.sha256"
  /usr/bin/chmod 0555 -- "${RECEIPT_STAGING}"; assert_inventory "${RECEIPT_STAGING}" "${expected}"
  (cd "${RECEIPT_STAGING}" && /usr/bin/sha256sum -c -- receipt.sha256 >/dev/null) || fail 'activation receipt does not verify'
  /usr/bin/sync -f "${RECEIPT_STAGING}"; /usr/bin/sync -f /root
  /usr/bin/mv -T --no-clobber -- "${RECEIPT_STAGING}" "${RECEIPT_FINAL}" || fail 'activation receipt no-replace publish failed'
  /usr/bin/sync -f /root
  RECEIPT_STAGING_OWNED='false'
  RECEIPT_PUBLISHED='true'; assert_directory "${RECEIPT_FINAL}" 555 0 0; assert_inventory "${RECEIPT_FINAL}" "${expected}"
  for name in ${RECEIPT_FILES} receipt.sha256; do
    assert_closed_file_metadata "${RECEIPT_FINAL}/${name}" 444 0 0
  done
  (cd "${RECEIPT_FINAL}" && /usr/bin/sha256sum -c -- receipt.sha256 >/dev/null) || fail 'published activation receipt does not verify'
}

[[ "${EUID}" -eq 0 && "$#" -eq 0 ]] || fail 'root EUID and zero arguments are required'
[[ "$0" == "${LIVE_SELF}" && -f "${LIVE_SELF}" && ! -L "${LIVE_SELF}" ]] || fail 'live activation path differs'
[[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h' -- "${LIVE_SELF}")" == 'regular file|500|0|0|1' ]] || fail 'live activation metadata differs'
exec 8<"${LIVE_SELF}"
LIVE_SELF_ID="$(/usr/bin/stat -Lc '%d:%i' -- /proc/$$/fd/8)" || fail 'cannot bind live activation identity'
LIVE_SELF_SHA256="$(sha256_of /proc/$$/fd/8)" || fail 'cannot hash live activation'
LIVE_SELF_BYTES="$(/usr/bin/stat -Lc '%s' -- /proc/$$/fd/8)" || fail 'cannot size live activation'
readonly LIVE_SELF_ID LIVE_SELF_SHA256 LIVE_SELF_BYTES
verify_live_self
secure_reexec_with_r1_build_locks
R1_PHASE_A_LOCK_ID="$(/usr/bin/stat -Lc '%d:%i' -- "/proc/$$/fd/${R1_PHASE_A_LOCK_FD}")" || \
  fail 'cannot bind R1 Phase A build lock'
R1_PHASE_B_LOCK_ID="$(/usr/bin/stat -Lc '%d:%i' -- "/proc/$$/fd/${R1_PHASE_B_LOCK_FD}")" || \
  fail 'cannot bind R1 Phase B build lock'
readonly R1_PHASE_A_LOCK_ID R1_PHASE_B_LOCK_ID
assert_r1_state_filesystem
verify_r1_build_lock_bindings
verify_failed_activation_history
assert_absent "${RECEIPT_FINAL}"; assert_absent "${RECEIPT_STAGING}"; assert_absent "${OUTER_LOCK}"
trap '' HUP INT TERM
/usr/bin/mkdir -m 0700 -- "${OUTER_LOCK}"
OUTER_LOCK_OWNED='true'
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
/usr/bin/chown root:root -- "${OUTER_LOCK}"
exec 9<"${OUTER_LOCK}"
/usr/bin/flock -n 9 || fail 'cannot lock activation'
[[ -f "${GLOBAL_LOCK}" && ! -L "${GLOBAL_LOCK}" ]] || fail 'R2 global lock is absent'
[[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h|%s' -- "${GLOBAL_LOCK}")" == 'regular empty file|600|0|0|1|0' ]] || fail 'R2 global lock metadata differs'
exec 10<>"${GLOBAL_LOCK}"
/usr/bin/flock -n 10 || fail 'another R2 bootstrap or activation holds the global lock'
GLOBAL_LOCK_ID="$(/usr/bin/stat -Lc '%d:%i' -- /proc/$$/fd/10)" || fail 'cannot bind R2 global lock'
readonly GLOBAL_LOCK_ID
verify_r1_build_lock_bindings
verify_r1_seal
R1_SEAL_TREE_SHA256="$(r1_seal_tree_digest)" || fail 'cannot pin R1 seal tree'; readonly R1_SEAL_TREE_SHA256
printf '%s\n' "${R1_SEAL_TREE_SHA256}" >"${OUTER_LOCK}/r1-seal-tree.sha256"
verify_failed_activation_history
verify_r2_disk; validate_request; assert_r1_vector; assert_r2_pre_reload_pristine "${PHASE_A}"; assert_r2_pre_reload_pristine "${PHASE_B}"
available="$(/usr/bin/df -B1 --output=avail /var/lib | /usr/bin/tail -n1 | /usr/bin/tr -d ' ')" || fail 'cannot inspect /var/lib capacity'
[[ "${available}" =~ ^[0-9]+$ && "${available}" -ge 1073741824 ]] || fail 'less than 1 GiB is available on /var/lib'
trap '' HUP INT TERM
/usr/bin/install -d -o root -g root -m 0700 -- "${RECEIPT_STAGING}"
RECEIPT_STAGING_OWNED='true'
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
printf '%s  %s\n' "${LIVE_SELF_SHA256}" "${LIVE_SELF}" >"${RECEIPT_STAGING}/activation-self-pin.sha256"
printf '%s  %s\n' "${FAILED_ACTIVATOR_SHA256}" "${FAILED_ACTIVATOR}" >"${RECEIPT_STAGING}/failed-activation-self-pin.sha256"
/usr/bin/systemd-analyze verify "${PHASE_A_UNIT}" "${PHASE_B_UNIT}" >"${RECEIPT_STAGING}/systemd-analyze.txt" 2>&1 || fail 'systemd unit verification failed'
capture_pair "${PHASE_A}" "${PHASE_B}" "${RECEIPT_STAGING}/r2-before-reload.systemctl-show.txt"
capture_r1_state "${RECEIPT_STAGING}/r1-before-reload-state.txt" || \
  fail 'cannot capture R1 state before reload'
printf '%s\n' "${R1_SEAL_TREE_SHA256}" >"${RECEIPT_STAGING}/r1-seal-tree.sha256"
verify_r1_seal; [[ "$(r1_seal_tree_digest)" == "${R1_SEAL_TREE_SHA256}" ]] || fail 'R1 seal tree changed before reload'
verify_live_self
verify_failed_activation_history
verify_r2_disk; validate_request; assert_r1_vector
assert_r1_state_matches "${RECEIPT_STAGING}/r1-before-reload-state.txt"
assert_r2_pre_reload_pristine "${PHASE_A}"; assert_r2_pre_reload_pristine "${PHASE_B}"

# From the reload through atomic receipt publication, every expected evidence
# file exists and termination signals are deferred.  Commands are captured as
# statuses rather than allowed to abandon an unsealed post-mutation staging.
for placeholder in phase-a-manifest.sha256 phase-a-publication-inventory.txt \
  phase-a.journal.txt post-start-validation.txt \
  r1-after-reload-state.txt r1-after-start-state.txt \
  r1-after-reload.systemctl-show.txt r1-after-start.systemctl-show.txt \
  r2-after-reload.systemctl-show.txt r2-after-start.systemctl-show.txt \
  start-exit.txt; do
  printf '%s\n' 'not-captured' >"${RECEIPT_STAGING}/${placeholder}"
done

trap '' HUP INT TERM
MUTATION_BEGUN='true'
set +e
/usr/bin/systemctl daemon-reload
RELOAD_EXIT="$?"
capture_pair "${PHASE_A}" "${PHASE_B}" "${RECEIPT_STAGING}/r2-after-reload.systemctl-show.txt"
R2_RELOAD_CAPTURE_EXIT="$?"
capture_pair "${R1_PHASE_A}" "${R1_PHASE_B}" "${RECEIPT_STAGING}/r1-after-reload.systemctl-show.txt"
R1_RELOAD_CAPTURE_EXIT="$?"
capture_r1_state "${RECEIPT_STAGING}/r1-after-reload-state.txt"
R1_RELOAD_STATE_EXIT="$?"
(
  [[ "${RELOAD_EXIT}" -eq 0 && "${R2_RELOAD_CAPTURE_EXIT}" -eq 0 && \
    "${R1_RELOAD_CAPTURE_EXIT}" -eq 0 && "${R1_RELOAD_STATE_EXIT}" -eq 0 ]] || exit 1
  verify_r1_seal
  verify_live_self
  verify_failed_activation_history
  [[ "$(r1_seal_tree_digest)" == "${R1_SEAL_TREE_SHA256}" ]] || fail 'R1 seal tree changed after reload'
  /usr/bin/cmp -s -- "${RECEIPT_STAGING}/r1-before-reload-state.txt" \
    "${RECEIPT_STAGING}/r1-after-reload-state.txt" || fail 'R1 state changed during reload'
  assert_r1_state_matches "${RECEIPT_STAGING}/r1-before-reload-state.txt"
  assert_r1_vector; verify_r2_disk; validate_request
  assert_r2_never_started "${PHASE_A}"; assert_r2_never_started "${PHASE_B}"
)
POST_RELOAD_EXIT="$?"

START_EXIT='124'
if [[ "${POST_RELOAD_EXIT}" -eq 0 ]]; then
  /usr/bin/systemctl start --no-ask-password --wait -- "${PHASE_A}"
  START_EXIT="$?"
fi
capture_pair "${PHASE_A}" "${PHASE_B}" "${RECEIPT_STAGING}/r2-after-start.systemctl-show.txt"
R2_START_CAPTURE_EXIT="$?"
capture_pair "${R1_PHASE_A}" "${R1_PHASE_B}" "${RECEIPT_STAGING}/r1-after-start.systemctl-show.txt"
R1_START_CAPTURE_EXIT="$?"
capture_r1_state "${RECEIPT_STAGING}/r1-after-start-state.txt"
R1_START_STATE_EXIT="$?"
phase_a_current="$(manager_document "${PHASE_A}")"
MANAGER_READ_EXIT="$?"
if [[ "${MANAGER_READ_EXIT}" -eq 0 ]]; then INVOCATION="$(property "${phase_a_current}" InvocationID)"; else INVOCATION=''; fi
JOURNAL_CAPTURE_EXIT='1'
if [[ "${INVOCATION}" =~ ^[0-9a-f]{32}$ ]]; then
  if ! /usr/bin/journalctl --no-pager --quiet "_SYSTEMD_INVOCATION_ID=${INVOCATION}" -u "${PHASE_A}" --output=short-iso-precise >"${RECEIPT_STAGING}/phase-a.journal.txt"; then
    printf '%s\n' 'journal-capture-failed' >"${RECEIPT_STAGING}/phase-a.journal.txt"
  elif [[ ! -s "${RECEIPT_STAGING}/phase-a.journal.txt" ]] || \
    ! /usr/bin/grep -Fq 'vista.r8-native-builder-phase-a-manifest/v1' "${RECEIPT_STAGING}/phase-a.journal.txt"; then
    JOURNAL_CAPTURE_EXIT='2'
  else
    JOURNAL_CAPTURE_EXIT='0'
  fi
else
  printf '%s\n' 'invocation-id-unavailable' >"${RECEIPT_STAGING}/phase-a.journal.txt"
fi
POST_VALIDATION_EXIT='0'
if [[ "${POST_RELOAD_EXIT}" -eq 0 && "${START_EXIT}" -eq 0 && \
  "${R2_START_CAPTURE_EXIT}" -eq 0 && "${R1_START_CAPTURE_EXIT}" -eq 0 && \
  "${R1_START_STATE_EXIT}" -eq 0 && "${MANAGER_READ_EXIT}" -eq 0 ]]; then
  (
    verify_r1_seal
    verify_live_self
    verify_failed_activation_history
    [[ "$(r1_seal_tree_digest)" == "${R1_SEAL_TREE_SHA256}" ]] || fail 'R1 seal tree changed after start'
    /usr/bin/cmp -s -- "${RECEIPT_STAGING}/r1-before-reload-state.txt" \
      "${RECEIPT_STAGING}/r1-after-start-state.txt" || fail 'R1 state changed during Phase A start'
    assert_r1_state_matches "${RECEIPT_STAGING}/r1-before-reload-state.txt"
    assert_r1_vector
    verify_phase_a_publication
    assert_r2_never_started "${PHASE_B}"
    doc="$(manager_document "${PHASE_A}")"
    [[ "$(property "${doc}" LoadState)|$(property "${doc}" ActiveState)|$(property "${doc}" SubState)|$(property "${doc}" Result)|$(property "${doc}" ExecMainCode)|$(property "${doc}" ExecMainStatus)|$(property "${doc}" NRestarts)|$(property "${doc}" MainPID)|$(property "${doc}" ControlPID)" == 'loaded|inactive|dead|success|1|0|0|0|0' ]] || fail 'successful R2 Phase A manager close vector differs'
    printf '%s\n' 'post-start-validation=passed'
  ) >"${RECEIPT_STAGING}/post-start-validation.txt" 2>&1
  POST_VALIDATION_EXIT="$?"
else
  POST_VALIDATION_EXIT='1'
  printf '%s\n' "post-start-validation=skipped reload=${RELOAD_EXIT} reload_gate=${POST_RELOAD_EXIT} start=${START_EXIT} captures=${R2_START_CAPTURE_EXIT},${R1_START_CAPTURE_EXIT},${R1_START_STATE_EXIT},${MANAGER_READ_EXIT}" >"${RECEIPT_STAGING}/post-start-validation.txt"
fi
set -e
if [[ "${RELOAD_EXIT}" -eq 0 && "${POST_RELOAD_EXIT}" -eq 0 && "${START_EXIT}" -eq 0 && "${POST_VALIDATION_EXIT}" -eq 0 && "${JOURNAL_CAPTURE_EXIT}" -eq 0 ]]; then OUTCOME='succeeded'; else OUTCOME='failed-preserved-no-retry'; fi
seal_receipt "${OUTCOME}" "${START_EXIT}" "${INVOCATION}"
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ "${RELOAD_EXIT}" -ne 0 || "${POST_RELOAD_EXIT}" -ne 0 || "${START_EXIT}" -ne 0 || "${POST_VALIDATION_EXIT}" -ne 0 || "${JOURNAL_CAPTURE_EXIT}" -ne 0 ]]; then
  printf '%s\n' "VISTA_R8_NATIVE_BUILDER_R2_PHASE_A_FAILED_PRESERVED=${RECEIPT_FINAL}" >&2
  exit 125
fi
verify_r1_seal; [[ "$(r1_seal_tree_digest)" == "${R1_SEAL_TREE_SHA256}" ]] || fail 'R1 seal tree changed after start'
verify_live_self
verify_failed_activation_history
assert_r1_state_matches "${RECEIPT_FINAL}/r1-before-reload-state.txt"
assert_r1_vector
verify_phase_a_publication
assert_r2_never_started "${PHASE_B}"
phase_a_doc="$(manager_document "${PHASE_A}")"
[[ "$(property "${phase_a_doc}" LoadState)|$(property "${phase_a_doc}" ActiveState)|$(property "${phase_a_doc}" SubState)|$(property "${phase_a_doc}" Result)|$(property "${phase_a_doc}" ExecMainCode)|$(property "${phase_a_doc}" ExecMainStatus)|$(property "${phase_a_doc}" NRestarts)|$(property "${phase_a_doc}" MainPID)|$(property "${phase_a_doc}" ControlPID)" == 'loaded|inactive|dead|success|1|0|0|0|0' ]] || fail 'successful R2 Phase A manager close vector differs'
printf '%s\n' "VISTA_R8_NATIVE_BUILDER_R2_PHASE_A_SUCCEEDED=${RECEIPT_FINAL}"
printf '%s\n' 'Phase B was not started; no unit was enabled, restarted, or reset-failed.'
