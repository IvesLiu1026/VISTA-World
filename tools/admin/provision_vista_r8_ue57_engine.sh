#!/bin/sh
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
IFS=' '
export PATH LC_ALL LANG IFS
unset ENV BASH_ENV CDPATH GLOBIGNORE PYTHONHOME PYTHONPATH LD_PRELOAD LD_LIBRARY_PATH

# This wrapper must be installed root:root 0500 at the literal path below.
# The helper, source pin, and Python literals below are the independently
# reviewed final-repin candidate values; changing any input requires
# regenerating all three.
SELF=/root/vista-r8-ue57-authority-r2/provision_vista_r8_ue57_engine.sh
HELPER=/root/vista-r8-ue57-authority-r2/vista_r8_ue57_authority_admin.py
SOURCE_PIN=/root/vista-r8-ue57-authority-r2/engine-source-pin.json
PYTHON=/usr/bin/python3.10
ENGINE_LOCK=/root/vista-r8-ue57-authority-r2/.engine.lock
EXPECTED_HELPER_SHA256=247f5d6b0cf55de2b7840574c5529ed4c4560fb1176d152b9bed41f8f01f280f
EXPECTED_HELPER_BYTES=508969
EXPECTED_SOURCE_PIN_SHA256=7b30cd3b5628a21579efc19013a1d13e9557684c6b8ab3b6495eb42544e4b3d9
EXPECTED_SOURCE_PIN_BYTES=786
EXPECTED_PYTHON_SHA256=7d51cd6b48b521277f5caa4610a82126e315fa2be4df069823a8b1eeb5bd4a86
EXPECTED_PYTHON_BYTES=5917224
ACK='I acknowledge one fresh publication of the reviewed VISTA R8 UE 5.7 engine authority.'
RECONCILE_ACK='I acknowledge reconciliation of the existing reviewed VISTA R8 UE 5.7 engine authority without republishing or deleting it.'

fail() { printf '%s\n' "R8_ENGINE_WRAPPER_FAILED: $*" >&2; exit 2; }
test "$(/usr/bin/id -u)" = 0 || fail 'root EUID required'
test "$0" = "$SELF" || fail 'literal installed wrapper path required'
test "$(/usr/bin/stat -Lc '%a:%u:%g:%h:%s' "$SELF")" = "500:0:0:1:$(/usr/bin/stat -Lc %s "$SELF")" || fail 'wrapper metadata differs'
test "$(/usr/bin/stat -Lc '%a:%u:%g:%h:%s' "$HELPER")" = "500:0:0:1:$EXPECTED_HELPER_BYTES" || fail 'helper metadata differs'
test "$(/usr/bin/sha256sum "$HELPER" | /usr/bin/cut -d' ' -f1)" = "$EXPECTED_HELPER_SHA256" || fail 'helper digest differs'
test "$(/usr/bin/stat -Lc '%a:%u:%g:%h:%s' "$SOURCE_PIN")" = "444:0:0:1:$EXPECTED_SOURCE_PIN_BYTES" || fail 'source pin metadata differs'
test "$(/usr/bin/sha256sum "$SOURCE_PIN" | /usr/bin/cut -d' ' -f1)" = "$EXPECTED_SOURCE_PIN_SHA256" || fail 'source pin digest differs'
test "$(/usr/bin/stat -Lc '%a:%u:%g:%h:%s' "$ENGINE_LOCK")" = "600:0:0:1:0" || fail 'engine lock metadata differs'
exec 9<"$PYTHON"
test "$(/usr/bin/stat -Lc '%a:%u:%g:%h:%s' /proc/self/fd/9)" = "755:0:0:1:$EXPECTED_PYTHON_BYTES" || fail 'held Python metadata differs'
test "$(/usr/bin/sha256sum /proc/self/fd/9 | /usr/bin/cut -d' ' -f1)" = "$EXPECTED_PYTHON_SHA256" || fail 'held Python digest differs'
test "$#" = 2 || fail 'one operation and exact acknowledgement required'
OP=$1
ACK_VALUE=$2
case "$OP" in
  publish-engine) test "$ACK_VALUE" = "$ACK" || fail 'publish acknowledgement differs' ;;
  reconcile-engine) test "$ACK_VALUE" = "$RECONCILE_ACK" || fail 'reconciliation acknowledgement differs' ;;
  *) fail 'operation differs' ;;
esac

exec /usr/bin/env -i PATH=/usr/bin:/bin LANG=C.UTF-8 \
  /proc/self/fd/9 -I -B "$HELPER" "$OP" --acknowledgement "$ACK_VALUE"
