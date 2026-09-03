#!/usr/bin/env python3
"""根据 MySQL / PostgreSQL / Oracle 元数据生成 Hive 建表 DDL。

用法:
  python3 hive_sql/generate_ddl.py --database ai_chatbot --table analytics_event
  python3 hive_sql/generate_ddl.py --database cdc_demo --table orders --source-type postgresql \
      --host 192.168.3.100 --port 5432 --user debezium --password debezium --schema public --partition-dt
  python3 hive_sql/generate_ddl.py --database ORCL --table ORDERS --source-type oracle \
      --host 192.168.3.100 --port 1521 --user scott --password tiger
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

from common.services.schema_sync import fetch_source_columns  # noqa: E402

GENERATED_DIR = Path(__file__).resolve().parent / "generated"


def _decimal(p, s):
    return f"DECIMAL({p or 10},{s or 0})"


def mysql_type_to_hive(column: dict) -> str:
    t = (column.get("data_type") or "").lower()
    ct = (column.get("column_type") or "").lower()
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
        return _decimal(column.get("numeric_precision"), column.get("numeric_scale"))
    if t == "date":
        return "DATE"
    if t in ("datetime", "timestamp"):
        return "TIMESTAMP"
    if t in ("binary", "varbinary", "blob", "tinyblob", "mediumblob", "longblob"):
        return "BINARY"
    return "STRING"


def pg_type_to_hive(column: dict) -> str:
    t = (column.get("data_type") or "").lower()
    if t in ("smallint", "int2"):
        return "SMALLINT"
    if t in ("integer", "int4"):
        return "INT"
    if t in ("bigint", "int8"):
        return "BIGINT"
    if t in ("boolean", "bool"):
        return "BOOLEAN"
    if t in ("numeric", "decimal"):
        return (
            _decimal(column.get("numeric_precision"), column.get("numeric_scale"))
            if column.get("numeric_precision") is not None
            else "STRING"
        )
    if t == "real":
        return "FLOAT"
    if t in ("double precision", "float8"):
        return "DOUBLE"
    if t == "date":
        return "DATE"
    if "timestamp" in t:
        return "TIMESTAMP"
    return "STRING"


def oracle_type_to_hive(column: dict) -> str:
    t = (column.get("data_type") or "").lower()
    ct = (column.get("column_type") or "").upper()
    if t == "number":
        if ct and not ct.startswith("NUMBER("):
            return "DOUBLE"
        p = column.get("numeric_precision")
        return _decimal(p, column.get("numeric_scale")) if p else "DOUBLE"
    if t in ("float", "binary_double"):
        return "DOUBLE"
    if t == "binary_float":
        return "FLOAT"
    if t == "date":
        return "DATE"
    if t == "timestamp":
        return "TIMESTAMP"
    if t == "boolean":
        return "BOOLEAN"
    return "STRING"


def mapper_for(source_type: str):
    if source_type in ("postgresql", "gaussdb", "dws"):
        return pg_type_to_hive
    if source_type == "oracle":
        return oracle_type_to_hive
    return mysql_type_to_hive


def build_hive_ddl(table: str, columns: list[dict], hive_database: str, mapper,
                   location_prefix: str, partition_dt: bool) -> str:
    lines = [f"CREATE EXTERNAL TABLE IF NOT EXISTS `{hive_database}`.`{table}` ("]
    for column in columns:
        comment = (column.get("comment") or "").strip().replace("'", "\\'")
        comment_sql = f" COMMENT '{comment}'" if comment else ""
        lines.append(f"    `{column['name']}` {mapper(column)}{comment_sql},")
    lines[-1] = lines[-1].rstrip(",")
    lines.append(")")
    if partition_dt:
        lines.append("PARTITIONED BY (`dt` STRING COMMENT '分区日期 yyyy-MM-dd')")
    location = f"{location_prefix.rstrip('/')}/{hive_database}.db/{table}"
    lines.append("STORED AS ORC")
    lines.append(f"LOCATION '{location}'")
    lines.append(";")
    return "\n".join(lines)


def source_config_from_args(args) -> dict:
    if args.source_type == "mysql":
        return {
            "db_type": "mysql",
            "host": args.host or os.environ.get("DB_HOST", "192.168.3.100"),
            "port": args.port or int(os.environ.get("DB_PORT", "3306")),
            "user": args.user or os.environ.get("DB_USER", "root"),
            "password": args.password or os.environ.get("DB_PASSWORD", ""),
            "database": args.database,
        }
    if args.source_type in ("postgresql", "gaussdb", "dws"):
        return {
            "db_type": args.source_type,
            "host": args.host or os.environ.get("PG_HOST", "192.168.3.100"),
            "port": args.port or int(os.environ.get("PG_PORT", "5432")),
            "user": args.user or os.environ.get("PG_USER", "debezium"),
            "password": args.password or os.environ.get("PG_PASSWORD", ""),
            "database": args.database,
            "schema": args.schema,
        }
    return {
        "db_type": "oracle",
        "host": args.host,
        "port": args.port or 1521,
        "user": args.user,
        "password": args.password,
        "database": args.database,
        "schema": args.schema,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="从源端元数据生成 Hive 建表 DDL")
    parser.add_argument("--database", required=True)
    parser.add_argument("--source-type", choices=["mysql", "postgresql", "oracle"], default="mysql")
    parser.add_argument("--table", default=None)
    parser.add_argument("--tables", default=None)
    parser.add_argument("--schema", default=None)
    parser.add_argument("--hive-db", default=None, help="Hive 目标库(默认同源库名)")
    parser.add_argument("--location-prefix", default="hdfs://nameservice1/user/hive/warehouse")
    parser.add_argument("--partition-dt", action="store_true")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--out-dir", default=str(GENERATED_DIR))
    args = parser.parse_args()

    tables = [t.strip() for t in (args.tables or "").split(",") if t.strip()]
    if args.table:
        tables.append(args.table)
    tables = list(dict.fromkeys(tables))
    if not tables:
        parser.error("请指定 --table 或 --tables")

    source_config = source_config_from_args(args)
    mapper = mapper_for(args.source_type)
    hive_database = args.hive_db or args.database
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for table in tables:
        columns = fetch_source_columns(
            args.source_type, source_config, args.database, table, schema=args.schema
        )
        sql = build_hive_ddl(
            table, columns, hive_database, mapper,
            location_prefix=args.location_prefix, partition_dt=args.partition_dt,
        )
        header = (
            f"-- 由 hive_sql/generate_ddl.py 生成 at {datetime.now():%Y-%m-%d %H:%M:%S}\n"
            f"-- 源: {args.source_type} {args.database}.{table} -> Hive {hive_database}.{table}\n\n"
        )
        out_file = out_dir / f"{table}.hive.sql"
        out_file.write_text(header + sql + "\n", encoding="utf-8")
        print(f"[OK] {table} -> {out_file}")
        for line in sql.splitlines()[:6]:
            print("     " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
