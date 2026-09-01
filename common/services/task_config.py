"""结构同步定时任务配置与 crontab 管理。"""
from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TASK_PATH = PROJECT_ROOT / "tools" / "schema_sync_task.json"
SCRIPT_PATH = PROJECT_ROOT / "tools" / "run_schema_sync.sh"
LOG_PATH = PROJECT_ROOT / "logs" / "cron_schema_sync.log"
CRON_MARKER = "metadata-django-schema-sync"

DEFAULT_TASK = {
    "enabled": True,
    "database": "ai_chatbot",
    "tables": "analytics_event",
    "doris_database": "test_db",
    "apply": True,
    "cron_minute": 0,
    "cron_hour": 3,
}


def load_task() -> dict:
    task = dict(DEFAULT_TASK)
    if TASK_PATH.exists():
        try:
            task.update(json.loads(TASK_PATH.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return task


def save_task(task: dict) -> dict:
    merged = dict(DEFAULT_TASK)
    merged.update(task)
    TASK_PATH.parent.mkdir(parents=True, exist_ok=True)
    TASK_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return merged


def cron_line(task: dict) -> str:
    minute = int(task.get("cron_minute", 0))
    hour = int(task.get("cron_hour", 3))
    return (
        f"{minute} {hour} * * * {SCRIPT_PATH} "
        f">> {LOG_PATH} 2>&1  # {CRON_MARKER}"
    )


def get_crontab_lines() -> list[str]:
    proc = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if proc.returncode != 0:
        return []
    return proc.stdout.splitlines()


def install_cron(task: dict) -> dict:
    """把任务行写入用户 crontab(幂等, 按 marker 替换)。"""
    new_line = cron_line(task)
    lines = get_crontab_lines()
    output = []
    replaced = False
    for line in lines:
        if CRON_MARKER in line:
            if not replaced:
                output.append(new_line)
                replaced = True
            continue
        output.append(line)
    if not replaced:
        output.append(new_line)
    proc = subprocess.run(
        ["crontab", "-"],
        input="\n".join(output) + "\n",
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"写入 crontab 失败: {proc.stderr.strip()}")
    return {"installed": True, "line": new_line}


def remove_cron() -> dict:
    lines = get_crontab_lines()
    output = [line for line in lines if CRON_MARKER not in line]
    proc = subprocess.run(
        ["crontab", "-"],
        input="\n".join(output) + ("\n" if output else ""),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"更新 crontab 失败: {proc.stderr.strip()}")
    return {"installed": False, "line": None}


def cron_state(task: dict) -> dict:
    """返回当前 crontab 中该任务的状态与下次执行时间。"""
    lines = get_crontab_lines()
    present = any(CRON_MARKER in line for line in lines)
    now = datetime.datetime.now()
    minute = int(task.get("cron_minute", 0))
    hour = int(task.get("cron_hour", 3))
    next_run = None
    for offset in range(2):
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + datetime.timedelta(days=offset)
        if candidate > now:
            next_run = candidate.strftime("%Y-%m-%d %H:%M:%S")
            break
    return {
        "enabled": bool(task.get("enabled", True)) and present,
        "in_crontab": present,
        "next_run": next_run,
        "crontab_line": cron_line(task) if task.get("enabled", True) else None,
    }
