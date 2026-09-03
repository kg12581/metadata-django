"""行数对账: MySQL/PostgreSQL 源表 与 Doris 目标表 COUNT 对比。"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_$]+$")


def _check_identifier(name: str) -> str:
    if not _IDENTIFIER_RE.match(str(name)):
        raise ValueError(f"非法表名/库名: {name}")
    return str(name)


def count_mysql_table(config: dict, database: str, table: str) -> int:
    import pymysql

    conn = pymysql.connect(
        host=config["host"],
        port=config.get("port", 3306),
        user=config.get("user", ""),
        password=config.get("password", ""),
        database=database,
        connect_timeout=10,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM `{_check_identifier(table)}`")
            return int(cursor.fetchone()[0])
    finally:
        conn.close()


def count_pg_table(config: dict, database: str, schema: str, table: str) -> int:
    import psycopg2

    conn = psycopg2.connect(
        host=config["host"],
        port=config.get("port", 5432),
        dbname=database,
        user=config.get("user", ""),
        password=config.get("password", ""),
        connect_timeout=10,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f'SELECT COUNT(*) FROM "{_check_identifier(schema)}"."{_check_identifier(table)}"'
            )
            return int(cursor.fetchone()[0])
    finally:
        conn.close()


def count_doris_table(config: dict, database: str, table: str) -> int:
    """Doris FE 走 MySQL 协议。表不存在时抛异常。"""
    import pymysql

    conn = pymysql.connect(
        host=config["host"],
        port=config.get("port", 9030),
        user=config.get("user", ""),
        password=config.get("password", ""),
        database=database,
        connect_timeout=10,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM `{_check_identifier(table)}`")
            return int(cursor.fetchone()[0])
    finally:
        conn.close()


def count_oracle_table(config: dict, service: str, table: str) -> int:
    import oracledb

    conn = oracledb.connect(
        user=config.get("user", ""),
        password=config.get("password", ""),
        dsn=f"{config['host']}:{config.get('port', 1521)}/{service or config.get('database', '')}",
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(f'SELECT COUNT(*) FROM "{_check_identifier(table)}"')
            return int(cursor.fetchone()[0])
    finally:
        conn.close()


def reconcile_table(
    source_type: str,
    source_config: dict,
    database: str,
    table: str,
    doris_config: dict,
    doris_database: str,
    schema: str | None = None,
) -> dict:
    """对账单张表, 返回 {table, source_count, doris_count, status, diff}。"""
    try:
        if source_type == "postgresql":
            source_count = count_pg_table(source_config, database, schema or "public", table)
        else:
            source_count = count_mysql_table(source_config, database, table)
    except Exception as exc:
        return {"table": table, "status": "source_error", "message": str(exc)}
    try:
        doris_count = count_doris_table(doris_config, doris_database, table)
    except Exception as exc:
        return {
            "table": table,
            "source_count": source_count,
            "status": "doris_missing",
            "message": str(exc),
        }
    status = "ok" if source_count == doris_count else "mismatch"
    return {
        "table": table,
        "source_count": source_count,
        "doris_count": doris_count,
        "status": status,
        "diff": doris_count - source_count,
    }


def send_webhook(webhook: str, payload: dict) -> None:
    """POST JSON 到告警 webhook(钉钉/飞书/企业微信机器人格式自适配)。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        webhook,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        response.read()
