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
RSYNC_WEB_READ_OPTS=(--chown=root:snh48-web --chmod=D750,F640)

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

"${SSH_MUX[@]}" "$ALIYUN" 'getent group snh48-web >/dev/null && install -d -o root -g snh48-web -m 0750 /home/snh48-fan-hub/schedule_record /home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449 /home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers /home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies /home/snh48-fan-hub/room_record/陈嘉仪_161808449/messages_shards /home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts /home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts /home/snh48-fan-hub/room_record/陈嘉仪_161808449/room_voice_replays /home/snh48-fan-hub/flip_data/web /home/snh48-fan-hub/flip_data/audio /home/snh48-fan-hub/flip_data/video && mkdir -p /home/snh48_web/website/data /home/snh48_web/website/data/memories'

# 1. chenjiayi_events.csv（事件/行程主文件，网站优先读取）
rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --partial -e "$RSYNC_RSH" /home/snh48-fan-hub/schedule_record/chenjiayi_events.csv "$ALIYUN:/home/snh48-fan-hub/schedule_record/chenjiayi_events.csv"
echo "$LOG_TAG chenjiayi_events.csv done"

# 2. schedule.csv（事件/行程兼容副本，旧配置和回退读取）
rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --partial -e "$RSYNC_RSH" /home/snh48-fan-hub/schedule_record/schedule.csv "$ALIYUN:/home/snh48-fan-hub/schedule_record/schedule.csv"
echo "$LOG_TAG schedule.csv done"

# 3. live_push_replays（仅同步陈嘉仪的数据）
rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --delete --partial -e "$RSYNC_RSH" /home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449/ "$ALIYUN:/home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449/"
echo "$LOG_TAG live_push_replays done"

# 5. live_covers（直播封面原图）
rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --delete --partial -e "$RSYNC_RSH" /home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers/ "$ALIYUN:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers/"
echo "$LOG_TAG live_covers done"

# 6. gift_replies（礼物回复页小数据）
rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --delete --partial -e "$RSYNC_RSH" /home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies/ "$ALIYUN:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies/"
echo "$LOG_TAG gift_replies done"

# 7. messages_shards（房间消息页分片小数据；旧分片稳定，新消息只更新最后一个小文件和 manifest）
rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --delete --partial -e "$RSYNC_RSH" /home/snh48-fan-hub/room_record/陈嘉仪_161808449/messages_shards/ "$ALIYUN:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/messages_shards/"
echo "$LOG_TAG messages_shards done"

# 8. audio_transcripts（房间消息页语音转录小数据，不同步语音原文件）
rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --delete --partial -e "$RSYNC_RSH" /home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts/ "$ALIYUN:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts/"
echo "$LOG_TAG audio_transcripts done"

# 9. score_gifts（只读派生小数据；可写业务状态走版本化复制）
rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --delete --partial --exclude='.*.lock' --exclude='live_business_fulfillments.json' -e "$RSYNC_RSH" /home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts/ "$ALIYUN:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts/"
echo "$LOG_TAG score_gifts done"

# 10. room_voice_replays（内容先到，manifest 最后原子提交，避免网站读到半个发布包）
ROOM_VOICE_SOURCE="/home/snh48-fan-hub/room_record/陈嘉仪_161808449/room_voice_replays"
ROOM_VOICE_DEST="/home/snh48-fan-hub/room_record/陈嘉仪_161808449/room_voice_replays"
ROOM_VOICE_MANIFEST_TMP="$ROOM_VOICE_DEST/.manifest.json.sync.$$"
rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --partial --delay-updates --exclude='/manifest.json' -e "$RSYNC_RSH" "$ROOM_VOICE_SOURCE/" "$ALIYUN:$ROOM_VOICE_DEST/"
echo "$LOG_TAG room_voice_replays payload done"
rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --partial -e "$RSYNC_RSH" "$ROOM_VOICE_SOURCE/manifest.json" "$ALIYUN:$ROOM_VOICE_MANIFEST_TMP"
"${SSH_MUX[@]}" "$ALIYUN" "mv -f '$ROOM_VOICE_MANIFEST_TMP' '$ROOM_VOICE_DEST/manifest.json'"
echo "$LOG_TAG room_voice_replays manifest committed"
rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --delete-delay --ignore-existing --exclude='/manifest.json' --exclude='/.manifest.json.sync.*' -e "$RSYNC_RSH" "$ROOM_VOICE_SOURCE/" "$ALIYUN:$ROOM_VOICE_DEST/"
echo "$LOG_TAG room_voice_replays obsolete payload cleaned"
echo "$LOG_TAG room_voice_replays done"

# 11. flip_data/audio（翻牌页本地语音依赖；不同步 metadata、Token 或配置）
if [ -d /home/snh48-fan-hub/flip_data/audio ]; then
  rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --delete --partial -e "$RSYNC_RSH" /home/snh48-fan-hub/flip_data/audio/ "$ALIYUN:/home/snh48-fan-hub/flip_data/audio/"
  echo "$LOG_TAG flip_data/audio done"
else
  echo "$LOG_TAG flip_data/audio skipped (source missing)"
fi

# 12. flip_data/video（翻牌页本地视频依赖；不同步 metadata、Token 或配置）
if [ -d /home/snh48-fan-hub/flip_data/video ]; then
  rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --delete --partial -e "$RSYNC_RSH" /home/snh48-fan-hub/flip_data/video/ "$ALIYUN:/home/snh48-fan-hub/flip_data/video/"
  echo "$LOG_TAG flip_data/video done"
else
  echo "$LOG_TAG flip_data/video skipped (source missing)"
fi

# 13. flip_data/web（媒体到齐后同步账号数据，accounts.json 最后原子提交）
if [ -d /home/snh48-fan-hub/flip_data/web ]; then
  FLIP_WEB_SOURCE="/home/snh48-fan-hub/flip_data/web"
  FLIP_WEB_DEST="/home/snh48-fan-hub/flip_data/web"
  FLIP_ACCOUNTS_TMP="$FLIP_WEB_DEST/.accounts.json.sync.$$"
  rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --partial --delay-updates --exclude='/accounts.json' --exclude='*.tmp' --exclude='.*.sync.*' -e "$RSYNC_RSH" "$FLIP_WEB_SOURCE/" "$ALIYUN:$FLIP_WEB_DEST/"
  if [ -f "$FLIP_WEB_SOURCE/accounts.json" ]; then
    rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --partial -e "$RSYNC_RSH" "$FLIP_WEB_SOURCE/accounts.json" "$ALIYUN:$FLIP_ACCOUNTS_TMP"
    "${SSH_MUX[@]}" "$ALIYUN" "mv -f '$FLIP_ACCOUNTS_TMP' '$FLIP_WEB_DEST/accounts.json'"
  fi
  rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --delete-delay --ignore-existing --exclude='/accounts.json' --exclude='*.tmp' --exclude='.*.sync.*' -e "$RSYNC_RSH" "$FLIP_WEB_SOURCE/" "$ALIYUN:$FLIP_WEB_DEST/"
  echo "$LOG_TAG flip_data/web done"
else
  echo "$LOG_TAG flip_data/web skipped (source missing)"
fi

if [ "${PREWARM_IMAGE_PROXY:-0}" = "1" ]; then
  PREWARM_LIMIT=${PREWARM_LIMIT:-120}
  PREWARM_WORKERS=${PREWARM_WORKERS:-8}
  case "$PREWARM_LIMIT" in ''|*[!0-9]*) echo "$LOG_TAG invalid PREWARM_LIMIT"; exit 2;; esac
  case "$PREWARM_WORKERS" in ''|*[!0-9]*) echo "$LOG_TAG invalid PREWARM_WORKERS"; exit 2;; esac
  "${SSH_MUX[@]}" "$ALIYUN" "cd /home/snh48_web && python3 script/prewarm_image_proxy.py --base-url https://cjy.xn--6qq986b3xl --limit $PREWARM_LIMIT --workers $PREWARM_WORKERS"
  echo "$LOG_TAG image proxy prewarm done"
fi

echo "$LOG_TAG All sync completed"
