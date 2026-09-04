#!/usr/bin/env bash
set -euo pipefail

# Install a readable systemd alias without replacing the historical unit name.
# The target unit remains the compatibility contract used by older automation.
SERVICE_ALIAS=${SERVICE_ALIAS:?SERVICE_ALIAS is required}
SERVICE_TARGET=${SERVICE_TARGET:?SERVICE_TARGET is required}

case "$SERVICE_ALIAS" in
  ''|/*|*..*|*'/'*)
    echo "Invalid SERVICE_ALIAS" >&2
    exit 2
    ;;
esac
case "$SERVICE_TARGET" in
  ''|/*|*..*|*'/'*)
    echo "Invalid SERVICE_TARGET" >&2
    exit 2
    ;;
esac

ln -sfn "$SERVICE_TARGET" "/etc/systemd/system/$SERVICE_ALIAS"
systemctl daemon-reload
echo "Installed systemd alias $SERVICE_ALIAS -> $SERVICE_TARGET"
