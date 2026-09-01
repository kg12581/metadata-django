#!/usr/bin/env bash
# =====================================================================
# 提交 Flink SQL 作业
# 用法: ./submit_flink_sql.sh <job.sql>
#   FLINK_HOME=/opt/flink  (环境变量可覆盖)
# =====================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FLINK_HOME="${FLINK_HOME:-/opt/flink}"
SQL_FILE="${1:?用法: ./submit_flink_sql.sh <job.sql>}"

if [[ ! -f "$SQL_FILE" ]]; then
  if [[ -f "$PROJECT_DIR/flink_sql/$SQL_FILE" ]]; then
    SQL_FILE="$PROJECT_DIR/flink_sql/$SQL_FILE"
  else
    echo "SQL 文件不存在: $SQL_FILE" >&2
    exit 1
  fi
fi

if [[ ! -x "$FLINK_HOME/bin/sql-client.sh" ]]; then
  echo "找不到 Flink sql-client: $FLINK_HOME/bin/sql-client.sh (可设 FLINK_HOME)" >&2
  exit 1
fi

LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/flink_submit_$(date +%F_%H%M%S).log"

echo "[$(date '+%F %T')] 提交作业: $SQL_FILE -> 日志 $LOG_FILE"
"$FLINK_HOME/bin/sql-client.sh" -f "$SQL_FILE" 2>&1 | tee "$LOG_FILE"
echo "[$(date '+%F %T')] 提交结束, exit=${PIPESTATUS[0]}"
exit "${PIPESTATUS[0]}"
