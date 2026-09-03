"""etl_kafka_doris 解析与窗口逻辑(导入独立脚本模块)。"""
import importlib.util
import json
from pathlib import Path

ETL_PATH = Path(__file__).resolve().parent.parent.parent / "etl" / "etl_kafka_doris.py"


def _load_etl():
    spec = importlib.util.spec_from_file_location("etl_kafka_doris_module", ETL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_date_window_is_24h():
    etl = _load_etl()
    start, end = etl.date_window_ms("2026-09-01", "Asia/Shanghai")
    assert (end - start) == 24 * 3600 * 1000


def test_parse_debezium_update():
    etl = _load_etl()
    message = {
        "payload": {
            "before": None,
            "after": {"id": 1, "product": "demo"},
            "source": {"ts_ms": 1788105600000},
            "op": "u",
            "ts_ms": 1788105600123,
        }
    }
    parsed = etl.parse_message(json.dumps(message).encode())
    assert parsed["op"] == "u"
    assert parsed["after"]["product"] == "demo"
    assert parsed["ts_ms"] == 1788105600123


def test_parse_debezium_delete_with_key():
    etl = _load_etl()
    message = {"payload": {"before": {"id": 1}, "after": None, "op": "d", "ts_ms": 1788105600999}}
    key = {"schema": {}, "payload": {"id": 1}}
    parsed = etl.parse_message(json.dumps(message).encode(), json.dumps(key).encode())
    assert parsed["op"] == "d"
    assert parsed["key_payload"] == {"id": 1}
