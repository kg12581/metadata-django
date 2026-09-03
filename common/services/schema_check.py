"""MySQL 与 Doris 表结构一致性校验。"""
from __future__ import annotations

import re

from ..readers.doris import DorisReader
from ..readers.mysql import MySQLReader

_INT_TYPES = {"tinyint", "smallint", "mediumint", "int", "integer", "bigint"}
_DECIMAL_RE = re.compile(r"^decimal\((\d+),\s*(\d+)\)$", re.IGNORECASE)
_LEN_RE = re.compile(r"^(char|varchar)\((\d+)\)$", re.IGNORECASE)


def normalize_type(raw_type: str) -> str:
    """把 MySQL / Doris 类型归一化后比较, 忽略 int 展示宽度、大小写、空格。"""
    text = (raw_type or "").strip().lower().replace(" ", "")
    if text in ("bool", "boolean"):
        return "boolean"
    if text.startswith("tinyint(1)"):
        return "boolean"
    base = re.sub(r"\(\d+\)$", "", text)  # int(11) -> int
    if base in _INT_TYPES:
        return base
    return text


def fetch_mysql_columns(mysql_config: dict, database: str, table: str) -> list[dict]:
    reader = MySQLReader(
        host=mysql_config["host"],
        port=mysql_config["port"],
        user=mysql_config["user"],
        password=mysql_config["password"],
        database=database,
        timeout=10,
    )
    try:
        with reader:
            return reader.list_columns(database, table)
    finally:
        reader.close()


def fetch_doris_columns(doris_config: dict, database: str, table: str) -> list[dict]:
    reader = DorisReader(
        host=doris_config["host"],
        port=doris_config["port"],
        user=doris_config["user"],
        password=doris_config["password"],
        database=doris_config.get("database") or database,
        timeout=10,
    )
    try:
        with reader:
            if table not in reader.list_tables(database):
                raise LookupError(f"表 {database}.{table} 在 Doris 中不存在")
            return reader.columns(database, table)
    finally:
        reader.close()


def compare_table(mysql_columns: list[dict], doris_columns: list[dict]) -> dict:
    """比较两边的列集合, 返回差异与一致性结论。"""
    mysql_map = {col["name"]: col for col in mysql_columns}
    doris_map = {col["name"]: col for col in doris_columns}

    differences: list[dict] = []
    warnings: list[dict] = []

    for name in mysql_map:
        if name not in doris_map:
            differences.append(
                {"type": "missing_in_doris", "column": name, "mysql": mysql_map[name]["column_type"], "doris": None}
            )

    for name in doris_map:
        if name not in mysql_map:
            differences.append(
                {"type": "extra_in_doris", "column": name, "mysql": None, "doris": doris_map[name]["column_type"]}
            )

    for name in mysql_map:
        if name not in doris_map:
            continue
        mysql_type = normalize_type(mysql_map[name]["data_type"])
        doris_type = normalize_type(doris_map[name]["data_type"])
        if mysql_type != doris_type:
            differences.append(
                {
                    "type": "type_mismatch",
                    "column": name,
                    "mysql": mysql_map[name]["column_type"],
                    "doris": doris_map[name]["column_type"],
                }
            )

    mysql_names = [col["name"] for col in mysql_columns]
    doris_names = [col["name"] for col in doris_columns]
    if mysql_names != doris_names:
        warnings.append(
            {"type": "column_order_different", "mysql": mysql_names, "doris": doris_names}
        )

    for name in mysql_map:
        if name in doris_map and mysql_map[name]["is_nullable"] != doris_map[name]["is_nullable"]:
            warnings.append(
                {
                    "type": "nullable_different",
                    "column": name,
                    "mysql": mysql_map[name]["is_nullable"],
                    "doris": doris_map[name]["is_nullable"],
                }
            )

    return {
        "consistent": not differences,
        "differences": differences,
        "warnings": warnings,
        "mysql_columns": [{"name": c["name"], "type": c["column_type"], "nullable": c["is_nullable"]} for c in mysql_columns],
        "doris_columns": [{"name": c["name"], "type": c["column_type"], "nullable": c["is_nullable"]} for c in doris_columns],
    }


def check_tables(
    mysql_config: dict,
    doris_config: dict,
    database: str,
    tables: list[str],
    doris_database: str | None = None,
) -> dict:
    """批量校验多张表, 返回 {table: result} 与整体结论。"""
    target_database = doris_database or doris_config.get("database") or database
    results: dict[str, dict] = {}
    errors: dict[str, str] = {}

    for table in tables:
        try:
            mysql_columns = fetch_mysql_columns(mysql_config, database, table)
            doris_columns = fetch_doris_columns(doris_config, target_database, table)
            results[table] = compare_table(mysql_columns, doris_columns)
        except LookupError as exc:
            errors[table] = str(exc)
            results[table] = {
                "consistent": False,
                "differences": [{"type": "table_missing", "message": str(exc)}],
                "warnings": [],
                "mysql_columns": [],
                "doris_columns": [],
            }
        except Exception as exc:
            errors[table] = f"校验失败: {exc}"
            results[table] = {
                "consistent": False,
                "differences": [{"type": "check_error", "message": str(exc)}],
                "warnings": [],
                "mysql_columns": [],
                "doris_columns": [],
            }

    return {
        "database": database,
        "doris_database": target_database,
        "consistent": all(result["consistent"] for result in results.values()),
        "tables": results,
        "errors": errors,
    }


def compare_source_doris(
    source_type: str,
    source_config: dict,
    database: str,
    table: str,
    doris_config: dict | None = None,
    doris_database: str | None = None,
    schema: str | None = None,
) -> dict:
    """通用结构比对: 任意支持读取的源端(MySQL/PG/Oracle/ClickHouse 等) vs Doris。"""
    from ..config import get_doris_config
    from ..readers.doris import DorisReader
    from .schema_sync import _map_source_type_to_doris

    target = doris_config or get_doris_config()
    target_db = doris_database or target.get("database") or database
    try:
        from .schema_sync import fetch_source_columns

        source_columns = fetch_source_columns(
            source_type, source_config, database, table, schema=schema
        )
        reader = DorisReader(
            host=target["host"],
            port=target["port"],
            user=target["user"],
            password=target["password"],
            database=target_db,
            timeout=10,
        )
        with reader:
            if table not in reader.list_tables(target_db):
                return {
                    "consistent": False,
                    "differences": [{"type": "table_missing", "message": f"Doris 表不存在: {target_db}.{table}"}],
                    "warnings": [],
                    "source_columns": [],
                    "doris_columns": [],
                }
            doris_columns = reader.columns(target_db, table)
    except Exception as exc:
        return {
            "consistent": False,
            "differences": [{"type": "check_error", "message": str(exc)}],
            "warnings": [],
            "source_columns": [],
            "doris_columns": [],
        }

    source_map = {c["name"]: c for c in source_columns}
    doris_map = {c["name"]: c for c in doris_columns}
    differences = []
    warnings = []
    for name in source_map:
        if name not in doris_map:
            differences.append({"type": "missing_in_target", "column": name,
                                "source": source_map[name]["column_type"]})
    for name in doris_map:
        if name not in source_map:
            differences.append({"type": "extra_in_target", "column": name,
                                "target": doris_map[name]["column_type"]})
    for name in source_map:
        if name in doris_map:
            source_sig = _map_source_type_to_doris(source_map[name], source_type).lower().replace(" ", "")
            target_sig = (doris_map[name].get("column_type") or "").lower().replace(" ", "")
            if source_sig != target_sig:
                differences.append({
                    "type": "type_mismatch", "column": name,
                    "source": source_map[name]["column_type"], "target": doris_map[name]["column_type"],
                })
            if source_map[name].get("is_nullable") != doris_map[name].get("is_nullable"):
                warnings.append({"type": "nullable_different", "column": name,
                                 "source": source_map[name]["is_nullable"],
                                 "target": doris_map[name]["is_nullable"]})
    return {
        "consistent": not differences,
        "differences": differences,
        "warnings": warnings,
        "source_columns": [
            {"name": c["name"], "type": c["column_type"], "nullable": c["is_nullable"]}
            for c in source_columns
        ],
        "doris_columns": [
            {"name": c["name"], "type": c["column_type"], "nullable": c["is_nullable"]}
            for c in doris_columns
        ],
    }
