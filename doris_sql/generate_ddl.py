#!/usr/bin/env python3
"""根据 MySQL / PostgreSQL / Oracle 元数据生成 Doris 建表/结构变更 DDL。

用法:
  python3 doris_sql/generate_ddl.py --database ai_chatbot --table analytics_event
  python3 doris_sql/generate_ddl.py --database cdc_demo --table orders --source-type postgresql \
      --host 192.168.3.100 --port 5432 --user debezium --password debezium --schema public
  python3 doris_sql/generate_ddl.py --database ORCL --table ORDERS --source-type oracle \
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

from common.config import get_database_config, get_doris_config  # noqa: E402
from common.services.schema_sync import (  # noqa: E402
    build_create_statement,
    fetch_source_columns,
    fetch_source_primary_keys,
    plan_table_sync,
)

GENERATED_DIR = Path(__file__).resolve().parent / "generated"


def source_config_from_args(args) -> dict:
    if args.source_type == "mysql":
        return get_database_config({"db_type": "mysql", "database": args.database})
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
    parser = argparse.ArgumentParser(description="从源端元数据生成 Doris DDL")
    parser.add_argument("--database", required=True, help="源库(mysql 库名 / pg dbname / oracle service)")
    parser.add_argument("--source-type", choices=["mysql", "postgresql", "oracle"], default="mysql")
    parser.add_argument("--table", default=None, help="单张表")
    parser.add_argument("--tables", default=None, help="多张表(逗号分隔)")
    parser.add_argument("--mode", choices=["create", "sync"], default="create")
    parser.add_argument("--schema", default=None, help="PG schema / Oracle owner(默认 public/当前用户)")
    parser.add_argument("--doris-db", default=None, help="Doris 目标库(默认 .env DORIS_DATABASE)")
    parser.add_argument("--host", default=None, help="源主机(仅 pg/oracle 需要)")
    parser.add_argument("--port", type=int, default=None, help="源端口")
    parser.add_argument("--user", default=None, help="源用户")
    parser.add_argument("--password", default=None, help="源密码")
    parser.add_argument("--out-dir", default=str(GENERATED_DIR))
    args = parser.parse_args()

    tables = [t.strip() for t in (args.tables or "").split(",") if t.strip()]
    if args.table:
        tables.append(args.table)
    tables = list(dict.fromkeys(tables))
    if not tables:
        parser.error("请指定 --table 或 --tables")

    source_config = source_config_from_args(args)
    doris_config = get_doris_config({"doris_database": args.doris_db})
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for table in tables:
        if args.mode == "create":
            columns = fetch_source_columns(
                args.source_type, source_config, args.database, table, schema=args.schema
            )
            primary_keys = fetch_source_primary_keys(
                args.source_type, source_config, args.database, table, schema=args.schema
            )
            target_db = args.doris_db or doris_config.get("database") or args.database
            sql = build_create_statement(
                target_db, table, columns, primary_keys, source_type=args.source_type
            )
            header = (
                f"-- 由 doris_sql/generate_ddl.py 生成 at {datetime.now():%Y-%m-%d %H:%M:%S}\n"
                f"-- 源: {args.source_type} {args.database}.{table} -> Doris {target_db}.{table}\n\n"
            )
            statements = [header + sql]
        else:
            plan = plan_table_sync(
                source_config,
                doris_config,
                args.database,
                table,
                doris_database=args.doris_db,
                source_type=args.source_type,
                drop_columns=True,
                auto_create=True,
            )
            header = (
                f"-- 由 doris_sql/generate_ddl.py 生成 at {datetime.now():%Y-%m-%d %H:%M:%S}\n"
                f"-- 源: {args.source_type} {args.database}.{table} -> {plan['doris_table']} (sync)\n"
                f"-- 新增: {', '.join(plan['add_columns']) or '-'} | "
                f"删除: {', '.join(plan['drop_columns']) or '-'} | "
                f"修改: {', '.join(m['column'] for m in plan['modify_columns']) or '-'}\n\n"
            )
            statements = (
                [header + "\n".join(plan["statements"])]
                if plan["statements"]
                else [header + "-- 结构一致, 无需变更"]
            )

        out_file = out_dir / f"{table}.ddl.sql"
        out_file.write_text("\n\n".join(statements) + "\n", encoding="utf-8")
        print(f"[OK] {table} -> {out_file}")
        for line in statements[0].splitlines()[:6]:
            print("     " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
