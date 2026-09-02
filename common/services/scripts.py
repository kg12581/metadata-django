"""脚本管理: 扫描/读写/运行项目内 shell 与 python 脚本。"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from django.utils import timezone

from ..models import ScriptRun

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_DIRS = [
    name for name in ("tools", "etl", "flink_sql", "doris_sql", "hive_sql")
    if (PROJECT_ROOT / name).exists()
]
for extra in os.environ.get("SCRIPTS_EXTRA_DIRS", "").split(","):
    if extra.strip() and (PROJECT_ROOT / extra.strip()).is_dir():
        SCRIPT_DIRS.append(extra.strip())
EXTENSIONS = (".sh", ".py")


def _resolve(relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("只允许项目内相对路径")
    if rel.suffix not in EXTENSIONS:
        raise ValueError("只支持 .sh / .py 脚本")
    path = (PROJECT_ROOT / rel).resolve()
    if not any(str(path).startswith(str((PROJECT_ROOT / d).resolve())) for d in SCRIPT_DIRS):
        raise ValueError("脚本不在受管目录内")
    return path


def list_scripts() -> list[dict]:
    entries = []
    for directory in SCRIPT_DIRS:
        root = PROJECT_ROOT / directory
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix in EXTENSIONS and "__pycache__" not in path.parts:
                rel = path.relative_to(PROJECT_ROOT)
                stat = path.stat()
                entries.append(
                    {
                        "path": str(rel),
                        "dir": directory,
                        "name": path.name,
                        "kind": "python" if path.suffix == ".py" else "shell",
                        "size": stat.st_size,
                    }
                )
    return entries


def read_script(relative: str) -> str:
    return _resolve(relative).read_text(encoding="utf-8", errors="replace")


def save_script(relative: str, content: str) -> dict:
    path = _resolve(relative)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
    return {"path": relative, "size": path.stat().st_size}


def create_script(directory: str, name: str, content: str) -> dict:
    if directory not in SCRIPT_DIRS:
        raise ValueError(f"目录不在受管范围: {directory}")
    name = Path(name).name  # 防目录穿越
    if not name.endswith(EXTENSIONS):
        raise ValueError("只支持 .sh / .py")
    path = PROJECT_ROOT / directory / name
    if path.exists():
        raise ValueError(f"脚本已存在: {directory}/{name}")
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
    return {"path": f"{directory}/{name}", "size": path.stat().st_size}


def delete_script(relative: str) -> dict:
    path = _resolve(relative)
    path.unlink()
    return {"path": relative, "deleted": True}


def run_script(relative: str, args: list[str] | None = None, timeout: int = 600) -> dict:
    path = _resolve(relative)
    command = (
        ["bash", str(path), *(args or [])]
        if path.suffix == ".sh"
        else [sys.executable, str(path), *(args or [])]
    )
    started = time.time()
    record = ScriptRun(script_path=relative, args=args or [])
    record.save()
    try:
        proc = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        record.status = "success" if proc.returncode == 0 else "failed"
        record.exit_code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + "\n" + (exc.stderr or "") + f"\n[超时 {timeout}s]"
        record.status = "timeout"
        record.exit_code = None
    except Exception as exc:
        output = str(exc)
        record.status = "failed"
        record.exit_code = None
    record.output = output[-8000:]
    record.duration_ms = int((time.time() - started) * 1000)
    record.started_at = timezone.now()
    record.save()
    return {
        "run_id": record.id,
        "status": record.status,
        "exit_code": record.exit_code,
        "duration_ms": record.duration_ms,
        "output": record.output,
    }
