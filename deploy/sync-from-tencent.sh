#!/bin/bash
# =============================================================
# 从腾讯云拉取网站必要运行数据到阿里云香港服务器（cjy.我爱你）
# 在阿里云服务器上执行，通过 SSH 连接腾讯云读取数据
# =============================================================
# 使用方式：
#   手动执行：bash deploy/sync-from-tencent.sh
#   自动同步由 deploy/sync-from-tencent-if-changed.sh 每分钟检测变化后触发
# =============================================================

set -euo pipefail

TENCENT=${TENCENT:-root@124.222.72.203}
LOCK_FILE=${TENCENT_PULL_LOCK_FILE:-/tmp/snh48_sync_from_tencent.lock}
if [ "${SYNC_FROM_TENCENT_LOCKED:-0}" != "1" ]; then
  if ! env SYNC_FROM_TENCENT_LOCKED=1 TENCENT_PULL_LOCK_FILE="$LOCK_FILE" flock -n "$LOCK_FILE" bash "$0" "$@"; then
    echo "[sync-from-tencent][$(date '+%Y-%m-%d %H:%M:%S')] previous sync still running, skipped"
  fi
  exit 0
fi

LOG_TAG="[sync-from-tencent][$(date '+%Y-%m-%d %H:%M:%S')]"

echo "$LOG_TAG Starting sync..."

mkdir -p \
  /home/snh48-fan-hub/schedule_record \
  /home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449 \
  /home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers \
  /home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies \
  /home/snh48-fan-hub/room_record/陈嘉仪_161808449/messages_shards \
  /home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts \
  /home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts \
  /home/snh48_web/website/data

CONTROL_DIR=$(mktemp -d "${TMPDIR:-/tmp}/snh48_tencent_pull.XXXXXX")
CONTROL_PATH="$CONTROL_DIR/control"
cleanup() {
  ssh -S "$CONTROL_PATH" -O exit "$TENCENT" >/dev/null 2>&1 || true
  rmdir "$CONTROL_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

ssh -M -S "$CONTROL_PATH" -fN "$TENCENT"
RSYNC_RSH="ssh -S $CONTROL_PATH"

# 1. chenjiayi_events.csv（事件/行程主文件，网站优先读取）
rsync -az --partial -e "$RSYNC_RSH" "$TENCENT:/home/snh48-fan-hub/schedule_record/chenjiayi_events.csv" /home/snh48-fan-hub/schedule_record/chenjiayi_events.csv
echo "$LOG_TAG chenjiayi_events.csv done"

# 2. schedule.csv（事件/行程兼容副本，旧配置和回退读取）
rsync -az --partial -e "$RSYNC_RSH" "$TENCENT:/home/snh48-fan-hub/schedule_record/schedule.csv" /home/snh48-fan-hub/schedule_record/schedule.csv
echo "$LOG_TAG schedule.csv done"

# 3. manual_events.csv（网站手动事件，接口按请求读取）
rsync -az --partial -e "$RSYNC_RSH" "$TENCENT:/home/snh48_web/website/data/manual_events.csv" /home/snh48_web/website/data/manual_events.csv
echo "$LOG_TAG manual_events.csv done"

# 4. live_push_replays（仅同步陈嘉仪的数据）
rsync -az --delete --partial -e "$RSYNC_RSH" "$TENCENT:/home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449/" /home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449/
echo "$LOG_TAG live_push_replays done"

# 5. live_covers（直播封面原图）
rsync -az --delete --partial -e "$RSYNC_RSH" "$TENCENT:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers/" /home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers/
echo "$LOG_TAG live_covers done"

# 6. gift_replies（礼物回复页小数据）
rsync -az --delete --partial -e "$RSYNC_RSH" "$TENCENT:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies/" /home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies/
echo "$LOG_TAG gift_replies done"

# 7. messages_shards（房间消息页分片小数据；旧分片稳定，新消息只更新最后一个小文件和 manifest）
rsync -az --delete --partial -e "$RSYNC_RSH" "$TENCENT:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/messages_shards/" /home/snh48-fan-hub/room_record/陈嘉仪_161808449/messages_shards/
echo "$LOG_TAG messages_shards done"

# 8. audio_transcripts（房间消息页语音转录小数据，不同步语音原文件）
rsync -az --delete --partial -e "$RSYNC_RSH" "$TENCENT:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts/" /home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts/
echo "$LOG_TAG audio_transcripts done"

# 9. score_gifts（计分礼物页小数据）
rsync -az --delete --partial -e "$RSYNC_RSH" "$TENCENT:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts/" /home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts/
echo "$LOG_TAG score_gifts done"

if [ "${PREWARM_IMAGE_PROXY:-0}" = "1" ]; then
  PREWARM_LIMIT=${PREWARM_LIMIT:-120}
  PREWARM_WORKERS=${PREWARM_WORKERS:-8}
  case "$PREWARM_LIMIT" in ''|*[!0-9]*) echo "$LOG_TAG invalid PREWARM_LIMIT"; exit 2;; esac
  case "$PREWARM_WORKERS" in ''|*[!0-9]*) echo "$LOG_TAG invalid PREWARM_WORKERS"; exit 2;; esac
  cd /home/snh48_web
  python3 script/prewarm_image_proxy.py --base-url https://cjy.xn--6qq986b3xl --limit "$PREWARM_LIMIT" --workers "$PREWARM_WORKERS"
  echo "$LOG_TAG image proxy prewarm done"
fi

echo "$LOG_TAG All sync completed"
