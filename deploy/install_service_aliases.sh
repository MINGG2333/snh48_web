#!/usr/bin/env bash
set -euo pipefail

# Install a readable systemd alias without replacing the historical unit name.
# The target unit remains the compatibility contract used by older automation.
SERVICE_ALIAS=${SERVICE_ALIAS:?SERVICE_ALIAS is required}
SERVICE_TARGET=${SERVICE_TARGET:?SERVICE_TARGET is required}

if [[ ! "$SERVICE_ALIAS" =~ ^[A-Za-z0-9_.@-]+$ || ! "$SERVICE_TARGET" =~ ^[A-Za-z0-9_.@-]+$ ]]; then
  echo "Invalid service alias or target" >&2
  exit 2
fi

ln -sfn "$SERVICE_TARGET" "/etc/systemd/system/$SERVICE_ALIAS"
systemctl daemon-reload
echo "Installed systemd alias $SERVICE_ALIAS -> $SERVICE_TARGET"
