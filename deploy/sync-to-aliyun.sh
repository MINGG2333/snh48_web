#!/bin/bash
# =============================================================
# 同步数据到阿里云香港服务器（cjy.我爱你）
# 在腾讯云服务器上执行，通过 SSH 密钥免密同步
# =============================================================
# 使用方式：
#   生产自动同步已改为阿里云执行 deploy/sync-from-tencent-if-changed.sh 主动拉取。
#   本脚本只作为腾讯云手动推送到阿里云的临时兜底。
#   手动执行：bash deploy/sync-to-aliyun.sh
# =============================================================

set -euo pipefail

ALIYUN=${ALIYUN:-root@8.210.188.184}
LOCK_FILE=${ALIYUN_SYNC_LOCK_FILE:-/tmp/snh48_sync_to_aliyun.lock}
if [ "${SYNC_TO_ALIYUN_LOCKED:-0}" != "1" ]; then
  if ! env SYNC_TO_ALIYUN_LOCKED=1 ALIYUN_SYNC_LOCK_FILE="$LOCK_FILE" flock -n "$LOCK_FILE" bash "$0" "$@"; then
    echo "[sync-to-aliyun][$(date '+%Y-%m-%d %H:%M:%S')] previous sync still running, skipped"
  fi
  exit 0
fi

LOG_TAG="[sync-to-aliyun][$(date '+%Y-%m-%d %H:%M:%S')]"

echo "$LOG_TAG Starting sync..."

CONTROL_DIR=$(mktemp -d "${TMPDIR:-/tmp}/snh48_aliyun_sync.XXXXXX")
CONTROL_PATH="$CONTROL_DIR/control"
cleanup() {
  ssh -S "$CONTROL_PATH" -O exit "$ALIYUN" >/dev/null 2>&1 || true
  rmdir "$CONTROL_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

ssh -M -S "$CONTROL_PATH" -fN "$ALIYUN"
SSH_MUX=(ssh -S "$CONTROL_PATH")
RSYNC_RSH="ssh -S $CONTROL_PATH"

"${SSH_MUX[@]}" "$ALIYUN" 'mkdir -p /home/snh48-fan-hub/schedule_record /home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449 /home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers /home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies /home/snh48-fan-hub/room_record/陈嘉仪_161808449/messages_shards /home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts /home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts /home/snh48_web/website/data /home/snh48_web/website/data/memories'

# 1. chenjiayi_events.csv（事件/行程主文件，网站优先读取）
rsync -az --partial -e "$RSYNC_RSH" /home/snh48-fan-hub/schedule_record/chenjiayi_events.csv "$ALIYUN:/home/snh48-fan-hub/schedule_record/chenjiayi_events.csv"
echo "$LOG_TAG chenjiayi_events.csv done"

# 2. schedule.csv（事件/行程兼容副本，旧配置和回退读取）
rsync -az --partial -e "$RSYNC_RSH" /home/snh48-fan-hub/schedule_record/schedule.csv "$ALIYUN:/home/snh48-fan-hub/schedule_record/schedule.csv"
echo "$LOG_TAG schedule.csv done"

# 3. manual_events.csv（网站手动事件，接口按请求读取）
rsync -az --partial -e "$RSYNC_RSH" /home/snh48_web/website/data/manual_events.csv "$ALIYUN:/home/snh48_web/website/data/manual_events.csv"
echo "$LOG_TAG manual_events.csv done"

# 4. memories.json（记忆页运行数据；腾讯云为写入源，阿里云为副本）
if [ -e /home/snh48_web/website/data/memories/memories.json ]; then
  rsync -az --partial -e "$RSYNC_RSH" /home/snh48_web/website/data/memories/memories.json "$ALIYUN:/home/snh48_web/website/data/memories/memories.json"
  echo "$LOG_TAG memories.json done"
else
  echo "$LOG_TAG memories.json skipped (source missing)"
fi

# 5. live_push_replays（仅同步陈嘉仪的数据）
rsync -az --delete --partial -e "$RSYNC_RSH" /home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449/ "$ALIYUN:/home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449/"
echo "$LOG_TAG live_push_replays done"

# 6. live_covers（直播封面原图）
rsync -az --delete --partial -e "$RSYNC_RSH" /home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers/ "$ALIYUN:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers/"
echo "$LOG_TAG live_covers done"

# 7. gift_replies（礼物回复页小数据）
rsync -az --delete --partial -e "$RSYNC_RSH" /home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies/ "$ALIYUN:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies/"
echo "$LOG_TAG gift_replies done"

# 8. messages_shards（房间消息页分片小数据；旧分片稳定，新消息只更新最后一个小文件和 manifest）
rsync -az --delete --partial -e "$RSYNC_RSH" /home/snh48-fan-hub/room_record/陈嘉仪_161808449/messages_shards/ "$ALIYUN:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/messages_shards/"
echo "$LOG_TAG messages_shards done"

# 9. audio_transcripts（房间消息页语音转录小数据，不同步语音原文件）
rsync -az --delete --partial -e "$RSYNC_RSH" /home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts/ "$ALIYUN:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts/"
echo "$LOG_TAG audio_transcripts done"

# 10. score_gifts（计分礼物页小数据）
rsync -az --delete --partial -e "$RSYNC_RSH" /home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts/ "$ALIYUN:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts/"
echo "$LOG_TAG score_gifts done"

if [ "${PREWARM_IMAGE_PROXY:-0}" = "1" ]; then
  PREWARM_LIMIT=${PREWARM_LIMIT:-120}
  PREWARM_WORKERS=${PREWARM_WORKERS:-8}
  case "$PREWARM_LIMIT" in ''|*[!0-9]*) echo "$LOG_TAG invalid PREWARM_LIMIT"; exit 2;; esac
  case "$PREWARM_WORKERS" in ''|*[!0-9]*) echo "$LOG_TAG invalid PREWARM_WORKERS"; exit 2;; esac
  "${SSH_MUX[@]}" "$ALIYUN" "cd /home/snh48_web && python3 script/prewarm_image_proxy.py --base-url https://cjy.xn--6qq986b3xl --limit $PREWARM_LIMIT --workers $PREWARM_WORKERS"
  echo "$LOG_TAG image proxy prewarm done"
fi

echo "$LOG_TAG All sync completed"
