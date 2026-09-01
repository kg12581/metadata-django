#!/usr/bin/env bash
# =====================================================================
# 每日 T+1 调度脚本
#   处理"昨天"一天的 Kafka(PG Debezium) 变更数据, 增量写入 Doris
#
# 用法:
#   ./etl/run_daily_t1.sh                 # 处理昨天
#   ./etl/run_daily_t1.sh 2026-08-31      # 指定日期(补数)
#
# crontab 示例(每天 01:30 执行):
#   30 1 * * * /Users/kgt/code/metadata-django/etl/run_daily_t1.sh \
#     >> /Users/kgt/code/metadata-django/logs/cron_t1.log 2>&1
# =====================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# 加载 .env(可选, 用于覆盖 KAFKA_*/DORIS_* 环境变量)
if [[ -f "$PROJECT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$PROJECT_DIR/.env"
  set +a
fi

# T-1 日期(macOS / Linux 兼容); 也可通过第一个参数指定
if [[ "$(uname)" == "Darwin" ]]; then
  T1_DATE="${1:-$(date -v-1d +%F)}"
else
  T1_DATE="${1:-$(date -d "yesterday" +%F)}"
fi

PYTHON="${PYTHON:-python3}"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/etl_${T1_DATE}.log"

echo "[$(date '+%F %T')] T+1 调度开始: 处理 $T1_DATE 的 Kafka 数据 -> Doris"
"$PYTHON" "$SCRIPT_DIR/etl_kafka_doris.py" --date "$T1_DATE" >> "$LOG_FILE" 2>&1
RC=$?
echo "[$(date '+%F %T')] T+1 调度结束: exit=$RC, 日志=$LOG_FILE"
exit $RC
