"""pytest 全局配置: Django 环境 + 外部调用隔离。"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

import django  # noqa: E402

django.setup()

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def block_external_calls(monkeypatch):
    """测试内禁止真实 LLM 调用(远端依赖由 mock 替代)。"""
    from common.services import llm

    def _fake_chat(prompt, system=None, max_tokens=1500):
        return "AI_MOCK_OK"

    monkeypatch.setattr(llm, "chat", _fake_chat)


@pytest.fixture
def page_paths():
    return [
        "/",
        "/sources/",
        "/sql-helper/",
        "/reconcile/",
        "/scheduler/",
        "/scripts/",
        "/docs/",
        "/sql-files/",
        "/lineage/",
        "/ops/",
        "/ai-sql/",
        "/spark2sql/",
        "/oracle2hive/",
        "/healthz/",
    ]
