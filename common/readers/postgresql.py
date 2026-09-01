"""PostgreSQL 元数据读取器 (information_schema + pg_catalog)。"""
from __future__ import annotations

from .base import MetadataReader


class PostgreSQLReader(MetadataReader):
    DB_TYPE = "postgresql"

    def _connect(self):
        try:
            import psycopg2
            from psycopg2.extras import DictCursor
        except ImportError as exc:  # pragma: no cover - 依赖缺失提示
            raise RuntimeError(
                "缺少 psycopg2, 请先执行: pip install -r requirements.txt"
            ) from exc
        return psycopg2.connect(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.user,
            password=self.password,
            connect_timeout=self.timeout,
            cursor_factory=DictCursor,
        )

    def _execute(self, sql: str, params: dict) -> list[dict]:
        cursor = self.connect().cursor()
        try:
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def list_schemas(self) -> list[str]:
        rows = self._execute(
            """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name NOT IN ('pg_catalog', 'information_schema')
              AND schema_name NOT LIKE 'pg_toast%'
              AND schema_name NOT LIKE 'pg_temp%'
            ORDER BY schema_name
            """,
            None,
        )
        return [row["schema_name"] for row in rows]

    def list_tables(self, schema: str) -> list[dict]:
        rows = self._execute(
            """
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = %(schema)s
            ORDER BY table_name
            """,
            {"schema": schema},
        )
        comments = self._execute(
            """
            SELECT c.relname AS table_name, obj_description(c.oid, 'pg_class') AS comment
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = %(schema)s
              AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
            """,
            {"schema": schema},
        )
        comment_map = {row["table_name"]: (row["comment"] or "") for row in comments}
        return [
            {
                "schema": row["table_schema"],
                "name": row["table_name"],
                "table_type": row["table_type"] or "",
                "comment": comment_map.get(row["table_name"], ""),
            }
            for row in rows
        ]

    def list_columns(self, schema: str, table: str) -> list[dict]:
        rows = self._execute(
            """
            SELECT c.column_name,
                   c.ordinal_position,
                   c.data_type,
                   c.udt_name AS column_type,
                   c.column_default,
                   c.is_nullable,
                   c.character_maximum_length AS max_length,
                   c.numeric_precision,
                   c.numeric_scale,
                   col_description(
                       format('%%I.%%I', c.table_schema, c.table_name)::regclass::oid,
                       c.ordinal_position
                   ) AS comment
            FROM information_schema.columns c
            WHERE c.table_schema = %(schema)s
              AND c.table_name = %(table)s
            ORDER BY c.ordinal_position
            """,
            {"schema": schema, "table": table},
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
            SELECT c2.relname AS index_name,
                   i.indisunique AS is_unique,
                   i.indisprimary AS is_primary,
                   pg_get_indexdef(i.indexrelid) AS definition,
                   ARRAY(
                       SELECT a.attname
                       FROM unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord)
                       JOIN pg_attribute a
                         ON a.attrelid = c1.oid AND a.attnum = k.attnum
                       ORDER BY k.ord
                   ) AS column_names
            FROM pg_class c1
            JOIN pg_namespace n ON n.oid = c1.relnamespace
            JOIN pg_index i ON i.indrelid = c1.oid
            JOIN pg_class c2 ON c2.oid = i.indexrelid
            WHERE n.nspname = %(schema)s
              AND c1.relname = %(table)s
            ORDER BY c2.relname
            """,
            {"schema": schema, "table": table},
        )
        return [
            {
                "name": row["index_name"],
                "is_unique": bool(row["is_unique"]),
                "is_primary": bool(row["is_primary"]),
                "column_names": list(row["column_names"] or []),
                "definition": row["definition"] or "",
            }
            for row in rows
        ]

    def list_constraints(self, schema: str, table: str) -> list[dict]:
        rows = self._execute(
            """
            SELECT tc.constraint_name,
                   tc.constraint_type,
                   kcu.column_name,
                   ccu.table_schema AS referenced_schema,
                   ccu.table_name   AS referenced_table,
                   ccu.column_name  AS referenced_column
            FROM information_schema.table_constraints tc
            LEFT JOIN information_schema.key_column_usage kcu
                   ON kcu.constraint_name = tc.constraint_name
                  AND kcu.table_schema = tc.table_schema
                  AND kcu.table_name = tc.table_name
            LEFT JOIN information_schema.constraint_column_usage ccu
                   ON ccu.constraint_name = tc.constraint_name
                  AND ccu.constraint_schema = tc.constraint_schema
            WHERE tc.table_schema = %(schema)s
              AND tc.table_name = %(table)s
            ORDER BY tc.constraint_name, kcu.ordinal_position
            """,
            {"schema": schema, "table": table},
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
