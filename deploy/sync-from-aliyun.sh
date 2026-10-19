#!/bin/bash
# =============================================================
# 从阿里云拉取"数据加工/AI 生成"派生数据回腾讯云（cjy-tencent）
# 在腾讯云服务器上执行，通过 SSH 连接阿里云读取数据
# =============================================================
# 2026-10-16 迁移拓扑：fan-hub 数据加工/AI 生成迁到阿里云
# （root@8.210.188.184），采集留腾讯云。本脚本把阿里云本地产出的派生
# 数据回流腾讯云，供腾讯云网站读取与 COS 归档；正向（采集数据去阿里云）
# 由阿里云侧 cron 运行 deploy/sync-from-tencent-if-changed.sh 拉取。
#
# 权威性与覆盖规则：
# - private_handover/移交包/行程组/ 自 2026-10-16 起转为阿里云权威，
#   腾讯云侧不再写入；该目录只经本脚本反向回流（正向 hub 组用
#   --update 防旧副本回滚）。
# - 除行程组外，正反两个方向不同步任何相同路径。
# - 所有目录同步不使用 --delete：迁移窗口内腾讯云派生服务可能仍在写，
#   避免阿里云侧尚缺的新文件被回流误删；派生目录为追加式，删除不传播
#   可接受。
# - 所有 rsync 加 --update 防回滚：迁移窗口内腾讯云本地文件可能更新，
#   只有阿里云源更新的文件才回流；切换完成后阿里云是唯一产地，
#   --update 行为等同普通镜像（删除仍不传播）。
# - 单文件源缺失时跳过，绝不删除腾讯云本地文件（本地文件可能是现役
#   权威副本）。
# - notifications/notification_events.jsonl 只落地到腾讯云
#   notifications/aliyun_relay/notification_events.jsonl；两端各自产生
#   通知事件，绝不能覆盖腾讯云本地同名文件。
# - score_gifts 排除可写业务状态 live_business_fulfillments.json 与
#   .*.lock（该状态按 doc/shared_runtime_state.md 走腾讯云权威版本化复制）。
# - 全局排除锁文件与临时文件（*.lock / *.tmp / .*.sync.*）。
#
# 使用方式：
#   手动执行：bash deploy/sync-from-aliyun.sh [derived|notify|all]
#   自动同步由 deploy/sync-from-aliyun-if-changed.sh 每分钟检测变化后触发
# =============================================================

set -euo pipefail

ALIYUN=${ALIYUN:-root@8.210.188.184}
LOCK_FILE=${ALIYUN_PULL_LOCK_FILE:-/tmp/snh48_sync_from_aliyun.lock}
SSH_OPTS=(
  -o BatchMode=yes
  -o ConnectTimeout=10
  -o ServerAliveInterval=15
  -o ServerAliveCountMax=2
)
if [ "${SYNC_FROM_ALIYUN_LOCKED:-0}" != "1" ]; then
  if ! env SYNC_FROM_ALIYUN_LOCKED=1 ALIYUN_PULL_LOCK_FILE="$LOCK_FILE" flock -n "$LOCK_FILE" bash "$0" "$@"; then
    echo "[sync-from-aliyun][$(date '+%Y-%m-%d %H:%M:%S')] previous sync still running, skipped"
  fi
  exit 0
fi

LOG_TAG="[sync-from-aliyun][$(date '+%Y-%m-%d %H:%M:%S')]"

# 单文件同步：源缺失只跳过，绝不删除腾讯云本地文件（本地可能是现役权威副本）。
sync_file_from_aliyun() {
  local source_path=$1
  local destination_path=$2
  local source_state
  if ! source_state=$(ssh "${SSH_OPTS[@]}" -S "$CONTROL_PATH" "$ALIYUN" "if [ -f '$source_path' ]; then printf present; elif [ -e '$source_path' ]; then printf invalid; else printf absent; fi"); then
    echo "$LOG_TAG unable to inspect source file: $source_path" >&2
    return 1
  fi
  case "$source_state" in
    present)
      rsync -az --update --partial -e "$RSYNC_RSH" "$ALIYUN:$source_path" "$destination_path"
      ;;
    absent)
      echo "$LOG_TAG source missing, skipped: $source_path"
      ;;
    *)
      echo "$LOG_TAG source path is not a regular file: $source_path" >&2
      return 1
      ;;
  esac
}

# 目录同步：源缺失只跳过；统一不用 --delete（见文件头规则）。
sync_dir_from_aliyun() {
  local source_dir=$1
  local destination_dir=$2
  shift 2
  if ssh "${SSH_OPTS[@]}" -S "$CONTROL_PATH" "$ALIYUN" "test -d '$source_dir'"; then
    rsync -az --update --partial --exclude='*.lock' --exclude='*.tmp' --exclude='.*.sync.*' "$@" -e "$RSYNC_RSH" "$ALIYUN:$source_dir/" "$destination_dir/"
  else
    echo "$LOG_TAG source missing, skipped: $source_dir"
  fi
}

if [ "$#" -eq 0 ]; then
  SYNC_GROUPS=(derived notify)
else
  SYNC_GROUPS=("$@")
fi

sync_derived=0
sync_notify=0
for group in "${SYNC_GROUPS[@]}"; do
  case "$group" in
    derived) sync_derived=1 ;;
    notify) sync_notify=1 ;;
    all) sync_derived=1; sync_notify=1 ;;
    *) echo "$LOG_TAG unknown sync group: $group"; exit 2 ;;
  esac
done

echo "$LOG_TAG Starting sync groups=$(IFS=,; echo "${SYNC_GROUPS[*]}")..."

mkdir -p \
  /home/snh48-fan-hub/schedule_record/backups \
  /home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies \
  /home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts \
  /home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts \
  /home/snh48-fan-hub/room_record/pk_scores \
  /home/snh48-fan-hub/flip_data/web \
  /home/snh48-fan-hub/flip_data/audio \
  /home/snh48-fan-hub/flip_data/video \
  /home/snh48-fan-hub/notifications/codex_runs \
  /home/snh48-fan-hub/notifications/aliyun_relay \
  "/home/snh48-fan-hub/private_handover/移交包/行程组"

CONTROL_DIR=$(mktemp -d "${TMPDIR:-/tmp}/snh48_aliyun_pull.XXXXXX")
CONTROL_PATH="$CONTROL_DIR/control"
cleanup() {
  ssh "${SSH_OPTS[@]}" -S "$CONTROL_PATH" -O exit "$ALIYUN" >/dev/null 2>&1 || true
  rmdir "$CONTROL_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

ssh "${SSH_OPTS[@]}" -M -S "$CONTROL_PATH" -fN "$ALIYUN"
RSYNC_RSH="ssh -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 -S $CONTROL_PATH"

if [ "$sync_derived" -eq 1 ]; then
  # D1. 事件/行程 CSV（阿里云产出，回流供腾讯云网站与归档读取）
  sync_file_from_aliyun /home/snh48-fan-hub/schedule_record/chenjiayi_events.csv /home/snh48-fan-hub/schedule_record/chenjiayi_events.csv
  sync_file_from_aliyun /home/snh48-fan-hub/schedule_record/chenjiayi_milestones.csv /home/snh48-fan-hub/schedule_record/chenjiayi_milestones.csv
  sync_file_from_aliyun /home/snh48-fan-hub/schedule_record/schedule.csv /home/snh48-fan-hub/schedule_record/schedule.csv
  # D1b. 行程管线状态与校对报告（2026-10-17 起退出 git，随本组回流）
  sync_file_from_aliyun /home/snh48-fan-hub/schedule_record/automaintenance_state.json /home/snh48-fan-hub/schedule_record/automaintenance_state.json
  sync_file_from_aliyun /home/snh48-fan-hub/schedule_record/reconcile_state.json /home/snh48-fan-hub/schedule_record/reconcile_state.json
  sync_file_from_aliyun "/home/snh48-fan-hub/schedule_record/人工分析记录/公演场次权威校对_latest.md" "/home/snh48-fan-hub/schedule_record/人工分析记录/公演场次权威校对_latest.md"
  echo "$LOG_TAG schedule CSVs done"

  # D2. schedule_record/backups（阿里云自动维护备份回流归档）
  sync_dir_from_aliyun /home/snh48-fan-hub/schedule_record/backups /home/snh48-fan-hub/schedule_record/backups
  echo "$LOG_TAG schedule_record/backups done"

  # D3. 房间派生数据（礼物回复、语音转录）
  sync_dir_from_aliyun /home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies /home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies
  echo "$LOG_TAG gift_replies done"
  sync_dir_from_aliyun /home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts /home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts
  echo "$LOG_TAG audio_transcripts done"

  # D4. score_gifts（排除可写业务状态与采集锁：live_business_fulfillments.json
  # 走腾讯云权威版本化复制，不随本组回流）
  sync_dir_from_aliyun /home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts /home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts \
    --exclude='.*.lock' --exclude='live_business_fulfillments.json'
  echo "$LOG_TAG score_gifts done"

  # D5. pk_scores（房间计分 PK 派生小数据）
  sync_dir_from_aliyun /home/snh48-fan-hub/room_record/pk_scores /home/snh48-fan-hub/room_record/pk_scores
  echo "$LOG_TAG pk_scores done"

  # D6. flip_data/audio、video（账号级翻牌媒体）
  sync_dir_from_aliyun /home/snh48-fan-hub/flip_data/audio /home/snh48-fan-hub/flip_data/audio
  echo "$LOG_TAG flip_data/audio done"
  sync_dir_from_aliyun /home/snh48-fan-hub/flip_data/video /home/snh48-fan-hub/flip_data/video
  echo "$LOG_TAG flip_data/video done"

  # D7. flip_data/web（媒体到齐后 accounts.json 最后原子提交，避免网站读到半个发布包）
  mkdir -p /home/snh48-fan-hub/flip_data/web
  if ssh "${SSH_OPTS[@]}" -S "$CONTROL_PATH" "$ALIYUN" 'test -d /home/snh48-fan-hub/flip_data/web'; then
    FLIP_WEB_SOURCE="$ALIYUN:/home/snh48-fan-hub/flip_data/web/"
    FLIP_WEB_DEST="/home/snh48-fan-hub/flip_data/web"
    FLIP_ACCOUNTS_TMP="$FLIP_WEB_DEST/.accounts.json.sync.$$"
    rsync -az --update --partial --delay-updates --exclude='/accounts.json' --exclude='*.tmp' --exclude='.*.sync.*' --exclude='*.lock' -e "$RSYNC_RSH" "$FLIP_WEB_SOURCE" "$FLIP_WEB_DEST/"
    if ssh "${SSH_OPTS[@]}" -S "$CONTROL_PATH" "$ALIYUN" 'test -f /home/snh48-fan-hub/flip_data/web/accounts.json'; then
      rsync -az --partial -e "$RSYNC_RSH" "${FLIP_WEB_SOURCE}accounts.json" "$FLIP_ACCOUNTS_TMP"
      # 与 --update 等效：本地副本更新时保留本地（迁移窗口防回滚）
      if [ ! -e "$FLIP_WEB_DEST/accounts.json" ] || [ "$FLIP_ACCOUNTS_TMP" -nt "$FLIP_WEB_DEST/accounts.json" ]; then
        mv -f "$FLIP_ACCOUNTS_TMP" "$FLIP_WEB_DEST/accounts.json"
      else
        rm -f -- "$FLIP_ACCOUNTS_TMP"
        echo "$LOG_TAG flip_data/web accounts.json local copy newer, kept"
      fi
    fi
    echo "$LOG_TAG flip_data/web done"
  else
    echo "$LOG_TAG flip_data/web skipped (source missing)"
  fi

  # D8. 小助理行程草稿状态
  sync_file_from_aliyun /home/snh48-fan-hub/notifications/assistant_schedule_draft_state.json /home/snh48-fan-hub/notifications/assistant_schedule_draft_state.json
  echo "$LOG_TAG assistant_schedule_draft_state done"

  # D9. 行程组稿件（xlsx 与小助理稿件反向回流；2026-10-16 起阿里云权威，
  # 腾讯云不再写入；仅此子目录，移交包其余子目录不回流）
  sync_dir_from_aliyun "/home/snh48-fan-hub/private_handover/移交包/行程组" "/home/snh48-fan-hub/private_handover/移交包/行程组"
  echo "$LOG_TAG 行程组 done"
fi

if [ "$sync_notify" -eq 1 ]; then
  # N1. codex_runs（阿里云 codex 运行记录，回流供腾讯云侧 COS 归档）
  sync_dir_from_aliyun /home/snh48-fan-hub/notifications/codex_runs /home/snh48-fan-hub/notifications/codex_runs
  echo "$LOG_TAG codex_runs done"

  # N2. 阿里云通知事件总线中继：落地 aliyun_relay 子目录，
  # 绝不覆盖腾讯云本地 notifications/notification_events.jsonl
  sync_file_from_aliyun /home/snh48-fan-hub/notifications/notification_events.jsonl /home/snh48-fan-hub/notifications/aliyun_relay/notification_events.jsonl
  echo "$LOG_TAG notification_events relay done"

  # N3. xlsx 云文档代推 outbox（阿里云 automaintenance 写请求，腾讯云
  # xlsx-push-relay.timer 校验 md5 后代推飞书云文档；relay 按 md5 幂等）
  sync_file_from_aliyun /home/snh48-fan-hub/notifications/xlsx_push_request.json /home/snh48-fan-hub/notifications/xlsx_push_request.json
  echo "$LOG_TAG xlsx_push_request done"
fi

echo "$LOG_TAG All sync completed"
