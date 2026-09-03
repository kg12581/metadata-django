"""模型层测试: 密码加密、类型选择、对账/调度任务。"""
import pytest

from common.models import (
    DatabaseType,
    MetadataSourceConfig,
    ReconcileTask,
    SchedulerJob,
    SourceType,
)


@pytest.mark.django_db
def test_source_password_encrypted_at_rest():
    source = MetadataSourceConfig.objects.create(
        name="加密测试",
        db_type="mysql",
        host="192.168.3.100",
        username="root",
        password="SuperSecret123",
    )
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT password FROM common_metadatasourceconfig WHERE id = %s",
            [source.pk],
        )
        stored = cursor.fetchone()[0]
    assert stored.startswith("enc:")
    assert "SuperSecret123" not in stored
    source.refresh_from_db()
    assert source.password == "SuperSecret123"


@pytest.mark.django_db
def test_source_update_password_roundtrip():
    source = MetadataSourceConfig.objects.create(
        name="更新测试", db_type="mysql", host="h", password="old-pass"
    )
    source.password = "new-pass"
    source.save()
    source.refresh_from_db()
    assert source.password == "new-pass"


def test_type_choices_cover_odps():
    assert "odps" in DatabaseType.values
    assert "odps" in SourceType.values


@pytest.mark.django_db
def test_reconcile_task_create_without_tables_blocked_by_view():
    """任务模型本身可建; 参数校验在视图层, 见 api 测试。"""
    task = ReconcileTask.objects.create(
        name="模型层任务", task_type="row_count", tables=["t1"]
    )
    assert task.tables == ["t1"]


def test_scheduler_cron_fields():
    job = SchedulerJob(name="x", job_type="etl", cron_minute=30, cron_hour=2)
    assert job.cron_fields() == "30 2 * * *"
