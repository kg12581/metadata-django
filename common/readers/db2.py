"""DB2 元数据读取器 (ibm_db, 需 DB2 驱动)。"""
from __future__ import annotations

from .base import MetadataReader


class DB2Reader(MetadataReader):
    DB_TYPE = "db2"

    def _connect(self):
        try:
            import ibm_db
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "缺少 ibm_db 驱动, 请先安装 DB2 客户端并执行: pip install ibm_db"
            ) from exc
        conn_str = (
            f"DATABASE={self.database};HOSTNAME={self.host};PORT={self.port or 50000};"
            f"UID={self.user};PWD={self.password};PROTOCOL=TCPIP"
        )
        return ibm_db.connect(conn_str, "", "")

    def _fetch(self, sql: str) -> list[tuple]:
        import ibm_db

        stmt = ibm_db.exec_immediate(self.connect(), sql)
        rows = []
        row = ibm_db.fetch_tuple(stmt)
        while row is not False:
            rows.append(tuple(row))
            row = ibm_db.fetch_tuple(stmt)
        ibm_db.free_result(stmt)
        return rows

    def list_schemas(self) -> list[str]:
        rows = self._fetch(
            "SELECT DISTINCT TABSCHEMA FROM SYSCAT.TABLES "
            "WHERE TABSCHEMA NOT IN ('SYSIBM','SYSCAT','SYSSTAT','SYSTOOLS')"
        )
        return [row[0] for row in rows]

    def list_tables(self, schema: str | None = None) -> list[dict]:
        owner = (schema or self.user or "USER").upper()
        safe_owner = owner.replace("'", "''")
        rows = self._fetch(
            "SELECT TABNAME, TYPE, REMARKS FROM SYSCAT.TABLES "
            f"WHERE TABSCHEMA = '{safe_owner}' ORDER BY TABNAME"
        )
        return [
            {
                "schema": owner,
                "name": row[0],
                "table_type": "VIEW" if row[1] == "V" else "TABLE",
                "comment": row[2] or "",
            }
            for row in rows
        ]

    def list_columns(self, schema: str, table: str) -> list[dict]:
        owner = (schema or self.user or "USER").upper()
        safe = (owner, table.upper())
        rows = self._fetch(
            "SELECT COLNAME, TYPENAME, LENGTH, SCALE, NULLS, REMARKS, DEFAULT, COLNO "
            "FROM SYSCAT.COLUMNS "
            f"WHERE TABSCHEMA = '{safe[0].replace(chr(39), chr(39) * 2)}' "
            f"AND TABNAME = '{safe[1].replace(chr(39), chr(39) * 2)}' ORDER BY COLNO"
        )
        result = []
        for index, row in enumerate(rows, start=1):
            data_type = (row[1] or "").lower()
            result.append(
                {
                    "name": row[0],
                    "ordinal_position": index,
                    "data_type": data_type,
                    "column_type": row[1] or "",
                    "column_default": row[6],
                    "is_nullable": (row[4] or "Y").upper() == "Y",
                    "max_length": int(row[2]) if data_type in ("varchar", "char", "graphic") else None,
                    "numeric_precision": int(row[2]) if data_type in ("decimal", "numeric") else None,
                    "numeric_scale": int(row[3] or 0) if data_type in ("decimal", "numeric") else None,
                    "comment": row[5] or "",
                }
            )
        return result

    def list_indexes(self, schema: str, table: str) -> list[dict]:
        return []

    def list_constraints(self, schema: str, table: str) -> list[dict]:
        return []
