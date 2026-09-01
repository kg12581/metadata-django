"""Flink 作业自动管理。

用法:
  python manage.py flink_sync --check                  # 监控所有作业结构差异(默认)
  python manage.py flink_sync --check --job pg-debezium-kafka-to-doris
  python manage.py flink_sync --generate               # 只重新生成 SQL
  python manage.py flink_sync --apply --job pg-debezium-kafka-to-doris

crontab 每 10 分钟监控(只检查不重启):
  */10 * * * * cd /Users/kgt/code/metadata-django && .venv/bin/python manage.py flink_sync --check >> logs/flink_sync.log 2>&1
"""
import json

from django.core.management.base import BaseCommand

from common.services.flink_sync import apply_job, check_all_jobs, generate_job


class Command(BaseCommand):
    help = "Flink 作业自动管理: 监控表结构变更 -> savepoint 停止 -> 生成 SQL -> 重启"

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true", help="监控所有作业结构差异(默认)")
        parser.add_argument("--job", default=None, help="指定作业名(默认全部)")
        parser.add_argument("--generate", action="store_true", help="只重新生成 SQL, 不停作业")
        parser.add_argument("--apply", action="store_true", help="完整流程: Doris 结构同步 -> savepoint 停止 -> 生成 SQL -> 提交")
        parser.add_argument(
            "--no-doris-sync", dest="doris_sync", action="store_false", default=True,
            help="apply 时不自动同步 Doris 结构",
        )

    def handle(self, *args, **options):
        if options["apply"]:
            result = apply_job(options["job"], doris_sync=options["doris_sync"])
        elif options["generate"]:
            result = generate_job(options["job"])
        else:
            result = check_all_jobs()
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
