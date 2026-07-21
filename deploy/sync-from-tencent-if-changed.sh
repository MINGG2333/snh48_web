#!/bin/bash
# Run Aliyun pull from Tencent only when Tencent source data files changed.

set -euo pipefail

TENCENT=${TENCENT:-root@124.222.72.203}
STATE_FILE=${TENCENT_PULL_STATE_FILE:-/tmp/snh48_sync_from_tencent.state}
LOCK_FILE=${TENCENT_PULL_CHANGE_LOCK_FILE:-/tmp/snh48_sync_from_tencent_change.lock}

fingerprint() {
  local group=$1
  ssh \
    -o BatchMode=yes \
    -o ConnectTimeout=10 \
    -o ServerAliveInterval=15 \
    -o ServerAliveCountMax=2 \
    "$TENCENT" 'bash -s' "$group" <<'REMOTE_FINGERPRINT'
set -euo pipefail

group=$1
case "$group" in
  core)
    sources=(
      /home/snh48-fan-hub/schedule_record/chenjiayi_events.csv
      /home/snh48-fan-hub/schedule_record/schedule.csv
      /home/snh48_web/website/data/manual_events.csv
      /home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449
      /home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers
    )
    ;;
  dynamic)
    sources=(
      /home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies
      /home/snh48-fan-hub/room_record/陈嘉仪_161808449/messages_shards
      /home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts
      /home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts
      /home/snh48-fan-hub/room_record/陈嘉仪_161808449/room_voice_replays
      /home/snh48-fan-hub/flip_data/web/flip_cards.json
      /home/snh48-fan-hub/flip_data/audio
      /home/snh48-fan-hub/flip_data/video
    )
    ;;
  *)
    echo "unknown sync group: $group" >&2
    exit 2
    ;;
esac

for src in "${sources[@]}"; do
  if [ -e "$src" ]; then
    find "$src" -type f ! -name '.*.lock' ! -name 'live_business_fulfillments.json' -printf '%p\t%s\t%T@\n' 2>/dev/null
  else
    printf '%s\tmissing\t0\n' "$src"
  fi
done | sort | sha256sum | awk '{print $1}'
REMOTE_FINGERPRINT
}

mkdir -p "$(dirname "$STATE_FILE")"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[sync-from-tencent-if-changed][$(date '+%Y-%m-%d %H:%M:%S')] previous check still running, skipped"
  exit 0
fi

groups=(core dynamic)
changed_groups=()
current_values=()

for group in "${groups[@]}"; do
  current=$(fingerprint "$group")
  previous=""
  group_state_file="${STATE_FILE}.${group}"
  if [ -f "$group_state_file" ]; then
    previous=$(cat "$group_state_file" 2>/dev/null || true)
  fi
  current_values+=("$group=$current")
  if [ "$current" != "$previous" ]; then
    changed_groups+=("$group")
  fi
done

if [ "${#changed_groups[@]}" -eq 0 ]; then
  echo "[sync-from-tencent-if-changed][$(date '+%Y-%m-%d %H:%M:%S')] no source changes, skipped"
  exit 0
fi

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
changed_csv=$(IFS=,; echo "${changed_groups[*]}")
echo "[sync-from-tencent-if-changed][$(date '+%Y-%m-%d %H:%M:%S')] source changed groups=$changed_csv, pulling..."
bash "$SCRIPT_DIR/sync-from-tencent.sh" "${changed_groups[@]}"
for item in "${current_values[@]}"; do
  group=${item%%=*}
  value=${item#*=}
  printf '%s\n' "$value" > "${STATE_FILE}.${group}"
done
echo "[sync-from-tencent-if-changed][$(date '+%Y-%m-%d %H:%M:%S')] state updated"
