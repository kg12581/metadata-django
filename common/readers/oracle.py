"""Oracle 元数据读取器 (python-oracledb thin 模式)。"""
from __future__ import annotations

import re

from .base import MetadataReader

_NUMBER_RE = re.compile(r"^NUMBER\((\d+)(?:,\s*(\d+))?\)$", re.IGNORECASE)
_LEN_RE = re.compile(r"^(VARCHAR2|NVARCHAR2|CHAR|NCHAR|RAW)\((\d+)(?:\s+BYTE|\s+CHAR)?\)$", re.IGNORECASE)


def parse_oracle_type(data_type: str, data_length, precision, scale) -> dict:
    text = (data_type or "").strip()
    info = {
        "data_type": text.lower(),
        "column_type": text,
        "max_length": None,
        "numeric_precision": None,
        "numeric_scale": None,
    }
    upper = text.upper()
    match = _LEN_RE.match(text)
    if match:
        info["data_type"] = match.group(1).lower()
        info["column_type"] = text
        info["max_length"] = int(match.group(2))
        return info
    match = _NUMBER_RE.match(text)
    if match:
        info["data_type"] = "number"
        info["numeric_precision"] = int(match.group(1))
        info["numeric_scale"] = int(match.group(2) or 0)
        return info
    ts = re.match(r"^(TIMESTAMP)(?:\((\d+)\))?( WITH TIME ZONE| WITH LOCAL TIME ZONE)?$", text, re.IGNORECASE)
    if ts:
        info["data_type"] = "timestamp"
        info["column_type"] = text
        return info
    if upper == "NUMBER":
        info["numeric_precision"] = precision
        info["numeric_scale"] = scale
    elif upper in ("VARCHAR2", "NVARCHAR2", "CHAR", "NCHAR", "RAW"):
        info["max_length"] = int(data_length or 0) or None
    return info


class OracleReader(MetadataReader):
    """连接 Oracle(thin), database 参数为 service name / SID。"""

    DB_TYPE = "oracle"

    def _connect(self):
        try:
            import oracledb
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("缺少 oracledb, 请先执行: pip install oracledb") from exc
        return oracledb.connect(
            user=self.user,
            password=self.password,
            dsn=f"{self.host}:{self.port}/{self.database}",
        )

    def _execute(self, sql: str, params: tuple = ()) -> list[tuple]:
        cursor = self.connect().cursor()
        try:
            cursor.execute(sql, params)
            return list(cursor.fetchall())
        finally:
            cursor.close()

    def list_schemas(self) -> list[str]:
        return [self.user.upper()] if self.user else [self.database]

    def list_tables(self, schema: str | None = None) -> list[dict]:
        rows = self._execute(
            """
            SELECT table_name, 'TABLE' AS table_type FROM user_tables
            UNION ALL
            SELECT view_name, 'VIEW' FROM user_views
            ORDER BY 1
            """
        )
        comments = {
            row[0]: (row[1] or "")
            for row in self._execute(
                "SELECT table_name, comments FROM user_tab_comments"
            )
        }
        return [
            {
                "schema": self.user.upper() if self.user else self.database,
                "name": row[0],
                "table_type": row[1],
                "comment": comments.get(row[0], ""),
            }
            for row in rows
        ]

    def list_columns(self, schema: str, table: str) -> list[dict]:
        rows = self._execute(
            """
            SELECT c.column_name, c.data_type, c.data_length,
                   c.data_precision, c.data_scale, c.nullable, c.data_default,
                   cc.comments
            FROM user_tab_columns c
            LEFT JOIN user_col_comments cc
                   ON cc.table_name = c.table_name AND cc.column_name = c.column_name
            WHERE c.table_name = :1
            ORDER BY c.column_id
            """,
            (table.upper(),),
        )
        result = []
        for index, row in enumerate(rows, start=1):
            info = parse_oracle_type(row[1], row[2], row[3], row[4])
            result.append(
                {
                    "name": row[0],
                    "ordinal_position": index,
                    "data_type": info["data_type"],
                    "column_type": info["column_type"],
                    "column_default": row[6],
                    "is_nullable": (row[5] or "Y").upper() == "Y",
                    "max_length": info["max_length"],
                    "numeric_precision": info["numeric_precision"],
                    "numeric_scale": info["numeric_scale"],
                    "comment": row[7] or "",
                }
            )
        return result

    def primary_keys(self, table: str) -> list[str]:
        rows = self._execute(
            """
            SELECT cc.column_name
            FROM user_constraints c
            JOIN user_cons_columns cc
              ON cc.constraint_name = c.constraint_name
             AND cc.owner = c.owner
            WHERE c.table_name = :1 AND c.constraint_type = 'P'
            ORDER BY cc.position
            """,
            (table.upper(),),
        )
        return [row[0] for row in rows]

    def list_indexes(self, schema: str, table: str) -> list[dict]:
        return []

    def list_constraints(self, schema: str, table: str) -> list[dict]:
        return []
