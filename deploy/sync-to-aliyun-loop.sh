#!/bin/bash
# Run Tencent -> Aliyun website data sync repeatedly with a short interval.

set -euo pipefail

INTERVAL=${ALIYUN_SYNC_INTERVAL_SECONDS:-15}
case "$INTERVAL" in
  ''|*[!0-9]*) echo "invalid ALIYUN_SYNC_INTERVAL_SECONDS=$INTERVAL" >&2; exit 2 ;;
esac
if [ "$INTERVAL" -lt 5 ]; then
  echo "ALIYUN_SYNC_INTERVAL_SECONDS must be at least 5" >&2
  exit 2
fi

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LOCK_FILE=${ALIYUN_SYNC_LOCK_FILE:-/tmp/snh48_sync_to_aliyun.lock}

echo "[sync-to-aliyun-loop][$(date '+%Y-%m-%d %H:%M:%S')] starting interval=${INTERVAL}s"
while true; do
  started_at=$(date +%s)
  if flock -n "$LOCK_FILE" bash "$SCRIPT_DIR/sync-to-aliyun.sh"; then
    :
  else
    echo "[sync-to-aliyun-loop][$(date '+%Y-%m-%d %H:%M:%S')] previous sync still running, skipped"
  fi
  finished_at=$(date +%s)
  elapsed=$((finished_at - started_at))
  sleep_for=$((INTERVAL - elapsed))
  if [ "$sleep_for" -gt 0 ]; then
    sleep "$sleep_for"
  fi
done
