#!/usr/bin/env bash
# =====================================================================
# 按 pipeline.name 停止 Flink 作业
# 用法: ./stop_flink_sql.sh "pg-debezium-kafka-to-doris"
#   FLINK_HOME=/opt/flink  (环境变量可覆盖)
# =====================================================================
set -euo pipefail

FLINK_HOME="${FLINK_HOME:-/opt/flink}"
JOB_NAME="${1:?用法: ./stop_flink_sql.sh <pipeline.name>}"

if [[ ! -x "$FLINK_HOME/bin/flink" ]]; then
  echo "找不到 Flink: $FLINK_HOME/bin/flink (可设 FLINK_HOME)" >&2
  exit 1
fi

JOB_ID="$("$FLINK_HOME/bin/flink" list 2>/dev/null | grep "$JOB_NAME" | awk '{print $1}' | head -1)"
if [[ -z "$JOB_ID" ]]; then
  echo "未找到运行中的作业: $JOB_NAME" >&2
  exit 1
fi

echo "停止作业 $JOB_NAME (jobid=$JOB_ID)"
"$FLINK_HOME/bin/flink" cancel "$JOB_ID"
