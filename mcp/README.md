# metadata-django MCP Server

把平台 REST API 封装成 [MCP(Model Context Protocol)](https://modelcontextprotocol.io/)
tools, 让 Codex / Claude Desktop 等 AI 客户端可以直接调用元数据查询、结构校验、
自动 DDL、DataX、对账、SQL 血缘等能力。

## 前置

1. Django 服务在运行: `python manage.py runserver` (默认 http://127.0.0.1:8000)
2. 安装依赖: `pip install "mcp>=2"` (v2 API, FastMCP 已更名 MCPServer)

## 启动(stdio)

```bash
MCP_DJANGO_URL=http://127.0.0.1:8000 python mcp/server.py
```

## 接入 Codex

在 `~/.codex/config.toml` 增加:

```toml
[mcp_servers.metadata-django]
command = "python3"
args = ["/Users/kgt/code/metadata-django/mcp/server.py"]
env = { MCP_DJANGO_URL = "http://127.0.0.1:8000" }
```

重启 Codex 后即可用自然语言调用, 例如:
"列出已同步的数据源, 并校验 ai_chatbot.analytics_event 与 Doris 结构是否一致"

## 接入 Claude Desktop

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "metadata-django": {
      "command": "python3",
      "args": ["/Users/kgt/code/metadata-django/mcp/server.py"],
      "env": { "MCP_DJANGO_URL": "http://127.0.0.1:8000" }
    }
  }
}
```

## 可用 Tools

| Tool | 说明 |
| --- | --- |
| `metadata_sync` | 同步远端元数据入库 |
| `list_databases` / `table_detail` | 查询元数据 |
| `schema_check` | MySQL vs Doris 结构校验 |
| `datax_sync` | DataX 同步(preview 可选) |
| `schema_sync` | 自动 DDL 对齐 Doris |
| `sources_list` / `source_test` | 数据源配置 |
| `sql_helper` | 按表生成常用 SQL |
| `reconcile_tasks` / `reconcile_run` | 对账中心 |
| `sql_files_list` / `sql_files_read` | SQL 文件库 |
| `lineage_parse` | SQL 血缘解析 |
| `llm_analyze_sql` | 大模型分析 SQL |
| `ops_summary` | 运营看板统计 |
| `docs_read` | 在线文档 |

## 说明

- 所有工具最终调用平台 REST API, 鉴权/限流与平台一致
- 写操作(同步/DDL/DataX/对账执行)请先 preview/确认, 平台本身默认预览优先
