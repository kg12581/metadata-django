#!/usr/bin/env bash
# =====================================================================
# 每日定时执行: 指定表的 MySQL -> Doris 表结构同步
#
# 默认执行 DDL(--apply); 如需只预览:
#   SCHEMA_SYNC_APPLY=0 ./tools/run_schema_sync.sh
#
# crontab 示例(每天 03:00):
#   0 3 * * * /Users/kgt/code/metadata-django/tools/run_schema_sync.sh \
#     >> /Users/kgt/code/metadata-django/logs/cron_schema_sync.log 2>&1
# =====================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

if [[ -f "$PROJECT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$PROJECT_DIR/.env"
  set +a
fi

PYTHON="${PYTHON:-python3}"

LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/schema_sync_$(date +%F).log"

# 读取任务配置 tools/schema_sync_task.json(环境变量可覆盖)
TASK_JSON="$PROJECT_DIR/tools/schema_sync_task.json"
TASK_DATABASE="ai_chatbot"
TASK_TABLES="analytics_event"
TASK_DORIS_DATABASE="test_db"
TASK_APPLY=1
if [[ -f "$TASK_JSON" ]]; then
  TASK_DATABASE="$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("database","ai_chatbot"))' "$TASK_JSON")"
  TASK_TABLES="$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("tables","analytics_event"))' "$TASK_JSON")"
  TASK_DORIS_DATABASE="$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("doris_database","test_db"))' "$TASK_JSON")"
  TASK_APPLY="$("$PYTHON" -c 'import json,sys; print(1 if json.load(open(sys.argv[1])).get("apply",True) else 0)' "$TASK_JSON")"
fi

DATABASE="${SCHEMA_SYNC_DATABASE:-$TASK_DATABASE}"
TABLES="${SCHEMA_SYNC_TABLES:-$TASK_TABLES}"
DORIS_DATABASE="${SCHEMA_SYNC_DORIS_DATABASE:-$TASK_DORIS_DATABASE}"
APPLY="${SCHEMA_SYNC_APPLY:-$TASK_APPLY}"   # 1=执行 DDL, 0=仅预览

ARGS=(--database "$DATABASE" --tables "$TABLES" --doris-database "$DORIS_DATABASE")
if [[ "$APPLY" == "1" ]]; then
  ARGS+=(--apply)
fi

echo "[$(date '+%F %T')] 结构同步开始: $DATABASE [$TABLES] -> $DORIS_DATABASE (apply=$APPLY)"
"$PYTHON" manage.py schema_sync "${ARGS[@]}" >> "$LOG_FILE" 2>&1
RC=$?
echo "[$(date '+%F %T')] 结构同步结束: exit=$RC, 日志=$LOG_FILE"
exit $RC
