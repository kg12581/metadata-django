"""Flink SQL 生成/恢复逻辑单测(不触达真实集群)。"""
from common.services.flink_sync import generate_runtime_sql


def _columns():
    return [
        {"name": "id", "data_type": "integer", "column_type": "int4", "is_nullable": False},
        {"name": "name", "data_type": "character varying", "column_type": "varchar",
         "is_nullable": True, "max_length": 100},
    ]


def test_generate_sql_without_savepoint():
    sql = generate_runtime_sql(
        {"name": "job-x", "kafka_topic": "cdc.t", "kafka_bootstrap_servers": "k:9092",
         "source_type": "postgresql_debezium", "doris_host": "h", "doris_fe_http_port": 8030,
         "doris_user": "u", "doris_password": "", "doris_database": "db", "doris_table": "t",
         "primary_keys": ["id"], "checkpoint_dir": "file:///cp"},
        _columns(),
    )
    assert "execution.savepoint.path" not in sql
    assert "CREATE TABLE pg_kafka_source" in sql


def test_generate_sql_with_savepoint():
    sql = generate_runtime_sql(
        {"name": "job-x", "kafka_topic": "cdc.t", "kafka_bootstrap_servers": "k:9092",
         "source_type": "postgresql_debezium", "doris_host": "h", "doris_fe_http_port": 8030,
         "doris_user": "u", "doris_password": "", "doris_database": "db", "doris_table": "t",
         "primary_keys": ["id"], "checkpoint_dir": "file:///cp"},
        _columns(),
        savepoint_path="file:///data/flink/savepoint/savepoint-abc-1",
    )
    assert "SET 'execution.savepoint.path' = 'file:///data/flink/savepoint/savepoint-abc-1';" in sql
