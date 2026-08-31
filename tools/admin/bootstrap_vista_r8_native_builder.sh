#!/usr/bin/env bash
# Install or append one fixed part of the inactive VISTA R8 native builder.
#
# The live script and its source assets must first be copied into the exact
# root-owned review root below. This helper never reloads systemd, starts or
# enables a unit, executes the builder, compiles code, or accepts a destination.

set -euo pipefail
IFS=$'\n\t'
export LC_ALL=C LANG=C PATH=/usr/sbin:/usr/bin:/sbin:/bin
unset BASH_ENV ENV CDPATH GLOBIGNORE PYTHONHOME PYTHONPATH

readonly BUILDER_NAME='vista-r8-builder'
readonly BUILDER_UID='997'
readonly BUILDER_GID='997'
readonly BUILDER_HOME='/nonexistent'
readonly BUILDER_SHELL='/usr/sbin/nologin'

readonly TRUSTED_ROOT='/root/vista-r8-native-builder-bootstrap-r1'
readonly TRUSTED_SELF="${TRUSTED_ROOT}/bootstrap_vista_r8_native_builder.sh"
readonly TRUSTED_BUILDER="${TRUSTED_ROOT}/vista_r8_native_builder.py"
readonly TRUSTED_SYSTEMD="${TRUSTED_ROOT}/systemd"
readonly PHASE_A_UNIT='vista-r8-native-builder-phase-a.service'
readonly PHASE_B_UNIT='vista-r8-native-builder-phase-b.service'
readonly TRUSTED_PHASE_A_UNIT="${TRUSTED_SYSTEMD}/${PHASE_A_UNIT}"
readonly TRUSTED_PHASE_B_UNIT="${TRUSTED_SYSTEMD}/${PHASE_B_UNIT}"

readonly INPUT_CANDIDATE_ROOT='/root/vista-r8-native-builder-bootstrap-input-r1'
readonly CANDIDATE_BUNDLE="${INPUT_CANDIDATE_ROOT}/source.bundle"
readonly CANDIDATE_PHASE_A_REQUEST="${INPUT_CANDIDATE_ROOT}/phase-a-request.json"
readonly CANDIDATE_PHASE_B_REQUEST="${INPUT_CANDIDATE_ROOT}/phase-b-request.json"

readonly LIBEXEC_ROOT='/usr/local/libexec/vista-r8-native-builder-r1'
readonly BUILDER_DEST="${LIBEXEC_ROOT}/vista_r8_native_builder.py"
readonly INPUT_ROOT='/etc/vista-r8-native-builder-r1'
readonly BUNDLE_DEST="${INPUT_ROOT}/source.bundle"
readonly PHASE_A_REQUEST_DEST="${INPUT_ROOT}/phase-a-request.json"
readonly PHASE_B_REQUEST_DEST="${INPUT_ROOT}/phase-b-request.json"
readonly STATE_ROOT='/var/lib/vista-r8-native-builder-r1'
readonly PHASE_A_SLOT="${STATE_ROOT}/phase-a-slot"
readonly PHASE_B_SLOT="${STATE_ROOT}/phase-b-slot"
readonly PHASE_A_FINAL="${PHASE_A_SLOT}/published"
readonly PHASE_B_FINAL="${PHASE_B_SLOT}/published"
readonly UNIT_ROOT='/etc/systemd/system'
readonly -a SYSTEMD_UNIT_SEARCH_ROOTS=(
  '/etc/systemd/system.control'
  '/run/systemd/system.control'
  '/run/systemd/transient'
  '/run/systemd/generator.early'
  '/etc/systemd/system'
  '/etc/systemd/system.attached'
  '/run/systemd/system'
  '/run/systemd/system.attached'
  '/run/systemd/generator'
  '/usr/local/lib/systemd/system'
  '/usr/lib/systemd/system'
  '/lib/systemd/system'
  '/run/systemd/generator.late'
)
readonly -a SYSTEMD_DROPIN_NAMES=(
  'vista-.service.d'
  'vista-r8-.service.d'
  'vista-r8-native-.service.d'
  'vista-r8-native-builder-.service.d'
  'vista-r8-native-builder-phase-.service.d'
  'service.d'
)

readonly INSTALL_FRAMEWORK='install-framework'
readonly INSTALL_PHASE_A='install-phase-a-inputs'
readonly INSTALL_PHASE_B='install-phase-b-request'
readonly FRAMEWORK_ACK='I acknowledge installation or exact reconciliation of the fixed inactive VISTA R8 native-builder framework without starting a service or build.'
readonly PHASE_A_ACK='I acknowledge fresh append or exact reconciliation of the reviewed VISTA R8 native-builder source bundle and phase A request without starting a build.'
readonly PHASE_B_ACK='I acknowledge fresh append or exact reconciliation of the reviewed VISTA R8 native-builder phase B request after closed phase A publication without starting a build.'
readonly SUBID_RANGE_AWK='
$0 == "" { next }
NF != 3 || $1 == "" || $2 !~ /^[0-9]+$/ || $3 !~ /^[0-9]+$/ {
  invalid = 1
  next
}
{
  start = $2 + 0
  count = $3 + 0
  end = start + count
  if (count < 1 || start < 0 || start > 4294967295 ||
      count > 4294967295 || end > 4294967296) {
    invalid = 1
    next
  }
  if ($1 == builder || (target >= start && target < end)) {
    rejected = 1
  }
}
END {
  if (invalid) exit 2
  if (rejected) exit 0
  exit 1
}
'
readonly PROCESS_ID_AWK='
$1 == "Uid:" {
  if (seen_uid || NF != 5) invalid = 1
  seen_uid = 1
  for (field = 2; field <= NF; field++) {
    if ($field !~ /^[0-9]+$/) invalid = 1
    if (($field + 0) == target) matched = 1
  }
}
$1 == "Gid:" {
  if (seen_gid || NF != 5) invalid = 1
  seen_gid = 1
  for (field = 2; field <= NF; field++) {
    if ($field !~ /^[0-9]+$/) invalid = 1
    if (($field + 0) == target) matched = 1
  }
}
$1 == "Groups:" {
  if (seen_groups) invalid = 1
  seen_groups = 1
  for (field = 2; field <= NF; field++) {
    if ($field !~ /^[0-9]+$/) invalid = 1
    if (($field + 0) == target) matched = 1
  }
}
END {
  if (invalid || !seen_uid || !seen_gid || !seen_groups) exit 2
  if (matched) exit 0
  exit 1
}
'

readonly BOOTSTRAP_PID="$$"
TEMP_PATH=''

fail() {
  printf '%s\n' "vista-r8-native-builder bootstrap: $*" >&2
  exit 126
}

cleanup() {
  if [[ -n "${TEMP_PATH}" && -e "${TEMP_PATH}" ]]; then
    /usr/bin/rm -f -- "${TEMP_PATH}"
  fi
}
trap cleanup EXIT HUP INT TERM

[[ "${EUID}" -eq 0 ]] || fail 'root EUID is required'

file_sha256() {
  local output
  output="$(/usr/bin/sha256sum -- "$1")" || fail "cannot hash $1"
  printf '%s' "${output%% *}"
}

validate_pin_literal() {
  local label="$1" sha256="$2" size="$3"
  [[ "${sha256}" =~ ^[0-9a-f]{64}$ ]] || fail "${label} SHA-256 is invalid"
  [[ "${size}" =~ ^[1-9][0-9]*$ ]] || fail "${label} size is invalid"
}

assert_directory() {
  local path="$1" uid="$2" gid="$3" mode="$4" label="$5" metadata
  [[ -d "${path}" && ! -L "${path}" ]] || fail "${label} is not a directory"
  metadata="$(/usr/bin/stat -c '%u:%g:%a' -- "${path}")" || \
    fail "cannot stat ${label}"
  [[ "${metadata}" == "${uid}:${gid}:${mode#0}" ]] || \
    fail "${label} owner or mode differs"
}

assert_closed_regular() {
  local path="$1" uid="$2" gid="$3" mode="$4" label="$5" metadata
  [[ -f "${path}" && ! -L "${path}" ]] || fail "${label} is not a regular file"
  metadata="$(/usr/bin/stat -c '%u:%g:%h:%a:%s' -- "${path}")" || \
    fail "cannot stat ${label}"
  [[ "${metadata}" =~ ^${uid}:${gid}:1:${mode#0}:[1-9][0-9]*$ ]] || \
    fail "${label} metadata differs"
}

ensure_directory() {
  local path="$1" owner="$2" group="$3" mode="$4" uid="$5" gid="$6"
  if [[ -e "${path}" || -L "${path}" ]]; then
    assert_directory "${path}" "${uid}" "${gid}" "${mode}" "${path}"
  else
    /usr/bin/install -d -o "${owner}" -g "${group}" -m "${mode}" -- "${path}"
  fi
  /usr/bin/sync --file-system -- "${path}"
  /usr/bin/sync --file-system -- "${path%/*}"
}

assert_exact_inventory() {
  local root="$1"
  shift
  local -a expected=("$@") entries=()
  local entry name wanted expected_name
  mapfile -d '' -t entries < <(
    /usr/bin/find "${root}" -mindepth 1 -maxdepth 1 -print0
  )
  [[ "${#entries[@]}" -eq "${#expected[@]}" ]] || \
    fail "unexpected inventory below ${root}"
  for entry in "${entries[@]}"; do
    name="${entry##*/}"
    wanted='false'
    for expected_name in "${expected[@]}"; do
      if [[ "${name}" == "${expected_name}" ]]; then
        wanted='true'
        break
      fi
    done
    [[ "${wanted}" == 'true' ]] || fail "unexpected entry below ${root}: ${name}"
  done
}

assert_inventory_is_one_of() {
  local root="$1" first="$2" second="$3"
  local -a entries=()
  local entry name
  local seen_first='false' seen_second='false'
  mapfile -d '' -t entries < <(
    /usr/bin/find "${root}" -mindepth 1 -maxdepth 1 -print0
  )
  [[ "${#entries[@]}" -ge 1 && "${#entries[@]}" -le 2 ]] || \
    fail "invalid append-only prefix below ${root}"
  for entry in "${entries[@]}"; do
    name="${entry##*/}"
    case "${name}" in
      "${first}") seen_first='true' ;;
      "${second}") seen_second='true' ;;
      *) fail "unexpected entry below ${root}: ${name}" ;;
    esac
  done
  [[ "${seen_first}" == 'true' ]] || fail "missing prefix entry below ${root}: ${first}"
  if [[ "${seen_second}" == 'true' ]]; then
    [[ "${#entries[@]}" -eq 2 ]] || fail "invalid prefix below ${root}"
  fi
}

assert_path_and_open_trusted_assets() {
  local live_self
  live_self="$(/usr/bin/readlink -f -- "${BASH_SOURCE[0]}")"
  [[ "${live_self}" == "${TRUSTED_SELF}" ]] || fail 'trusted bootstrap path differs'
  assert_directory "${TRUSTED_ROOT}" 0 0 0555 'trusted bootstrap root'
  assert_directory "${TRUSTED_SYSTEMD}" 0 0 0555 'trusted systemd source root'
  assert_exact_inventory "${TRUSTED_ROOT}" \
    'bootstrap_vista_r8_native_builder.sh' 'vista_r8_native_builder.py' 'systemd'
  assert_exact_inventory "${TRUSTED_SYSTEMD}" "${PHASE_A_UNIT}" "${PHASE_B_UNIT}"
  [[ ! -L "${TRUSTED_SELF}" && ! -L "${TRUSTED_BUILDER}" && \
    ! -L "${TRUSTED_PHASE_A_UNIT}" && ! -L "${TRUSTED_PHASE_B_UNIT}" ]] || \
    fail 'trusted source symlink is forbidden'
  exec {SELF_FD}<"${TRUSTED_SELF}"
  exec {BUILDER_FD}<"${TRUSTED_BUILDER}"
  exec {PHASE_A_UNIT_FD}<"${TRUSTED_PHASE_A_UNIT}"
  exec {PHASE_B_UNIT_FD}<"${TRUSTED_PHASE_B_UNIT}"
  readonly SELF_FD BUILDER_FD PHASE_A_UNIT_FD PHASE_B_UNIT_FD
}

held_path() {
  printf '/proc/%s/fd/%s' "${BOOTSTRAP_PID}" "$1"
}

verify_held_file() {
  local descriptor="$1" uid="$2" gid="$3" mode="$4"
  local sha256="$5" size="$6" label="$7" path metadata
  path="$(held_path "${descriptor}")"
  [[ -f "${path}" ]] || fail "held ${label} is not regular"
  metadata="$(/usr/bin/stat -Lc '%u:%g:%h:%a:%s' -- "${path}")" || \
    fail "cannot stat held ${label}"
  [[ "${metadata}" == "${uid}:${gid}:1:${mode#0}:${size}" ]] || \
    fail "held ${label} metadata differs"
  [[ "$(file_sha256 "${path}")" == "${sha256}" ]] || \
    fail "held ${label} SHA-256 differs"
}

observed_held_pin() {
  local descriptor="$1" uid="$2" gid="$3" mode="$4" label="$5"
  local path size sha256
  path="$(held_path "${descriptor}")"
  size="$(/usr/bin/stat -Lc '%s' -- "${path}")" || fail "cannot size ${label}"
  [[ "${size}" =~ ^[1-9][0-9]*$ ]] || fail "${label} must be non-empty"
  sha256="$(file_sha256 "${path}")"
  verify_held_file "${descriptor}" "${uid}" "${gid}" "${mode}" \
    "${sha256}" "${size}" "${label}"
  printf '%s %s\n' "${sha256}" "${size}"
}

verify_installed_file() {
  local path="$1" sha256="$2" size="$3" mode="$4" label="$5" metadata
  [[ -f "${path}" && ! -L "${path}" ]] || fail "${label} is not regular"
  metadata="$(/usr/bin/stat -c '%u:%g:%h:%a:%s' -- "${path}")" || \
    fail "cannot stat ${label}"
  [[ "${metadata}" == "0:0:1:${mode#0}:${size}" ]] || \
    fail "${label} owner, mode, links, or size differs"
  [[ "$(file_sha256 "${path}")" == "${sha256}" ]] || fail "${label} SHA-256 differs"
}

install_held_once() {
  local descriptor="$1" destination="$2" sha256="$3" size="$4" mode="$5" label="$6"
  local source
  source="$(held_path "${descriptor}")"
  if [[ -e "${destination}" || -L "${destination}" ]]; then
    verify_installed_file "${destination}" "${sha256}" "${size}" "${mode}" "${label}"
    /usr/bin/sync --file-system -- "${destination}"
    /usr/bin/sync --file-system -- "${destination%/*}"
    return
  fi
  TEMP_PATH="${destination}.new.$$"
  [[ ! -e "${TEMP_PATH}" && ! -L "${TEMP_PATH}" ]] || \
    fail "temporary destination exists: ${TEMP_PATH}"
  /usr/bin/install -o root -g root -m "${mode}" -- "${source}" "${TEMP_PATH}"
  verify_installed_file "${TEMP_PATH}" "${sha256}" "${size}" "${mode}" \
    "temporary ${label}"
  /usr/bin/sync --file-system -- "${TEMP_PATH}"
  /usr/bin/mv --no-clobber --no-target-directory -- "${TEMP_PATH}" "${destination}"
  if [[ -e "${TEMP_PATH}" || -L "${TEMP_PATH}" ]]; then
    /usr/bin/rm -f -- "${TEMP_PATH}"
  fi
  TEMP_PATH=''
  verify_installed_file "${destination}" "${sha256}" "${size}" "${mode}" "${label}"
  /usr/bin/sync --file-system -- "${destination}"
  /usr/bin/sync --file-system -- "${destination%/*}"
}

create_lock_once() {
  local path="$1" metadata
  if [[ ! -e "${path}" && ! -L "${path}" ]]; then
    /usr/bin/install -o "${BUILDER_NAME}" -g "${BUILDER_NAME}" -m 0600 \
      -- /dev/null "${path}"
  fi
  verify_lock "${path}"
  /usr/bin/sync --file-system -- "${path}"
  /usr/bin/sync --file-system -- "${path%/*}"
}

verify_lock() {
  local path="$1" metadata
  [[ -f "${path}" && ! -L "${path}" ]] || fail "lock is not regular: ${path}"
  metadata="$(/usr/bin/stat -c '%u:%g:%h:%a:%s' -- "${path}")" || \
    fail "cannot stat lock: ${path}"
  [[ "${metadata}" == "${BUILDER_UID}:${BUILDER_GID}:1:600:0" ]] || \
    fail "lock metadata differs: ${path}"
}

validate_group() {
  local allow_create="$1" by_name by_gid name password gid members
  by_name="$(/usr/bin/getent group "${BUILDER_NAME}" || true)"
  by_gid="$(/usr/bin/getent group "${BUILDER_GID}" || true)"
  if [[ -z "${by_name}" && -z "${by_gid}" ]]; then
    [[ "${allow_create}" == 'true' ]] || fail 'builder group is absent'
    /usr/sbin/groupadd --system --gid "${BUILDER_GID}" "${BUILDER_NAME}"
    by_name="$(/usr/bin/getent group "${BUILDER_NAME}")"
    by_gid="$(/usr/bin/getent group "${BUILDER_GID}")"
  fi
  [[ -n "${by_name}" && "${by_name}" == "${by_gid}" ]] || \
    fail 'builder group name/GID collision'
  IFS=: read -r name password gid members <<<"${by_name}"
  [[ "${name}" == "${BUILDER_NAME}" && "${gid}" == "${BUILDER_GID}" && \
    -z "${members}" ]] || fail 'builder group record differs'
}

validate_user() {
  local allow_create="$1" by_name by_uid name password uid gid gecos home shell status
  by_name="$(/usr/bin/getent passwd "${BUILDER_NAME}" || true)"
  by_uid="$(/usr/bin/getent passwd "${BUILDER_UID}" || true)"
  if [[ -z "${by_name}" && -z "${by_uid}" ]]; then
    [[ "${allow_create}" == 'true' ]] || fail 'builder user is absent'
    /usr/sbin/useradd --system --uid "${BUILDER_UID}" --gid "${BUILDER_GID}" \
      --home-dir "${BUILDER_HOME}" --shell "${BUILDER_SHELL}" \
      --no-create-home --no-user-group --password '!' "${BUILDER_NAME}"
    by_name="$(/usr/bin/getent passwd "${BUILDER_NAME}")"
    by_uid="$(/usr/bin/getent passwd "${BUILDER_UID}")"
  fi
  [[ -n "${by_name}" && "${by_name}" == "${by_uid}" ]] || \
    fail 'builder user name/UID collision'
  IFS=: read -r name password uid gid gecos home shell <<<"${by_name}"
  [[ "${name}" == "${BUILDER_NAME}" && "${uid}" == "${BUILDER_UID}" && \
    "${gid}" == "${BUILDER_GID}" && "${home}" == "${BUILDER_HOME}" && \
    "${shell}" == "${BUILDER_SHELL}" ]] || fail 'builder passwd record differs'
  [[ "$(/usr/bin/id -G "${BUILDER_NAME}")" == "${BUILDER_GID}" ]] || \
    fail 'builder supplementary groups are forbidden'
  status="$(/usr/bin/passwd --status "${BUILDER_NAME}")" || \
    fail 'cannot inspect builder password status'
  IFS=' ' read -r name password _ <<<"${status}"
  [[ "${name}" == "${BUILDER_NAME}" && "${password}" == 'L' ]] || \
    fail 'builder password must be locked'
  reject_subordinate_id_ranges
}

reject_subordinate_id_ranges() {
  local database status
  for database in /etc/subuid /etc/subgid; do
    [[ -e "${database}" ]] || continue
    [[ -f "${database}" && ! -L "${database}" ]] || \
      fail "subordinate-ID database is not a regular file: ${database}"
    if /usr/bin/awk -F: -v target="${BUILDER_UID}" -v builder="${BUILDER_NAME}" \
      "${SUBID_RANGE_AWK}" "${database}"; then
      fail "builder identity or numeric ID 997 has a delegated range in ${database}"
    else
      status="$?"
      [[ "${status}" -eq 1 ]] || fail "invalid subordinate-ID database: ${database}"
    fi
  done
}

assert_builder_identity_unused() {
  local status_file status pid
  local -a status_files=(/proc/[0-9]*/status)
  for status_file in "${status_files[@]}"; do
    [[ -e "${status_file}" ]] || continue
    if [[ ! -f "${status_file}" || -L "${status_file}" ]]; then
      [[ ! -e "${status_file}" ]] && continue
      fail "cannot inspect process identity: ${status_file}"
    fi
    if /usr/bin/awk -v target="${BUILDER_UID}" "${PROCESS_ID_AWK}" \
      "${status_file}" 2>/dev/null; then
      pid="${status_file#/proc/}"
      pid="${pid%/status}"
      fail "numeric UID/GID 997 is active in process ${pid}"
    else
      status="$?"
      [[ "${status}" -eq 1 ]] && continue
      [[ ! -e "${status_file}" ]] && continue
      fail "cannot validate process identity: ${status_file}"
    fi
  done
}

assert_unit_inactive_and_empty() {
  local unit="$1" state events
  state="$(/usr/bin/systemctl is-active "${unit}" 2>/dev/null || true)"
  case "${state}" in
    inactive | failed | unknown) ;;
    *) fail "unit must be inactive: ${unit} (${state:-no state})" ;;
  esac
  events="/sys/fs/cgroup/system.slice/${unit}/cgroup.events"
  if [[ -e "${events}" ]]; then
    /usr/bin/grep -qx 'populated 0' "${events}" || fail "unit cgroup is populated: ${unit}"
  fi
}

manager_property_value() {
  local document="$1" property="$2" line value=''
  local count='0'
  while IFS= read -r line || [[ -n "${line}" ]]; do
    if [[ "${line}" == "${property}="* ]]; then
      count="$((count + 1))"
      value="${line#*=}"
    fi
  done <<<"${document}"
  [[ "${count}" -eq 1 ]] || \
    fail "manager property ${property} is missing or duplicated"
  printf '%s' "${value}"
}

assert_unit_manager_provenance() {
  local unit="$1" expected="${UNIT_ROOT}/${unit}" document line key
  local load_state fragment_path drop_in_paths unit_file_state names
  local wanted_by required_by
  local -a lines=()
  document="$(/usr/bin/systemctl show --no-pager \
    --property=LoadState \
    --property=FragmentPath \
    --property=DropInPaths \
    --property=UnitFileState \
    --property=Names \
    --property=WantedBy \
    --property=RequiredBy \
    -- "${unit}")" || fail "cannot inspect manager provenance for ${unit}"
  mapfile -t lines <<<"${document}"
  [[ "${#lines[@]}" -eq 7 ]] || \
    fail "manager provenance property inventory differs for ${unit}"
  for line in "${lines[@]}"; do
    key="${line%%=*}"
    case "${key}" in
      LoadState | FragmentPath | DropInPaths | UnitFileState | Names | WantedBy | RequiredBy) ;;
      *) fail "unexpected manager provenance property for ${unit}: ${key}" ;;
    esac
  done
  load_state="$(manager_property_value "${document}" LoadState)"
  fragment_path="$(manager_property_value "${document}" FragmentPath)"
  drop_in_paths="$(manager_property_value "${document}" DropInPaths)"
  unit_file_state="$(manager_property_value "${document}" UnitFileState)"
  names="$(manager_property_value "${document}" Names)"
  wanted_by="$(manager_property_value "${document}" WantedBy)"
  required_by="$(manager_property_value "${document}" RequiredBy)"

  [[ -z "${drop_in_paths}" ]] || \
    fail "manager DropInPaths are forbidden for ${unit}"
  [[ -z "${wanted_by}" && -z "${required_by}" ]] || \
    fail "manager reverse dependencies are forbidden for ${unit}"
  [[ -z "${names}" || "${names}" == "${unit}" ]] || \
    fail "manager aliases are forbidden for ${unit}"
  case "${unit_file_state}" in
    '' | static | disabled) ;;
    *) fail "manager UnitFileState is enabled, linked, masked, or otherwise forbidden for ${unit}: ${unit_file_state}" ;;
  esac
  case "${load_state}" in
    not-found)
      [[ -z "${fragment_path}" ]] || \
        fail "not-found manager unit has a FragmentPath: ${unit}"
      ;;
    loaded)
      [[ -f "${expected}" && ! -L "${expected}" ]] || \
        fail "loaded manager fragment is not the installed regular file: ${unit}"
      [[ "${fragment_path}" == "${expected}" ]] || \
        fail "manager FragmentPath differs for ${unit}: ${fragment_path}"
      [[ "${names}" == "${unit}" ]] || \
        fail "loaded manager Names differs for ${unit}: ${names}"
      ;;
    *) fail "manager LoadState is forbidden for ${unit}: ${load_state}" ;;
  esac
}

assert_unit_filesystem_provenance() {
  local unit="$1" require_fragment="$2" expected="${UNIT_ROOT}/${unit}"
  local root candidate dropin link raw_target resolved_target dependency
  local grep_status
  local -a links=() dependencies=()

  [[ -r /proc/1/environ ]] || \
    fail 'cannot inspect PID 1 environment for SYSTEMD_UNIT_PATH'
  if /usr/bin/grep -zq '^SYSTEMD_UNIT_PATH=' /proc/1/environ; then
    fail 'custom SYSTEMD_UNIT_PATH is forbidden'
  else
    grep_status="$?"
    [[ "${grep_status}" -eq 1 ]] || \
      fail 'cannot inspect PID 1 environment for SYSTEMD_UNIT_PATH'
  fi

  if [[ -e "${expected}" || -L "${expected}" ]]; then
    [[ -f "${expected}" && ! -L "${expected}" ]] || \
      fail "installed FragmentPath is not a regular file: ${expected}"
  else
    [[ "${require_fragment}" == 'false' ]] || \
      fail "installed FragmentPath is absent: ${expected}"
  fi

  for root in "${SYSTEMD_UNIT_SEARCH_ROOTS[@]}"; do
    [[ -e "${root}" || -L "${root}" ]] || continue
    [[ -d "${root}" ]] || fail "systemd search root is not a directory: ${root}"
    candidate="${root}/${unit}"
    if [[ "${candidate}" != "${expected}" && \
      ( -e "${candidate}" || -L "${candidate}" ) ]]; then
      fail "shadow fragment, link, or mask is forbidden: ${candidate}"
    fi
    for dropin in "${unit}.d" "${SYSTEMD_DROPIN_NAMES[@]}"; do
      if [[ -e "${root}/${dropin}" || -L "${root}/${dropin}" ]]; then
        fail "systemd drop-in path is forbidden: ${root}/${dropin}"
      fi
    done

    /usr/bin/find -H "${root}" -mindepth 1 -print0 >/dev/null || \
      fail "cannot exhaustively inspect systemd search root: ${root}"
    mapfile -d '' -t links < <(
      /usr/bin/find -H "${root}" -mindepth 1 -type l -print0
    )
    for link in "${links[@]}"; do
      raw_target="$(/usr/bin/readlink -- "${link}")" || \
        fail "cannot inspect systemd symlink: ${link}"
      resolved_target="$(/usr/bin/readlink -f -- "${link}" 2>/dev/null || true)"
      if [[ "${link##*/}" == "${unit}" || \
        "${raw_target}" == "${unit}" || "${raw_target}" == */"${unit}" || \
        "${resolved_target}" == "${expected}" ]]; then
        fail "systemd alias, mask, enabled link, or linked unit is forbidden: ${link}"
      fi
    done

    mapfile -d '' -t dependencies < <(
      /usr/bin/find -H "${root}" -mindepth 2 \
        \( -path "*.wants/${unit}" -o -path "*.requires/${unit}" \) -print0
    )
    for dependency in "${dependencies[@]}"; do
      fail "systemd wants/requires entry is forbidden: ${dependency}"
    done
  done
}

assert_systemd_provenance() {
  local require_fragment="$1"
  assert_unit_filesystem_provenance "${PHASE_A_UNIT}" "${require_fragment}"
  assert_unit_filesystem_provenance "${PHASE_B_UNIT}" "${require_fragment}"
  assert_unit_manager_provenance "${PHASE_A_UNIT}"
  assert_unit_manager_provenance "${PHASE_B_UNIT}"
}

assert_services_quiescent() {
  [[ -d /run/systemd/system ]] || fail 'a running systemd system manager is required'
  assert_unit_inactive_and_empty "${PHASE_A_UNIT}"
  assert_unit_inactive_and_empty "${PHASE_B_UNIT}"
  assert_systemd_provenance 'false'
}

verify_framework() {
  validate_group 'false'
  validate_user 'false'
  assert_directory "${LIBEXEC_ROOT}" 0 0 0555 'installed libexec root'
  assert_directory "${INPUT_ROOT}" 0 0 0555 'installed input root'
  assert_directory "${STATE_ROOT}" 0 0 0555 'installed state root'
  assert_directory "${PHASE_A_SLOT}" "${BUILDER_UID}" "${BUILDER_GID}" 0711 \
    'phase A slot'
  assert_directory "${PHASE_B_SLOT}" "${BUILDER_UID}" "${BUILDER_GID}" 0711 \
    'phase B slot'
  verify_lock "${PHASE_A_SLOT}/.build.lock"
  verify_lock "${PHASE_B_SLOT}/.build.lock"
  verify_installed_file "${BUILDER_DEST}" "${BUILDER_SOURCE_SHA256}" \
    "${BUILDER_SOURCE_SIZE}" 0444 'installed builder'
  verify_installed_file "${UNIT_ROOT}/${PHASE_A_UNIT}" "${PHASE_A_UNIT_SHA256}" \
    "${PHASE_A_UNIT_SIZE}" 0644 'installed phase A unit'
  verify_installed_file "${UNIT_ROOT}/${PHASE_B_UNIT}" "${PHASE_B_UNIT_SHA256}" \
    "${PHASE_B_UNIT_SIZE}" 0644 'installed phase B unit'
  assert_systemd_provenance 'true'
  assert_exact_inventory "${LIBEXEC_ROOT}" 'vista_r8_native_builder.py'
  assert_exact_inventory "${STATE_ROOT}" 'phase-a-slot' 'phase-b-slot'
}

assert_closed_phase_a() {
  assert_directory "${PHASE_A_FINAL}" "${BUILDER_UID}" "${BUILDER_GID}" 0555 \
    'closed phase A root'
  assert_exact_inventory "${PHASE_A_FINAL}" \
    'artifacts' 'manifest.json' 'manifests' 'parent-seal-candidate'
  assert_directory "${PHASE_A_FINAL}/artifacts" "${BUILDER_UID}" \
    "${BUILDER_GID}" 0555 'phase A artifacts'
  assert_exact_inventory "${PHASE_A_FINAL}/artifacts" \
    'transfer-r8-ue57-stage-installer' \
    'launch-vista-authority-parent-seal' \
    'bootstrap-r8-ue57-initial-authorities'
  assert_directory "${PHASE_A_FINAL}/manifests" "${BUILDER_UID}" \
    "${BUILDER_GID}" 0555 'phase A manifests'
  assert_exact_inventory "${PHASE_A_FINAL}/manifests" \
    'stage-transfer-launcher.json' \
    'parent-seal-launcher.json' \
    'initial-bootstrap-launcher.json'
  assert_directory "${PHASE_A_FINAL}/parent-seal-candidate" "${BUILDER_UID}" \
    "${BUILDER_GID}" 0555 'phase A parent-seal candidate'
  assert_exact_inventory "${PHASE_A_FINAL}/parent-seal-candidate" \
    'vista_authority_parent_seal.py' 'launch-vista-authority-parent-seal'
  local name
  for name in \
    'transfer-r8-ue57-stage-installer' \
    'launch-vista-authority-parent-seal' \
    'bootstrap-r8-ue57-initial-authorities'; do
    assert_closed_regular "${PHASE_A_FINAL}/artifacts/${name}" \
      "${BUILDER_UID}" "${BUILDER_GID}" 0555 "phase A artifact ${name}"
  done
  for name in \
    'stage-transfer-launcher.json' \
    'parent-seal-launcher.json' \
    'initial-bootstrap-launcher.json'; do
    assert_closed_regular "${PHASE_A_FINAL}/manifests/${name}" \
      "${BUILDER_UID}" "${BUILDER_GID}" 0444 "phase A manifest ${name}"
  done
  assert_closed_regular "${PHASE_A_FINAL}/parent-seal-candidate/vista_authority_parent_seal.py" \
    "${BUILDER_UID}" "${BUILDER_GID}" 0444 'phase A parent-seal helper'
  assert_closed_regular "${PHASE_A_FINAL}/parent-seal-candidate/launch-vista-authority-parent-seal" \
    "${BUILDER_UID}" "${BUILDER_GID}" 0555 'phase A parent-seal launcher'
  assert_closed_regular "${PHASE_A_FINAL}/manifest.json" \
    "${BUILDER_UID}" "${BUILDER_GID}" 0444 'phase A manifest'
  assert_exact_inventory "${PHASE_A_SLOT}" '.build.lock' 'published'
  assert_exact_inventory "${PHASE_B_SLOT}" '.build.lock'
}

verify_operation_close_state() {
  local operation="$1"
  verify_framework
  case "${operation}" in
    "${INSTALL_FRAMEWORK}")
      [[ "$#" -eq 8 ]] || fail 'terminal install-framework arguments differ'
      assert_exact_inventory "${INPUT_ROOT}"
      assert_exact_inventory "${PHASE_A_SLOT}" '.build.lock'
      assert_exact_inventory "${PHASE_B_SLOT}" '.build.lock'
      [[ ! -e "${PHASE_A_FINAL}" && ! -L "${PHASE_A_FINAL}" ]] || \
        fail 'terminal framework state unexpectedly contains phase A publication'
      [[ ! -e "${PHASE_B_FINAL}" && ! -L "${PHASE_B_FINAL}" ]] || \
        fail 'terminal framework state unexpectedly contains phase B publication'
      ;;
    "${INSTALL_PHASE_A}")
      [[ "$#" -eq 6 ]] || fail 'terminal install-phase-a arguments differ'
      assert_exact_inventory "${INPUT_ROOT}" 'source.bundle' 'phase-a-request.json'
      verify_installed_file "${BUNDLE_DEST}" "$2" "$3" 0444 \
        'terminal installed source bundle'
      verify_installed_file "${PHASE_A_REQUEST_DEST}" "$4" "$5" 0444 \
        'terminal installed phase A request'
      verify_held_file "${BUNDLE_FD}" 0 0 0400 "$2" "$3" \
        'terminal source bundle candidate'
      verify_held_file "${PHASE_A_REQUEST_FD}" 0 0 0400 "$4" "$5" \
        'terminal phase A request candidate'
      assert_exact_inventory "${PHASE_A_SLOT}" '.build.lock'
      assert_exact_inventory "${PHASE_B_SLOT}" '.build.lock'
      [[ ! -e "${PHASE_A_FINAL}" && ! -L "${PHASE_A_FINAL}" ]] || \
        fail 'terminal phase A input state already contains phase A publication'
      [[ ! -e "${PHASE_B_FINAL}" && ! -L "${PHASE_B_FINAL}" ]] || \
        fail 'terminal phase A input state unexpectedly contains phase B publication'
      ;;
    "${INSTALL_PHASE_B}")
      [[ "$#" -eq 4 ]] || fail 'terminal install-phase-b arguments differ'
      assert_exact_inventory "${INPUT_ROOT}" \
        'source.bundle' 'phase-a-request.json' 'phase-b-request.json'
      verify_installed_file "${BUNDLE_DEST}" \
        "${PHASE_B_EXISTING_BUNDLE_SHA256}" \
        "${PHASE_B_EXISTING_BUNDLE_SIZE}" 0444 \
        'terminal installed source bundle'
      verify_installed_file "${PHASE_A_REQUEST_DEST}" \
        "${PHASE_B_EXISTING_PHASE_A_SHA256}" \
        "${PHASE_B_EXISTING_PHASE_A_SIZE}" 0444 \
        'terminal installed phase A request'
      verify_installed_file "${PHASE_B_REQUEST_DEST}" "$2" "$3" 0444 \
        'terminal installed phase B request'
      verify_held_file "${BUNDLE_FD}" 0 0 0400 \
        "${PHASE_B_EXISTING_BUNDLE_SHA256}" \
        "${PHASE_B_EXISTING_BUNDLE_SIZE}" 'terminal source bundle candidate'
      verify_held_file "${PHASE_A_REQUEST_FD}" 0 0 0400 \
        "${PHASE_B_EXISTING_PHASE_A_SHA256}" \
        "${PHASE_B_EXISTING_PHASE_A_SIZE}" 'terminal phase A request candidate'
      verify_held_file "${PHASE_B_REQUEST_FD}" 0 0 0400 "$2" "$3" \
        'terminal phase B request candidate'
      assert_closed_phase_a
      assert_exact_inventory "${PHASE_B_SLOT}" '.build.lock'
      [[ ! -e "${PHASE_B_FINAL}" && ! -L "${PHASE_B_FINAL}" ]] || \
        fail 'terminal phase B input state already contains phase B publication'
      ;;
    *) fail 'terminal operation differs' ;;
  esac
}

assert_path_and_open_trusted_assets
IFS=' ' read -r SELF_SOURCE_SHA256 SELF_SOURCE_SIZE < <(
  observed_held_pin "${SELF_FD}" 0 0 0500 'trusted live bootstrap'
)
IFS=' ' read -r BUILDER_SOURCE_SHA256 BUILDER_SOURCE_SIZE < <(
  observed_held_pin "${BUILDER_FD}" 0 0 0400 'trusted builder source'
)
IFS=' ' read -r PHASE_A_UNIT_SHA256 PHASE_A_UNIT_SIZE < <(
  observed_held_pin "${PHASE_A_UNIT_FD}" 0 0 0400 'trusted phase A unit'
)
IFS=' ' read -r PHASE_B_UNIT_SHA256 PHASE_B_UNIT_SIZE < <(
  observed_held_pin "${PHASE_B_UNIT_FD}" 0 0 0400 'trusted phase B unit'
)
readonly SELF_SOURCE_SHA256 SELF_SOURCE_SIZE
readonly BUILDER_SOURCE_SHA256 BUILDER_SOURCE_SIZE
readonly PHASE_A_UNIT_SHA256 PHASE_A_UNIT_SIZE
readonly PHASE_B_UNIT_SHA256 PHASE_B_UNIT_SIZE

readonly OPERATION="${1:-}"
case "${OPERATION}" in
  "${INSTALL_FRAMEWORK}")
    [[ "$#" -eq 8 ]] || fail 'install-framework arguments differ'
    validate_pin_literal 'builder source' "$2" "$3"
    validate_pin_literal 'phase A unit source' "$4" "$5"
    validate_pin_literal 'phase B unit source' "$6" "$7"
    [[ "$8" == "${FRAMEWORK_ACK}" ]] || fail 'install-framework acknowledgement differs'
    verify_held_file "${BUILDER_FD}" 0 0 0400 "$2" "$3" 'builder source'
    verify_held_file "${PHASE_A_UNIT_FD}" 0 0 0400 "$4" "$5" 'phase A unit source'
    verify_held_file "${PHASE_B_UNIT_FD}" 0 0 0400 "$6" "$7" 'phase B unit source'
    assert_services_quiescent
    assert_builder_identity_unused
    validate_group 'true'
    validate_user 'true'
    ensure_directory "${LIBEXEC_ROOT}" root root 0555 0 0
    ensure_directory "${INPUT_ROOT}" root root 0555 0 0
    ensure_directory "${STATE_ROOT}" root root 0555 0 0
    ensure_directory "${PHASE_A_SLOT}" "${BUILDER_NAME}" "${BUILDER_NAME}" 0711 \
      "${BUILDER_UID}" "${BUILDER_GID}"
    ensure_directory "${PHASE_B_SLOT}" "${BUILDER_NAME}" "${BUILDER_NAME}" 0711 \
      "${BUILDER_UID}" "${BUILDER_GID}"
    create_lock_once "${PHASE_A_SLOT}/.build.lock"
    create_lock_once "${PHASE_B_SLOT}/.build.lock"
    install_held_once "${BUILDER_FD}" "${BUILDER_DEST}" "$2" "$3" 0444 \
      'installed builder'
    install_held_once "${PHASE_A_UNIT_FD}" "${UNIT_ROOT}/${PHASE_A_UNIT}" "$4" "$5" \
      0644 'installed phase A unit'
    install_held_once "${PHASE_B_UNIT_FD}" "${UNIT_ROOT}/${PHASE_B_UNIT}" "$6" "$7" \
      0644 'installed phase B unit'
    assert_exact_inventory "${INPUT_ROOT}"
    assert_exact_inventory "${PHASE_A_SLOT}" '.build.lock'
    assert_exact_inventory "${PHASE_B_SLOT}" '.build.lock'
    verify_framework
    ;;
  "${INSTALL_PHASE_A}")
    [[ "$#" -eq 6 ]] || fail 'install-phase-a-inputs arguments differ'
    validate_pin_literal 'source bundle' "$2" "$3"
    validate_pin_literal 'phase A request' "$4" "$5"
    [[ "$6" == "${PHASE_A_ACK}" ]] || fail 'install-phase-a acknowledgement differs'
    assert_directory "${INPUT_CANDIDATE_ROOT}" 0 0 0700 'bootstrap input root'
    assert_exact_inventory "${INPUT_CANDIDATE_ROOT}" \
      'source.bundle' 'phase-a-request.json'
    [[ ! -L "${CANDIDATE_BUNDLE}" && ! -L "${CANDIDATE_PHASE_A_REQUEST}" ]] || \
      fail 'phase A input candidate symlink is forbidden'
    exec {BUNDLE_FD}<"${CANDIDATE_BUNDLE}"
    exec {PHASE_A_REQUEST_FD}<"${CANDIDATE_PHASE_A_REQUEST}"
    readonly BUNDLE_FD PHASE_A_REQUEST_FD
    verify_held_file "${BUNDLE_FD}" 0 0 0400 "$2" "$3" 'source bundle candidate'
    verify_held_file "${PHASE_A_REQUEST_FD}" 0 0 0400 "$4" "$5" \
      'phase A request candidate'
    assert_services_quiescent
    assert_builder_identity_unused
    verify_framework
    assert_exact_inventory "${PHASE_A_SLOT}" '.build.lock'
    assert_exact_inventory "${PHASE_B_SLOT}" '.build.lock'
    [[ ! -e "${PHASE_A_FINAL}" && ! -L "${PHASE_A_FINAL}" ]] || \
      fail 'phase A is already published'
    [[ ! -e "${PHASE_B_FINAL}" && ! -L "${PHASE_B_FINAL}" ]] || \
      fail 'phase B is already published'
    if [[ -e "${BUNDLE_DEST}" || -L "${BUNDLE_DEST}" ]]; then
      assert_inventory_is_one_of "${INPUT_ROOT}" 'source.bundle' 'phase-a-request.json'
    else
      assert_exact_inventory "${INPUT_ROOT}"
    fi
    install_held_once "${BUNDLE_FD}" "${BUNDLE_DEST}" "$2" "$3" 0444 \
      'installed source bundle'
    install_held_once "${PHASE_A_REQUEST_FD}" "${PHASE_A_REQUEST_DEST}" "$4" "$5" \
      0444 'installed phase A request'
    assert_exact_inventory "${INPUT_ROOT}" 'source.bundle' 'phase-a-request.json'
    verify_held_file "${BUNDLE_FD}" 0 0 0400 "$2" "$3" 'source bundle candidate'
    verify_held_file "${PHASE_A_REQUEST_FD}" 0 0 0400 "$4" "$5" \
      'phase A request candidate'
    ;;
  "${INSTALL_PHASE_B}")
    [[ "$#" -eq 4 ]] || fail 'install-phase-b-request arguments differ'
    validate_pin_literal 'phase B request' "$2" "$3"
    [[ "$4" == "${PHASE_B_ACK}" ]] || fail 'install-phase-b acknowledgement differs'
    assert_directory "${INPUT_CANDIDATE_ROOT}" 0 0 0700 'bootstrap input root'
    assert_exact_inventory "${INPUT_CANDIDATE_ROOT}" \
      'source.bundle' 'phase-a-request.json' 'phase-b-request.json'
    [[ ! -L "${CANDIDATE_BUNDLE}" && \
      ! -L "${CANDIDATE_PHASE_A_REQUEST}" && \
      ! -L "${CANDIDATE_PHASE_B_REQUEST}" ]] || \
      fail 'phase B input candidate symlink is forbidden'
    exec {BUNDLE_FD}<"${CANDIDATE_BUNDLE}"
    exec {PHASE_A_REQUEST_FD}<"${CANDIDATE_PHASE_A_REQUEST}"
    exec {PHASE_B_REQUEST_FD}<"${CANDIDATE_PHASE_B_REQUEST}"
    readonly BUNDLE_FD PHASE_A_REQUEST_FD PHASE_B_REQUEST_FD
    IFS=' ' read -r PHASE_B_EXISTING_BUNDLE_SHA256 \
      PHASE_B_EXISTING_BUNDLE_SIZE < <(
        observed_held_pin "${BUNDLE_FD}" 0 0 0400 'source bundle candidate'
      )
    IFS=' ' read -r PHASE_B_EXISTING_PHASE_A_SHA256 \
      PHASE_B_EXISTING_PHASE_A_SIZE < <(
        observed_held_pin "${PHASE_A_REQUEST_FD}" 0 0 0400 \
          'phase A request candidate'
      )
    readonly PHASE_B_EXISTING_BUNDLE_SHA256 PHASE_B_EXISTING_BUNDLE_SIZE
    readonly PHASE_B_EXISTING_PHASE_A_SHA256 PHASE_B_EXISTING_PHASE_A_SIZE
    verify_held_file "${PHASE_B_REQUEST_FD}" 0 0 0400 "$2" "$3" \
      'phase B request candidate'
    assert_services_quiescent
    assert_builder_identity_unused
    verify_framework
    assert_closed_phase_a
    assert_exact_inventory "${INPUT_ROOT}" 'source.bundle' 'phase-a-request.json'
    install_held_once "${PHASE_B_REQUEST_FD}" "${PHASE_B_REQUEST_DEST}" "$2" "$3" \
      0444 'installed phase B request'
    assert_exact_inventory "${INPUT_ROOT}" \
      'source.bundle' 'phase-a-request.json' 'phase-b-request.json'
    verify_held_file "${PHASE_B_REQUEST_FD}" 0 0 0400 "$2" "$3" \
      'phase B request candidate'
    ;;
  *) fail 'operation must be install-framework, install-phase-a-inputs, or install-phase-b-request' ;;
esac

assert_services_quiescent
assert_systemd_provenance 'true'
assert_builder_identity_unused
verify_held_file "${SELF_FD}" 0 0 0500 "${SELF_SOURCE_SHA256}" \
  "${SELF_SOURCE_SIZE}" 'trusted live bootstrap'
verify_held_file "${BUILDER_FD}" 0 0 0400 "${BUILDER_SOURCE_SHA256}" \
  "${BUILDER_SOURCE_SIZE}" 'trusted builder source'
verify_held_file "${PHASE_A_UNIT_FD}" 0 0 0400 "${PHASE_A_UNIT_SHA256}" \
  "${PHASE_A_UNIT_SIZE}" 'trusted phase A unit'
verify_held_file "${PHASE_B_UNIT_FD}" 0 0 0400 "${PHASE_B_UNIT_SHA256}" \
  "${PHASE_B_UNIT_SIZE}" 'trusted phase B unit'
verify_operation_close_state "$@"

printf '%s\n' "${OPERATION} complete; systemd was not reloaded, enabled, or started"
