#!/usr/bin/env python3
"""PostgreSQL Debezium -> Kafka -> Doris 每日 T+1 增量 ETL。

流程:
  1. 从 Kafka 消费 Debezium 变更事件(topic 形如 <prefix>.<schema>.<table>,
     例如 cdcpg.public.orders), 消息格式为 Debezium JSON
  2. 按事件时间(source.ts_ms / ts_ms)过滤出指定日期(T-1)一天的数据
  3. 增量写入 Doris(Unique Key 模型):
       op=c/r/u  -> INSERT ... ON DUPLICATE KEY UPDATE (upsert)
       op=d      -> DELETE BY 主键
       op=t      -> TRUNCATE TABLE
  4. 提交 Kafka offset, 下次调度从断点继续

用法:
  python etl/etl_kafka_doris.py [--date 2026-08-31] [--dry-run] [--replay]

配置优先级: 环境变量 > etl/config.json > 内置默认值
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


# ---------------------------------------------------------------- 配置

def load_config() -> dict:
    config = {
        "kafka_bootstrap_servers": "192.168.3.100:9092",
        "kafka_group_id": "etl_doris_pg_debezium_t1",
        "kafka_topics": ["cdcpg.public.orders"],
        "kafka_idle_timeout": 30,
        "kafka_max_runtime": 7200,
        "timezone": "Asia/Shanghai",
        "doris_host": "192.168.3.100",
        "doris_port": 9030,
        "doris_user": "root",
        "doris_password": "",
        "doris_database": "test_db",
        "batch_size": 500,
        "topics": {},  # topic -> {doris_database, doris_table, primary_keys}
    }
    if CONFIG_PATH.exists():
        file_config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        for key in ("kafka_bootstrap_servers", "kafka_group_id", "kafka_topics",
                    "kafka_idle_timeout", "kafka_max_runtime", "timezone",
                    "doris_host", "doris_port", "doris_user", "doris_password",
                    "doris_database", "batch_size", "topics"):
            if key in file_config and file_config[key] not in (None, ""):
                config[key] = file_config[key]

    env_map = {
        "KAFKA_BOOTSTRAP_SERVERS": "kafka_bootstrap_servers",
        "KAFKA_GROUP_ID": "kafka_group_id",
        "KAFKA_TOPICS": "kafka_topics",
        "KAFKA_IDLE_TIMEOUT": "kafka_idle_timeout",
        "KAFKA_MAX_RUNTIME": "kafka_max_runtime",
        "ETL_TIMEZONE": "timezone",
        "DORIS_HOST": "doris_host",
        "DORIS_PORT": "doris_port",
        "DORIS_USER": "doris_user",
        "DORIS_PASSWORD": "doris_password",
        "DORIS_DATABASE": "doris_database",
    }
    for env_key, config_key in env_map.items():
        value = os.environ.get(env_key)
        if value:
            if config_key == "kafka_topics":
                config[config_key] = [t.strip() for t in value.split(",") if t.strip()]
            elif config_key in ("kafka_idle_timeout", "kafka_max_runtime", "batch_size", "doris_port"):
                config[config_key] = int(value)
            else:
                config[config_key] = value.strip()
    return config


def parse_args(config: dict) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="消费 Kafka(PG Debezium) 一天的数据, 增量写入 Doris (T+1)"
    )
    default_date = (datetime.now(ZoneInfo(config["timezone"])) - timedelta(days=1)).strftime("%F")
    parser.add_argument("--date", default=default_date, help="处理日期 T-1 (YYYY-MM-DD), 默认昨天")
    parser.add_argument("--dry-run", action="store_true", help="只消费统计, 不写 Doris")
    parser.add_argument("--replay", action="store_true", help="用全新消费组从 earliest 重放(用于补数)")
    parser.add_argument("--topics", default=None, help="覆盖 topic 列表(逗号分隔)")
    parser.add_argument("--group-id", default=None, help="覆盖 Kafka 消费组")
    parser.add_argument("--bootstrap-servers", default=None, help="覆盖 Kafka 地址")
    parser.add_argument("--doris-database", default=None, help="覆盖 Doris 目标库")
    parser.add_argument("--idle-timeout", type=int, default=None, help="无新消息多久后结束(秒)")
    parser.add_argument("--max-runtime", type=int, default=None, help="最多消费时长(秒)")
    return parser.parse_args()


# ---------------------------------------------------------------- 日期窗口

def date_window_ms(date_str: str, tz_name: str) -> tuple[int, int]:
    tz = ZoneInfo(tz_name)
    start = datetime.fromisoformat(f"{date_str}T00:00:00").replace(tzinfo=tz)
    end = start + timedelta(days=1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


# ---------------------------------------------------------------- Debezium 解析

def parse_message(value_raw, key_raw=None) -> dict | None:
    """解析 Debezium 消息, 返回 {op, before, after, ts_ms, key_payload}。"""
    if not value_raw:
        return None
    try:
        value = json.loads(value_raw) if isinstance(value_raw, (bytes, str)) else value_raw
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(value, dict):
        return None

    payload = value.get("payload")
    if not isinstance(payload, dict):
        payload = value  # 兼容直接就是 payload 的消息

    before = payload.get("before")
    after = payload.get("after")
    before = before if isinstance(before, dict) else None
    after = after if isinstance(after, dict) else None

    source = payload.get("source")
    if not isinstance(source, dict):
        source = {}
    ts_ms = payload.get("ts_ms") or source.get("ts_ms")

    key_payload = None
    if key_raw:
        try:
            key = json.loads(key_raw) if isinstance(key_raw, (bytes, str)) else key_raw
            kp = key.get("payload") if isinstance(key, dict) else None
            if isinstance(kp, dict):
                key_payload = kp
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "op": payload.get("op", ""),
        "before": before,
        "after": after,
        "ts_ms": ts_ms,
        "key_payload": key_payload,
    }


def resolve_target(config: dict, topic: str) -> tuple[str, str, list[str]]:
    entry = config.get("topics", {}).get(topic, {}) or {}
    database = entry.get("doris_database") or config.get("doris_database") or "test_db"
    table = entry.get("doris_table") or topic.rsplit(".", 1)[-1]
    primary_keys = list(entry.get("primary_keys") or [])
    return database, table, primary_keys


def to_db_value(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def quote(name: str) -> str:
    return "`" + str(name).replace("`", "``") + "`"


# ---------------------------------------------------------------- Doris 写入

class DorisWriter:
    def __init__(self, config: dict):
        self.config = config
        self.connection = None
        self.upserts: dict[tuple, list[tuple]] = {}
        self.deletes: dict[tuple, list[tuple]] = {}
        self.batch_size = config.get("batch_size", 500)

    def _connect(self):
        if self.connection is None:
            import pymysql
            self.connection = pymysql.connect(
                host=self.config["doris_host"],
                port=self.config["doris_port"],
                user=self.config["doris_user"],
                password=self.config["doris_password"],
                charset="utf8mb4",
                autocommit=True,
                connect_timeout=10,
            )
        return self.connection

    def add_upsert(self, database: str, table: str, row: dict):
        columns = tuple(row.keys())
        key = ("upsert", database, table, columns)
        self.upserts.setdefault(key, []).append(tuple(to_db_value(row[c]) for c in columns))
        self._maybe_flush()

    def add_delete(self, database: str, table: str, pk_columns: list[str], values: dict):
        if not pk_columns:
            return
        columns = tuple(pk_columns)
        key = ("delete", database, table, columns)
        self.deletes.setdefault(key, []).append(tuple(to_db_value(values[c]) for c in columns))
        self._maybe_flush()

    def _maybe_flush(self):
        if sum(len(rows) for rows in self.upserts.values()) >= self.batch_size:
            self.flush_upserts()
        if sum(len(rows) for rows in self.deletes.values()) >= self.batch_size:
            self.flush_deletes()

    def flush_upserts(self):
        if not self.upserts:
            return
        cursor = self._connect().cursor()
        try:
            for (_, database, table, columns), rows in self.upserts.items():
                col_sql = ", ".join(quote(c) for c in columns)
                update_sql = ", ".join(f"{quote(c)}=VALUES({quote(c)})" for c in columns)
                sql = (
                    f"INSERT INTO {quote(database)}.{quote(table)} ({col_sql}) "
                    f"VALUES ({', '.join(['%s'] * len(columns))}) "
                    f"ON DUPLICATE KEY UPDATE {update_sql}"
                )
                cursor.executemany(sql, rows)
        finally:
            cursor.close()
        self.upserts.clear()

    def flush_deletes(self):
        if not self.deletes:
            return
        cursor = self._connect().cursor()
        try:
            for (_, database, table, columns), rows in self.deletes.items():
                where_sql = " AND ".join(f"{quote(c)}=%s" for c in columns)
                sql = f"DELETE FROM {quote(database)}.{quote(table)} WHERE {where_sql}"
                cursor.executemany(sql, rows)
        finally:
            cursor.close()
        self.deletes.clear()

    def truncate(self, database: str, table: str):
        cursor = self._connect().cursor()
        try:
            cursor.execute(f"TRUNCATE TABLE {quote(database)}.{quote(table)}")
        finally:
            cursor.close()

    def close(self):
        try:
            self.flush_upserts()
            self.flush_deletes()
        finally:
            if self.connection is not None:
                self.connection.close()
                self.connection = None


# ---------------------------------------------------------------- 主流程

def consume_and_apply(config: dict, args: argparse.Namespace) -> dict:
    from kafka import KafkaConsumer

    start_ms, end_ms = date_window_ms(args.date, config["timezone"])
    topics = [t.strip() for t in args.topics.split(",")] if args.topics else config["kafka_topics"]
    group_id = args.group_id or config["kafka_group_id"]
    if args.replay:
        group_id = f"{group_id}_replay_{args.date.replace('-', '')}"
    idle_timeout = args.idle_timeout or config["kafka_idle_timeout"]
    max_runtime = args.max_runtime or config["kafka_max_runtime"]
    if args.doris_database:
        config["doris_database"] = args.doris_database

    print(f"[窗口] {args.date} ({config['timezone']}) = "
          f"[{start_ms}, {end_ms}) | topics={topics} | group={group_id}")

    consumer = KafkaConsumer(
        *topics,
        bootstrap_servers=config["kafka_bootstrap_servers"],
        group_id=group_id,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        consumer_timeout_ms=5000,
        request_timeout_ms=30000,
    )

    writer = None if args.dry_run else DorisWriter(config)
    stats = {
        "consumed": 0,
        "bad_message": 0,
        "out_of_window": 0,
        "unknown_op": 0,
        "no_after": 0,
        "upsert": 0,
        "delete": 0,
        "truncate": 0,
    }
    last_active = time.time()
    deadline = time.time() + max_runtime

    try:
        while time.time() < deadline:
            batch = consumer.poll(timeout_ms=5000, max_records=1000)
            if not batch:
                if time.time() - last_active > idle_timeout:
                    print(f"[结束] 已 {idle_timeout}s 无新消息, 到达 Kafka 尾部")
                    break
                continue

            for topic_partition, records in batch.items():
                topic = topic_partition.topic
                database, table, primary_keys = resolve_target(config, topic)
                for record in records:
                    stats["consumed"] += 1
                    last_active = time.time()
                    message = parse_message(record.value, record.key)
                    if message is None:
                        stats["bad_message"] += 1
                        continue

                    ts_ms = message["ts_ms"] or record.timestamp
                    if ts_ms is None or not (start_ms <= ts_ms < end_ms):
                        stats["out_of_window"] += 1
                        continue

                    op = message["op"]
                    if op in ("c", "r", "u"):
                        if not message["after"]:
                            stats["no_after"] += 1
                            continue
                        if args.dry_run:
                            stats["upsert"] += 1
                        else:
                            writer.add_upsert(database, table, message["after"])
                            stats["upsert"] += 1
                    elif op == "d":
                        if message["key_payload"] and not primary_keys:
                            primary_keys = list(message["key_payload"].keys())
                        row = message["key_payload"] or message["before"] or {}
                        if not primary_keys and row:
                            primary_keys = list(row.keys())
                        if not primary_keys or not row:
                            stats["bad_message"] += 1
                            continue
                        if args.dry_run:
                            stats["delete"] += 1
                        else:
                            writer.add_delete(database, table, primary_keys, row)
                            stats["delete"] += 1
                    elif op == "t":
                        if not args.dry_run:
                            writer.truncate(database, table)
                        stats["truncate"] += 1
                    else:
                        stats["unknown_op"] += 1

            if writer is not None:
                writer.flush_upserts()
                writer.flush_deletes()
    finally:
        if writer is not None:
            writer.close()
        try:
            consumer.commit()
            print("[提交] Kafka offset 已提交")
        except Exception as exc:
            print(f"[警告] offset 提交失败: {exc}", file=sys.stderr)
        consumer.close()

    return stats


def main() -> int:
    config = load_config()
    args = parse_args(config)
    print(f"== ETL 启动: 处理 {args.date} 的数据 ==")
    stats = consume_and_apply(config, args)
    print(f"== ETL 完成: {json.dumps(stats, ensure_ascii=False)} ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
