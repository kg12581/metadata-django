"""执行已保存的对账任务。

用法:
  python manage.py reconcile_task --task 1
"""
import json

from django.core.management.base import BaseCommand

from common.models import ReconcileTask
from common.services.reconcile_engine import run_task


class Command(BaseCommand):
    help = "执行对账任务(行数/主键快照/字段值/指标/元数据)"

    def add_arguments(self, parser):
        parser.add_argument("--task", type=int, required=True, help="ReconcileTask id")

    def handle(self, *args, **options):
        task = ReconcileTask.objects.get(pk=options["task"])
        run = run_task(task)
        self.stdout.write(json.dumps(
            {
                "task": task.name,
                "status": run.status,
                "summary": run.summary,
                "error": run.error,
                "duration_ms": run.duration_ms,
            },
            ensure_ascii=False,
            indent=2,
        ))
        if run.details:
            self.stdout.write("明细:")
            for row in run.details:
                self.stdout.write("  " + json.dumps(row, ensure_ascii=False))
