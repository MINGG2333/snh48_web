#!/bin/bash
# Run Tencent pull from Aliyun only when Aliyun source data files changed.
# 2026-10-16 迁移拓扑：派生数据（行程 CSV、房间派生、翻牌产物、行程组稿件、
# codex 运行记录、通知事件中继）以阿里云为产地，每分钟检测指纹后由
# deploy/sync-from-aliyun.sh 拉回腾讯云。分组：derived / notify。

set -euo pipefail

ALIYUN=${ALIYUN:-root@8.210.188.184}
STATE_FILE=${ALIYUN_PULL_STATE_FILE:-/tmp/snh48_sync_from_aliyun.state}
LOCK_FILE=${ALIYUN_PULL_CHANGE_LOCK_FILE:-/tmp/snh48_sync_from_aliyun_change.lock}

fingerprint() {
  local group=$1
  ssh \
    -o BatchMode=yes \
    -o ConnectTimeout=10 \
    -o ServerAliveInterval=15 \
    -o ServerAliveCountMax=2 \
    "$ALIYUN" 'bash -s' "$group" <<'REMOTE_FINGERPRINT'
set -euo pipefail

group=$1
case "$group" in
  derived)
    sources=(
      /home/snh48-fan-hub/schedule_record/chenjiayi_events.csv
      /home/snh48-fan-hub/schedule_record/chenjiayi_milestones.csv
      /home/snh48-fan-hub/schedule_record/schedule.csv
      /home/snh48-fan-hub/schedule_record/backups
      /home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies
      /home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts
      /home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts
      /home/snh48-fan-hub/room_record/pk_scores
      /home/snh48-fan-hub/flip_data/web
      /home/snh48-fan-hub/flip_data/audio
      /home/snh48-fan-hub/flip_data/video
      /home/snh48-fan-hub/notifications/assistant_schedule_draft_state.json
      /home/snh48-fan-hub/private_handover/移交包/行程组
    )
    ;;
  notify)
    sources=(
      /home/snh48-fan-hub/notifications/codex_runs
    )
    ;;
  *)
    echo "unknown sync group: $group" >&2
    exit 2
    ;;
esac

# 与 sync-from-aliyun.sh 同步范围保持一致：排除锁/临时/同步中间文件，
# score_gifts 的可写业务状态 live_business_fulfillments.json 不进指纹。
for src in "${sources[@]}"; do
  if [ -e "$src" ]; then
    find "$src" -type f ! -name '.*.lock' ! -name '*.lock' ! -name '*.tmp' ! -name '.*.sync.*' ! -name 'live_business_fulfillments.json' -printf '%p\t%s\t%T@\n' 2>/dev/null
  else
    printf '%s\tmissing\t0\n' "$src"
  fi
done | sort | sha256sum | awk '{print $1}'
REMOTE_FINGERPRINT
}

mkdir -p "$(dirname "$STATE_FILE")"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[sync-from-aliyun-if-changed][$(date '+%Y-%m-%d %H:%M:%S')] previous check still running, skipped"
  exit 0
fi

groups=(derived notify)
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
  echo "[sync-from-aliyun-if-changed][$(date '+%Y-%m-%d %H:%M:%S')] no source changes, skipped"
  exit 0
fi

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
changed_csv=$(IFS=,; echo "${changed_groups[*]}")
echo "[sync-from-aliyun-if-changed][$(date '+%Y-%m-%d %H:%M:%S')] source changed groups=$changed_csv, pulling..."
bash "$SCRIPT_DIR/sync-from-aliyun.sh" "${changed_groups[@]}"
for item in "${current_values[@]}"; do
  group=${item%%=*}
  value=${item#*=}
  printf '%s\n' "$value" > "${STATE_FILE}.${group}"
done
echo "[sync-from-aliyun-if-changed][$(date '+%Y-%m-%d %H:%M:%S')] state updated"
