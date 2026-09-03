"""调度中心与脚本管理工具的纯逻辑测试(不执行子进程/crontab)。"""
from datetime import datetime, timedelta

from common.models import SchedulerJob
from common.services.scheduler import build_command
from common.services.scripts import _resolve


def test_etl_command_auto_fills_yesterday():
    job = SchedulerJob(job_type="etl", args=["--dry-run"])
    command = build_command(job)
    assert command[-1] == "--dry-run"
    assert command[-3] == "--date"
    assert command[-2] == (datetime.now() - timedelta(days=1)).strftime("%F")


def test_etl_command_keeps_custom_date():
    job = SchedulerJob(job_type="etl", args=["--date", "2026-09-01"])
    command = build_command(job)
    assert "--date" in command
    assert command[command.index("--date") + 1] == "2026-09-01"


def test_script_path_rejects_traversal():
    import pytest

    with pytest.raises(ValueError):
        _resolve("../manage.py")
    with pytest.raises(ValueError):
        _resolve("/etc/passwd")
    with pytest.raises(ValueError):
        _resolve("common/models.py")  # 不在受管目录


def test_script_path_accepts_managed_python():
    path = _resolve("tools/datax_sync.py")
    assert path.exists()


def test_scripts_allowed_dirs_cover_managed():
    from common.services.scripts import SCRIPT_DIRS

    assert "tools" in SCRIPT_DIRS
    assert "etl" in SCRIPT_DIRS
