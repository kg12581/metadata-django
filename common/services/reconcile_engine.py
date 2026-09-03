"""对账引擎: 行数 / 主键快照 / 字段值 / 业务指标 / 元数据 五种对账。"""
from __future__ import annotations

import hashlib
import time

from django.utils import timezone

from ..models import ReconcileRun, ReconcileTask
from .reconcile import (
    count_doris_table,
    count_mysql_table,
    count_pg_table,
)


def source_connection(source_config, database: str) -> dict | None:
    if source_config is None:
        return None
    return {
        "host": source_config.host,
        "port": source_config.port or 3306,
        "user": source_config.username or "",
        "password": source_config.password or "",
        "database": database or source_config.database_name,
    }


def _query(conn_config: dict, sql: str, db_type: str = "mysql") -> list[tuple]:
    if db_type == "postgresql":
        import psycopg2

        conn = psycopg2.connect(**conn_config, connect_timeout=10)
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                return cursor.fetchall()
        finally:
            conn.close()
    import pymysql

    conn = pymysql.connect(**conn_config, connect_timeout=10)
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            return list(cursor.fetchall())
    finally:
        conn.close()


def _table_sql(identifier: str, table: str) -> str:
    return f"`{table}`"


def _row_count(source_type: str, src: dict, database: str, schema: str, table: str,
               target: dict, target_db: str) -> dict:
    if source_type == "postgresql":
        source_count = count_pg_table(src, database, schema or "public", table)
    else:
        source_count = count_mysql_table(src, database, table)
    try:
        target_count = count_doris_table(target, target_db, table)
    except Exception as exc:
        return {"table": table, "status": "target_missing", "message": str(exc)}
    return {
        "table": table,
        "source_count": source_count,
        "target_count": target_count,
        "status": "ok" if source_count == target_count else "mismatch",
        "diff": target_count - source_count,
    }


def _fetch_hash(conn: dict, db_type: str, table_sql: str, pk_sql: str, limit: int = 200000) -> dict:
    rows = _query(conn, f"SELECT {pk_sql} FROM {table_sql} ORDER BY {pk_sql}", db_type)
    count = len(rows)
    if count > limit:
        return {"count": count, "hash": None, "sampled": True}
    digest = hashlib.md5()
    for row in rows:
        digest.update("|".join(str(v) for v in row).encode("utf-8", errors="replace"))
        digest.update(b";")
    return {"count": count, "hash": digest.hexdigest(), "sampled": False}


def _pk_snapshot(source_type: str, src: dict, database: str, schema: str, table: str,
                 target: dict, target_db: str, pk_columns: list[str]) -> dict:
    pk_sql = ", ".join(f"`{c}`" for c in pk_columns)
    try:
        source = _fetch_hash(src, source_type, _table_sql("", table), pk_sql)
    except Exception as exc:
        return {"table": table, "status": "source_error", "message": str(exc)}
    try:
        target = _fetch_hash(target, "mysql", f"`{table}`", pk_sql)
    except Exception as exc:
        return {"table": table, "status": "target_missing", "message": str(exc)}
    same = source["count"] == target["count"] and (
        source["sampled"] or source["hash"] == target["hash"]
    )
    return {
        "table": table,
        "source_count": source["count"],
        "target_count": target["count"],
        "source_hash": source["hash"],
        "target_hash": target["hash"],
        "status": "ok" if same else "mismatch",
    }


def _field_value(source_type: str, src: dict, database: str, schema: str, table: str,
                 target: dict, target_db: str, columns: list[str]) -> dict:
    if not columns:
        return {"table": table, "status": "skipped", "message": "未配置 columns"}
    try:
        count_doris_table(target, target_db, table)
    except Exception as exc:
        return {"table": table, "status": "target_missing", "message": str(exc)}
    differences = []
    for column in columns:
        quoted = f"`{column}`"
        sql = (
            f"SELECT COUNT({quoted}), COUNT(DISTINCT {quoted}), "
            f"MIN({quoted}), MAX({quoted}) FROM {_table_sql('', table)}"
        )
        try:
            source_row = _query(src, sql, source_type)[0]
            target_row = _query(target, sql)[0]
        except Exception as exc:
            differences.append({"column": column, "status": "error", "message": str(exc)})
            continue
        source_vals = [str(v) for v in source_row]
        target_vals = [str(v) for v in target_row]
        if source_vals != target_vals:
            differences.append(
                {
                    "column": column,
                    "status": "mismatch",
                    "source": source_vals,
                    "target": target_vals,
                }
            )
    return {
        "table": table,
        "status": "ok" if not differences else "mismatch",
        "differences": differences,
    }


def _metric(source_type: str, src: dict, database: str, schema: str, table: str,
            target: dict, target_db: str, metric_sql: str) -> dict:
    try:
        count_doris_table(target, target_db, table)
    except Exception as exc:
        return {"table": table, "status": "target_missing", "message": str(exc)}
    sql = metric_sql.format(schema=schema or "", table=table)
    try:
        source_rows = _query(src, sql, source_type)
        target_rows = _query(target, sql)
    except Exception as exc:
        return {"table": table, "status": "error", "message": str(exc)}
    source_vals = [str(v) for v in (source_rows[0] if source_rows else [])]
    target_vals = [str(v) for v in (target_rows[0] if target_rows else [])]
    same = source_vals == target_vals
    return {
        "table": table,
        "metric_sql": sql,
        "source": source_vals,
        "target": target_vals,
        "status": "ok" if same else "mismatch",
    }


def _metadata(source_type: str, src: dict, database: str, schema: str, table: str,
              target: dict, target_db: str) -> dict:
    from ..readers.doris import DorisReader
    from ..readers.mysql import MySQLReader
    from ..readers.postgresql import PostgreSQLReader

    try:
        if source_type == "postgresql":
            reader = PostgreSQLReader(
                host=src["host"], port=src.get("port", 5432), user=src.get("user", ""),
                password=src.get("password", ""), database=database, timeout=10,
            )
            with reader:
                source_cols = reader.list_columns(schema or "public", table)
        else:
            reader = MySQLReader(
                host=src["host"], port=src.get("port", 3306), user=src.get("user", ""),
                password=src.get("password", ""), database=database, timeout=10,
            )
            with reader:
                source_cols = reader.list_columns(database, table)
        dreader = DorisReader(
            host=target["host"], port=target.get("port", 9030), user=target.get("user", ""),
            password=target.get("password", ""), database=target_db, timeout=10,
        )
        with dreader:
            if table not in dreader.list_tables(target_db):
                return {"table": table, "status": "target_missing", "message": "Doris 表不存在"}
            target_cols = dreader.columns(target_db, table)
    except Exception as exc:
        return {"table": table, "status": "error", "message": str(exc)}

    from .schema_sync import diff_columns

    diff = diff_columns(source_cols, target_cols)
    differences = (
        [{"type": "add", "column": c["name"]} for c in diff["add"]]
        + [{"type": "drop", "column": c["name"]} for c in diff["drop"]]
        + [
            {"type": "modify", "column": item["mysql"]["name"],
             "source": item["mysql"]["column_type"], "target": item["doris"]["column_type"]}
            for item in diff["modify"]
        ]
    )
    return {
        "table": table,
        "status": "ok" if not differences else "mismatch",
        "differences": differences,
        "source_columns": len(source_cols),
        "target_columns": len(target_cols),
    }


HANDLERS = {
    "row_count": _row_count,
    "pk_snapshot": _pk_snapshot,
    "field_value": _field_value,
    "metric": _metric,
    "metadata": _metadata,
}


def run_task(task: ReconcileTask, persist: bool = True) -> ReconcileRun:
    run = ReconcileRun(task=task, status="running")
    if persist:
        run.save()
    start = time.time()
    details: list[dict] = []
    try:
        source_config = task.source_config
        raw_source_type = (source_config.db_type if source_config else "mysql")
        source_type = (
            "mysql"
            if raw_source_type in ("mysql", "oceanbase")
            else "postgresql"
            if raw_source_type in ("postgresql", "gaussdb", "dws")
            else raw_source_type
        )
        src = source_connection(source_config, task.source_db_name)
        if src is None:
            raise ValueError("任务未关联源配置(source_config)")
        from common.config import get_doris_config

        doris_cfg = get_doris_config({"doris_database": task.target_db_name})
        target = {
            "host": doris_cfg["host"],
            "port": doris_cfg["port"],
            "user": doris_cfg["user"],
            "password": doris_cfg["password"],
            "database": doris_cfg["database"] or task.target_db_name,
        }
        target_db = doris_cfg["database"] or task.target_db_name
        if source_type not in ("mysql", "postgresql"):
            raise ValueError(f"源类型暂不支持: {source_type}")
        handler = HANDLERS[task.task_type]

        for table in task.tables or []:
            kwargs = {
                "source_type": source_type,
                "src": src,
                "database": task.source_db_name,
                "schema": task.source_schema or "public",
                "table": table,
                "target": target,
                "target_db": target_db,
            }
            if task.task_type == "pk_snapshot":
                kwargs["pk_columns"] = task.pk_columns or []
            elif task.task_type == "field_value":
                kwargs["columns"] = task.columns or []
            elif task.task_type == "metric":
                kwargs["metric_sql"] = task.metric_sql
            details.append(handler(**kwargs))

        ok_count = sum(1 for d in details if d.get("status") == "ok")
        summary = {
            "task_type": task.task_type,
            "total": len(details),
            "ok": ok_count,
            "mismatch": len(details) - ok_count,
        }
        run.status = "success"
        run.summary = summary
        run.details = details
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)
    run.duration_ms = int((time.time() - start) * 1000)
    run.ran_at = timezone.now()
    if persist:
        run.save()
    return run
