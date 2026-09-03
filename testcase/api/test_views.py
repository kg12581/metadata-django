"""对外接口冒烟测试(仅本地 SQLite 测试库, 无远端依赖)。"""
import json

import pytest

from common.models import MetadataSourceConfig, ReconcileTask


@pytest.mark.django_db
def test_healthz(client):
    response = client.get("/healthz/")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ok"


@pytest.mark.django_db
def test_pages_render(client, page_paths):
    for path in page_paths:
        response = client.get(path)
        assert response.status_code == 200, f"{path} -> {response.status_code}"


@pytest.mark.django_db
def test_docs_api(client):
    response = client.get("/api/metadata/docs/")
    names = [d["name"] for d in response.json()["data"]]
    assert "04-api-reference.md" in names
    response = client.get("/api/metadata/docs/file/?name=04-api-reference.md")
    assert response.status_code == 200
    assert "<table>" in response.json()["data"]["html"]


@pytest.mark.django_db
def test_source_crud_masks_password(client):
    response = client.post(
        "/api/metadata/sources/create/",
        data=json.dumps(
            {
                "name": "API 测试源",
                "db_type": "mysql",
                "host": "192.168.3.100",
                "port": 3306,
                "database_name": "ai_chatbot",
                "username": "root",
                "password": "api-secret-pass",
                "enabled": True,
            }
        ),
        content_type="application/json",
    )
    body = response.json()
    assert body["code"] == 0
    source_id = body["data"]["id"]
    assert body["data"]["password_set"] is True
    assert "password" not in body["data"]

    response = client.get("/api/metadata/sources/")
    assert all("password" not in s for s in response.json()["data"])

    response = client.post(f"/api/metadata/sources/{source_id}/delete/")
    assert response.json()["code"] == 0


@pytest.mark.django_db
def test_lineage_parse_api(client):
    response = client.post(
        "/api/metadata/lineage/parse/",
        data=json.dumps({"sql": "INSERT INTO dwd.a SELECT id FROM ods.b", "save": True}),
        content_type="application/json",
    )
    assert response.json()["code"] == 0
    parsed = response.json()["data"]["parsed"]
    assert parsed[0]["sources"] == ["ods.b"]


@pytest.mark.django_db
def test_reconcile_task_validation(client):
    response = client.post(
        "/api/metadata/reconcile/tasks/create/",
        data=json.dumps(
            {
                "name": "非法任务",
                "task_type": "row_count",
                "tables": [],
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "tables 不能为空" in response.json()["message"]


@pytest.mark.django_db
def test_scheduler_job_validation(client):
    response = client.post(
        "/api/metadata/scheduler/jobs/create/",
        data=json.dumps(
            {
                "name": "非法脚本任务",
                "job_type": "script",
                "script_path": "tools/not-exists.sh",
                "cron_hour": 2,
                "cron_minute": 0,
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "脚本不存在" in response.json()["message"]


@pytest.mark.django_db
def test_ai_assist_api_uses_mock(client):
    response = client.post(
        "/api/metadata/llm/sql-assist/",
        data=json.dumps({"request": "统计订单", "mode": "generate"}),
        content_type="application/json",
    )
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["result"] == "AI_MOCK_OK"


@pytest.mark.django_db
def test_scripts_list_contains_managed_scripts(client):
    response = client.get("/api/metadata/scripts/")
    paths = [s["path"] for s in response.json()["data"]["scripts"]]
    assert "etl/etl_kafka_doris.py" in paths
    assert any(path.endswith(".sh") for path in paths)
