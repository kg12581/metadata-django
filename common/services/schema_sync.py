"""MySQL -> Doris 表结构自动对齐服务。

根据 MySQL 元数据自动对 Doris 表执行结构变更:
  - Doris 表不存在 -> 自动建表(Unique Key 模型, 主键来自 MySQL)
  - MySQL 有、Doris 没有的字段 -> ADD COLUMN
  - Doris 有、MySQL 没有的字段 -> DROP COLUMN(可选)
  - 类型/可空性不一致 -> MODIFY COLUMN
"""
from __future__ import annotations

import re

from ..readers.doris import DorisReader, quote_identifier
from ..readers.mysql import MySQLReader
_DATETIME_RE = re.compile(r"^datetime\((\d+)\)$", re.IGNORECASE)

POSTGRES_LIKE_TYPES = {"postgresql", "gaussdb", "dws"}


def map_mysql_type_to_doris(column: dict) -> str:
    """把 MySQL 字段类型映射成 Doris DDL 类型。"""
    data_type = (column.get("data_type") or "").lower()
    column_type = (column.get("column_type") or "").lower()
    max_length = column.get("max_length")
    precision = column.get("numeric_precision")
    scale = column.get("numeric_scale")

    if data_type in ("tinyint",) and column_type in ("tinyint(1)", "tinyint(1) unsigned"):
        return "BOOLEAN"
    if data_type == "tinyint":
        return "TINYINT"
    if data_type == "smallint":
        return "SMALLINT"
    if data_type in ("mediumint", "int", "integer"):
        return "INT"
    if data_type == "bigint":
        return "BIGINT"
    if data_type == "float":
        return "FLOAT"
    if data_type == "double":
        return "DOUBLE"
    if data_type in ("decimal", "numeric"):
        p = precision or 10
        s = scale or 0
        return f"DECIMAL({p},{s})"
    if data_type == "char":
        return f"CHAR({max_length or 1})"
    if data_type == "varchar":
        return f"VARCHAR({max_length or 255})"
    if data_type in ("text", "tinytext", "mediumtext", "longtext"):
        return "STRING"
    if data_type == "date":
        return "DATE"
    if data_type in ("datetime", "timestamp"):
        match = _DATETIME_RE.match(column_type)
        return f"DATETIME({match.group(1)})" if match else "DATETIME"
    if data_type == "time":
        return "STRING"
    if data_type in ("bool", "boolean"):
        return "BOOLEAN"
    if data_type == "json":
        return "JSON"
    if data_type in ("binary", "varbinary", "blob", "tinyblob", "mediumblob", "longblob",
                     "enum", "set", "uuid", "year", "bit"):
        return "STRING"
    return "STRING"


def map_pg_type_to_doris(column: dict) -> str:
    t = (column.get("data_type") or "").lower()
    precision = column.get("numeric_precision")
    scale = column.get("numeric_scale")
    max_length = column.get("max_length")
    if t in ("smallint", "int2"):
        return "SMALLINT"
    if t in ("integer", "int4"):
        return "INT"
    if t in ("bigint", "int8"):
        return "BIGINT"
    if t in ("boolean", "bool"):
        return "BOOLEAN"
    if t in ("numeric", "decimal"):
        if precision is None:
            return "STRING"
        return f"DECIMAL({min(int(precision), 38)},{scale or 0})"
    if t == "real":
        return "FLOAT"
    if t in ("double precision", "float8"):
        return "DOUBLE"
    if t in ("character varying", "varchar"):
        return f"VARCHAR({max_length})" if max_length and max_length <= 65533 else "STRING"
    if t in ("character", "char"):
        return f"CHAR({max_length or 1})"
    if t == "date":
        return "DATE"
    if t in ("timestamp without time zone", "timestamp with time zone", "timestamp"):
        return "DATETIME"
    if t in ("json", "jsonb"):
        return "JSON"
    return "STRING"


def map_oracle_type_to_doris(column: dict) -> str:
    t = (column.get("data_type") or "").lower()
    ct = (column.get("column_type") or "").upper()
    precision = column.get("numeric_precision")
    scale = column.get("numeric_scale")
    max_length = column.get("max_length")
    if t == "number":
        if ct and not ct.startswith("NUMBER("):
            precision = None
        if precision is None:
            return "DOUBLE"
        return f"DECIMAL({precision},{scale or 0})"
    if t in ("float", "binary_double"):
        return "DOUBLE"
    if t == "binary_float":
        return "FLOAT"
    if t in ("varchar2", "nvarchar2"):
        return f"VARCHAR({max_length})" if max_length and max_length <= 65533 else "STRING"
    if t in ("char", "nchar"):
        return f"CHAR({max_length or 1})"
    if t == "date":
        return "DATE"
    if t == "timestamp":
        return "DATETIME"
    if t in ("boolean",):
        return "BOOLEAN"
    return "STRING"


def _map_source_type_to_doris(column: dict, source_type: str) -> str:
    if source_type in POSTGRES_LIKE_TYPES:
        return map_pg_type_to_doris(column)
    if source_type == "oracle":
        return map_oracle_type_to_doris(column)
    return map_mysql_type_to_doris(column)


def _escape_comment(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace("'", "\\'")


def _default_sql(column: dict) -> str:
    """生成 DEFAULT 子句(仅处理可安全表达的默认值)。"""
    default = column.get("column_default")
    if default is None:
        return ""
    text = str(default).strip()
    upper = text.upper()
    if upper in ("NULL",):
        return "DEFAULT NULL"
    if upper.startswith("CURRENT_TIMESTAMP"):
        return "DEFAULT CURRENT_TIMESTAMP"
    # 跳过函数/表达式默认值
    if re.search(r"\(.*\)", text) or upper in ("UUID()", "GEN_RANDOM_UUID()"):
        return ""
    try:
        float(text)
        return f"DEFAULT {text}"
    except ValueError:
        pass
    return f"DEFAULT '{_escape_comment(text)}'"


def column_ddl(column: dict, doris_type: str | None = None, source_type: str = "mysql") -> str:
    """生成单个列的 DDL 片段。"""
    doris_type = doris_type or _map_source_type_to_doris(column, source_type)
    parts = [quote_identifier(column["name"]), doris_type]
    parts.append("NULL" if column.get("is_nullable", True) else "NOT NULL")
    default_sql = _default_sql(column)
    if default_sql:
        parts.append(default_sql)
    comment = (column.get("comment") or "").strip()
    if comment:
        parts.append(f"COMMENT '{_escape_comment(comment)}'")
    return " ".join(parts)


def fetch_mysql_primary_keys(mysql_config: dict, database: str, table: str) -> list[str]:
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
            for index in reader.list_indexes(database, table):
                if index.get("is_primary"):
                    return list(index.get("column_names") or [])
    finally:
        reader.close()
    return []


def fetch_source_columns(source_type: str, config: dict, database: str, table: str,
                         schema: str | None = None) -> list[dict]:
    """按源类型读取字段(MySQL 协议 / PG 协议 / Oracle)。"""
    if source_type in POSTGRES_LIKE_TYPES:
        from ..readers.postgresql import PostgreSQLReader

        reader = PostgreSQLReader(
            host=config["host"], port=config.get("port", 5432), user=config.get("user", ""),
            password=config.get("password", ""), database=database, timeout=10,
        )
        try:
            with reader:
                return reader.list_columns(schema or "public", table)
        finally:
            reader.close()
    if source_type == "oracle":
        from ..readers.oracle import OracleReader

        reader = OracleReader(
            host=config["host"], port=config.get("port", 1521), user=config.get("user", ""),
            password=config.get("password", ""), database=database, timeout=10,
        )
        try:
            with reader:
                return reader.list_columns(schema or "", table)
        finally:
            reader.close()
    from ..readers.mysql import MySQLReader

    reader = MySQLReader(
        host=config["host"], port=config.get("port", 3306), user=config.get("user", ""),
        password=config.get("password", ""), database=database, timeout=10,
    )
    try:
        with reader:
            return reader.list_columns(database, table)
    finally:
        reader.close()


def fetch_source_primary_keys(source_type: str, config: dict, database: str, table: str,
                              schema: str | None = None) -> list[str]:
    if source_type == "oracle":
        from ..readers.oracle import OracleReader

        reader = OracleReader(
            host=config["host"], port=config.get("port", 1521), user=config.get("user", ""),
            password=config.get("password", ""), database=database, timeout=10,
        )
        try:
            with reader:
                return reader.primary_keys(table)
        finally:
            reader.close()
    if source_type in POSTGRES_LIKE_TYPES:
        from ..readers.postgresql import PostgreSQLReader

        reader = PostgreSQLReader(
            host=config["host"], port=config.get("port", 5432), user=config.get("user", ""),
            password=config.get("password", ""), database=database, timeout=10,
        )
        try:
            with reader:
                for index in reader.list_indexes(schema or "public", table):
                    if index.get("is_primary"):
                        return list(index.get("column_names") or [])
        finally:
            reader.close()
        return []
    return fetch_mysql_primary_keys(config, database, table)


def fetch_doris_table(doris_config: dict, database: str, table: str):
    """返回 Doris 列列表; 表不存在返回 None。"""
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
                return None
            return reader.columns(database, table)
    finally:
        reader.close()


def diff_columns(mysql_columns: list[dict], doris_columns: list[dict],
                 source_type: str = "mysql") -> dict:
    mysql_map = {col["name"]: col for col in mysql_columns}
    doris_map = {col["name"]: col for col in doris_columns}

    add = [mysql_map[name] for name in mysql_map if name not in doris_map]
    drop = [doris_map[name] for name in doris_map if name not in mysql_map]
    modify = []
    for name in mysql_map:
        if name not in doris_map:
            continue
        m, d = mysql_map[name], doris_map[name]
        mysql_sig = _map_source_type_to_doris(m, source_type).lower().replace(" ", "")
        doris_sig = (d.get("column_type") or "").lower().replace(" ", "")
        type_same = mysql_sig == doris_sig
        nullable_same = m.get("is_nullable") == d.get("is_nullable")
        if not (type_same and nullable_same):
            modify.append({"mysql": m, "doris": d})
    return {"add": add, "drop": drop, "modify": modify}


def build_create_statement(database: str, table: str, mysql_columns: list[dict],
                           primary_keys: list[str], source_type: str = "mysql") -> str:
    if not mysql_columns:
        raise ValueError(f"MySQL 表 {database}.{table} 没有字段, 无法建表")
    if not primary_keys:
        primary_keys = [mysql_columns[0]["name"]]
    lines = [f"CREATE TABLE {quote_identifier(database)}.{quote_identifier(table)} ("]
    lines.extend(f"    {column_ddl(col, source_type=source_type)}," for col in mysql_columns)
    lines.append(f"    UNIQUE KEY ({', '.join(quote_identifier(k) for k in primary_keys)})")
    lines.append(")")
    lines.append(f"DISTRIBUTED BY HASH({quote_identifier(primary_keys[0])}) BUCKETS 1")
    lines.append('PROPERTIES ("replication_num" = "1")')
    return "\n".join(lines)


def build_alter_statements(database: str, table: str, diff: dict,
                           drop_columns: bool = True, source_type: str = "mysql") -> list[str]:
    statements = []
    for column in diff["add"]:
        statements.append(
            f"ALTER TABLE {quote_identifier(database)}.{quote_identifier(table)} "
            f"ADD COLUMN {column_ddl(column, source_type=source_type)}"
        )
    for column in diff["drop"]:
        if drop_columns:
            statements.append(
                f"ALTER TABLE {quote_identifier(database)}.{quote_identifier(table)} "
                f"DROP COLUMN {quote_identifier(column['name'])}"
            )
    for item in diff["modify"]:
        column = item["mysql"]
        statements.append(
            f"ALTER TABLE {quote_identifier(database)}.{quote_identifier(table)} "
            f"MODIFY COLUMN {column_ddl(column, source_type=source_type)}"
        )
    return statements


def _fetch_mysql_columns(mysql_config: dict, database: str, table: str) -> list[dict]:
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


def plan_table_sync(
    config: dict,
    doris_config: dict,
    database: str,
    table: str,
    doris_database: str | None = None,
    *,
    source_type: str = "mysql",
    drop_columns: bool = True,
    auto_create: bool = True,
) -> dict:
    """生成某张表的对齐方案(不执行), 返回 actions + SQL 语句。"""
    target_database = doris_database or doris_config.get("database") or database
    source_columns = fetch_source_columns(source_type, config, database, table)
    doris_columns = fetch_doris_table(doris_config, target_database, table)

    plan = {
        "table": table,
        "doris_table": f"{target_database}.{table}",
        "create": False,
        "add_columns": [],
        "drop_columns": [],
        "modify_columns": [],
        "statements": [],
        "warnings": [],
    }

    if doris_columns is None:
        if not auto_create:
            plan["warnings"].append("Doris 表不存在且 auto_create=false")
            return plan
        primary_keys = fetch_source_primary_keys(source_type, config, database, table)
        if not primary_keys:
            plan["warnings"].append(
                f"源表无主键, 自动建表将使用首个字段 {source_columns[0]['name']} 作为 key"
            )
        plan["create"] = True
        plan["statements"].append(
            build_create_statement(
                target_database, table, source_columns, primary_keys,
                source_type=source_type,
            )
        )
        return plan

    diff = diff_columns(source_columns, doris_columns, source_type=source_type)
    plan["add_columns"] = [col["name"] for col in diff["add"]]
    plan["drop_columns"] = [col["name"] for col in diff["drop"]]
    plan["modify_columns"] = [
        {"column": item["mysql"]["name"],
         "mysql": item["mysql"]["column_type"],
         "doris": item["doris"]["column_type"]}
        for item in diff["modify"]
    ]
    plan["statements"] = build_alter_statements(
        target_database, table, diff, drop_columns=drop_columns, source_type=source_type
    )
    if diff["drop"] and not drop_columns:
        plan["warnings"].append("检测到 Doris 多余字段, drop_columns=false 已跳过")
    return plan


def execute_statements(doris_config: dict, statements: list[str]) -> list[dict]:
    """在 Doris 上按顺序执行 DDL, 返回每条的执行结果。"""
    import pymysql

    results = []
    if not statements:
        return results
    connection = pymysql.connect(
        host=doris_config["host"],
        port=doris_config["port"],
        user=doris_config["user"],
        password=doris_config["password"],
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=10,
    )
    try:
        with connection.cursor() as cursor:
            for statement in statements:
                try:
                    cursor.execute(statement)
                    results.append({"statement": statement, "success": True})
                except Exception as exc:
                    results.append({"statement": statement, "success": False, "error": str(exc)})
    finally:
        connection.close()
    return results


def sync_table_schema(
    config: dict,
    doris_config: dict,
    database: str,
    table: str,
    doris_database: str | None = None,
    *,
    source_type: str = "mysql",
    preview: bool = True,
    drop_columns: bool = True,
    auto_create: bool = True,
) -> dict:
    """预览或执行单表结构对齐, 返回结果。"""
    plan = plan_table_sync(
        config,
        doris_config,
        database,
        table,
        doris_database=doris_database,
        source_type=source_type,
        drop_columns=drop_columns,
        auto_create=auto_create,
    )
    plan["preview"] = preview
    plan["executed"] = False
    plan["results"] = []
    if preview:
        return plan
    plan["results"] = execute_statements(doris_config, plan["statements"])
    plan["executed"] = True
    plan["success"] = all(r["success"] for r in plan["results"]) if plan["results"] else True
    return plan
