#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=${ROOT_DIR:-/home/snh48_web}
NODE_ID=${NODE_ID:?NODE_ID is required (for example: tencent or aliyun)}
ACCESS_PATTERN=${ACCESS_PATTERN:?ACCESS_PATTERN is required}
ACTIVE_LOG=${ACTIVE_LOG:?ACTIVE_LOG is required}
COS_CONFIG=${COS_CONFIG:-}
COS_CREDENTIALS=${COS_CREDENTIALS:-}

install -o root -g root -m 0755 "$ROOT_DIR/script/website_observability.py" /usr/local/libexec/snh48-website-observability.py
install -o root -g root -m 0644 "$ROOT_DIR/deploy/systemd/snh48-website-metrics.service" /etc/systemd/system/snh48-website-metrics.service
install -o root -g root -m 0644 "$ROOT_DIR/deploy/systemd/snh48-website-metrics.timer" /etc/systemd/system/snh48-website-metrics.timer
install -o root -g root -m 0644 "$ROOT_DIR/deploy/systemd/snh48-website-log-archive.service" /etc/systemd/system/snh48-website-log-archive.service
install -o root -g root -m 0644 "$ROOT_DIR/deploy/systemd/snh48-website-log-archive.timer" /etc/systemd/system/snh48-website-log-archive.timer
install -o root -g root -m 0644 "$ROOT_DIR/deploy/logrotate/nginx" /etc/logrotate.d/nginx

install -d -o root -g root -m 0700 /etc/snh48-web /var/lib/snh48-web/metrics /var/lib/snh48-web/log-archives
if [[ ! -e /etc/snh48-web/observability.env ]]; then
    umask 077
    cat > /etc/snh48-web/observability.env <<EOF
WEBSITE_METRICS_NODE_ID=$NODE_ID
WEBSITE_METRICS_ACCESS_PATTERNS=$(printf '%q' "$ACCESS_PATTERN")
WEBSITE_METRICS_ACTIVE_PATHS=$(printf '%q' "$ACTIVE_LOG")
WEBSITE_METRICS_OUTPUT_DIR=/var/lib/snh48-web/metrics/$NODE_ID
WEBSITE_LOG_ARCHIVE_NODE_ID=$NODE_ID
WEBSITE_LOG_ARCHIVE_PATTERNS=/var/log/nginx/*.log*
WEBSITE_LOG_ARCHIVE_ACTIVE_PATHS=/var/log/nginx/*.log
WEBSITE_LOG_ARCHIVE_STATE_DIR=/var/lib/snh48-web/log-archives/$NODE_ID
WEBSITE_LOG_ARCHIVE_THRESHOLD_BYTES=1073741824
COS_RCLONE_CONFIG=$COS_CONFIG
COS_CREDENTIALS_FILE=$COS_CREDENTIALS
COS_REMOTE=cjy_archive
COS_BUCKET=cjy-archive-1429902869
COS_PREFIX=website-logs
EOF
    chmod 0600 /etc/snh48-web/observability.env
fi

logrotate -d /etc/logrotate.d/nginx >/dev/null
systemctl daemon-reload
systemctl enable --now snh48-website-metrics.timer snh48-website-log-archive.timer
systemctl start snh48-website-metrics.service
systemctl start snh48-website-log-archive.service || {
    echo 'log archive check failed; no files were deleted' >&2
    exit 1
}
