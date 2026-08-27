#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
relay_source=${repo_root}/tools/runtime/input_relay/sunshine_x11.py
unit_source=${repo_root}/ops/systemd/vista-sunshine-x11-input-relay.service
relay_target=${HOME}/.local/libexec/vista-sunshine-x11-input-relay
unit_target=${HOME}/.config/systemd/user/vista-sunshine-x11-input-relay.service

if [[ ! -f ${relay_source} ]]; then
  echo "Relay source is missing: ${relay_source}" >&2
  exit 1
fi

if [[ ! -S /tmp/.X11-unix/X117 ]]; then
  echo "Xvfb display socket /tmp/.X11-unix/X117 is unavailable." >&2
  exit 1
fi

virtinput_gid=$(getent group virtinput | cut -d: -f3)
manager_pid=$(systemctl show "user@$(id -u).service" --property=MainPID --value)
if [[ -z ${manager_pid} || ${manager_pid} == 0 ]] ||
  ! awk -v gid="${virtinput_gid}" '$1 == "Groups:" { for (i = 2; i <= NF; i++) if ($i == gid) found = 1 } END { exit !found }' "/proc/${manager_pid}/status"; then
  echo "The systemd user manager has not inherited the virtinput group." >&2
  exit 1
fi

for required_name in "Keyboard passthrough" "Mouse passthrough" "Mouse passthrough (absolute)"; do
  found=false
  for sys_event in /sys/class/input/event*; do
    [[ -r ${sys_event}/device/name ]] || continue
    if [[ $(<"${sys_event}/device/name") == "${required_name}" ]]; then
      event_node=/dev/input/${sys_event##*/}
      read -r mode owner group < <(stat -c '%a %U %G' "${event_node}")
      if [[ ${mode} != 660 || ${owner} != root || ${group} != virtinput ]]; then
        echo "Relay permissions are not installed for ${event_node} (${required_name})." >&2
        exit 1
      fi
      found=true
      break
    fi
  done
  if [[ ${found} != true ]]; then
    echo "Sunshine device not found: ${required_name}" >&2
    exit 1
  fi
done

install -d -m 0755 "${HOME}/.local/libexec" "${HOME}/.config/systemd/user"
install -m 0755 "${relay_source}" "${relay_target}"
install -m 0644 "${unit_source}" "${unit_target}"

systemctl --user daemon-reload
systemctl --user enable --now vista-sunshine-x11-input-relay.service
systemctl --user status vista-sunshine-x11-input-relay.service --no-pager -l
