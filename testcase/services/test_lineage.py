"""SQL 血缘解析单测。"""
import pytest

from common.models import LineageEdge
from common.services.lineage import parse_sql, save_lineage


def test_parse_insert_select_and_ctas():
    sql = (
        "INSERT INTO dwd.t1 SELECT a.id FROM ods.a JOIN dim.b ON a.bid = b.id WHERE a.dt='x';"
        "CREATE TABLE dws.t2 AS SELECT * FROM ods.c;"
    )
    parsed = parse_sql(sql)
    targets = {item["target"]: item["sources"] for item in parsed}
    assert targets["dwd.t1"] == ["ods.a", "dim.b"]
    assert targets["dws.t2"] == ["ods.c"]


def test_parse_ignores_plain_select():
    assert parse_sql("SELECT * FROM ods.a LIMIT 10;") == []


@pytest.mark.django_db
def test_save_lineage_roundtrip():
    edges = save_lineage("example.sql", "INSERT INTO dwd.x SELECT id FROM ods.y;")
    assert edges == [{"source": "ods.y", "target": "dwd.x"}]
    assert LineageEdge.objects.filter(source_table="ods.y", target_table="dwd.x").exists()
