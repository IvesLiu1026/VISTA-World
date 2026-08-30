#!/bin/sh
set -eu

# This wrapper must be installed root:root 0500 at the literal path below.
# The helper and reviewed source-pin literals are intentionally fail-closed
# until independent review records their exact final bytes.
SELF=/root/vista-r8-ue57-authority-r2/provision_vista_r8_ue57_engine.sh
HELPER=/root/vista-r8-ue57-authority-r2/vista_r8_ue57_authority_admin.py
SOURCE_PIN=/root/vista-r8-ue57-authority-r2/engine-source-pin.json
PYTHON=/usr/bin/python3.10
ENGINE_LOCK=/root/vista-r8-ue57-authority-r2/.engine.lock
EXPECTED_HELPER_SHA256=REVIEWED_HELPER_SHA256_REQUIRED
EXPECTED_HELPER_BYTES=0
EXPECTED_SOURCE_PIN_SHA256=REVIEWED_ENGINE_SOURCE_PIN_SHA256_REQUIRED
EXPECTED_SOURCE_PIN_BYTES=0
EXPECTED_PYTHON_SHA256=REVIEWED_PYTHON_SHA256_REQUIRED
EXPECTED_PYTHON_BYTES=0
ACK='I acknowledge one fresh publication of the reviewed VISTA R8 UE 5.7 engine authority.'
RECONCILE_ACK='I acknowledge reconciliation of the existing reviewed VISTA R8 UE 5.7 engine authority without republishing or deleting it.'

fail() { printf '%s\n' "R8_ENGINE_WRAPPER_FAILED: $*" >&2; exit 2; }
test "$(id -u)" = 0 || fail 'root EUID required'
test "$0" = "$SELF" || fail 'literal installed wrapper path required'
case "$EXPECTED_HELPER_SHA256:$EXPECTED_SOURCE_PIN_SHA256:$EXPECTED_PYTHON_SHA256" in
  (*REQUIRED*) fail 'independent reviewed hashes are not installed' ;;
esac
test "$(stat -Lc '%a:%u:%g:%h:%s' "$SELF")" = "500:0:0:1:$(stat -Lc %s "$SELF")" || fail 'wrapper metadata differs'
test "$(stat -Lc '%a:%u:%g:%h:%s' "$HELPER")" = "500:0:0:1:$EXPECTED_HELPER_BYTES" || fail 'helper metadata differs'
test "$(sha256sum "$HELPER" | cut -d' ' -f1)" = "$EXPECTED_HELPER_SHA256" || fail 'helper digest differs'
test "$(stat -Lc '%a:%u:%g:%h:%s' "$SOURCE_PIN")" = "444:0:0:1:$EXPECTED_SOURCE_PIN_BYTES" || fail 'source pin metadata differs'
test "$(sha256sum "$SOURCE_PIN" | cut -d' ' -f1)" = "$EXPECTED_SOURCE_PIN_SHA256" || fail 'source pin digest differs'
test "$(stat -Lc '%a:%u:%g:%h:%s' "$ENGINE_LOCK")" = "600:0:0:1:0" || fail 'engine lock metadata differs'
exec 9<"$PYTHON"
test "$(stat -Lc '%a:%u:%g:%h:%s' /proc/self/fd/9)" = "755:0:0:1:$EXPECTED_PYTHON_BYTES" || fail 'held Python metadata differs'
test "$(sha256sum /proc/self/fd/9 | cut -d' ' -f1)" = "$EXPECTED_PYTHON_SHA256" || fail 'held Python digest differs'
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
