"""Flink SQL 作业自动管理: 监控表结构变更 -> savepoint 停止 -> 重新生成 SQL -> 重启。"""
from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from ..readers.mysql import MySQLReader
from ..readers.postgresql import PostgreSQLReader

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FLINK_SQL_DIR = PROJECT_ROOT / "flink_sql"
JOBS_PATH = FLINK_SQL_DIR / "jobs.json"
STATE_PATH = FLINK_SQL_DIR / "jobs_state.json"
GENERATED_DIR = FLINK_SQL_DIR / "generated"


# ---------------------------------------------------------------- 配置

def load_jobs_config() -> dict:
    if not JOBS_PATH.exists():
        raise FileNotFoundError(f"缺少 Flink 作业配置: {JOBS_PATH}")
    return json.loads(JOBS_PATH.read_text(encoding="utf-8"))


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- 源元数据

def fetch_source_columns(job: dict) -> list[dict]:
    source = job["source_db"]
    db_type = source.get("db_type", "mysql")
    if db_type == "postgresql":
        reader = PostgreSQLReader(
            host=source["host"],
            port=source.get("port", 5432),
            user=source.get("user", ""),
            password=source.get("password", ""),
            database=source["database"],
            timeout=10,
        )
        try:
            with reader:
                return reader.list_columns(source.get("schema", "public"), job["source_table"])
        finally:
            reader.close()
    reader = MySQLReader(
        host=source["host"],
        port=source.get("port", 3306),
        user=source.get("user", ""),
        password=source.get("password", ""),
        database=source["database"],
        timeout=10,
    )
    try:
        with reader:
            return reader.list_columns(source["database"], job["source_table"])
    finally:
        reader.close()


# ---------------------------------------------------------------- 类型映射

def flink_type_mapping(column: dict, source_type: str) -> dict:
    """返回 {source_type, sink_type, transform}。
    transform 为 None 表示直接透传; 否则 (表达式, alias)。
    """
    t = (column.get("data_type") or "").lower()
    ct = (column.get("column_type") or "").lower()
    precision = column.get("numeric_precision")
    scale = column.get("numeric_scale")
    name = column.get("name", "")

    if source_type == "postgresql_debezium":
        if t in ("smallint", "int2"):
            return {"source": "SMALLINT", "sink": "SMALLINT", "transform": None}
        if t in ("integer", "int4"):
            return {"source": "INT", "sink": "INT", "transform": None}
        if t in ("bigint", "int8"):
            return {"source": "BIGINT", "sink": "BIGINT", "transform": None}
        if t in ("numeric", "decimal"):
            p = precision or 10
            s = scale or 2
            return {"source": "STRING", "sink": f"DECIMAL({p}, {s})", "transform": None}
        if t in ("boolean", "bool"):
            return {"source": "BOOLEAN", "sink": "BOOLEAN", "transform": None}
        if t == "date":
            return {"source": "DATE", "sink": "DATE", "transform": None}
        if "timestamp" in t:
            return {
                "source": "TIMESTAMP_LTZ(6)",
                "sink": "STRING",
                "transform": ("DATE_FORMAT(%s, 'yyyy-MM-dd HH:mm:ss.SSSSSS') AS %s", name),
            }
        return {"source": "STRING", "sink": "STRING", "transform": None}

    # mysql_canal
    if t == "tinyint" and ct.startswith("tinyint(1)"):
        return {"source": "BOOLEAN", "sink": "BOOLEAN", "transform": None}
    if t == "tinyint":
        return {"source": "TINYINT", "sink": "TINYINT", "transform": None}
    if t == "smallint":
        return {"source": "SMALLINT", "sink": "SMALLINT", "transform": None}
    if t in ("mediumint", "int", "integer"):
        return {"source": "INT", "sink": "INT", "transform": None}
    if t == "bigint":
        return {"source": "BIGINT", "sink": "BIGINT", "transform": None}
    if t == "float":
        return {"source": "FLOAT", "sink": "FLOAT", "transform": None}
    if t == "double":
        return {"source": "DOUBLE", "sink": "DOUBLE", "transform": None}
    if t in ("decimal", "numeric"):
        p = precision or 10
        s = scale or 0
        return {"source": f"DECIMAL({p}, {s})", "sink": f"DECIMAL({p}, {s})", "transform": None}
    if t == "date":
        return {"source": "DATE", "sink": "DATE", "transform": None}
    return {"source": "STRING", "sink": "STRING", "transform": None}


def columns_signature(columns: list[dict], source_type: str) -> list[dict]:
    result = []
    for column in columns:
        mapping = flink_type_mapping(column, source_type)
        result.append({"name": column["name"], "flink_type": mapping["source"]})
    return result


def signature_hash(signatures: list[dict]) -> str:
    raw = json.dumps(signatures, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- SQL 生成

def generate_runtime_sql(job: dict, columns: list[dict],
                         savepoint_path: str | None = None) -> str:
    source_type = job["source_type"]
    source_table = "pg_kafka_source" if source_type == "postgresql_debezium" else "mysql_kafka_source"
    sink_table = "doris_target"
    primary_keys = job.get("primary_keys") or []
    pk_sql = ", ".join(f"`{k}`" for k in primary_keys)
    mapping = {c["name"]: flink_type_mapping(c, source_type) for c in columns}

    lines = [
        f"-- Generated by metadata-django flink_sync at {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"-- Job: {job['name']} | {job['kafka_topic']} -> {job['doris_database']}.{job['doris_table']}",
        "",
        "SET 'execution.runtime-mode' = 'STREAMING';",
        f"SET 'pipeline.name' = '{job.get('pipeline_name') or job['name']}';",
        "SET 'parallelism.default' = '1';",
        "SET 'table.local-time-zone' = 'Asia/Shanghai';",
        "SET 'execution.checkpointing.interval' = '10000';",
        "SET 'execution.checkpointing.mode' = 'EXACTLY_ONCE';",
        "SET 'execution.checkpointing.externalized-checkpoint-retention' = 'RETAIN_ON_CANCELLATION';",
        "SET 'state.backend' = 'rocksdb';",
        f"SET 'state.checkpoints.dir' = '{job.get('checkpoint_dir', 'file:///data/flink/checkpoint')}/{job['name']}';",
        "SET 'table.exec.source.idle-timeout' = '60s';",
        "",
    ]
    if savepoint_path:
        lines.insert(-1, f"SET 'execution.savepoint.path' = '{savepoint_path}';")

    lines.append(f"CREATE TABLE {source_table} (")
    for column in columns:
        lines.append(f"    `{column['name']}` {mapping[column['name']]['source']},")
    if pk_sql:
        lines.append(f"    PRIMARY KEY ({pk_sql}) NOT ENFORCED")
    lines.append(") WITH (")
    lines.append("    'connector' = 'kafka',")
    lines.append(f"    'topic' = '{job['kafka_topic']}',")
    lines.append(f"    'properties.bootstrap.servers' = '{job['kafka_bootstrap_servers']}',")
    lines.append(f"    'properties.group.id' = '{job.get('pipeline_name') or job['name']}_flink',")
    lines.append("    'scan.startup.mode' = 'latest-offset',")
    if source_type == "postgresql_debezium":
        lines.append("    'format' = 'debezium-json',")
        lines.append("    'debezium-json.timestamp-format.standard' = 'ISO-8601'")
    else:
        lines.append("    'format' = 'canal-json'")
    lines.append(");")
    lines.append("")

    lines.append(f"CREATE TABLE {sink_table} (")
    for column in columns:
        lines.append(f"    `{column['name']}` {mapping[column['name']]['sink']},")
    if pk_sql:
        lines.append(f"    PRIMARY KEY ({pk_sql}) NOT ENFORCED")
    lines.append(") WITH (")
    lines.append("    'connector' = 'doris',")
    lines.append(f"    'fenodes' = '{job['doris_host']}:{job.get('doris_fe_http_port', 8030)}',")
    lines.append(f"    'table.identifier' = '{job['doris_database']}.{job['doris_table']}',")
    lines.append(f"    'username' = '{job.get('doris_user', 'root')}',")
    lines.append(f"    'password' = '{job.get('doris_password', '')}',")
    lines.append(f"    'sink.label-prefix' = '{job['name']}_',")
    lines.append("    'sink.enable.batch-mode' = 'false',")
    lines.append("    'sink.max-retries' = '3',")
    lines.append("    'sink.properties.format' = 'json',")
    lines.append("    'sink.properties.read_json_by_line' = 'true'")
    lines.append(");")
    lines.append("")

    select_parts = []
    for column in columns:
        m = mapping[column["name"]]
        if m["transform"]:
            expression, alias = m["transform"]
            col_ref = "`" + column["name"] + "`"
            select_parts.append("    " + (expression % col_ref) + f" AS `{alias}`")
        else:
            select_parts.append(f"    `{column['name']}`")
    lines.append(f"INSERT INTO {sink_table}")
    lines.append("SELECT")
    lines.append(",\n".join(select_parts))
    lines.append(f"FROM {source_table};")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 状态与监控

def save_generated_sql(job: dict, sql: str, signatures: list[dict]) -> Path:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    generated_file = GENERATED_DIR / job["generated_file"]
    generated_file.write_text(sql, encoding="utf-8")
    state = load_state()
    state[job["name"]] = {
        "columns_hash": signature_hash(signatures),
        "columns": signatures,
        "sql_file": str(generated_file),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    save_state(state)
    return generated_file


def monitor_job(job: dict, flink_cfg: dict) -> dict:
    """获取源元数据并与上次生成的结构对比, 返回差异。"""
    columns = fetch_source_columns(job)
    signatures = columns_signature(columns, job["source_type"])
    current_hash = signature_hash(signatures)
    state = load_state()
    previous = state.get(job["name"]) or {}
    declared = previous.get("columns", [])
    declared_map = {c["name"]: c["flink_type"] for c in declared}
    current_map = {c["name"]: c["flink_type"] for c in signatures}

    diff = {
        "add": [name for name in current_map if name not in declared_map],
        "drop": [name for name in declared_map if name not in current_map],
        "modify": [
            {"column": name, "old": declared_map[name], "new": current_map[name]}
            for name in current_map
            if name in declared_map and declared_map[name] != current_map[name]
        ],
    }
    return {
        "job": job["name"],
        "source": f"{job['source_db'].get('database')}.{job['source_table']}",
        "columns_count": len(signatures),
        "changed": bool(previous) and previous.get("columns_hash") != current_hash,
        "first_time": not bool(previous),
        "diff": diff,
        "has_difference": bool(diff["add"] or diff["drop"] or diff["modify"]),
        "running": job_running_state(job["name"], flink_cfg),
        "declared_columns": declared,
        "current_columns": signatures,
    }


def job_running_state(job_name: str, flink_cfg: dict) -> dict:
    try:
        status, body = _rest_get(flink_cfg["flink_rest"], "/jobs/overview")
        if status != 200:
            return {"ok": False, "state": "REST_ERROR", "message": f"HTTP {status}"}
        for job in body.get("jobs", []):
            if job.get("name") == job_name:
                return {"ok": True, "state": job.get("state"), "jobid": job.get("jid")}
        return {"ok": True, "state": "NOT_RUNNING", "jobid": None}
    except Exception as exc:
        return {"ok": False, "state": "ERROR", "message": str(exc)}


def check_job_structure(job: dict, flink_cfg: dict | None = None) -> dict:
    """启动 Flink SQL 前比对 源表 vs Doris 目标表结构。"""
    from .schema_check import compare_source_doris

    source = job["source_db"]
    source_type = source.get("db_type", "mysql")
    result = compare_source_doris(
        source_type,
        source,
        source.get("database", ""),
        job["source_table"],
        doris_config={
            "host": job["doris_host"],
            "port": job.get("doris_fe_http_port", 9030),
            "user": job.get("doris_user", "root"),
            "password": job.get("doris_password", ""),
            "database": job["doris_database"],
        },
        doris_database=job["doris_database"],
        schema=source.get("schema"),
    )
    return {"job": job["name"], "consistent": result["consistent"],
            "differences": result["differences"], "warnings": result["warnings"]}


# ---------------------------------------------------------------- Flink 执行

def _rest_get(base: str, path: str) -> tuple[int, dict]:
    request = urllib.request.Request(base.rstrip("/") + path, method="GET")
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _rest_post(base: str, path: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        base.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, {"message": exc.read().decode("utf-8", errors="replace")}


def stop_with_savepoint(job_name: str, flink_cfg: dict, savepoint_dir: str) -> dict:
    """通过 Flink REST 触发 savepoint 并取消作业。"""
    running = job_running_state(job_name, flink_cfg)
    if not running.get("ok"):
        return {"ok": False, "message": running.get("message", "查询作业状态失败")}
    if running.get("state") == "NOT_RUNNING":
        return {"ok": True, "state": "NOT_RUNNING", "message": "作业未运行, 无需停止"}
    jobid = running["jobid"]
    status, body = _rest_post(
        flink_cfg["flink_rest"],
        f"/jobs/{jobid}/savepoints",
        {"target-directory": savepoint_dir, "cancel-job": True},
    )
    if status != 202:
        return {"ok": False, "message": f"触发 savepoint 失败: HTTP {status} {body}"}
    request_id = body.get("request-id")
    result = {
        "ok": True,
        "jobid": jobid,
        "request_id": request_id,
        "savepoint_dir": savepoint_dir,
    }
    # 轮询 savepoint 状态(作业取消后可能 404, 视为已完成)
    for _ in range(20):
        time.sleep(2)
        try:
            status, sb = _rest_get(
                flink_cfg["flink_rest"],
                f"/jobs/{jobid}/savepoints/{request_id}",
            )
            if status == 200:
                state = (sb.get("status") or {}).get("id")
                if state == "COMPLETED":
                    result["savepoint_state"] = "COMPLETED"
                    result["location"] = sb.get("location")
                    return result
                if state == "FAILED":
                    result["ok"] = False
                    result["savepoint_state"] = "FAILED"
                    result["message"] = str(sb)
                    return result
        except Exception:
            # 作业已取消 -> savepoint 查询 404
            result["savepoint_state"] = "COMPLETED_AFTER_CANCEL"
            return result
    result["savepoint_state"] = "TIMEOUT"
    return result


def latest_savepoint_location(job_name: str, flink_cfg: dict, savepoint_dir: str) -> str | None:
    """尝试通过 Flink REST 查询作业最近一次 savepoint 位置。"""
    running = job_running_state(job_name, flink_cfg)
    jobid = running.get("jobid") if running.get("ok") else None
    if not jobid:
        return None
    try:
        status, body = _rest_get(flink_cfg["flink_rest"], f"/jobs/{jobid}/checkpoints")
        if status != 200:
            return None
        latest = (body.get("latest") or {}).get("savepoint")
        if latest:
            return latest.get("location")
    except Exception:
        pass
    return None


def submit_sql(job: dict, sql_file: Path, flink_cfg: dict) -> dict:
    """通过 flink_cli_prefix(本地 flink 或 ssh 前缀) 提交生成好的 SQL。"""
    prefix = flink_cfg.get("flink_cli_prefix", "").strip()
    cli_bin = flink_cfg.get("flink_cli_bin", "/opt/flink/bin")
    if not prefix:
        return {
            "submitted": False,
            "message": "未配置 flink_cli_prefix, 无法自动提交; SQL 已生成, 请手动执行 "
                       f"./flink_sql/submit_flink_sql.sh {job['generated_file']}",
        }
    command = shlex.split(prefix) + [f"{cli_bin}/sql-client.sh", "-f", str(sql_file)]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=300)
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        return {
            "submitted": proc.returncode == 0,
            "exit_code": proc.returncode,
            "log_tail": "\n".join(output.strip().splitlines()[-30:]),
        }
    except Exception as exc:
        return {"submitted": False, "message": f"提交命令执行失败: {exc}"}


# ---------------------------------------------------------------- 主流程

def check_all_jobs() -> dict:
    flink_cfg = load_jobs_config()
    results = []
    for job in flink_cfg["jobs"]:
        try:
            results.append(monitor_job(job, flink_cfg))
        except Exception as exc:
            results.append({"job": job["name"], "error": str(exc)})
    return {"flink_rest": flink_cfg["flink_rest"], "jobs": results}


def generate_job(job_name: str | None = None) -> dict:
    """只重新生成 SQL 并更新状态(不停作业/不提交)。"""
    flink_cfg = load_jobs_config()
    results = []
    for job in flink_cfg["jobs"]:
        if job_name and job["name"] != job_name:
            continue
        try:
            columns = fetch_source_columns(job)
            signatures = columns_signature(columns, job["source_type"])
            sql = generate_runtime_sql(job, columns)
            path = save_generated_sql(job, sql, signatures)
            results.append(
                {
                    "job": job["name"],
                    "columns": len(columns),
                    "sql_file": str(path),
                    "sql_head": "\n".join(sql.splitlines()[:8]),
                }
            )
        except Exception as exc:
            results.append({"job": job["name"], "error": str(exc)})
    return {"results": results}


def apply_job(job_name: str, *, doris_sync: bool = True,
              check_structure: bool = True, force_structure: bool = False,
              resume: bool = True) -> dict:
    """完整流程: (可选)Doris 结构同步 -> savepoint 停止 -> 生成 SQL -> 提交。"""
    flink_cfg = load_jobs_config()
    job = next((j for j in flink_cfg["jobs"] if j["name"] == job_name), None)
    if job is None:
        raise ValueError(f"未找到作业: {job_name}")

    result = {"job": job["name"], "steps": []}

    # 0) 同步前结构比对闸门(实时全量/增量作业统一先比对)
    if check_structure:
        structure = check_job_structure(job, flink_cfg)
        result["steps"].append({"step": "structure_check", **structure})
        if not structure["consistent"] and not force_structure:
            result["steps"].append({
                "step": "blocked",
                "message": "源表与 Doris 目标表结构不一致, 未停止/重启作业; "
                           "可先执行 schema_sync 对齐, 或传 force_structure=true 强制",
            })
            return result

    # 1) Doris 结构同步(仅 MySQL 源支持自动; PG 提示人工)
    if doris_sync:
        if job["source_db"].get("db_type") == "mysql":
            from .schema_sync import sync_table_schema
            mysql_config = {
                "db_type": "mysql",
                "host": job["source_db"]["host"],
                "port": job["source_db"].get("port", 3306),
                "user": job["source_db"].get("user", ""),
                "password": job["source_db"].get("password", ""),
                "database": job["source_db"]["database"],
            }
            doris_config = {
                "host": job["doris_host"],
                "port": job.get("doris_fe_http_port", 8030),
                "user": job.get("doris_user", "root"),
                "password": job.get("doris_password", ""),
                "database": job["doris_database"],
            }
            plan = sync_table_schema(
                mysql_config,
                doris_config,
                job["source_db"]["database"],
                job["source_table"],
                doris_database=job["doris_database"],
                preview=False,
            )
            result["steps"].append({"step": "doris_schema_sync", **plan})
        else:
            result["steps"].append(
                {"step": "doris_schema_sync", "skipped": True,
                 "message": "PG 源结构同步暂不支持自动执行, 请确认 Doris 表结构已更新"}
            )

    # 2) savepoint 停止
    stop = stop_with_savepoint(job["name"], flink_cfg, flink_cfg.get("savepoint_dir", "file:///data/flink/savepoint"))
    result["steps"].append({"step": "stop_with_savepoint", **stop})
    if not stop.get("ok"):
        return result

    # 3) 生成 SQL
    columns = fetch_source_columns(job)
    signatures = columns_signature(columns, job["source_type"])
    savepoint_path = stop.get("location") or (
        latest_savepoint_location(job["name"], flink_cfg,
                                  flink_cfg.get("savepoint_dir", "file:///data/flink/savepoint"))
        if resume else None
    )
    sql = generate_runtime_sql(
        job, columns, savepoint_path=savepoint_path if resume else None
    )
    path = save_generated_sql(job, sql, signatures)
    result["steps"].append({
        "step": "generate_sql",
        "sql_file": str(path),
        "columns": len(columns),
        "resume_from_savepoint": savepoint_path,
    })

    # 4) 提交
    submit = submit_sql(job, path, flink_cfg)
    result["steps"].append({"step": "submit", **submit})
    return result
