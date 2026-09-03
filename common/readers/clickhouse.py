"""ClickHouse 元数据读取器 (clickhouse-connect, HTTP 8123)。"""
from __future__ import annotations

import re

from .base import MetadataReader


class ClickHouseReader(MetadataReader):
    DB_TYPE = "clickhouse"

    def _connect(self):
        try:
            import clickhouse_connect
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("缺少 clickhouse-connect, 请先执行: pip install clickhouse-connect") from exc
        return clickhouse_connect.get_client(
            host=self.host,
            port=self.port or 8123,
            username=self.user,
            password=self.password,
            database=self.database or "default",
            connect_timeout=self.timeout,
        )

    def list_schemas(self) -> list[str]:
        if self.database:
            return [self.database]
        rows = self.connect().query("SHOW DATABASES").result_rows
        return [row[0] for row in rows if row[0] not in ("system", "INFORMATION_SCHEMA")]

    def list_tables(self, schema: str | None = None) -> list[dict]:
        database = schema or self.database or "default"
        rows = self.connect().query(
            "SELECT name, engine, comment FROM system.tables "
            "WHERE database = {database:String} ORDER BY name",
            parameters={"database": database},
        ).result_rows
        return [
            {
                "schema": database,
                "name": row[0],
                "table_type": row[1] or "TABLE",
                "comment": row[2] or "",
            }
            for row in rows
        ]

    def list_columns(self, schema: str, table: str) -> list[dict]:
        database = schema or self.database or "default"
        rows = self.connect().query(
            "SELECT name, type, comment FROM system.columns "
            "WHERE database = {database:String} AND table = {table:String} "
            "ORDER BY position",
            parameters={"database": database, "table": table},
        ).result_rows
        result = []
        for index, row in enumerate(rows, start=1):
            raw_type = row[1] or ""
            lower = raw_type.lower()
            base = lower.split("(", 1)[0]
            precision = scale = max_length = None
            decimal = re.match(r"^decimal\((\d+),\s*(\d+)\)", lower)
            if decimal:
                precision, scale = int(decimal.group(1)), int(decimal.group(2))
            fixed = re.match(r"^fixedstring\((\d+)\)", lower)
            if fixed:
                max_length = int(fixed.group(1))
            result.append(
                {
                    "name": row[0],
                    "ordinal_position": index,
                    "data_type": base or lower,
                    "column_type": raw_type,
                    "column_default": None,
                    "is_nullable": True,
                    "max_length": max_length,
                    "numeric_precision": precision,
                    "numeric_scale": scale,
                    "comment": row[2] or "",
                }
            )
        return result

    def list_indexes(self, schema: str, table: str) -> list[dict]:
        return []

    def list_constraints(self, schema: str, table: str) -> list[dict]:
        return []
