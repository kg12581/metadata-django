"""根据 MySQL 元数据自动对齐 Doris 表结构。

用法:
  python manage.py schema_sync --database ai_chatbot --tables analytics_event
  python manage.py schema_sync --database ai_chatbot --tables t1,t2 --apply

默认只预览; --apply 才真正在 Doris 上执行 DDL。
"""
from django.core.management.base import BaseCommand

from common.config import get_database_config, get_doris_config
from common.services.schema_sync import sync_table_schema


class Command(BaseCommand):
    help = "按 MySQL 元数据对齐 Doris 表结构(新增/删除/修改字段, 不存在自动建表)"

    def add_arguments(self, parser):
        parser.add_argument("--database", required=True, help="MySQL 源库")
        parser.add_argument("--tables", required=True, help="逗号分隔的表名列表")
        parser.add_argument("--doris-database", default=None, help="Doris 目标库(默认 DORIS_DATABASE)")
        parser.add_argument("--apply", action="store_true", help="执行 DDL(默认仅预览)")
        parser.add_argument(
            "--no-drop-columns", dest="drop_columns", action="store_false", default=True,
            help="不删除 Doris 中多余字段",
        )
        parser.add_argument(
            "--no-auto-create", dest="auto_create", action="store_false", default=True,
            help="Doris 表不存在时不自动建表",
        )

    def handle(self, *args, **options):
        mysql_config = get_database_config({"db_type": "mysql", "database": options["database"]})
        doris_config = get_doris_config({"doris_database": options.get("doris_database")})
        tables = [t.strip() for t in options["tables"].split(",") if t.strip()]
        if not tables:
            self.stderr.write("--tables 不能为空")
            return

        for table in tables:
            result = sync_table_schema(
                mysql_config,
                doris_config,
                mysql_config["database"],
                table,
                doris_database=options.get("doris_database"),
                preview=not options["apply"],
                drop_columns=options["drop_columns"],
                auto_create=options["auto_create"],
            )
            self.stdout.write(
                self.style.WARNING(f"== {result['table']} -> {result['doris_table']} ==")
            )
            if result.get("create"):
                self.stdout.write(self.style.NOTICE("  自动建表"))
            for column in result.get("add_columns", []):
                self.stdout.write(f"  ADD COLUMN {column}")
            for column in result.get("drop_columns", []):
                self.stdout.write(f"  DROP COLUMN {column}")
            for item in result.get("modify_columns", []):
                self.stdout.write(
                    f"  MODIFY {item['column']}: {item['mysql']} -> {item['doris']}"
                )
            for statement in result.get("statements", []):
                self.stdout.write("    " + statement)
            for warning in result.get("warnings", []):
                self.stdout.write(self.style.WARNING("  ! " + warning))
            for item in result.get("results", []):
                if item["success"]:
                    self.stdout.write(self.style.SUCCESS("  [OK] " + item["statement"]))
                else:
                    self.stderr.write(self.style.ERROR(f"  [FAIL] {item['statement']}\n  {item.get('error')}"))
