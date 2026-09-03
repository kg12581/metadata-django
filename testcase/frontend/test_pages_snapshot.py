"""页面快照: 把关键页面渲染结果存为 HTML 快照(便于人工核对)。"""
import json
from pathlib import Path

import pytest

SNAPSHOT_DIR = Path(__file__).resolve().parent.parent / "snapshots"

SNAPSHOT_PAGES = {
    "dashboard": "/",
    "sources": "/sources/",
    "reconcile": "/reconcile/",
    "scheduler": "/scheduler/",
    "sql_helper": "/sql-helper/",
    "docs": "/docs/?file=04-api-reference.md",
    "ai_sql": "/ai-sql/",
    "spark2hive": "/spark2sql/",
    "oracle2hive": "/oracle2hive/",
}


@pytest.mark.django_db
def test_page_snapshots(client):
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    index = []
    for name, path in SNAPSHOT_PAGES.items():
        response = client.get(path)
        assert response.status_code == 200, f"{path} -> {response.status_code}"
        target = SNAPSHOT_DIR / f"{name}.html"
        target.write_text(response.content.decode("utf-8", errors="replace"), encoding="utf-8")
        index.append({"name": name, "path": path, "file": str(target), "bytes": target.stat().st_size})
    (SNAPSHOT_DIR / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
