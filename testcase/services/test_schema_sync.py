"""schema-sync / schema-check 纯逻辑单测(无外部依赖)。"""
from common.services.schema_check import normalize_type
from common.services.schema_sync import (
    build_alter_statements,
    build_create_statement,
    column_ddl,
    diff_columns,
    map_mysql_type_to_doris,
)


def test_map_mysql_type_to_doris():
    assert map_mysql_type_to_doris({"data_type": "int", "column_type": "int(11)"}) == "INT"
    assert map_mysql_type_to_doris({"data_type": "bigint", "column_type": "bigint(20)"}) == "BIGINT"
    assert map_mysql_type_to_doris({"data_type": "tinyint", "column_type": "tinyint(1)"}) == "BOOLEAN"
    assert (
        map_mysql_type_to_doris(
            {"data_type": "varchar", "column_type": "varchar(255)", "max_length": 255}
        )
        == "VARCHAR(255)"
    )
    assert (
        map_mysql_type_to_doris(
            {
                "data_type": "decimal",
                "column_type": "decimal(10,2)",
                "numeric_precision": 10,
                "numeric_scale": 2,
            }
        )
        == "DECIMAL(10,2)"
    )
    assert map_mysql_type_to_doris({"data_type": "datetime", "column_type": "datetime(3)"}) == "DATETIME(3)"


def test_column_ddl_default_and_comment():
    ddl = column_ddl(
        {
            "name": "status",
            "data_type": "tinyint",
            "column_type": "tinyint(1)",
            "is_nullable": True,
            "column_default": "1",
            "comment": "状态",
        }
    )
    assert "BOOLEAN" in ddl and "DEFAULT 1" in ddl and "COMMENT '状态'" in ddl


def test_diff_columns_detects_length_and_nullable():
    mysql_cols = [
        {"name": "id", "data_type": "int", "column_type": "int", "is_nullable": False},
        {
            "name": "name",
            "data_type": "varchar",
            "column_type": "varchar(100)",
            "is_nullable": True,
            "max_length": 100,
        },
    ]
    doris_cols = [
        {"name": "id", "data_type": "int", "column_type": "INT", "is_nullable": True},
        {
            "name": "name",
            "data_type": "varchar",
            "column_type": "VARCHAR(50)",
            "is_nullable": True,
            "max_length": 50,
        },
        {"name": "old_col", "data_type": "varchar", "column_type": "VARCHAR(10)", "is_nullable": True},
    ]
    diff = diff_columns(mysql_cols, doris_cols)
    assert [c["name"] for c in diff["drop"]] == ["old_col"]
    assert [i["mysql"]["name"] for i in diff["modify"]] == ["id", "name"]


def test_build_create_and_alter_statements():
    columns = [
        {"name": "id", "data_type": "int", "column_type": "int", "is_nullable": False},
        {"name": "name", "data_type": "varchar", "column_type": "varchar(100)", "is_nullable": True, "max_length": 100},
    ]
    create = build_create_statement("test_db", "users", columns, ["id"])
    assert "UNIQUE KEY (`id`)" in create
    assert "DISTRIBUTED BY HASH(`id`)" in create

    diff = {"add": [], "drop": [{"name": "old_col"}], "modify": []}
    statements = build_alter_statements("test_db", "users", diff, drop_columns=True)
    assert any("DROP COLUMN `old_col`" in s for s in statements)
    statements_no_drop = build_alter_statements("test_db", "users", diff, drop_columns=False)
    assert statements_no_drop == []


def test_normalize_type():
    assert normalize_type("int(11)") == "int"
    assert normalize_type("tinyint(1)") == "boolean"
    assert normalize_type("BOOLEAN") == "boolean"
    assert normalize_type("decimal(10, 2)") == "decimal(10,2)"
