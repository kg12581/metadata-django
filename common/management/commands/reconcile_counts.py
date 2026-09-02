"""每日行数对账: 源表(MySQL/PG) 与 Doris 目标表 COUNT 对比 + 可选 webhook 告警。

用法:
  python manage.py reconcile_counts --database ai_chatbot --doris-db test_db
  python manage.py reconcile_counts --database ai_chatbot --tables analytics_event,orders
  python manage.py reconcile_counts --database cdc_demo --source-type postgresql --schema public
  RECONCILE_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxx \
    python manage.py reconcile_counts --database ai_chatbot
"""
import json

from django.core.management.base import BaseCommand

from common.config import get_database_config, get_doris_config
from common.readers.mysql import MySQLReader
from common.readers.postgresql import PostgreSQLReader
from common.services.reconcile import reconcile_table, send_webhook


class Command(BaseCommand):
    help = "行数对账: 源端(MySQL/PG) vs Doris, 不一致可选 webhook 告警"

    def add_arguments(self, parser):
        parser.add_argument("--database", required=True, help="源库(MySQL 库名 / PG dbname)")
        parser.add_argument("--tables", default=None, help="对账表(逗号分隔, 默认全部)")
        parser.add_argument("--source-type", choices=["mysql", "postgresql"], default=None,
                            help="源类型(默认按 .env DB_TYPE)")
        parser.add_argument("--schema", default=None, help="PG schema(默认 public)")
        parser.add_argument("--doris-db", default=None, help="Doris 目标库(默认 .env DORIS_DATABASE)")
        parser.add_argument("--webhook", default=None, help="告警 webhook(默认取 RECONCILE_WEBHOOK)")

    def handle(self, *args, **options):
        import os

        source_type = options["source_type"] or get_database_config()["db_type"]
        if source_type == "postgresql":
            source_config = {
                "host": os.environ.get("PG_HOST", "192.168.3.100"),
                "port": int(os.environ.get("PG_PORT", "5432")),
                "user": os.environ.get("PG_USER", "debezium"),
                "password": os.environ.get("PG_PASSWORD", "debezium"),
            }
        else:
            source_config = get_database_config({"db_type": "mysql", "database": options["database"]})
        doris_config = get_doris_config({"doris_database": options["doris_db"]})
        doris_database = doris_config["database"] or options["database"]

        if options["tables"]:
            tables = [t.strip() for t in options["tables"].split(",") if t.strip()]
        else:
            if source_type == "postgresql":
                reader = PostgreSQLReader(**{**source_config, "database": options["database"]})
                with reader:
                    tables = [t["name"] for t in reader.list_tables(options["schema"] or "public")]
            else:
                reader = MySQLReader(
                    host=source_config["host"],
                    port=source_config["port"],
                    user=source_config["user"],
                    password=source_config["password"],
                    database=options["database"],
                )
                with reader:
                    tables = [t["name"] for t in reader.list_tables(options["database"])]

        results = [
            reconcile_table(
                source_type, source_config, options["database"], table,
                doris_config, doris_database, schema=options["schema"],
            )
            for table in tables
        ]
        summary = {
            "database": options["database"],
            "doris_database": doris_database,
            "total": len(results),
            "ok": sum(1 for r in results if r["status"] == "ok"),
            "mismatch": sum(1 for r in results if r["status"] == "mismatch"),
            "missing": sum(1 for r in results if r["status"] == "doris_missing"),
            "errors": sum(1 for r in results if r["status"] in ("source_error",)),
            "details": [r for r in results if r["status"] != "ok"],
        }
        self.stdout.write(self.style.NOTICE(
            f"对账完成: 共 {summary['total']} 表, "
            f"一致 {summary['ok']}, 不一致 {summary['mismatch']}, "
            f"Doris 缺失 {summary['missing']}, 源错误 {summary['errors']}"
        ))
        for row in summary["details"]:
            self.stdout.write("  " + json.dumps(row, ensure_ascii=False))

        webhook = options["webhook"] or os.environ.get("RECONCILE_WEBHOOK", "")
        if webhook and summary["details"]:
            try:
                send_webhook(webhook, {"msgtype": "text", "text": {"content": "行数对账异常\n" + json.dumps(summary, ensure_ascii=False)}})
                self.stdout.write(self.style.SUCCESS("告警已发送"))
            except Exception as exc:
                self.stderr.write(f"告警发送失败: {exc}")

        if summary["mismatch"]:
            self.stdout.write(self.style.ERROR("存在不一致, 请排查"))
            raise SystemExit(1)
