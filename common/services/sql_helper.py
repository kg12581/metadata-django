"""基于已同步元数据的 SQL 生成助手。"""
from __future__ import annotations

from ..models import MetadataColumn, MetadataDatabase, MetadataTable


def quote_name(name: str, db_type: str) -> str:
    if db_type in ("postgresql", "gaussdb", "dws", "opengauss"):
        return '"' + str(name).replace('"', '""') + '"'
    return "`" + str(name).replace("`", "``") + "`"


def _example_value(column: MetadataColumn) -> str:
    data_type = (column.data_type or "").lower()
    if data_type in ("tinyint", "smallint", "mediumint", "int", "integer", "bigint",
                     "float", "double", "decimal", "numeric"):
        return "0"
    if data_type in ("bool", "boolean") or data_type == "tinyint" and column.max_length == 1:
        return "1"
    if data_type == "date":
        return "'2026-09-01'"
    if data_type in ("datetime", "timestamp", "timestamptz"):
        return "'2026-09-01 00:00:00'"
    return "'xxx'"


def table_primary_keys(table: MetadataTable) -> list[str]:
    return [
        key
        for index in table.indexes.filter(is_primary=True)
        for key in (index.column_names or [])
    ]


def build_snippets(table: MetadataTable, columns: list[MetadataColumn],
                   database: MetadataDatabase) -> dict:
    db_type = database.db_type
    q = lambda name: quote_name(name, db_type)  # noqa: E731
    table_ref = f"{q(database.database_name)}.{q(table.schema_name)}.{q(table.name)}"
    if db_type == "postgresql":
        table_ref = f"{q(database.database_name)}.{q(table.schema_name)}.{q(table.name)}"
    else:
        table_ref = f"{q(database.database_name)}.{q(table.name)}"

    names = [c.name for c in columns]
    pk_columns = table_primary_keys(table) or (names[:1] if names else [])
    pk_where = " AND ".join(f"{q(pk)} = 0" for pk in pk_columns) or "1 = 1"
    columns_sql = ",\n    ".join(q(name) for name in names)
    column_list_sql = ", ".join(q(name) for name in names)

    snippets = {
        "select": f"SELECT\n    {columns_sql}\nFROM {table_ref}\nLIMIT 100;",
        "select_all": f"SELECT *\nFROM {table_ref}\nLIMIT 100;",
        "count": f"SELECT COUNT(*) AS cnt\nFROM {table_ref};",
        "insert": (
            f"INSERT INTO {table_ref}\n    ({column_list_sql})\nVALUES\n    "
            f"({', '.join(_example_value(c) for c in columns)});"
        ),
        "update": (
            f"UPDATE {table_ref}\nSET\n    {q(names[1]) if len(names) > 1 else q(names[0])} = 'xxx'\n"
            f"WHERE {pk_where};"
        ),
        "delete": f"DELETE FROM {table_ref}\nWHERE {pk_where};",
    }
    return snippets
