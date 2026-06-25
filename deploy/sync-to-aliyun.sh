#!/bin/bash
# =============================================================
# 同步数据到阿里云香港服务器（cjy.我爱你）
# 在腾讯云服务器上执行，通过 SSH 密钥免密同步
# =============================================================
# 使用方式：
#   手动执行：bash deploy/sync-to-aliyun.sh
#   定时任务（crontab -e，每10分钟）：
#     */10 * * * * bash /home/snh48_web/deploy/sync-to-aliyun.sh >> /var/log/snh48/sync-to-aliyun.log 2>&1
# =============================================================

set -euo pipefail

ALIYUN=${ALIYUN:-root@8.210.188.184}
LOG_TAG="[sync-to-aliyun][$(date '+%Y-%m-%d %H:%M:%S')]"

echo "$LOG_TAG Starting sync..."

ssh "$ALIYUN" 'mkdir -p /home/snh48-fan-hub/schedule_record /home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449 /home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers /home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies /home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts /home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts'

# 1. schedule.csv（行程表，网站实时读取）
rsync -az --partial /home/snh48-fan-hub/schedule_record/schedule.csv "$ALIYUN:/home/snh48-fan-hub/schedule_record/schedule.csv"
echo "$LOG_TAG schedule.csv done"

# 2. live_push_replays（仅同步陈嘉仪的数据）
rsync -az --delete --partial /home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449/ "$ALIYUN:/home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449/"
echo "$LOG_TAG live_push_replays done"

# 3. live_covers（直播封面原图）
rsync -az --delete --partial /home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers/ "$ALIYUN:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers/"
echo "$LOG_TAG live_covers done"

# 4. gift_replies（礼物回复页小数据）
rsync -az --delete --partial /home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies/ "$ALIYUN:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies/"
echo "$LOG_TAG gift_replies done"

# 5. messages.csv（房间消息页完整消息 CSV）
rsync -az --partial /home/snh48-fan-hub/room_record/陈嘉仪_161808449/messages.csv "$ALIYUN:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/messages.csv"
echo "$LOG_TAG messages.csv done"

# 6. audio_transcripts（房间消息页语音转录小数据，不同步语音原文件）
rsync -az --delete --partial /home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts/ "$ALIYUN:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts/"
echo "$LOG_TAG audio_transcripts done"

# 7. score_gifts（计分礼物页小数据）
rsync -az --delete --partial /home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts/ "$ALIYUN:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts/"
echo "$LOG_TAG score_gifts done"

if [ "${PREWARM_IMAGE_PROXY:-0}" = "1" ]; then
  PREWARM_LIMIT=${PREWARM_LIMIT:-120}
  PREWARM_WORKERS=${PREWARM_WORKERS:-8}
  case "$PREWARM_LIMIT" in ''|*[!0-9]*) echo "$LOG_TAG invalid PREWARM_LIMIT"; exit 2;; esac
  case "$PREWARM_WORKERS" in ''|*[!0-9]*) echo "$LOG_TAG invalid PREWARM_WORKERS"; exit 2;; esac
  ssh "$ALIYUN" "cd /home/snh48_web && python3 script/prewarm_image_proxy.py --base-url https://cjy.xn--6qq986b3xl --limit $PREWARM_LIMIT --workers $PREWARM_WORKERS"
  echo "$LOG_TAG image proxy prewarm done"
fi

echo "$LOG_TAG All sync completed"
