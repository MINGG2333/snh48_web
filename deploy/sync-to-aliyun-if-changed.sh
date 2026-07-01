#!/bin/bash
# Run Tencent -> Aliyun sync only when source data files changed.

set -euo pipefail

STATE_FILE=${ALIYUN_SYNC_STATE_FILE:-/tmp/snh48_sync_to_aliyun.state}
LOCK_FILE=${ALIYUN_SYNC_CHANGE_LOCK_FILE:-/tmp/snh48_sync_to_aliyun_change.lock}

sources=(
  /home/snh48-fan-hub/schedule_record/chenjiayi_events.csv
  /home/snh48-fan-hub/schedule_record/schedule.csv
  /home/snh48_web/website/data/manual_events.csv
  /home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449
  /home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers
  /home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies
  /home/snh48-fan-hub/room_record/陈嘉仪_161808449/messages_shards
  /home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts
  /home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts
)

fingerprint() {
  for src in "${sources[@]}"; do
    if [ -e "$src" ]; then
      find "$src" -type f -printf '%p\t%s\t%T@\n' 2>/dev/null
    else
      printf '%s\tmissing\t0\n' "$src"
    fi
  done | sort | sha256sum | awk '{print $1}'
}

mkdir -p "$(dirname "$STATE_FILE")"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[sync-to-aliyun-if-changed][$(date '+%Y-%m-%d %H:%M:%S')] previous check still running, skipped"
  exit 0
fi

current=$(fingerprint)
previous=""
if [ -f "$STATE_FILE" ]; then
  previous=$(cat "$STATE_FILE" 2>/dev/null || true)
fi

if [ "$current" = "$previous" ]; then
  echo "[sync-to-aliyun-if-changed][$(date '+%Y-%m-%d %H:%M:%S')] no source changes, skipped"
  exit 0
fi

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
echo "[sync-to-aliyun-if-changed][$(date '+%Y-%m-%d %H:%M:%S')] source changed, syncing..."
bash "$SCRIPT_DIR/sync-to-aliyun.sh"
printf '%s\n' "$current" > "$STATE_FILE"
echo "[sync-to-aliyun-if-changed][$(date '+%Y-%m-%d %H:%M:%S')] state updated"
