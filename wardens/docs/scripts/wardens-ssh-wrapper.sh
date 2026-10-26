#!/bin/sh
# Wardens SSH gateway — only allowlisted ops (no interactive root shell).
# Installed as forced command= on the MCP public key in authorized_keys.
#
# Allowed SSH_ORIGINAL_COMMAND values:
#   collect         — run wardens-collector (stdout JSON)
#   install-binary  — replace collector binary from stdin (raw ELF bytes)
#   version         — print wrapper + env version
set -eu

CMD="${SSH_ORIGINAL_COMMAND:-}"

case "$CMD" in
  collect)
    set -a
    # shellcheck disable=SC1091
    [ -f /etc/wardens/collector.env ] && . /etc/wardens/collector.env
    set +a
    exec /opt/wardens/bin/wardens-collector
    ;;
  install-binary)
    tmp="$(mktemp /tmp/wardens-bin.XXXXXX)"
    trap 'rm -f "$tmp"' EXIT INT TERM
    cat >"$tmp"
    # basic sanity: non-empty and looks like ELF or is large enough
    sz="$(wc -c <"$tmp" | tr -d ' ')"
    if [ "$sz" -lt 64 ]; then
      echo "wardens: install-binary payload too small ($sz)" >&2
      exit 2
    fi
    install -d /opt/wardens/bin
    install -m 0755 "$tmp" /opt/wardens/bin/wardens-collector
    echo "{\"ok\":true,\"path\":\"/opt/wardens/bin/wardens-collector\",\"bytes\":$sz}"
    ;;
  version)
    ver="unknown"
    # shellcheck disable=SC1091
    [ -f /etc/wardens/collector.env ] && . /etc/wardens/collector.env
    ver="${WARDEN_VERSION:-unknown}"
    echo "{\"wrapper\":\"1.0\",\"warden_version\":\"$ver\"}"
    ;;
  *)
    echo "wardens: command not allowed: ${CMD:-<empty>}" >&2
    exit 1
    ;;
esac
