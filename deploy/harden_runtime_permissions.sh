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
install -o root -g root -m 0755 deploy/privileged/snh48-social-credentials-bridge \
    /usr/local/sbin/snh48-social-credentials-bridge
install -o root -g root -m 0755 deploy/privileged/snh48-flip-account-bridge \
    /usr/local/sbin/snh48-flip-account-bridge
install -o root -g root -m 0440 deploy/privileged/snh48-web.sudoers \
    /etc/sudoers.d/snh48-web
visudo -cf /etc/sudoers.d/snh48-web >/dev/null

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

# Preserve private permissions for future files created by the application.
setfacl -R -m u:"$SERVICE_USER":rwX "$WEB_ROOT/website/data"
find "$WEB_ROOT/website/data" -type d -exec setfacl -m d:u:"$SERVICE_USER":rwx,d:m::rwx {} +

echo "Runtime permissions prepared for $SERVICE_USER."
