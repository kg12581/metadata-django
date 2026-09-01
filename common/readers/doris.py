"""Doris 元数据读取器。

Doris FE 支持 MySQL 协议, 用 pymysql 连接; 列结构通过 DESC 获取。
"""
from __future__ import annotations

import re

_INT_TYPES = {"tinyint", "smallint", "mediumint", "int", "integer", "bigint"}
_CHAR_TYPES = {"char", "varchar"}
_DECIMAL_RE = re.compile(r"^decimal\((\d+),\s*(\d+)\)$", re.IGNORECASE)
_LEN_RE = re.compile(r"^(char|varchar)\((\d+)\)$", re.IGNORECASE)


def parse_column_type(raw_type: str) -> dict:
    """解析 Doris 的 Type 字符串, 返回标准化信息。"""
    text = (raw_type or "").strip()
    lower = text.lower()
    info = {
        "data_type": lower,
        "column_type": text,
        "max_length": None,
        "numeric_precision": None,
        "numeric_scale": None,
    }
    match = _DECIMAL_RE.match(lower)
    if match:
        info["data_type"] = "decimal"
        info["numeric_precision"] = int(match.group(1))
        info["numeric_scale"] = int(match.group(2))
        return info
    match = _LEN_RE.match(lower)
    if match:
        info["data_type"] = match.group(1)
        info["max_length"] = int(match.group(2))
        return info
    base = re.sub(r"\(\d+\)", "", lower)
    if base in _INT_TYPES or base == "boolean":
        info["data_type"] = base
    return info


def quote_identifier(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


class DorisReader:
    """连接 Doris FE, 读取库/表/列信息。"""

    def __init__(self, host, port, user, password, database=None, timeout=10):
        self.host = host
        self.port = int(port)
        self.user = user
        self.password = password
        self.database = database
        self.timeout = timeout
        self._connection = None

    def _connect(self):
        try:
            import pymysql
        except ImportError as exc:
            raise RuntimeError("缺少 PyMySQL, 请先执行: pip install -r requirements.txt") from exc
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            charset="utf8mb4",
            connect_timeout=self.timeout,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def connect(self):
        if self._connection is None:
            self._connection = self._connect()
        return self._connection

    def _execute(self, sql: str) -> list[dict]:
        cursor = self.connect().cursor()
        try:
            cursor.execute(sql)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def list_databases(self) -> list[str]:
        rows = self._execute("SHOW DATABASES")
        return [row["Database"] for row in rows]

    def list_tables(self, database: str) -> list[str]:
        rows = self._execute(f"SHOW TABLES FROM {quote_identifier(database)}")
        key = next(iter(rows[0].keys())) if rows else "Tables_in_" + database
        return [row[key] for row in rows]

    def columns(self, database: str, table: str) -> list[dict]:
        """返回与 MySQLReader.list_columns 相同结构的列信息。"""
        rows = self._execute(
            f"DESC {quote_identifier(database)}.{quote_identifier(table)}"
        )
        result = []
        for index, row in enumerate(rows, start=1):
            info = parse_column_type(row["Type"])
            result.append(
                {
                    "name": row["Field"],
                    "ordinal_position": index,
                    "data_type": info["data_type"],
                    "column_type": info["column_type"],
                    "column_default": row.get("Default"),
                    "is_nullable": (row.get("Null") or "").upper() == "YES",
                    "max_length": info["max_length"],
                    "numeric_precision": info["numeric_precision"],
                    "numeric_scale": info["numeric_scale"],
                    "comment": "",
                }
            )
        return result

    def close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
