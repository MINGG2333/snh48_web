#!/bin/bash
# =============================================================
# 从腾讯云拉取网站必要运行数据到阿里云香港服务器（cjy.我爱你）
# 在阿里云服务器上执行，通过 SSH 连接腾讯云读取数据
# =============================================================
# 2026-10-16 迁移拓扑：fan-hub 数据加工/AI 生成迁到阿里云，采集留腾讯云。
# - 派生数据（schedule_record 三个 CSV、gift_replies、audio_transcripts、
#   score_gifts、flip_data/{web,audio,video}）转为阿里云本地产出，不再正向
#   拉取（继续拉会覆盖阿里云新数据）；阿里云产出经腾讯云侧
#   deploy/sync-from-aliyun.sh 反向回流。
# - 新增 hub 组：fan-hub 自动化在阿里云运行所需的输入（微博/B站清单、
#   管理员反馈中心、社交事件队列、口袋48账号配置、行程组稿件）。
#   hub 组含 Token/账号配置，不套用网站组只读权限，保持源端 root 权限。
# 使用方式：
#   手动执行：bash deploy/sync-from-tencent.sh [core|dynamic|hub|all]
#   自动同步由 deploy/sync-from-tencent-if-changed.sh 每分钟检测变化后触发
# =============================================================

set -euo pipefail

TENCENT=${TENCENT:-root@124.222.72.203}
LOCK_FILE=${TENCENT_PULL_LOCK_FILE:-/tmp/snh48_sync_from_tencent.lock}
SSH_OPTS=(
  -o BatchMode=yes
  -o ConnectTimeout=10
  -o ServerAliveInterval=15
  -o ServerAliveCountMax=2
)
if [ "${SYNC_FROM_TENCENT_LOCKED:-0}" != "1" ]; then
  if ! env SYNC_FROM_TENCENT_LOCKED=1 TENCENT_PULL_LOCK_FILE="$LOCK_FILE" flock -n "$LOCK_FILE" bash "$0" "$@"; then
    echo "[sync-from-tencent][$(date '+%Y-%m-%d %H:%M:%S')] previous sync still running, skipped"
  fi
  exit 0
fi

LOG_TAG="[sync-from-tencent][$(date '+%Y-%m-%d %H:%M:%S')]"
RSYNC_WEB_READ_OPTS=(--chown=root:snh48-web --chmod=D750,F640)

if ! getent group snh48-web >/dev/null; then
  echo "$LOG_TAG required group snh48-web is missing"
  exit 1
fi

sync_file_from_tencent() {
  local source_path=$1
  local destination_path=$2
  local source_state
  if ! source_state=$(ssh "${SSH_OPTS[@]}" -S "$CONTROL_PATH" "$TENCENT" "if [ -f '$source_path' ]; then printf present; elif [ -e '$source_path' ]; then printf invalid; else printf absent; fi"); then
    echo "$LOG_TAG unable to inspect source file: $source_path" >&2
    return 1
  fi
  case "$source_state" in
    present)
      rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --partial -e "$RSYNC_RSH" "$TENCENT:$source_path" "$destination_path"
      ;;
    absent)
      # A single-file rsync does not remove a missing destination.  Make the
      # deletion explicit after a successful source-side existence check.
      echo "$LOG_TAG source missing, removing destination: $destination_path"
      if [ -d "$destination_path" ]; then
        echo "$LOG_TAG destination is a directory: $destination_path" >&2
        return 1
      fi
      rm -f -- "$destination_path"
      ;;
    *)
      echo "$LOG_TAG source path is not a regular file: $source_path" >&2
      return 1
      ;;
  esac
}

# hub 组单文件同步：与 sync_file_from_tencent 相同的显式存在性检查语义，
# 但保持源端权限/属主（hub 数据含 Token/账号配置，不暴露给网站进程）。
sync_hub_file_from_tencent() {
  local source_path=$1
  local destination_path=$2
  local source_state
  if ! source_state=$(ssh "${SSH_OPTS[@]}" -S "$CONTROL_PATH" "$TENCENT" "if [ -f '$source_path' ]; then printf present; elif [ -e '$source_path' ]; then printf invalid; else printf absent; fi"); then
    echo "$LOG_TAG unable to inspect source file: $source_path" >&2
    return 1
  fi
  case "$source_state" in
    present)
      rsync -az --partial -e "$RSYNC_RSH" "$TENCENT:$source_path" "$destination_path"
      ;;
    absent)
      echo "$LOG_TAG source missing, removing destination: $destination_path"
      if [ -d "$destination_path" ]; then
        echo "$LOG_TAG destination is a directory: $destination_path" >&2
        return 1
      fi
      rm -f -- "$destination_path"
      ;;
    *)
      echo "$LOG_TAG source path is not a regular file: $source_path" >&2
      return 1
      ;;
  esac
}

remove_retired_local_file() {
  local destination_path=$1
  if [ -d "$destination_path" ]; then
    echo "$LOG_TAG retired path is a directory: $destination_path" >&2
    return 1
  fi
  rm -f -- "$destination_path"
}

if [ "$#" -eq 0 ]; then
  SYNC_GROUPS=(core dynamic hub)
else
  SYNC_GROUPS=("$@")
fi

sync_core=0
sync_dynamic=0
sync_hub=0
for group in "${SYNC_GROUPS[@]}"; do
  case "$group" in
    core) sync_core=1 ;;
    dynamic) sync_dynamic=1 ;;
    hub) sync_hub=1 ;;
    all) sync_core=1; sync_dynamic=1; sync_hub=1 ;;
    *) echo "$LOG_TAG unknown sync group: $group"; exit 2 ;;
  esac
done

echo "$LOG_TAG Starting sync groups=$(IFS=,; echo "${SYNC_GROUPS[*]}")..."

install -d -o root -g snh48-web -m 0750 \
  /home/snh48-fan-hub/schedule_record \
  /home/snh48-fan-hub/social_record/timeline \
  /home/snh48-fan-hub/live_record/陈嘉仪_161808449 \
  /home/snh48-fan-hub/performance_record/陈嘉仪_161808449 \
  /home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers \
  /home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies \
  /home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts \
  /home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts \
  /home/snh48-fan-hub/room_record/陈嘉仪_161808449/room_voice_replays \
  /home/snh48-fan-hub/flip_data/web \
  /home/snh48-fan-hub/flip_data/audio \
  /home/snh48-fan-hub/flip_data/video \
  /home/snh48-fan-hub/social_record/fan_counts
# hub 组目标目录：fan-hub 自动化自用（含 Token/账号配置），不走网站组权限
install -d -o root -g root -m 0755 \
  /home/snh48-fan-hub/social_record/weibo \
  /home/snh48-fan-hub/social_record/bilibili \
  /home/snh48-fan-hub/notifications \
  /home/snh48-fan-hub/private_handover/移交包/行程组
install -d -o root -g root -m 0700 \
  /home/snh48-fan-hub/config
mkdir -p \
  /home/snh48_web/website/data \
  /home/snh48_web/website/data/memories

# The manual timeline endpoint was removed.  Remove an old public-node copy;
# this is deliberately outside the shared-state and fan-hub data contracts.
remove_retired_local_file /home/snh48_web/website/data/manual_events.csv

CONTROL_DIR=$(mktemp -d "${TMPDIR:-/tmp}/snh48_tencent_pull.XXXXXX")
CONTROL_PATH="$CONTROL_DIR/control"
cleanup() {
  ssh "${SSH_OPTS[@]}" -S "$CONTROL_PATH" -O exit "$TENCENT" >/dev/null 2>&1 || true
  rmdir "$CONTROL_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

ssh "${SSH_OPTS[@]}" -M -S "$CONTROL_PATH" -fN "$TENCENT"
RSYNC_RSH="ssh -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 -S $CONTROL_PATH"

if [ "$sync_core" -eq 1 ]; then
  # 2026-10-16 迁移：chenjiayi_events.csv / chenjiayi_milestones.csv /
  # schedule.csv 转为阿里云本地产出，不再正向拉取（继续拉会覆盖阿里云新
  # 数据）；阿里云产出经腾讯云侧 deploy/sync-from-aliyun.sh 反向回流。

  # 1. lightweight authored Weibo/Douyin timeline data; no raw social CSV/Cookie is synced
  sync_file_from_tencent /home/snh48-fan-hub/social_record/timeline/chenjiayi_social_timeline.json /home/snh48-fan-hub/social_record/timeline/chenjiayi_social_timeline.json
  echo "$LOG_TAG social timeline done"

  # 2. live_record（仅同步陈嘉仪的数据）
  sync_file_from_tencent /home/snh48-fan-hub/live_record/live_index.csv /home/snh48-fan-hub/live_record/live_index.csv
  echo "$LOG_TAG live_index.csv done"
  # Website playback uses official m3u8 URLs; local capture videos are large
  # backups and are intentionally excluded from the cross-cloud web dataset.
  rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --delete --partial --exclude='live.ts' --exclude='live.capture.ts' -e "$RSYNC_RSH" "$TENCENT:/home/snh48-fan-hub/live_record/陈嘉仪_161808449/" /home/snh48-fan-hub/live_record/陈嘉仪_161808449/
  echo "$LOG_TAG live_record done"

  # Chen Jiayi participating performances: public interaction text only.
  # Keep the collector state, credentials, backup staging and media out of Aliyun.
  rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --partial --delay-updates \
    --include='*/' --include='*.json' --include='*.jsonl' --include='*.csv' --include='*.lrc' --exclude='*' \
    -e "$RSYNC_RSH" "$TENCENT:/home/snh48-fan-hub/performance_record/陈嘉仪_161808449/" \
    /home/snh48-fan-hub/performance_record/陈嘉仪_161808449/
  echo "$LOG_TAG performance interaction text done"

  # 3. live_covers（直播封面原图）
  rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --delete --partial -e "$RSYNC_RSH" "$TENCENT:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers/" /home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers/
  echo "$LOG_TAG live_covers done"

  # 4. 陈嘉仪直播录制之外的房间原始数据（消息、元数据和房间媒体）
  # 直播录制/下载回放视频位于 live_record，单独排除并归档 COS；房间原始
  # 数据属于用户要求的陈嘉仪完整副本，继续同步到阿里云网站节点。
  # 房间消息事实表 metadata/messages.jsonl 与月封存文件也经此组同步。
  # 排除：QChat 原始帧/影子排障文件（大且仅排障用）、封存备份、跨房间扫描
  # 产物（契约规定不进阿里云）。gift_replies/audio_transcripts/score_gifts
  # 自 2026-10-16 起为阿里云本地产出，排除保持不动，本地新文件不受 --delete
  # 影响（rsync 排除项在接收端受保护）。
  rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --delete --partial \
    --exclude='gift_replies/' \
    --exclude='audio_transcripts/' --exclude='score_gifts/' \
    --exclude='room_voice_replays/' --exclude='live_covers/' \
    --exclude='cross_room/' \
    --exclude='metadata/qchat_frames*.jsonl*' --exclude='metadata/qchat_shadow.jsonl' \
    --exclude='metadata/backups/' \
    --exclude='*.lock' --exclude='*.tmp' \
    -e "$RSYNC_RSH" "$TENCENT:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/" \
    /home/snh48-fan-hub/room_record/陈嘉仪_161808449/
  echo "$LOG_TAG chenjiayi room raw non-video data done"
fi

if [ "$sync_dynamic" -eq 1 ]; then
  # 2026-10-16 迁移：gift_replies / audio_transcripts / score_gifts /
  # flip_data/{web,audio,video} 转为阿里云本地产出，不再正向拉取；阿里云
  # 产出经腾讯云侧 deploy/sync-from-aliyun.sh 反向回流（score_gifts 的
  # 可写业务状态 live_business_fulfillments.json 仍走腾讯云权威版本化复制，
  # 反向同步同样排除）。

  # 6. room_voice_replays（内容先到，manifest 最后原子提交，避免网站读到半个发布包）
  ROOM_VOICE_SOURCE="$TENCENT:/home/snh48-fan-hub/room_record/陈嘉仪_161808449/room_voice_replays/"
  ROOM_VOICE_DEST="/home/snh48-fan-hub/room_record/陈嘉仪_161808449/room_voice_replays"
  ROOM_VOICE_MANIFEST_TMP="$ROOM_VOICE_DEST/.manifest.json.sync.$$"
  rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --partial --delay-updates --exclude='/manifest.json' -e "$RSYNC_RSH" "$ROOM_VOICE_SOURCE" "$ROOM_VOICE_DEST/"
  echo "$LOG_TAG room_voice_replays payload done"
  rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --partial -e "$RSYNC_RSH" "${ROOM_VOICE_SOURCE}manifest.json" "$ROOM_VOICE_MANIFEST_TMP"
  mv -f "$ROOM_VOICE_MANIFEST_TMP" "$ROOM_VOICE_DEST/manifest.json"
  echo "$LOG_TAG room_voice_replays manifest committed"
  rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --delete-delay --ignore-existing --exclude='/manifest.json' --exclude='/.manifest.json.sync.*' -e "$RSYNC_RSH" "$ROOM_VOICE_SOURCE" "$ROOM_VOICE_DEST/"
  echo "$LOG_TAG room_voice_replays obsolete payload cleaned"
  echo "$LOG_TAG room_voice_replays done"

  # 7. fan_counts（粉丝数记录页公开只读小数据；不同步原始社交 CSV 或 Cookie）
  if ssh -S "$CONTROL_PATH" "$TENCENT" 'test -d /home/snh48-fan-hub/social_record/fan_counts'; then
    rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --delete --partial -e "$RSYNC_RSH" "$TENCENT:/home/snh48-fan-hub/social_record/fan_counts/" /home/snh48-fan-hub/social_record/fan_counts/
    echo "$LOG_TAG fan_counts done"
  else
    echo "$LOG_TAG fan_counts skipped (source missing)"
  fi

  # 8. pocket48_ranks（口袋48榜单快照公开只读小数据；排除采集锁）
  if ssh -S "$CONTROL_PATH" "$TENCENT" 'test -d /home/snh48-fan-hub/pocket48_ranks/陈嘉仪_161808449'; then
    rsync -az "${RSYNC_WEB_READ_OPTS[@]}" --delete --partial --exclude='.*.lock' --exclude='.collector.lock' -e "$RSYNC_RSH" "$TENCENT:/home/snh48-fan-hub/pocket48_ranks/陈嘉仪_161808449/" /home/snh48-fan-hub/pocket48_ranks/陈嘉仪_161808449/
    echo "$LOG_TAG pocket48_ranks done"
  else
    echo "$LOG_TAG pocket48_ranks skipped (source missing)"
  fi
fi

if [ "$sync_hub" -eq 1 ]; then
  # hub 组：fan-hub 自动化在阿里云运行所需的输入（2026-10-16 迁移新增）。
  # 含 Token/账号配置，故意不使用 RSYNC_WEB_READ_OPTS，保持源端 root 权限。

  # H1. social_record/weibo/*.jsonl（微博监控清单；目录内转发器状态文件不同步）
  rsync -az --delete --partial \
    --include='*.jsonl' --exclude='*' \
    -e "$RSYNC_RSH" "$TENCENT:/home/snh48-fan-hub/social_record/weibo/" /home/snh48-fan-hub/social_record/weibo/
  echo "$LOG_TAG hub weibo jsonl done"

  # H2. social_record/bilibili/*.csv（B站监控清单）
  rsync -az --delete --partial \
    --include='*.csv' --exclude='*' \
    -e "$RSYNC_RSH" "$TENCENT:/home/snh48-fan-hub/social_record/bilibili/" /home/snh48-fan-hub/social_record/bilibili/
  echo "$LOG_TAG hub bilibili csv done"

  # H3. 管理员反馈中心（台式机→腾讯云→阿里云，供阿里云侧自动化消费）
  sync_hub_file_from_tencent /home/snh48-fan-hub/notifications/admin_feedback_center.md /home/snh48-fan-hub/notifications/admin_feedback_center.md
  echo "$LOG_TAG hub admin_feedback_center done"

  # H4. 社交事件队列（腾讯云社交监控产出，阿里云侧自动化消费）
  sync_hub_file_from_tencent /home/snh48-fan-hub/notifications/codex_social_event_queue.json /home/snh48-fan-hub/notifications/codex_social_event_queue.json
  echo "$LOG_TAG hub codex_social_event_queue done"

  # H5. 口袋48账号配置（含 Token，保持 root-only 权限）
  sync_hub_file_from_tencent /home/snh48-fan-hub/config/accounts.json /home/snh48-fan-hub/config/accounts.json
  sync_hub_file_from_tencent /home/snh48-fan-hub/config/koudai_token.json /home/snh48-fan-hub/config/koudai_token.json
  echo "$LOG_TAG hub pocket48 config done"

  # H6. 行程组稿件（仅此子目录）。--update 防回滚：2026-10-16 起该目录
  # 转为阿里云权威、腾讯云不再写；正向仅作迁移窗口的初始投递，阿里云侧
  # 较新的文件不会被旧副本覆盖，更新经 sync-from-aliyun.sh 反向回流。
  rsync -az --update --partial \
    --exclude='*.lock' --exclude='*.tmp' \
    -e "$RSYNC_RSH" "$TENCENT:/home/snh48-fan-hub/private_handover/移交包/行程组/" /home/snh48-fan-hub/private_handover/移交包/行程组/
  echo "$LOG_TAG hub 行程组 done"
fi

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
