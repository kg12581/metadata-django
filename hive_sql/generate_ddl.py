#!/usr/bin/env python3
"""根据 MySQL 元数据生成 Hive 建表 DDL。

用法:
  python3 hive_sql/generate_ddl.py --database ai_chatbot --table analytics_event
  python3 hive_sql/generate_ddl.py --database ai_chatbot --tables a,b --hive-db ods --partition-dt dt
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

import django  # noqa: E402

django.setup()

from common.config import get_database_config  # noqa: E402
from common.services.schema_check import fetch_mysql_columns  # noqa: E402

GENERATED_DIR = Path(__file__).resolve().parent / "generated"


def mysql_type_to_hive(column: dict) -> str:
    t = (column.get("data_type") or "").lower()
    ct = (column.get("column_type") or "").lower()
    precision = column.get("numeric_precision")
    scale = column.get("numeric_scale")
    max_length = column.get("max_length")

    if t == "tinyint" and ct.startswith("tinyint(1)"):
        return "BOOLEAN"
    if t == "tinyint":
        return "TINYINT"
    if t == "smallint":
        return "SMALLINT"
    if t in ("mediumint", "int", "integer"):
        return "INT"
    if t == "bigint":
        return "BIGINT"
    if t == "float":
        return "FLOAT"
    if t == "double":
        return "DOUBLE"
    if t in ("decimal", "numeric"):
        return f"DECIMAL({precision or 10},{scale or 0})"
    if t == "char":
        return f"CHAR({max_length or 1})"
    if t == "date":
        return "DATE"
    if t in ("datetime", "timestamp"):
        return "TIMESTAMP"
    if t in ("binary", "varbinary", "blob", "tinyblob", "mediumblob", "longblob"):
        return "BINARY"
    return "STRING"


def build_hive_ddl(
    database: str,
    table: str,
    columns: list[dict],
    hive_database: str,
    *,
    location_prefix: str,
    partition_dt: bool = False,
) -> str:
    lines = [
        f"CREATE EXTERNAL TABLE IF NOT EXISTS `{hive_database}`.`{table}` ("
    ]
    for column in columns:
        comment = (column.get("comment") or "").strip().replace("'", "\\'")
        comment_sql = f" COMMENT '{comment}'" if comment else ""
        lines.append(
            f"    `{column['name']}` {mysql_type_to_hive(column)}{comment_sql},"
        )
    lines[-1] = lines[-1].rstrip(",")
    lines.append(")")
    if partition_dt:
        lines.append("PARTITIONED BY (`dt` STRING COMMENT '分区日期 yyyy-MM-dd')")
    location = f"{location_prefix.rstrip('/')}/{hive_database}.db/{table}"
    lines.append("STORED AS ORC")
    lines.append(f"LOCATION '{location}'")
    lines.append(";")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="从 MySQL 元数据生成 Hive 建表 DDL")
    parser.add_argument("--database", required=True, help="MySQL 源库")
    parser.add_argument("--table", default=None, help="单张表")
    parser.add_argument("--tables", default=None, help="多张表(逗号分隔)")
    parser.add_argument("--hive-db", default=None, help="Hive 目标库(默认同源库名)")
    parser.add_argument("--location-prefix", default="hdfs://nameservice1/user/hive/warehouse",
                        help="Hive warehouse 路径前缀")
    parser.add_argument("--partition-dt", action="store_true", help="添加 dt 日期分区")
    parser.add_argument("--out-dir", default=str(GENERATED_DIR), help="输出目录")
    args = parser.parse_args()

    tables = [t.strip() for t in (args.tables or "").split(",") if t.strip()]
    if args.table:
        tables.append(args.table)
    tables = list(dict.fromkeys(tables))
    if not tables:
        parser.error("请指定 --table 或 --tables")

    mysql_config = get_database_config({"db_type": "mysql", "database": args.database})
    hive_database = args.hive_db or args.database
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for table in tables:
        columns = fetch_mysql_columns(mysql_config, args.database, table)
        sql = build_hive_ddl(
            args.database,
            table,
            columns,
            hive_database,
            location_prefix=args.location_prefix,
            partition_dt=args.partition_dt,
        )
        header = (
            f"-- 由 hive_sql/generate_ddl.py 生成 at {datetime.now():%Y-%m-%d %H:%M:%S}\n"
            f"-- 源: MySQL {args.database}.{table} -> Hive {hive_database}.{table}\n\n"
        )
        out_file = out_dir / f"{table}.hive.sql"
        out_file.write_text(header + sql + "\n", encoding="utf-8")
        print(f"[OK] {table} -> {out_file}")
        for line in sql.splitlines()[:6]:
            print("     " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
