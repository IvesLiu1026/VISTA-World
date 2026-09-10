#!/bin/sh
# Run manually with sudo on the target workstation after reviewing this file.
# Grants access only to virtual input devices used by this streaming setup.
set -eu
if test "$(id -u)" -ne 0; then
    printf '%s\n' 'Run this script with sudo from an administrator terminal.' >&2
    exit 1
fi
script_path=$(readlink -f "$0")
target_user=$(stat -c %U "$(dirname "$script_path")")
if test "$target_user" = root || test "$target_user" = UNKNOWN; then
    printf '%s\n' 'The environment directory must belong to its non-root runtime account.' >&2
    exit 1
fi
getent passwd "$target_user" >/dev/null
command -v setfacl >/dev/null
getent group input >/dev/null
rule=/etc/udev/rules.d/85-vista-streaming.rules
tmp_rule=$(mktemp)
trap 'rm -f "$tmp_rule"' EXIT HUP INT TERM
cat > "$tmp_rule" <<'EOF'
# VISTA: virtual input only; never grant access to physical keyboards/mice.
SUBSYSTEM=="misc", KERNEL=="uinput", OPTIONS+="static_node=uinput", RUN+="/usr/bin/setfacl -m g:vista-streaming:rw /dev/%k"
SUBSYSTEM=="misc", KERNEL=="uhid", RUN+="/usr/bin/setfacl -m g:vista-streaming:rw /dev/%k"
ACTION=="add|change", SUBSYSTEM=="input", KERNEL=="event[0-9]*", DEVPATH=="/devices/virtual/input/input*/event*", ATTRS{name}=="Keyboard passthrough", ATTRS{id/vendor}=="beef", ATTRS{id/product}=="dead", RUN+="/usr/bin/setfacl -m g:vista-streaming:rw /dev/input/%k", SYMLINK+="input/vista-sunshine-keyboard"
ACTION=="add|change", SUBSYSTEM=="input", KERNEL=="event[0-9]*", DEVPATH=="/devices/virtual/input/input*/event*", ATTRS{name}=="Mouse passthrough", ATTRS{id/vendor}=="beef", ATTRS{id/product}=="dead", RUN+="/usr/bin/setfacl -m g:vista-streaming:rw /dev/input/%k", SYMLINK+="input/vista-sunshine-mouse"
ACTION=="add|change", SUBSYSTEM=="input", KERNEL=="event[0-9]*", DEVPATH=="/devices/virtual/input/input*/event*", ATTRS{name}=="Mouse passthrough (absolute)", ATTRS{id/vendor}=="beef", ATTRS{id/product}=="dead", RUN+="/usr/bin/setfacl -m g:vista-streaming:rw /dev/input/%k", SYMLINK+="input/vista-sunshine-mouse-absolute"
EOF
upgrade_owned_rule=false
if test -e "$rule" && ! cmp -s "$tmp_rule" "$rule"; then
    rule_digest=$(sha256sum "$rule" | cut -d ' ' -f 1)
    if test "$rule_digest" = 2c259c4664d5c748bf269de2b64bbf2d85f79772a9a8fbede74eb817cc4997e8; then
        upgrade_owned_rule=true
    else
        printf '%s\n' 'A different existing VISTA input rule needs review; nothing changed.' >&2
        exit 2
    fi
fi
if getent group vista-streaming >/dev/null; then
    if test ! -f "$rule"; then
        printf '%s\n' 'The group already exists without this rule; review ownership first.' >&2
        exit 3
    fi
else
    groupadd --system vista-streaming
fi
usermod -a -G vista-streaming -- "$target_user"
install -o root -g root -m 0644 "$tmp_rule" "$rule"
modprobe uinput
modprobe uhid
udevadm control --reload-rules
udevadm trigger --subsystem-match=misc --sysname-match=uinput
udevadm trigger --subsystem-match=misc --sysname-match=uhid
udevadm settle
if test "$upgrade_owned_rule" = true; then
    # Restore the input group defined by the installed 60-sunshine.rules;
    # preserve the existing user ACLs and give VISTA an additive group ACL.
    chgrp input /dev/uinput /dev/uhid
    chmod 0660 /dev/uinput /dev/uhid
fi
setfacl -m g:vista-streaming:rw /dev/uinput /dev/uhid
printf '%s\n' 'VISTA additive virtual input permissions installed; existing input-group access preserved. No desktop or GPU job was restarted.'
