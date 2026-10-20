#!/bin/bash
# Run Aliyun pull from Tencent only when Tencent source data files changed.
# 2026-10-16 迁移：分组调整为 core/dynamic/hub（派生数据移出正向，详见
# sync-from-tencent.sh 头部）；阿里云产出经腾讯云侧 sync-from-aliyun 反向回流。

set -euo pipefail

TENCENT=${TENCENT:-root@124.222.72.203}
STATE_FILE=${TENCENT_PULL_STATE_FILE:-/tmp/snh48_sync_from_tencent.state}
LOCK_FILE=${TENCENT_PULL_CHANGE_LOCK_FILE:-/tmp/snh48_sync_from_tencent_change.lock}
RETIRED_LOCAL_FILES=(
  /home/snh48_web/website/data/manual_events.csv
)

cleanup_retired_local_files() {
  local path
  for path in "${RETIRED_LOCAL_FILES[@]}"; do
    if [ -d "$path" ]; then
      echo "[sync-from-tencent-if-changed][$(date '+%Y-%m-%d %H:%M:%S')] retired path is a directory: $path" >&2
      return 1
    fi
    if [ -e "$path" ]; then
      rm -f -- "$path"
      echo "[sync-from-tencent-if-changed][$(date '+%Y-%m-%d %H:%M:%S')] removed retired file: $path"
    fi
  done
}

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
  # 2026-10-16 迁移：schedule_record 三个 CSV 转为阿里云产出（反向回流），
  # 移出 core 指纹；dynamic 移除 gift_replies/audio_transcripts/score_gifts
  # 与 flip_data/{web,audio,video}（同因）；新增 hub 组。
  core)
    sources=(
      /home/snh48-fan-hub/social_record/timeline/chenjiayi_social_timeline.json
      /home/snh48-fan-hub/live_record/live_index.csv
      /home/snh48-fan-hub/live_record/陈嘉仪_161808449
      /home/snh48-fan-hub/performance_record/陈嘉仪_161808449
      /home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers
      /home/snh48-fan-hub/room_record/陈嘉仪_161808449/metadata
      /home/snh48-fan-hub/room_record/陈嘉仪_161808449/images
      /home/snh48-fan-hub/room_record/陈嘉仪_161808449/videos
      /home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio
      /home/snh48-fan-hub/room_record/陈嘉仪_161808449/expressions
      /home/snh48-fan-hub/room_record/陈嘉仪_161808449/gifts
    )
    ;;
  dynamic)
    sources=(
      /home/snh48-fan-hub/room_record/陈嘉仪_161808449/room_voice_replays
      /home/snh48-fan-hub/social_record/fan_counts
      /home/snh48-fan-hub/pocket48_ranks/陈嘉仪_161808449
    )
    ;;
  hub)
    {
      files=(
        /home/snh48-fan-hub/notifications/admin_feedback_center.md
        /home/snh48-fan-hub/notifications/codex_social_event_queue.json
        /home/snh48-fan-hub/notifications/blackboard_remote_commands.jsonl
        /home/snh48-fan-hub/config/accounts.json
        /home/snh48-fan-hub/config/koudai_token.json
      )
      for f in "${files[@]}"; do
        if [ -f "$f" ]; then
          stat -c '%n	%s	%Y' "$f"
        else
          printf '%s\tmissing\t0\n' "$f"
        fi
      done
      # 只跟踪自动化消费的清单文件；目录内转发器状态文件不进指纹
      find /home/snh48-fan-hub/social_record/weibo -maxdepth 1 -type f -name '*.jsonl' -printf '%p\t%s\t%T@\n' 2>/dev/null || true
      find /home/snh48-fan-hub/social_record/bilibili -maxdepth 1 -type f -name '*.csv' -printf '%p\t%s\t%T@\n' 2>/dev/null || true
      # 翻牌采集原始媒体（H7，供阿里云 flip_update_feedback 消费）
      for d in /home/snh48-fan-hub/flip_data/audio /home/snh48-fan-hub/flip_data/video; do
        if [ -d "$d" ]; then
          find "$d" -type f ! -name '*.lock' ! -name '*.tmp' -printf '%p\t%s\t%T@\n' 2>/dev/null
        fi
      done
      if [ -d /home/snh48-fan-hub/private_handover/移交包/行程组 ]; then
        find /home/snh48-fan-hub/private_handover/移交包/行程组 -type f ! -name '*.lock' ! -name '*.tmp' -printf '%p\t%s\t%T@\n' 2>/dev/null
      else
        printf '%s\tmissing\t0\n' /home/snh48-fan-hub/private_handover/移交包/行程组
      fi
    } | sort | sha256sum | awk '{print $1}'
    exit 0
    ;;
  *)
    echo "unknown sync group: $group" >&2
    exit 2
    ;;
esac

for src in "${sources[@]}"; do
  if [ -e "$src" ]; then
    find "$src" -type f ! -name '.*.lock' ! -name 'live_business_fulfillments.json' ! -name 'live.ts' ! -name 'live.capture.ts' ! -name 'qchat_frames*.jsonl*' ! -name 'qchat_shadow.jsonl' ! -path '*/metadata/backups/*' -printf '%p\t%s\t%T@\n' 2>/dev/null
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

groups=(core dynamic hub)
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
  cleanup_retired_local_files
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
