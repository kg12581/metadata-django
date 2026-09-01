"""手动/定时执行元数据同步: python manage.py sync_metadata [--schema xxx]"""
from django.core.management.base import BaseCommand

from common.config import get_database_config
from common.services.sync import sync_metadata as run_sync


class Command(BaseCommand):
    help = "从远端数据库同步元数据到 Django 表(配置来自 .env / 环境变量)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            default=None,
            help="只同步指定 schema(库), 默认同步全部",
        )

    def handle(self, *args, **options):
        overrides = {}
        if options.get("schema"):
            overrides["schema"] = options["schema"]
        config = get_database_config(overrides)
        database, stats = run_sync(config)
        self.stdout.write(
            self.style.SUCCESS(
                f"同步完成: {database} -> 表 {stats['tables']}, "
                f"字段 {stats['columns']}, 索引 {stats['indexes']}, "
                f"约束 {stats['constraints']}"
            )
        )
