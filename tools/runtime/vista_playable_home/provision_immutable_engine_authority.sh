#!/bin/bash
set -euo pipefail
IFS=$'\n\t'
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

SOURCE=/mnt/NAS2/yhliu/UE_5.7.3_prebuilt
AUTHORITY_PARENT=/data/vista-authorities
FINAL_AUTHORITY=/data/vista-authorities/ue-5.7.3-r1
FINAL_ENGINE=/data/vista-authorities/ue-5.7.3-r1/engine
FINAL_MANIFEST=/data/vista-authorities/ue-5.7.3-r1/engine-full-tree-manifest.json
INSTALL_ROOT=/root/vista-r5-engine-authority-r1
INSTALLED_SCRIPT=/root/vista-r5-engine-authority-r1/provision_immutable_engine_authority.sh
MANIFEST_HELPER=/root/vista-r5-engine-authority-r1/r5_engine_authority_admin.py
EXPECTED_HELPER_SHA256=4ca08f3f88ab7249255ebc9c551d725efa888a8527fe6b1b2d8a02acf395259e

fail_bootstrap() {
    echo "R5_ENGINE_BOOTSTRAP_REJECTED: $1" >&2
    exit 2
}

SELF_PATH=${BASH_SOURCE[0]}
if [[ ${SELF_PATH} != "${INSTALLED_SCRIPT}" || -L ${SELF_PATH} ]]; then
    fail_bootstrap \
        "run only the independently hash-verified installed script at ${INSTALLED_SCRIPT}; worktree execution is forbidden"
fi
if [[ $(/usr/bin/readlink -f -- "${SELF_PATH}") != "${INSTALLED_SCRIPT}" ]]; then
    fail_bootstrap "installed script path is non-canonical"
fi

verify_root_chain_directory() {
    local path=$1
    local uid gid mode
    if [[ ! -d ${path} || -L ${path} ]]; then
        fail_bootstrap "bootstrap ancestor is missing, not a directory, or a symlink: ${path}"
    fi
    IFS=' ' read -r uid gid mode < <(/usr/bin/stat -c '%u %g %a' -- "${path}")
    if [[ ${uid} != 0 || ${gid} != 0 || $((8#${mode} & 0022)) -ne 0 ]]; then
        fail_bootstrap "bootstrap ancestor must be root:root and not group/world writable: ${path}"
    fi
}

verify_installed_file() {
    local path=$1
    local uid gid mode kind
    if [[ ! -f ${path} || -L ${path} ]]; then
        fail_bootstrap "installed bootstrap file is missing, non-regular, or a symlink: ${path}"
    fi
    IFS=' ' read -r uid gid mode kind < <(/usr/bin/stat -c '%u %g %a %F' -- "${path}")
    if [[ ${uid} != 0 || ${gid} != 0 || ${mode} != 555 || ${kind} != "regular file" ]]; then
        fail_bootstrap "installed bootstrap file must be root:root regular mode 0555: ${path}"
    fi
}

for ancestor in / /root "${INSTALL_ROOT}"; do
    verify_root_chain_directory "${ancestor}"
done
if [[ $(/usr/bin/stat -c '%a' -- "${INSTALL_ROOT}") != 555 ]]; then
    fail_bootstrap "fixed bootstrap directory must have mode 0555"
fi
verify_installed_file "${INSTALLED_SCRIPT}"
verify_installed_file "${MANIFEST_HELPER}"
if ! printf '%s  %s\n' "${EXPECTED_HELPER_SHA256}" "${MANIFEST_HELPER}" \
    | /usr/bin/sha256sum -c - >/dev/null; then
    fail_bootstrap "installed manifest helper hash differs from the reviewed pin"
fi

if [[ ${EUID} -ne 0 ]]; then
    echo "This provisioning script must be run directly by root." >&2
    exit 2
fi
if [[ ! -d ${SOURCE} || -L ${SOURCE} || $(readlink -f -- "${SOURCE}") != "${SOURCE}" ]]; then
    echo "The fixed UE source root is missing, non-canonical, or a symlink." >&2
    exit 2
fi
if [[ -e ${FINAL_AUTHORITY} ]]; then
    echo "Refusing to replace the existing immutable authority." >&2
    exit 2
fi
if [[ -n $(/usr/bin/find "${SOURCE}" -xdev -type l -print -quit) ]]; then
    echo "The UE source contains a symlink; provisioning refuses symlink escape." >&2
    exit 2
fi

/usr/bin/install -d -o root -g root -m 0755 "${AUTHORITY_PARENT}"
STAGING=$(/usr/bin/mktemp -d "${AUTHORITY_PARENT}/.ue-5.7.3-r1.staging.XXXXXXXX")
MANIFEST_WORK=$(/usr/bin/mktemp -d /run/vista-r5-ue-manifests.XXXXXXXX)
PRE_MANIFEST=${MANIFEST_WORK}/pre.json
POST_MANIFEST=${MANIFEST_WORK}/post.json

cleanup() {
    /usr/bin/rm -rf --one-file-system -- "${MANIFEST_WORK}"
    if [[ -n ${STAGING:-} && -d ${STAGING} ]]; then
        /usr/bin/chmod -R u+rwX -- "${STAGING}" || true
        /usr/bin/rm -rf --one-file-system -- "${STAGING}"
    fi
}
trap cleanup EXIT

/usr/bin/python3 "${MANIFEST_HELPER}" snapshot \
    --scan-root "${SOURCE}" \
    --declared-root "${SOURCE}" \
    --output "${PRE_MANIFEST}"

/usr/bin/install -d -o root -g root -m 0700 "${STAGING}/engine"
/usr/bin/cp -a --reflink=auto --no-preserve=ownership \
    "${SOURCE}/." "${STAGING}/engine/"

/usr/bin/python3 "${MANIFEST_HELPER}" snapshot \
    --scan-root "${SOURCE}" \
    --declared-root "${SOURCE}" \
    --output "${POST_MANIFEST}"
/usr/bin/python3 "${MANIFEST_HELPER}" compare-content \
    "${PRE_MANIFEST}" "${POST_MANIFEST}"

/usr/bin/chown -R root:root -- "${STAGING}/engine"
/usr/bin/find "${STAGING}/engine" -xdev -type d -exec /usr/bin/chmod 0555 -- {} +
/usr/bin/find "${STAGING}/engine" -xdev -type f -perm /0111 -exec /usr/bin/chmod 0555 -- {} +
/usr/bin/find "${STAGING}/engine" -xdev -type f ! -perm /0111 -exec /usr/bin/chmod 0444 -- {} +

/usr/bin/python3 "${MANIFEST_HELPER}" snapshot \
    --scan-root "${STAGING}/engine" \
    --declared-root "${FINAL_ENGINE}" \
    --output "${STAGING}/engine-full-tree-manifest.json"
/usr/bin/python3 "${MANIFEST_HELPER}" compare-content \
    "${POST_MANIFEST}" "${STAGING}/engine-full-tree-manifest.json"

/usr/bin/chown root:root -- "${STAGING}/engine-full-tree-manifest.json" "${STAGING}"
/usr/bin/chmod 0444 -- "${STAGING}/engine-full-tree-manifest.json"
/usr/bin/chmod 0555 -- "${STAGING}"
/usr/bin/mv -T -- "${STAGING}" "${FINAL_AUTHORITY}"
STAGING=

MANIFEST_SHA256=$(/usr/bin/sha256sum -- "${FINAL_MANIFEST}" | /usr/bin/cut -d' ' -f1)
TREE_ROOT_DIGEST=$(
    /usr/bin/python3 -c \
        'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["tree_root_digest"])' \
        "${FINAL_MANIFEST}"
)
printf 'ENGINE_MANIFEST_SHA256=%s\n' "${MANIFEST_SHA256}"
printf 'ENGINE_TREE_ROOT_DIGEST=%s\n' "${TREE_ROOT_DIGEST}"
printf 'Immutable UE authority ready at %s\n' "${FINAL_AUTHORITY}"
