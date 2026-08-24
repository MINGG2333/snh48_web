#!/bin/bash
set -euo pipefail

SERVICE_USER="snh48-web"
SERVICE_GROUP="snh48-web"
WEB_ROOT="/home/snh48_web"
FAN_ROOT="/home/snh48-fan-hub"

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --home-dir /var/lib/snh48-web --create-home \
        --shell /sbin/nologin --user-group "$SERVICE_USER"
fi

install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 /var/lib/snh48-web
install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 /var/lib/snh48-web/.ssh
install -d -o root -g root -m 0755 /usr/local/libexec
install -o root -g root -m 0755 deploy/privileged/snh48_privileged_bridge_server.py \
    /usr/local/libexec/snh48-privileged-bridge-server
install -o root -g root -m 0755 deploy/privileged/snh48_privileged_bridge_client.py \
    /usr/local/bin/snh48-privileged-bridge-client
install -o root -g root -m 0644 deploy/systemd/snh48-privileged-bridge-flip.service \
    /etc/systemd/system/snh48-privileged-bridge-flip.service
install -o root -g root -m 0644 deploy/systemd/snh48-privileged-bridge-social.service \
    /etc/systemd/system/snh48-privileged-bridge-social.service
install -o root -g root -m 0644 deploy/systemd/snh48-web.service \
    /etc/systemd/system/snh48-web.service

# Code and generated website inputs remain root-owned; the service gets only
# the read access needed to render them.
setfacl -m u:"$SERVICE_USER":x /home /home/snh48-fan-hub
setfacl -m u:"$SERVICE_USER":rx /home/snh48_web
setfacl -R -m u:"$SERVICE_USER":rX "$WEB_ROOT/website"
for path in \
    "$FAN_ROOT/live_push_replays" \
    "$FAN_ROOT/room_record" \
    "$FAN_ROOT/schedule_record" \
    "$FAN_ROOT/flip_data" \
    "$FAN_ROOT/social_record"; do
    [ -e "$path" ] && setfacl -R -m u:"$SERVICE_USER":rX "$path"
done

# Runtime records contain IPs, emails, questions and administrator actions.
# Make the application account their sole non-root reader/writer.
for path in \
    "$WEB_ROOT/website/data" \
    "$WEB_ROOT/transcript_analyze/logs_backup" \
    "$WEB_ROOT/transcript_analyze/video_knowledge_db/qa_archive" \
    /var/log/snh48; do
    [ -e "$path" ] || install -d "$path"
    chown -R "$SERVICE_USER":"$SERVICE_GROUP" "$path"
    find "$path" -type d -exec chmod 0700 {} +
    find "$path" -type f -exec chmod 0600 {} +
done

# The service account owns runtime data, so no named/default ACL is needed.
# Removing inherited ACLs keeps the visible mode bits at 0700/0600; the unit's
# UMask=0077 protects files created after this script runs.
setfacl -Rb "$WEB_ROOT/website/data"
find "$WEB_ROOT/website/data" -type d -exec chmod 0700 {} +
find "$WEB_ROOT/website/data" -type f -exec chmod 0600 {} +

install -d -o root -g root -m 0700 "$FAN_ROOT/notifications/flip_web_admin"
if [ ! -e "$FAN_ROOT/flip_chat.html" ]; then
    install -o root -g root -m 0600 /dev/null "$FAN_ROOT/flip_chat.html"
fi

systemctl daemon-reload
systemctl enable snh48-privileged-bridge-flip.service snh48-privileged-bridge-social.service
systemctl restart snh48-privileged-bridge-flip.service snh48-privileged-bridge-social.service
if systemctl is-active --quiet snh48-web.service; then
    systemctl restart snh48-web.service
fi

# Remove the previous sudo transition only after both new brokers and the
# updated web unit have started successfully.
rm -f /etc/sudoers.d/snh48-web
rm -f /usr/local/sbin/snh48-social-credentials-bridge
rm -f /usr/local/sbin/snh48-flip-account-bridge

echo "Runtime permissions prepared for $SERVICE_USER."
