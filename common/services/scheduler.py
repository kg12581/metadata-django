"""调度中心: 执行脚本(脚本管理)与 ETL, 并同步到 crontab。"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from django.utils import timezone

from ..models import SchedulerJob, SchedulerRun
from .scripts import _resolve as resolve_script

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
CRON_PREFIX = "metadata-django-scheduler:"


def build_command(job: SchedulerJob) -> list[str]:
    """按任务类型构造执行命令。"""
    args = list(job.args or [])
    if job.job_type == "etl":
        command = [sys.executable, str(PROJECT_ROOT / "etl" / "etl_kafka_doris.py")]
        if "--date" not in args:
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%F")
            args = ["--date", yesterday] + args
        return command + args
    path = resolve_script(job.script_path)
    if path.suffix == ".sh":
        return ["bash", str(path)] + args
    return [sys.executable, str(path)] + args


def run_job(job: SchedulerJob, persist: bool = True) -> SchedulerRun:
    command = build_command(job)
    record = SchedulerRun(job=job)
    if persist:
        record.save()
    started = time.time()
    try:
        proc = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=job.timeout_seconds or 900,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        record.status = "success" if proc.returncode == 0 else "failed"
        record.exit_code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + "\n" + (exc.stderr or "") + f"\n[超时 {job.timeout_seconds}s]"
        record.status = "timeout"
    except Exception as exc:
        output = str(exc)
        record.status = "failed"
    record.output = output[-8000:]
    record.duration_ms = int((time.time() - started) * 1000)
    record.started_at = timezone.now()
    if persist:
        record.save()
    return record


def cron_line(job: SchedulerJob) -> str:
    python = sys.executable
    log_file = LOG_DIR / f"scheduler_{job.name.replace(' ', '_')}.log"
    return (
        f"{job.cron_minute} {job.cron_hour} * * * cd {PROJECT_ROOT} && "
        f"{python} manage.py scheduler_run --job {job.id} "
        f">> {log_file} 2>&1  # {CRON_PREFIX}{job.name}"
    )


def _get_crontab_lines() -> list[str]:
    proc = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return proc.stdout.splitlines() if proc.returncode == 0 else []


def refresh_crontab() -> dict:
    """重建调度中心 crontab 段: 移除旧 marker 行, 为启用任务重写。"""
    lines = _get_crontab_lines()
    kept = [line for line in lines if CRON_PREFIX not in line]
    jobs = SchedulerJob.objects.filter(enabled=True)
    for job in jobs:
        kept.append(cron_line(job))
    proc = subprocess.run(
        ["crontab", "-"],
        input="\n".join(kept) + ("\n" if kept else ""),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"更新 crontab 失败: {proc.stderr.strip()}")
    return {"jobs_in_crontab": jobs.count(), "lines": kept}


def remove_job_from_crontab(job_name: str) -> None:
    lines = _get_crontab_lines()
    kept = [line for line in lines if f"{CRON_PREFIX}{job_name}" not in line]
    subprocess.run(
        ["crontab", "-"],
        input="\n".join(kept) + ("\n" if kept else ""),
        capture_output=True,
        text=True,
    )
