#!/usr/bin/env bash
# =====================================================================
# Flink 结构变化自动修复(定时/事件驱动入口)
# 对 auto_repair=true 的作业: 监控发现结构变化 -> savepoint 停止 ->
# 对齐 Doris -> 复核 -> 从 savepoint 恢复, 数据不丢
#
# 用法:
#   ./tools/run_flink_repair.sh
#
# crontab 每 10 分钟(或调度中心定时任务):
#   */10 * * * * cd /Users/kgt/code/metadata-django && \
#     python3 manage.py flink_sync --auto-repair >> logs/flink_repair.log 2>&1
# =====================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

mkdir -p logs
PYTHON="${PYTHON:-python3}"

echo "[$(date '+%F %T')] Flink auto-repair 开始"
"$PYTHON" manage.py flink_sync --auto-repair 2>&1 | tee -a logs/flink_repair.log
RC=${PIPESTATUS[0]}
echo "[$(date '+%F %T')] Flink auto-repair 结束 exit=$RC"
exit $RC
