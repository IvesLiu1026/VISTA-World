#!/usr/bin/env bash
# Fresh, append-only preparation ceremony for the fixed VISTA R8 R2 builder.
#
# Install this reviewed file as /root/prepare_vista_r8_native_builder_r2.sh
# (root:root, 0500, one hard link) before invoking it.  It deliberately has no
# arguments and no reconciliation mode: every R2 destination must be absent.

set -euo pipefail
umask 077
IFS=$'\n\t'
export LC_ALL=C LANG=C PATH=/usr/sbin:/usr/bin:/sbin:/bin
unset BASH_ENV ENV CDPATH GLOBIGNORE PYTHONHOME PYTHONPATH

readonly LIVE_SELF='/root/prepare_vista_r8_native_builder_r2.sh'
readonly RUN_ROOT='/data/sysx/vista-world/runs/vista-action-world-r1/vista-r8-native-builder-r2-83f180e0-20260831a'
readonly REVIEWED_ROOT="${RUN_ROOT}/reviewed-sources"
readonly REVIEWED_SYSTEMD="${REVIEWED_ROOT}/systemd"
readonly REVIEWED_BOOTSTRAP="${REVIEWED_ROOT}/bootstrap_vista_r8_native_builder_r2.sh"
readonly REVIEWED_BUILDER="${REVIEWED_ROOT}/vista_r8_native_builder.py"
readonly REVIEWED_PHASE_A="${REVIEWED_SYSTEMD}/vista-r8-native-builder-r2-phase-a.service"
readonly REVIEWED_PHASE_B="${REVIEWED_SYSTEMD}/vista-r8-native-builder-r2-phase-b.service"
readonly REVIEWED_BUNDLE="${RUN_ROOT}/source.bundle"
readonly REVIEWED_REQUEST="${RUN_ROOT}/phase-a-request.json"
readonly REVIEWED_INPUT_SET="${RUN_ROOT}/input-set.json"

readonly COMMIT='83f180e03935bcc7994962ec95f2d8c8027f405d'
readonly BUNDLE_REF='refs/heads/codex/vista-r8-fresh-namespace-r2'
readonly CANDIDATE_UID='1000021'
readonly CANDIDATE_GID='1000001'
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
readonly INPUT_SET_SHA256='bd82c3b8899eb71835a60dbc34b13b3dc0a8d0f8ea904c68be253b9d4444da37'
readonly INPUT_SET_BYTES='1829'

readonly TRUSTED_ROOT='/root/vista-r8-native-builder-bootstrap-r2'
readonly TRUSTED_SYSTEMD="${TRUSTED_ROOT}/systemd"
readonly TRUSTED_BOOTSTRAP="${TRUSTED_ROOT}/bootstrap_vista_r8_native_builder_r2.sh"
readonly TRUSTED_BUILDER="${TRUSTED_ROOT}/vista_r8_native_builder.py"
readonly TRUSTED_PHASE_A="${TRUSTED_SYSTEMD}/vista-r8-native-builder-r2-phase-a.service"
readonly TRUSTED_PHASE_B="${TRUSTED_SYSTEMD}/vista-r8-native-builder-r2-phase-b.service"
readonly GLOBAL_LOCK="${TRUSTED_ROOT}/.bootstrap.lock"
readonly INPUT_CANDIDATE_ROOT='/root/vista-r8-native-builder-bootstrap-input-r2'
readonly LIBEXEC_ROOT='/usr/local/libexec/vista-r8-native-builder-r2'
readonly INPUT_ROOT='/etc/vista-r8-native-builder-r2'
readonly STATE_ROOT='/var/lib/vista-r8-native-builder-r2'
readonly PHASE_A_UNIT='vista-r8-native-builder-r2-phase-a.service'
readonly PHASE_B_UNIT='vista-r8-native-builder-r2-phase-b.service'
readonly PHASE_A_DEST="/etc/systemd/system/${PHASE_A_UNIT}"
readonly PHASE_B_DEST="/etc/systemd/system/${PHASE_B_UNIT}"
readonly TRUSTED_STAGING='/root/.vista-r8-native-builder-bootstrap-r2.83f180e0-20260831a.staging'
readonly INPUT_STAGING='/root/.vista-r8-native-builder-bootstrap-input-r2.83f180e0-20260831a.staging'
readonly ACTIVATION_RECEIPT='/root/vista-r8-native-builder-r2-phase-a-receipt-83f180e0-20260831a'
readonly ACTIVATION_STAGING='/root/.vista-r8-native-builder-r2-phase-a-receipt-83f180e0-20260831a.staging'
readonly OUTER_LOCK='/run/lock/vista-r8-native-builder-r2-prepare-83f180e0-20260831a.lock.d'

readonly FRAMEWORK_ACK='I acknowledge installation or exact reconciliation of the fixed inactive VISTA R8 native-builder framework without starting a service or build.'
readonly PHASE_A_ACK='I acknowledge fresh append or exact reconciliation of the reviewed VISTA R8 native-builder source bundle and phase A request without starting a build.'
readonly EXPECTED_TRUSTED_INVENTORY=$'.bootstrap.lock\nbootstrap_vista_r8_native_builder_r2.sh\nsystemd\nsystemd/vista-r8-native-builder-r2-phase-a.service\nsystemd/vista-r8-native-builder-r2-phase-b.service\nvista_r8_native_builder.py'
readonly EXPECTED_INPUT_INVENTORY=$'phase-a-request.json\nsource.bundle'

readonly R1_BUILDER='/usr/local/libexec/vista-r8-native-builder-r1/vista_r8_native_builder.py'
readonly R1_INPUT_ROOT='/etc/vista-r8-native-builder-r1'
readonly R1_STATE_ROOT='/var/lib/vista-r8-native-builder-r1'
readonly R1_PHASE_A='vista-r8-native-builder-phase-a.service'
readonly R1_PHASE_B='vista-r8-native-builder-phase-b.service'
readonly R1_BUILDER_SHA256='9b6c4b587456de26e9c20560d5eb62d09982e73e1e6cb9493dbf663b521fa441'
readonly R1_BUILDER_BYTES='211353'
readonly R1_PHASE_A_SHA256='f3acaf39ad92fe2bc70680c9f7e0d8ab1e1f68f68553ebd4a74137c0cf939520'
readonly R1_PHASE_A_BYTES='1858'
readonly R1_PHASE_B_SHA256='1e65b23e2ae857b88d3b488a63cfcba3d6462c265ff3b4d3b33da046b9f96035'
readonly R1_PHASE_B_BYTES='2143'
readonly R1_BUNDLE_SHA256='abd3c562ad5b975919aab3a6b0420f5326bd802774dda6e74a0db99d78b95387'
readonly R1_BUNDLE_BYTES='3329251'
readonly R1_REQUEST_SHA256='b5ce8dc8b558ee62f92247c97a5daa169ec83e3864fa388f6088aad3aa3a904f'
readonly R1_REQUEST_BYTES='2483604'

readonly -a SYSTEMD_UNIT_SEARCH_ROOTS=(
  '/etc/systemd/system.control' '/run/systemd/system.control'
  '/run/systemd/transient' '/run/systemd/generator.early'
  '/etc/systemd/system' '/etc/systemd/system.attached'
  '/run/systemd/system' '/run/systemd/system.attached'
  '/run/systemd/generator' '/usr/local/lib/systemd/system'
  '/usr/lib/systemd/system' '/lib/systemd/system'
  '/run/systemd/generator.late'
)
readonly -a SYSTEMD_DROPIN_NAMES=(
  'vista-.service.d' 'vista-r8-.service.d' 'vista-r8-native-.service.d'
  'vista-r8-native-builder-.service.d' 'vista-r8-native-builder-r2-.service.d'
  'vista-r8-native-builder-r2-phase-.service.d' 'service.d'
)

fail() { printf '%s\n' "VISTA R8 R2 prepare ceremony: $*" >&2; exit 126; }
sha256_of() { /usr/bin/sha256sum -- "$1" | /usr/bin/cut -d' ' -f1; }
held_path() { printf '/proc/%s/fd/%s' "$$" "$1"; }

FINAL_R2_PATH_PUBLISHED='false'
OUTER_LOCK_OWNED='false'
TRUSTED_STAGING_OWNED='false'
INPUT_STAGING_OWNED='false'
LIST_SEQUENCE='0'
cleanup() {
  local status="$?"
  if [[ "${FINAL_R2_PATH_PUBLISHED}" == 'false' ]]; then
    if [[ "${OUTER_LOCK_OWNED}" == 'true' && -n "${LIST_PATH:-}" && \
      -f "${LIST_PATH}" && ! -L "${LIST_PATH}" ]]; then
      /usr/bin/rm -f -- "${LIST_PATH}" || status=125
    fi
    [[ "${TRUSTED_STAGING_OWNED}" != 'true' || \
      ( ! -e "${TRUSTED_STAGING}" && ! -L "${TRUSTED_STAGING}" ) ]] || \
      /usr/bin/rm -rf --one-file-system -- "${TRUSTED_STAGING}"
    [[ "${INPUT_STAGING_OWNED}" != 'true' || \
      ( ! -e "${INPUT_STAGING}" && ! -L "${INPUT_STAGING}" ) ]] || \
      /usr/bin/rm -rf --one-file-system -- "${INPUT_STAGING}"
    if [[ "${OUTER_LOCK_OWNED}" == 'true' && -d "${OUTER_LOCK}" && ! -L "${OUTER_LOCK}" ]]; then
      /usr/bin/rmdir -- "${OUTER_LOCK}" 2>/dev/null || true
    fi
  fi
  exit "${status}"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

fresh_list() {
  LIST_SEQUENCE="$((LIST_SEQUENCE + 1))"
  LIST_PATH="${OUTER_LOCK}/traversal-${LIST_SEQUENCE}.nul"
  [[ ! -e "${LIST_PATH}" && ! -L "${LIST_PATH}" ]] || fail "traversal list exists: ${LIST_PATH}"
  ( set -o noclobber; : >"${LIST_PATH}" ) 2>/dev/null || fail "cannot create traversal list: ${LIST_PATH}"
  [[ -f "${LIST_PATH}" && ! -L "${LIST_PATH}" ]] || fail "traversal list differs: ${LIST_PATH}"
}

assert_absent() {
  local path="$1"
  [[ ! -e "${path}" && ! -L "${path}" ]] || fail "fresh path exists: ${path}"
}

assert_directory() {
  local path="$1" mode="$2" uid="$3" gid="$4"
  [[ -d "${path}" && ! -L "${path}" ]] || fail "directory differs: ${path}"
  [[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g' -- "${path}")" == \
    "directory|${mode}|${uid}|${gid}" ]] || fail "directory metadata differs: ${path}"
}

assert_file() {
  local path="$1" mode="$2" uid="$3" gid="$4" sha="$5" size="$6"
  [[ -f "${path}" && ! -L "${path}" ]] || fail "file differs: ${path}"
  [[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h|%s' -- "${path}")" == \
    "regular file|${mode}|${uid}|${gid}|1|${size}" ]] || fail "file metadata differs: ${path}"
  [[ "$(sha256_of "${path}")" == "${sha}" ]] || fail "file pin differs: ${path}"
}

assert_inventory() {
  local root="$1" expected="$2" observed
  observed="$(/usr/bin/find "${root}" -mindepth 1 -printf '%P\n' | /usr/bin/sort)" || fail "cannot inventory ${root}"
  [[ "${observed}" == "${expected}" ]] || fail "inventory differs: ${root}"
}

verify_candidate_fd() {
  local fd="$1" path="$2" sha="$3" size="$4" path_id held_id held_metadata
  assert_file "${path}" 444 "${CANDIDATE_UID}" "${CANDIDATE_GID}" "${sha}" "${size}"
  path_id="$(/usr/bin/stat -Lc '%d:%i' -- "${path}")"
  held_id="$(/usr/bin/stat -Lc '%d:%i' -- "$(held_path "${fd}")")"
  [[ "${path_id}" == "${held_id}" ]] || fail "candidate FD identity differs: ${path}"
  held_metadata="$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h|%s' -- "$(held_path "${fd}")")"
  [[ "${held_metadata}" == "regular file|444|${CANDIDATE_UID}|${CANDIDATE_GID}|1|${size}" ]] || \
    fail "held candidate metadata differs: ${path}"
  [[ "$(sha256_of "$(held_path "${fd}")")" == "${sha}" ]] || \
    fail "held candidate pin differs: ${path}"
  printf '%s' "${held_id}"
}

verify_live_self() {
  local path_id held_id held_metadata
  [[ -f "${LIVE_SELF}" && ! -L "${LIVE_SELF}" ]] || fail 'live prepare path differs'
  path_id="$(/usr/bin/stat -Lc '%d:%i' -- "${LIVE_SELF}")"
  held_id="$(/usr/bin/stat -Lc '%d:%i' -- "$(held_path 8)")"
  [[ "${path_id}" == "${held_id}" && "${path_id}" == "${LIVE_SELF_ID}" ]] || \
    fail 'live prepare identity changed'
  held_metadata="$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h|%s' -- "$(held_path 8)")"
  [[ "${held_metadata}" == "regular file|500|0|0|1|${LIVE_SELF_BYTES}" ]] || \
    fail 'held live prepare metadata differs'
  [[ "$(sha256_of "$(held_path 8)")" == "${LIVE_SELF_SHA256}" ]] || \
    fail 'live prepare bytes changed'
}

assert_r1_file_state() {
  assert_file "${R1_BUILDER}" 444 0 0 "${R1_BUILDER_SHA256}" "${R1_BUILDER_BYTES}"
  assert_file "/etc/systemd/system/${R1_PHASE_A}" 644 0 0 "${R1_PHASE_A_SHA256}" "${R1_PHASE_A_BYTES}"
  assert_file "/etc/systemd/system/${R1_PHASE_B}" 644 0 0 "${R1_PHASE_B_SHA256}" "${R1_PHASE_B_BYTES}"
  assert_file "${R1_INPUT_ROOT}/source.bundle" 444 0 0 "${R1_BUNDLE_SHA256}" "${R1_BUNDLE_BYTES}"
  assert_file "${R1_INPUT_ROOT}/phase-a-request.json" 444 0 0 "${R1_REQUEST_SHA256}" "${R1_REQUEST_BYTES}"
  assert_directory "${R1_STATE_ROOT}" 555 0 0
  assert_directory "${R1_STATE_ROOT}/phase-a-slot" 711 997 997
  assert_directory "${R1_STATE_ROOT}/phase-b-slot" 711 997 997
  [[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h|%s' -- "${R1_STATE_ROOT}/phase-a-slot/.build.lock")" == \
    'regular empty file|600|997|997|1|0' ]] || fail 'R1 Phase A lock differs'
  [[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h|%s' -- "${R1_STATE_ROOT}/phase-b-slot/.build.lock")" == \
    'regular empty file|600|997|997|1|0' ]] || fail 'R1 Phase B lock differs'
  assert_inventory "${R1_STATE_ROOT}" $'phase-a-slot\nphase-a-slot/.build.lock\nphase-b-slot\nphase-b-slot/.build.lock'
}

manager_document() {
  /usr/bin/systemctl show --no-pager \
    -p Id -p Names -p LoadState -p ActiveState -p SubState -p FragmentPath \
    -p DropInPaths -p UnitFileState -p WantedBy -p RequiredBy -p Job \
    -p ProcSubset -p NeedDaemonReload -p NRestarts -p MainPID -p ControlPID \
    -p Result -p ConditionResult -p ExecMainCode -p ExecMainStatus \
    -p ExecMainStartTimestampMonotonic -p ExecMainExitTimestampMonotonic \
    -p InvocationID -- "$1"
}

property() {
  local document="$1" key="$2" value count
  if ! count="$(/usr/bin/awk -F= -v key="${key}" '$1 == key {n++} END {print n+0}' <<<"${document}")"; then
    printf '%s' "__VISTA_INVALID_PROPERTY_${key}__"
    return 126
  fi
  if [[ "${count}" != 1 ]]; then
    printf '%s' "__VISTA_INVALID_PROPERTY_${key}__"
    return 126
  fi
  if ! value="$(/usr/bin/awk -F= -v key="${key}" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' <<<"${document}")"; then
    printf '%s' "__VISTA_INVALID_PROPERTY_${key}__"
    return 126
  fi
  printf '%s' "${value}"
}

assert_r1_manager_vector() {
  local a b
  a="$(manager_document "${R1_PHASE_A}")"; b="$(manager_document "${R1_PHASE_B}")"
  [[ "$(property "${a}" Id)|$(property "${a}" Names)|$(property "${a}" LoadState)|$(property "${a}" ActiveState)|$(property "${a}" SubState)" == \
    "${R1_PHASE_A}|${R1_PHASE_A}|loaded|failed|failed" ]] || fail 'R1 Phase A state vector differs'
  [[ "$(property "${a}" FragmentPath)|$(property "${a}" DropInPaths)|$(property "${a}" UnitFileState)|$(property "${a}" WantedBy)|$(property "${a}" RequiredBy)|$(property "${a}" Job)" == \
    "/etc/systemd/system/${R1_PHASE_A}||static|||" ]] || fail 'R1 Phase A provenance differs'
  [[ "$(property "${a}" ProcSubset)|$(property "${a}" NeedDaemonReload)|$(property "${a}" NRestarts)|$(property "${a}" MainPID)|$(property "${a}" ControlPID)" == \
    'all|no|0|0|0' ]] || fail 'R1 Phase A quiescence differs'
  [[ "$(property "${a}" Result)|$(property "${a}" ConditionResult)|$(property "${a}" ExecMainCode)|$(property "${a}" ExecMainStatus)" == \
    'exit-code|yes|1|2' ]] || fail 'R1 Phase A failure result differs'
  [[ "$(property "${a}" ExecMainStartTimestampMonotonic)|$(property "${a}" ExecMainExitTimestampMonotonic)|$(property "${a}" InvocationID)" == \
    '675339972529|675341234136|81d481f1eb764c60a737835b867fcb63' ]] || fail 'R1 Phase A execution identity differs'
  [[ "$(property "${b}" Id)|$(property "${b}" Names)|$(property "${b}" LoadState)|$(property "${b}" ActiveState)|$(property "${b}" SubState)" == \
    "${R1_PHASE_B}|${R1_PHASE_B}|loaded|inactive|dead" ]] || fail 'R1 Phase B state vector differs'
  [[ "$(property "${b}" FragmentPath)|$(property "${b}" DropInPaths)|$(property "${b}" UnitFileState)|$(property "${b}" WantedBy)|$(property "${b}" RequiredBy)|$(property "${b}" Job)" == \
    "/etc/systemd/system/${R1_PHASE_B}||static|||" ]] || fail 'R1 Phase B provenance differs'
  [[ "$(property "${b}" ProcSubset)|$(property "${b}" NeedDaemonReload)|$(property "${b}" NRestarts)|$(property "${b}" MainPID)|$(property "${b}" ControlPID)" == \
    'all|no|0|0|0' ]] || fail 'R1 Phase B quiescence differs'
  [[ "$(property "${b}" Result)|$(property "${b}" ConditionResult)|$(property "${b}" ExecMainCode)|$(property "${b}" ExecMainStatus)|$(property "${b}" ExecMainStartTimestampMonotonic)|$(property "${b}" ExecMainExitTimestampMonotonic)|$(property "${b}" InvocationID)" == \
    'success|no|0|0|0|0|' ]] || fail 'R1 Phase B never-started vector differs'
}

assert_fresh_unit_namespace() {
  local unit root candidate dropin link raw_target dependency doc list
  for unit in "${PHASE_A_UNIT}" "${PHASE_B_UNIT}"; do
    doc="$(manager_document "${unit}")"
    [[ "$(property "${doc}" LoadState)|$(property "${doc}" ActiveState)|$(property "${doc}" SubState)|$(property "${doc}" FragmentPath)|$(property "${doc}" DropInPaths)|$(property "${doc}" UnitFileState)|$(property "${doc}" WantedBy)|$(property "${doc}" RequiredBy)|$(property "${doc}" Job)|$(property "${doc}" MainPID)|$(property "${doc}" ControlPID)|$(property "${doc}" ExecMainStartTimestampMonotonic)|$(property "${doc}" ExecMainExitTimestampMonotonic)" == \
      'not-found|inactive|dead|||||||0|0|0|0' ]] || fail "R2 manager namespace is not fresh: ${unit}"
    assert_absent "/sys/fs/cgroup/system.slice/${unit}"
    for root in "${SYSTEMD_UNIT_SEARCH_ROOTS[@]}"; do
      [[ -e "${root}" || -L "${root}" ]] || continue
      [[ -d "${root}" && ! -L "${root}" ]] || fail "systemd search root differs: ${root}"
      candidate="${root}/${unit}"
      assert_absent "${candidate}"
      for dropin in "${unit}.d" "${SYSTEMD_DROPIN_NAMES[@]}"; do
        assert_absent "${root}/${dropin}"
      done
      fresh_list
      list="${LIST_PATH}"
      /usr/bin/find -H "${root}" -mindepth 1 -type l -print0 >"${list}" || \
        fail "cannot enumerate systemd aliases: ${root}"
      while IFS= read -r -d '' link; do
        raw_target="$(/usr/bin/readlink -- "${link}")" || fail "cannot inspect alias: ${link}"
        [[ "${link##*/}" != "${unit}" && "${raw_target}" != "${unit}" && "${raw_target}" != */"${unit}" ]] || \
          fail "systemd alias targets fresh R2 unit: ${link}"
      done <"${list}"
      /usr/bin/rm -f -- "${list}"
      fresh_list
      list="${LIST_PATH}"
      /usr/bin/find -H "${root}" -mindepth 2 \
        \( -path "*.wants/${unit}" -o -path "*.requires/${unit}" \) -print0 >"${list}" || \
        fail "cannot enumerate systemd dependencies: ${root}"
      while IFS= read -r -d '' dependency; do
        fail "systemd dependency targets fresh R2 unit: ${dependency}"
      done <"${list}"
      /usr/bin/rm -f -- "${list}"
    done
  done
}

assert_fresh_r2() {
  local path
  for path in "${TRUSTED_ROOT}" "${INPUT_CANDIDATE_ROOT}" "${LIBEXEC_ROOT}" \
    "${INPUT_ROOT}" "${STATE_ROOT}" "${PHASE_A_DEST}" "${PHASE_B_DEST}" \
    "${TRUSTED_STAGING}" "${INPUT_STAGING}" "${ACTIVATION_RECEIPT}" \
    "${ACTIVATION_STAGING}"; do
    assert_absent "${path}"
  done
  assert_fresh_unit_namespace
}

validate_input_documents() {
  local bundle_heads
  bundle_heads="$(/usr/bin/git bundle list-heads "$(held_path 14)")" || fail 'cannot list reviewed bundle heads'
  [[ "${bundle_heads}" == "${COMMIT} ${BUNDLE_REF}" ]] || fail 'source bundle commit/ref inventory differs'
  /usr/bin/python3.10 -I -B - "$(held_path 15)" "$(held_path 16)" <<'PY'
import hashlib, json, pathlib, sys

request = json.loads(pathlib.Path(sys.argv[1]).read_bytes())
input_set = json.loads(pathlib.Path(sys.argv[2]).read_bytes())
expected_commit = "83f180e03935bcc7994962ec95f2d8c8027f405d"
expected_bundle = {"sha256": "54ba5e0ae512fa9661ccec04ee245de6510d343ae21445f8f169b239fd557533", "size_bytes": 3301129}
expected_request = {"sha256": "fb8e99428b4e7cb043c96591f73d413500834667f263eeec3f3c70af66f318e0", "size_bytes": 2483438}
if request.get("schema") != "vista.r8-native-builder-request/v2" or request.get("phase") != "phase-a": raise SystemExit(2)
if request.get("source_commit") != expected_commit: raise SystemExit(2)
if request.get("trace_contract", {}).get("schema") != "vista.r8-native-builder-trace-contract/v5": raise SystemExit(2)
if request.get("source_bundle", {}).get("pin") != expected_bundle: raise SystemExit(2)
if request.get("source_bundle", {}).get("path") != "/etc/vista-r8-native-builder-r2/source.bundle": raise SystemExit(2)
if request.get("builder", {}).get("path") != "/usr/local/libexec/vista-r8-native-builder-r2/vista_r8_native_builder.py": raise SystemExit(2)
if request.get("builder", {}).get("service_unit", {}).get("path") != "/etc/systemd/system/vista-r8-native-builder-r2-phase-a.service": raise SystemExit(2)
claims = request.get("claims", {})
if claims.get("network_access") is not False or claims.get("production_native_output") is not False: raise SystemExit(2)
if claims.get("write_root") != "/var/lib/vista-r8-native-builder-r2": raise SystemExit(2)
projected = dict(request); observed = projected.pop("content_digest", None)
canonical = json.dumps(projected, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n"
if observed != hashlib.sha256(canonical).hexdigest(): raise SystemExit(2)
policies = []
for record in request["trace_contract"].get("host_files", []):
    for item in record.get("component_chain", []):
        if "metadata_policy" in item: policies.append((record.get("path"), item.get("path"), item["metadata_policy"]))
expected_paths = ["/proc", "/proc/sys", "/proc/sys/vm", "/proc/sys/vm/overcommit_memory"]
if policies != [("/proc/sys/vm/overcommit_memory", path, "proc-chain-mount-metadata-volatile-v2") for path in expected_paths]: raise SystemExit(2)
if input_set.get("schema") != "vista.r8-native-builder-r2-input-set/v1": raise SystemExit(2)
if input_set.get("source_commit") != expected_commit: raise SystemExit(2)
raw = pathlib.Path(sys.argv[1]).read_bytes()
if {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)} != expected_request: raise SystemExit(2)
PY
}

verify_trusted_tree() {
  assert_directory "${TRUSTED_ROOT}" 555 0 0
  assert_directory "${TRUSTED_SYSTEMD}" 555 0 0
  assert_inventory "${TRUSTED_ROOT}" "${EXPECTED_TRUSTED_INVENTORY}"
  assert_file "${TRUSTED_BOOTSTRAP}" 500 0 0 "${BOOTSTRAP_SHA256}" "${BOOTSTRAP_BYTES}"
  assert_file "${TRUSTED_BUILDER}" 400 0 0 "${BUILDER_SHA256}" "${BUILDER_BYTES}"
  assert_file "${TRUSTED_PHASE_A}" 400 0 0 "${PHASE_A_SHA256}" "${PHASE_A_BYTES}"
  assert_file "${TRUSTED_PHASE_B}" 400 0 0 "${PHASE_B_SHA256}" "${PHASE_B_BYTES}"
  [[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h|%s' -- "${GLOBAL_LOCK}")" == \
    'regular empty file|600|0|0|1|0' ]] || fail 'global lock differs'
}

verify_held_global_lock() {
  [[ "$(/usr/bin/stat -Lc '%d:%i' -- "${GLOBAL_LOCK}")" == \
    "$(/usr/bin/stat -Lc '%d:%i' -- "$(held_path "${GLOBAL_LOCK_FD}")")" ]] || \
    fail 'held global lock identity differs'
  [[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h|%s' -- "$(held_path "${GLOBAL_LOCK_FD}")")" == \
    'regular empty file|600|0|0|1|0' ]] || fail 'held global lock metadata differs'
}

verify_input_tree() {
  assert_directory "${INPUT_CANDIDATE_ROOT}" 700 0 0
  assert_inventory "${INPUT_CANDIDATE_ROOT}" "${EXPECTED_INPUT_INVENTORY}"
  assert_file "${INPUT_CANDIDATE_ROOT}/source.bundle" 400 0 0 "${BUNDLE_SHA256}" "${BUNDLE_BYTES}"
  assert_file "${INPUT_CANDIDATE_ROOT}/phase-a-request.json" 400 0 0 "${REQUEST_SHA256}" "${REQUEST_BYTES}"
}

verify_installed_framework() {
  assert_directory "${LIBEXEC_ROOT}" 555 0 0
  assert_directory "${INPUT_ROOT}" 555 0 0
  assert_directory "${STATE_ROOT}" 555 0 0
  assert_directory "${STATE_ROOT}/phase-a-slot" 711 997 997
  assert_directory "${STATE_ROOT}/phase-b-slot" 711 997 997
  assert_inventory "${LIBEXEC_ROOT}" 'vista_r8_native_builder.py'
  assert_inventory "${INPUT_ROOT}" "${EXPECTED_INPUT_INVENTORY}"
  assert_inventory "${STATE_ROOT}" $'phase-a-slot\nphase-a-slot/.build.lock\nphase-b-slot\nphase-b-slot/.build.lock'
  assert_file "${LIBEXEC_ROOT}/vista_r8_native_builder.py" 444 0 0 "${BUILDER_SHA256}" "${BUILDER_BYTES}"
  assert_file "${PHASE_A_DEST}" 644 0 0 "${PHASE_A_SHA256}" "${PHASE_A_BYTES}"
  assert_file "${PHASE_B_DEST}" 644 0 0 "${PHASE_B_SHA256}" "${PHASE_B_BYTES}"
  assert_file "${INPUT_ROOT}/source.bundle" 444 0 0 "${BUNDLE_SHA256}" "${BUNDLE_BYTES}"
  assert_file "${INPUT_ROOT}/phase-a-request.json" 444 0 0 "${REQUEST_SHA256}" "${REQUEST_BYTES}"
  [[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h|%s' -- "${STATE_ROOT}/phase-a-slot/.build.lock")" == \
    'regular empty file|600|997|997|1|0' ]] || fail 'R2 Phase A lock differs'
  [[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h|%s' -- "${STATE_ROOT}/phase-b-slot/.build.lock")" == \
    'regular empty file|600|997|997|1|0' ]] || fail 'R2 Phase B lock differs'
}

sync_tree() {
  local root="$1" path list
  fresh_list
  list="${LIST_PATH}"
  /usr/bin/find -P "${root}" -xdev -depth -print0 >"${list}" || fail "cannot enumerate sync tree: ${root}"
  while IFS= read -r -d '' path; do /usr/bin/sync --file-system -- "${path}"; done <"${list}"
  /usr/bin/rm -f -- "${list}"
  /usr/bin/sync --file-system -- "${root%/*}"
}

[[ "${EUID}" -eq 0 ]] || fail 'root EUID is required'
[[ "$0" == "${LIVE_SELF}" && -f "${LIVE_SELF}" && ! -L "${LIVE_SELF}" ]] || fail 'live prepare path differs'
[[ "$(/usr/bin/stat -Lc '%F|%a|%u|%g|%h' -- "${LIVE_SELF}")" == 'regular file|500|0|0|1' ]] || fail 'live prepare metadata differs'
exec 8<"${LIVE_SELF}"
LIVE_SELF_ID="$(/usr/bin/stat -Lc '%d:%i' -- "$(held_path 8)")" || fail 'cannot bind live prepare identity'
LIVE_SELF_SHA256="$(sha256_of "$(held_path 8)")" || fail 'cannot hash live prepare'
LIVE_SELF_BYTES="$(/usr/bin/stat -Lc '%s' -- "$(held_path 8)")" || fail 'cannot size live prepare'
readonly LIVE_SELF_ID LIVE_SELF_SHA256 LIVE_SELF_BYTES
verify_live_self

assert_absent "${OUTER_LOCK}"
trap '' HUP INT TERM
/usr/bin/mkdir -m 0700 -- "${OUTER_LOCK}"
OUTER_LOCK_OWNED='true'
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
/usr/bin/chown root:root -- "${OUTER_LOCK}"
exec 9<"${OUTER_LOCK}"
/usr/bin/flock -n 9 || fail 'cannot acquire outer prepare lock'

assert_directory "${RUN_ROOT}" 755 "${CANDIDATE_UID}" "${CANDIDATE_GID}"
assert_directory "${REVIEWED_ROOT}" 755 "${CANDIDATE_UID}" "${CANDIDATE_GID}"
assert_directory "${REVIEWED_SYSTEMD}" 755 "${CANDIDATE_UID}" "${CANDIDATE_GID}"
exec 10<"${REVIEWED_BOOTSTRAP}" 11<"${REVIEWED_BUILDER}" 12<"${REVIEWED_PHASE_A}" 13<"${REVIEWED_PHASE_B}"
exec 14<"${REVIEWED_BUNDLE}" 15<"${REVIEWED_REQUEST}" 16<"${REVIEWED_INPUT_SET}"
BOOTSTRAP_ID="$(verify_candidate_fd 10 "${REVIEWED_BOOTSTRAP}" "${BOOTSTRAP_SHA256}" "${BOOTSTRAP_BYTES}")" || fail 'cannot bind reviewed bootstrap'
BUILDER_ID="$(verify_candidate_fd 11 "${REVIEWED_BUILDER}" "${BUILDER_SHA256}" "${BUILDER_BYTES}")" || fail 'cannot bind reviewed builder'
PHASE_A_ID="$(verify_candidate_fd 12 "${REVIEWED_PHASE_A}" "${PHASE_A_SHA256}" "${PHASE_A_BYTES}")" || fail 'cannot bind reviewed Phase A unit'
PHASE_B_ID="$(verify_candidate_fd 13 "${REVIEWED_PHASE_B}" "${PHASE_B_SHA256}" "${PHASE_B_BYTES}")" || fail 'cannot bind reviewed Phase B unit'
BUNDLE_ID="$(verify_candidate_fd 14 "${REVIEWED_BUNDLE}" "${BUNDLE_SHA256}" "${BUNDLE_BYTES}")" || fail 'cannot bind reviewed bundle'
REQUEST_ID="$(verify_candidate_fd 15 "${REVIEWED_REQUEST}" "${REQUEST_SHA256}" "${REQUEST_BYTES}")" || fail 'cannot bind reviewed request'
INPUT_SET_ID="$(verify_candidate_fd 16 "${REVIEWED_INPUT_SET}" "${INPUT_SET_SHA256}" "${INPUT_SET_BYTES}")" || fail 'cannot bind reviewed input set'
readonly BOOTSTRAP_ID BUILDER_ID PHASE_A_ID PHASE_B_ID BUNDLE_ID REQUEST_ID INPUT_SET_ID
validate_input_documents
assert_r1_file_state
assert_r1_manager_vector
assert_fresh_r2

trap '' HUP INT TERM
/usr/bin/mkdir -m 0700 -- "${TRUSTED_STAGING}"
TRUSTED_STAGING_OWNED='true'
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
/usr/bin/chown root:root -- "${TRUSTED_STAGING}"
/usr/bin/install -d -o root -g root -m 0700 -- "${TRUSTED_STAGING}/systemd"
/usr/bin/install -o root -g root -m 0500 -- "$(held_path 10)" "${TRUSTED_STAGING}/bootstrap_vista_r8_native_builder_r2.sh"
/usr/bin/install -o root -g root -m 0400 -- "$(held_path 11)" "${TRUSTED_STAGING}/vista_r8_native_builder.py"
/usr/bin/install -o root -g root -m 0400 -- "$(held_path 12)" "${TRUSTED_STAGING}/systemd/${PHASE_A_UNIT}"
/usr/bin/install -o root -g root -m 0400 -- "$(held_path 13)" "${TRUSTED_STAGING}/systemd/${PHASE_B_UNIT}"
assert_absent "${TRUSTED_STAGING}/.bootstrap.lock"
/usr/bin/install -o root -g root -m 0600 -- /dev/null "${TRUSTED_STAGING}/.bootstrap.lock"
exec {GLOBAL_LOCK_FD}<>"${TRUSTED_STAGING}/.bootstrap.lock"
readonly GLOBAL_LOCK_FD
# Keep the no-replace lock inode open throughout this outer ceremony.  Each
# bootstrap invocation takes the exclusive flock itself; the outer held FD is
# an identity anchor and therefore intentionally is not locked here.
/usr/bin/chmod 0555 -- "${TRUSTED_STAGING}/systemd" "${TRUSTED_STAGING}"
sync_tree "${TRUSTED_STAGING}"
trap '' HUP INT TERM
/usr/bin/mv --no-clobber --no-target-directory -- "${TRUSTED_STAGING}" "${TRUSTED_ROOT}"
TRUSTED_STAGING_OWNED='false'
FINAL_R2_PATH_PUBLISHED='true'
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
assert_absent "${TRUSTED_STAGING}"
verify_trusted_tree
verify_held_global_lock
exec {GLOBAL_LOCK_FD}>&-

trap '' HUP INT TERM
/usr/bin/install -d -o root -g root -m 0700 -- "${INPUT_STAGING}"
INPUT_STAGING_OWNED='true'
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
/usr/bin/install -o root -g root -m 0400 -- "$(held_path 14)" "${INPUT_STAGING}/source.bundle"
/usr/bin/install -o root -g root -m 0400 -- "$(held_path 15)" "${INPUT_STAGING}/phase-a-request.json"
sync_tree "${INPUT_STAGING}"
/usr/bin/mv --no-clobber --no-target-directory -- "${INPUT_STAGING}" "${INPUT_CANDIDATE_ROOT}"
INPUT_STAGING_OWNED='false'
assert_absent "${INPUT_STAGING}"
verify_input_tree

/usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin \
  /usr/bin/bash "${TRUSTED_BOOTSTRAP}" install-framework \
  "${BUILDER_SHA256}" "${BUILDER_BYTES}" \
  "${PHASE_A_SHA256}" "${PHASE_A_BYTES}" \
  "${PHASE_B_SHA256}" "${PHASE_B_BYTES}" "${FRAMEWORK_ACK}"
/usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin \
  /usr/bin/bash "${TRUSTED_BOOTSTRAP}" install-phase-a-inputs \
  "${BUNDLE_SHA256}" "${BUNDLE_BYTES}" \
  "${REQUEST_SHA256}" "${REQUEST_BYTES}" "${PHASE_A_ACK}"

verify_trusted_tree
verify_input_tree
verify_installed_framework
[[ "$(verify_candidate_fd 10 "${REVIEWED_BOOTSTRAP}" "${BOOTSTRAP_SHA256}" "${BOOTSTRAP_BYTES}")" == "${BOOTSTRAP_ID}" ]] || fail 'reviewed bootstrap changed'
[[ "$(verify_candidate_fd 11 "${REVIEWED_BUILDER}" "${BUILDER_SHA256}" "${BUILDER_BYTES}")" == "${BUILDER_ID}" ]] || fail 'reviewed builder changed'
[[ "$(verify_candidate_fd 12 "${REVIEWED_PHASE_A}" "${PHASE_A_SHA256}" "${PHASE_A_BYTES}")" == "${PHASE_A_ID}" ]] || fail 'reviewed Phase A unit changed'
[[ "$(verify_candidate_fd 13 "${REVIEWED_PHASE_B}" "${PHASE_B_SHA256}" "${PHASE_B_BYTES}")" == "${PHASE_B_ID}" ]] || fail 'reviewed Phase B unit changed'
[[ "$(verify_candidate_fd 14 "${REVIEWED_BUNDLE}" "${BUNDLE_SHA256}" "${BUNDLE_BYTES}")" == "${BUNDLE_ID}" ]] || fail 'reviewed bundle changed'
[[ "$(verify_candidate_fd 15 "${REVIEWED_REQUEST}" "${REQUEST_SHA256}" "${REQUEST_BYTES}")" == "${REQUEST_ID}" ]] || fail 'reviewed request changed'
[[ "$(verify_candidate_fd 16 "${REVIEWED_INPUT_SET}" "${INPUT_SET_SHA256}" "${INPUT_SET_BYTES}")" == "${INPUT_SET_ID}" ]] || fail 'reviewed input set changed'
validate_input_documents
verify_live_self
assert_r1_file_state
assert_r1_manager_vector
assert_absent "${STATE_ROOT}/phase-a-slot/published"
assert_absent "${STATE_ROOT}/phase-b-slot/published"
assert_absent "${ACTIVATION_RECEIPT}"
assert_absent "${ACTIVATION_STAGING}"
printf '%s\n' 'VISTA_R8_NATIVE_BUILDER_R2_PREPARED_INACTIVE'
printf '%s\n' 'No daemon-reload, enable, start, reset-failed, or build was performed.'
