#!/usr/bin/env python3
"""metadata-django MCP Server: 把平台 REST API 暴露为 MCP tools。

运行前提: Django 服务已启动 (http://127.0.0.1:8000)。
用法: MCP_DJANGO_URL=http://127.0.0.1:8000 python mcp/server.py
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from mcp.server.mcpserver import MCPServer

BASE_URL = os.environ.get("MCP_DJANGO_URL", "http://127.0.0.1:8000").rstrip("/")

mcp = MCPServer("metadata-django")


def _api(path: str, payload: dict | None = None) -> dict:
    url = BASE_URL + path
    request = urllib.request.Request(url, method="POST" if payload is not None else "GET")
    if payload is not None:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"code": exc.code, "message": exc.read().decode("utf-8", errors="replace")[:500], "data": None}
    except Exception as exc:
        return {"code": 500, "message": f"Django 服务不可用: {exc}", "data": None}


def _dump(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool()
def metadata_sync(database: str = "", db_type: str = "mysql", schema: str = "") -> str:
    """同步远端数据库元数据到平台(库/表/字段/索引/约束)。database 为源库名。"""
    payload = {"db_type": db_type}
    if database:
        payload["database"] = database
    if schema:
        payload["schema"] = schema
    return _dump(_api("/api/metadata/sync/", payload))


@mcp.tool()
def list_databases() -> str:
    """列出已同步元数据的数据源及其表数量/状态。"""
    return _dump(_api("/api/metadata/databases/"))


@mcp.tool()
def table_detail(table_id: int) -> str:
    """查看某张表的字段/索引/约束详情。table_id 见 list_databases 返回。"""
    return _dump(_api(f"/api/metadata/tables/{table_id}/"))


@mcp.tool()
def schema_check(database: str, table: str, doris_database: str = "") -> str:
    """校验 MySQL 与 Doris 表结构是否一致, 返回 consistent=true/false 与差异。"""
    return _dump(_api("/api/metadata/datax/check/", {"database": database, "table": table, "doris_database": doris_database or None}))


@mcp.tool()
def datax_sync(database: str, table: str, doris_database: str = "", preview: bool = False) -> str:
    """先校验结构一致再执行 DataX 同步; preview=true 只生成 job 配置。"""
    return _dump(_api("/api/metadata/datax/sync/", {"database": database, "table": table, "doris_database": doris_database or None, "preview": preview}))


@mcp.tool()
def schema_sync(database: str, table: str, doris_database: str = "", preview: bool = True) -> str:
    """按 MySQL 元数据自动对齐 Doris 表结构(新增/删除/修改字段, 不存在自动建表)。默认预览。"""
    return _dump(_api("/api/metadata/schema-sync/", {"database": database, "table": table, "doris_database": doris_database or None, "preview": preview}))


@mcp.tool()
def sources_list() -> str:
    """列出已配置的元数据源(MySQL/PG/Oracle/Hive/Doris 等 JDBC 配置)。"""
    return _dump(_api("/api/metadata/sources/"))


@mcp.tool()
def source_test(source_id: int) -> str:
    """测试某个数据源配置的连通性。"""
    return _dump(_api(f"/api/metadata/sources/{source_id}/test/"))


@mcp.tool()
def sql_helper(table_id: int) -> str:
    """基于元数据返回该表字段与生成的 SELECT/INSERT/UPDATE/DELETE/COUNT SQL。"""
    return _dump(_api(f"/api/metadata/sql-helper/table/{table_id}/"))


@mcp.tool()
def reconcile_tasks() -> str:
    """列出对账任务(行数/主键快照/字段值/指标/元数据)。"""
    return _dump(_api("/api/metadata/reconcile/tasks/"))


@mcp.tool()
def reconcile_run(task_id: int) -> str:
    """执行指定对账任务并返回结果。task_id 来自 reconcile_tasks。"""
    return _dump(_api(f"/api/metadata/reconcile/tasks/{task_id}/run/"))


@mcp.tool()
def sql_files_list(path: str = "") -> str:
    """浏览 SQL 文件库目录(本地或远程 Linux SFTP), path 为相对目录。"""
    return _dump(_api(f"/api/metadata/sql-files/files/?path={urllib.request.quote(path)}"))


@mcp.tool()
def sql_files_read(path: str) -> str:
    """读取 SQL 文件内容。"""
    return _dump(_api(f"/api/metadata/sql-files/file/?path={urllib.request.quote(path)}"))


@mcp.tool()
def lineage_parse(sql: str, save: bool = False) -> str:
    """解析 SQL(INSERT...SELECT/CTAS) 中的表血缘, save=true 保存到平台。"""
    return _dump(_api("/api/metadata/lineage/parse/", {"sql": sql, "save": save}))


@mcp.tool()
def llm_analyze_sql(sql: str) -> str:
    """调用大模型分析 SQL(需平台配置 LLM_API_KEY)。"""
    return _dump(_api("/api/metadata/llm/analyze/", {"kind": "sql", "sql": sql}))


@mcp.tool()
def ops_summary(days: int = 7) -> str:
    """运营看板统计: 请求量/成功率/热点接口/错误(近 N 天)。"""
    return _dump(_api(f"/api/metadata/ops/summary/?days={days}"))


@mcp.tool()
def docs_read(name: str) -> str:
    """读取平台在线文档(如 01-architecture.md / 04-api-reference.md)。"""
    return _dump(_api(f"/api/metadata/docs/file/?name={urllib.request.quote(name)}"))


if __name__ == "__main__":
    mcp.run()
