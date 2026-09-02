"""执行调度任务(供 crontab 调用)。

用法:
  python manage.py scheduler_run --job 1
  python manage.py scheduler_run --job 1 --no-persist
"""
from django.core.management.base import BaseCommand

from common.models import SchedulerJob
from common.services.scheduler import run_job


class Command(BaseCommand):
    help = "执行调度中心的某个任务(脚本/ETL)"

    def add_arguments(self, parser):
        parser.add_argument("--job", type=int, required=True, help="SchedulerJob id")
        parser.add_argument("--no-persist", action="store_true", help="不写历史(测试用)")

    def handle(self, *args, **options):
        job = SchedulerJob.objects.get(pk=options["job"])
        record = run_job(job, persist=not options["no_persist"])
        self.stdout.write(
            f"[{record.status}] exit={record.exit_code} "
            f"duration={record.duration_ms}ms 任务={job.name}"
        )
        tail = "\n".join(record.output.splitlines()[-30:])
        if tail:
            self.stdout.write(tail)
