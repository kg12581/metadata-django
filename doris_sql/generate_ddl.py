#!/usr/bin/env python3
"""根据 MySQL 元数据生成 Doris 建表/结构变更 DDL。

用法:
  python3 doris_sql/generate_ddl.py --database ai_chatbot --table analytics_event
  python3 doris_sql/generate_ddl.py --database ai_chatbot --tables a,b --mode sync --doris-db test_db
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
from common.services.schema_check import fetch_mysql_columns  # noqa: E402
from common.services.schema_sync import (  # noqa: E402
    build_create_statement,
    fetch_mysql_primary_keys,
    plan_table_sync,
)

GENERATED_DIR = Path(__file__).resolve().parent / "generated"


def main() -> int:
    parser = argparse.ArgumentParser(description="从 MySQL 元数据生成 Doris DDL")
    parser.add_argument("--database", required=True, help="MySQL 源库")
    parser.add_argument("--table", default=None, help="单张表")
    parser.add_argument("--tables", default=None, help="多张表(逗号分隔)")
    parser.add_argument("--mode", choices=["create", "sync"], default="create",
                        help="create=生成建表 SQL; sync=与 Doris 对比输出 ALTER")
    parser.add_argument("--doris-db", default=None, help="Doris 目标库(默认取 .env DORIS_DATABASE)")
    parser.add_argument("--out-dir", default=str(GENERATED_DIR), help="输出目录")
    args = parser.parse_args()

    tables = [t.strip() for t in (args.tables or "").split(",") if t.strip()]
    if args.table:
        tables.append(args.table)
    tables = list(dict.fromkeys(tables))
    if not tables:
        parser.error("请指定 --table 或 --tables")

    mysql_config = get_database_config({"db_type": "mysql", "database": args.database})
    doris_config = get_doris_config({"doris_database": args.doris_db})
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for table in tables:
        if args.mode == "create":
            columns = fetch_mysql_columns(mysql_config, args.database, table)
            primary_keys = fetch_mysql_primary_keys(mysql_config, args.database, table)
            target_db = args.doris_db or doris_config.get("database") or args.database
            sql = build_create_statement(target_db, table, columns, primary_keys)
            header = (
                f"-- 由 doris_sql/generate_ddl.py 生成 at {datetime.now():%Y-%m-%d %H:%M:%S}\n"
                f"-- 源: MySQL {args.database}.{table} -> Doris {target_db}.{table}\n\n"
            )
            statements = [header + sql]
        else:
            plan = plan_table_sync(
                mysql_config,
                doris_config,
                args.database,
                table,
                doris_database=args.doris_db,
                drop_columns=True,
                auto_create=True,
            )
            header = (
                f"-- 由 doris_sql/generate_ddl.py 生成 at {datetime.now():%Y-%m-%d %H:%M:%S}\n"
                f"-- 源: MySQL {args.database}.{table} -> {plan['doris_table']} (sync 模式)\n"
                f"-- 新增: {', '.join(plan['add_columns']) or '-'} | "
                f"删除: {', '.join(plan['drop_columns']) or '-'} | "
                f"修改: {', '.join(m['column'] for m in plan['modify_columns']) or '-'}\n\n"
            )
            statements = [header + "\n".join(plan["statements"])] if plan["statements"] else [header + "-- 结构一致, 无需变更"]

        out_file = out_dir / f"{table}.ddl.sql"
        out_file.write_text("\n\n".join(statements) + "\n", encoding="utf-8")
        print(f"[OK] {table} -> {out_file}")
        first_lines = statements[0].splitlines()
        for line in first_lines[:6]:
            print("     " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
