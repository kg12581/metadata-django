"""MySQL 元数据读取器 (information_schema)。"""
from __future__ import annotations

from .base import MetadataReader


class MySQLReader(MetadataReader):
    DB_TYPE = "mysql"

    def _connect(self):
        try:
            import pymysql
        except ImportError as exc:  # pragma: no cover - 依赖缺失提示
            raise RuntimeError(
                "缺少 PyMySQL, 请先执行: pip install -r requirements.txt"
            ) from exc
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

    def _execute(self, sql: str, params: tuple) -> list[dict]:
        cursor = self.connect().cursor()
        try:
            cursor.execute(sql, params)
            # MySQL information_schema 返回大写列名, 统一转小写
            return [{key.lower(): value for key, value in row.items()} for row in cursor.fetchall()]
        finally:
            cursor.close()

    def list_schemas(self) -> list[str]:
        rows = self._execute(
            """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
            ORDER BY schema_name
            """,
            (),
        )
        return [row["schema_name"] for row in rows]

    def list_tables(self, schema: str) -> list[dict]:
        rows = self._execute(
            """
            SELECT table_schema, table_name, table_type, table_comment
            FROM information_schema.tables
            WHERE table_schema = %s
            ORDER BY table_name
            """,
            (schema,),
        )
        return [
            {
                "schema": row["table_schema"],
                "name": row["table_name"],
                "table_type": row["table_type"] or "",
                "comment": row["table_comment"] or "",
            }
            for row in rows
        ]

    def list_columns(self, schema: str, table: str) -> list[dict]:
        rows = self._execute(
            """
            SELECT column_name,
                   ordinal_position,
                   data_type,
                   column_type,
                   column_default,
                   is_nullable,
                   character_maximum_length AS max_length,
                   numeric_precision,
                   numeric_scale,
                   column_comment AS comment
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema, table),
        )
        return [
            {
                "name": row["column_name"],
                "ordinal_position": row["ordinal_position"],
                "data_type": row["data_type"] or "",
                "column_type": row["column_type"] or "",
                "column_default": row["column_default"],
                "is_nullable": (row["is_nullable"] or "").upper() == "YES",
                "max_length": row["max_length"],
                "numeric_precision": row["numeric_precision"],
                "numeric_scale": row["numeric_scale"],
                "comment": row["comment"] or "",
            }
            for row in rows
        ]

    def list_indexes(self, schema: str, table: str) -> list[dict]:
        rows = self._execute(
            """
            SELECT index_name, non_unique, column_name, seq_in_index
            FROM information_schema.statistics
            WHERE table_schema = %s
              AND table_name = %s
            ORDER BY index_name, seq_in_index
            """,
            (schema, table),
        )
        grouped: dict[str, dict] = {}
        for row in rows:
            entry = grouped.setdefault(
                row["index_name"],
                {
                    "name": row["index_name"],
                    "is_unique": row["non_unique"] == 0,
                    "is_primary": row["index_name"] == "PRIMARY",
                    "column_names": [],
                    "definition": "",
                },
            )
            if row["column_name"] and row["column_name"] not in entry["column_names"]:
                entry["column_names"].append(row["column_name"])
        return list(grouped.values())

    def list_constraints(self, schema: str, table: str) -> list[dict]:
        rows = self._execute(
            """
            SELECT tc.constraint_name,
                   tc.constraint_type,
                   kcu.column_name,
                   kcu.referenced_table_name AS referenced_table,
                   kcu.referenced_column_name AS referenced_column
            FROM information_schema.table_constraints tc
            LEFT JOIN information_schema.key_column_usage kcu
                   ON kcu.constraint_schema = tc.constraint_schema
                  AND kcu.table_name = tc.table_name
                  AND kcu.constraint_name = tc.constraint_name
            WHERE tc.table_schema = %s
              AND tc.table_name = %s
            ORDER BY tc.constraint_name, kcu.ordinal_position
            """,
            (schema, table),
        )
        grouped: dict[str, dict] = {}
        for row in rows:
            entry = grouped.setdefault(
                row["constraint_name"],
                {
                    "name": row["constraint_name"],
                    "constraint_type": row["constraint_type"],
                    "column_names": [],
                    "referenced_table": row["referenced_table"] or "",
                    "referenced_column": row["referenced_column"] or "",
                },
            )
            if row["column_name"] and row["column_name"] not in entry["column_names"]:
                entry["column_names"].append(row["column_name"])
            if not entry["referenced_table"] and row["referenced_table"]:
                entry["referenced_table"] = row["referenced_table"]
            if not entry["referenced_column"] and row["referenced_column"]:
                entry["referenced_column"] = row["referenced_column"]
        return list(grouped.values())
