#!/bin/bash
set -euo pipefail

SERVICE_USER="snh48-web"
SERVICE_GROUP="snh48-web"
WEB_ROOT="/home/snh48_web"
FAN_ROOT="/home/snh48-fan-hub"
KB_ROOT="$WEB_ROOT/transcript_analyze/video_knowledge_db"
SCORE_ROOT="$FAN_ROOT/room_record/陈嘉仪_161808449/score_gifts"
DANMU_CACHE="$FAN_ROOT/live_push_replays/陈嘉仪_161808449/.danmu_url_cache"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run as root." >&2
    exit 1
fi

if ! command -v setfacl >/dev/null 2>&1; then
    echo "setfacl is required (install the acl package)." >&2
    exit 1
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --home-dir /var/lib/snh48-web --create-home \
        --shell /usr/sbin/nologin --user-group "$SERVICE_USER"
fi

install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 /var/lib/snh48-web
install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 /var/lib/snh48-web/.ssh
install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 \
    "$WEB_ROOT/website/data" "$WEB_ROOT/transcript_analyze/logs_backup"
install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 "$KB_ROOT/qa_archive"
install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 "$DANMU_CACHE"

install -o root -g root -m 0755 deploy/privileged/snh48-shared-state-peer-bridge \
    /usr/local/sbin/snh48-shared-state-peer-bridge

# The application may traverse only the website and the explicitly mirrored
# data roots. Source code and generated inputs stay owned by their deployers.
setfacl -m u:"$SERVICE_USER":x /home "$WEB_ROOT" "$FAN_ROOT"
setfacl -R -m u:"$SERVICE_USER":rX "$WEB_ROOT/website" "$WEB_ROOT/transcript_analyze"
for path in \
    "$FAN_ROOT/live_push_replays" \
    "$FAN_ROOT/room_record" \
    "$FAN_ROOT/schedule_record" \
    "$FAN_ROOT/flip_data/web" \
    "$FAN_ROOT/social_record/timeline"; do
    [ -e "$path" ] && setfacl -R -m u:"$SERVICE_USER":rX "$path"
done

# Runtime records contain IPs, emails, questions, and administrator actions.
# They are private to root and the application account.
chown -R "$SERVICE_USER":"$SERVICE_GROUP" \
    "$WEB_ROOT/website/data" \
    "$WEB_ROOT/transcript_analyze/logs_backup" \
    "$KB_ROOT/qa_archive" \
    "$DANMU_CACHE"
for path in \
    "$WEB_ROOT/website/data" \
    "$WEB_ROOT/transcript_analyze/logs_backup" \
    "$KB_ROOT/qa_archive" \
    "$DANMU_CACHE"; do
    setfacl -Rb "$path"
    find "$path" -type d -exec chmod 0700 {} +
    find "$path" -type f -exec chmod 0600 {} +
done

# QA startup rotates qa_archive inside KB_ROOT, and shared score state uses
# atomic replacement in SCORE_ROOT. The systemd namespace limits writes to
# these two roots even though the service needs directory-level ACLs there.
setfacl -m u:"$SERVICE_USER":rwx "$KB_ROOT" "$SCORE_ROOT"
for path in \
    "$SCORE_ROOT/live_business_fulfillments.json" \
    "$SCORE_ROOT/.live_business_fulfillments.json.lock"; do
    if [ -e "$path" ]; then
        chown "$SERVICE_USER":"$SERVICE_GROUP" "$path"
        chmod 0600 "$path"
    fi
done

echo "Aliyun runtime permissions prepared for $SERVICE_USER."
