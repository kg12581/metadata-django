"""MaxCompute(ODPS) 元数据读取器 (pyodps)。"""
from __future__ import annotations

import re

from .base import MetadataReader

_DECIMAL_RE = re.compile(r"^decimal\((\d+),\s*(\d+)\)$", re.IGNORECASE)


def parse_odps_type(raw_type: str) -> dict:
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
    elif lower.startswith(("string", "varchar", "char")):
        size = re.search(r"\((\d+)\)", lower)
        if size:
            info["max_length"] = int(size.group(1))
            info["data_type"] = lower.split("(", 1)[0]
    return info


class ODPSReader(MetadataReader):
    DB_TYPE = "odps"

    def __init__(self, host, port, user, password, database, schema=None, timeout=15):
        super().__init__(host, port, user, password, database, schema=schema, timeout=timeout)
        self._odps = None

    def _connect(self):
        try:
            from odps import ODPS
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("缺少 pyodps, 请先执行: pip install pyodps") from exc
        # host=endpoint, user/password=AccessId/Secret, database=Project
        self._odps = ODPS(
            self.user,
            self.password,
            project=self.database,
            endpoint=self.host,
        )
        return self._odps

    def list_schemas(self) -> list[str]:
        return [self.database]

    def _tables(self, limit: int = 2000):
        odps = self.connect()
        tables = []
        for index, table in enumerate(odps.list_tables()):
            if index >= limit:
                break
            tables.append(table.name)
        return tables

    def list_tables(self, schema: str | None = None) -> list[dict]:
        return [
            {
                "schema": self.database,
                "name": name,
                "table_type": "TABLE",
                "comment": "",
            }
            for name in self._tables()
        ]

    def list_columns(self, schema: str, table: str) -> list[dict]:
        odps = self.connect()
        target = odps.get_table(table)
        result = []
        for index, column in enumerate(target.schema.columns, start=1):
            info = parse_odps_type(str(column.type))
            result.append(
                {
                    "name": column.name,
                    "ordinal_position": index,
                    "data_type": info["data_type"],
                    "column_type": info["column_type"],
                    "column_default": None,
                    "is_nullable": True,
                    "max_length": info["max_length"],
                    "numeric_precision": info["numeric_precision"],
                    "numeric_scale": info["numeric_scale"],
                    "comment": getattr(column, "comment", None) or "",
                }
            )
        for partition in target.schema.partitions:
            info = parse_odps_type(str(partition.type))
            result.append(
                {
                    "name": partition.name,
                    "ordinal_position": len(result) + 1,
                    "data_type": info["data_type"],
                    "column_type": info["column_type"],
                    "column_default": None,
                    "is_nullable": True,
                    "max_length": info["max_length"],
                    "numeric_precision": info["numeric_precision"],
                    "numeric_scale": info["numeric_scale"],
                    "comment": f"分区字段: {getattr(partition, 'comment', None) or ''}",
                }
            )
        return result

    def list_indexes(self, schema: str, table: str) -> list[dict]:
        return []

    def list_constraints(self, schema: str, table: str) -> list[dict]:
        return []
