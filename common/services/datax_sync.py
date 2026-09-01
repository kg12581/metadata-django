"""DataX 同步服务: 生成 MySQL -> Doris 的 DataX job 并执行。"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile

from .schema_check import check_tables, fetch_mysql_columns


def build_job(
    mysql_config: dict,
    doris_config: dict,
    database: str,
    table: str,
    column_names: list[str],
    *,
    split_pk: str | None = None,
    channel: int = 3,
    truncate: bool = True,
) -> dict:
    """构造 MySQL -> Doris 的 DataX job 配置。"""
    doris_database = doris_config.get("database") or database

    jdbc_url = (
        f"jdbc:mysql://{mysql_config['host']}:{mysql_config['port']}/{database}"
        "?useUnicode=true&characterEncoding=utf8&useSSL=false&allowPublicKeyRetrieval=true"
    )
    reader = {
        "name": "mysqlreader",
        "parameter": {
            "username": mysql_config["user"],
            "password": mysql_config["password"],
            "column": column_names,
            "connection": [
                {
                    "jdbcUrl": [jdbc_url],
                    "table": [table],
                }
            ],
        },
    }
    if split_pk:
        reader["parameter"]["splitPk"] = split_pk

    writer_parameter = {
        "username": doris_config["user"],
        "password": doris_config["password"],
        "database": doris_database,
        "table": table,
        "column": column_names,
        "preSql": [f"TRUNCATE TABLE `{doris_database}`.`{table}`"] if truncate else [],
        "postSql": [],
        "connection": [
            {
                "jdbcUrl": f"jdbc:mysql://{doris_config['host']}:{doris_config['port']}/{doris_database}",
                "selectedDatabase": doris_database,
            }
        ],
    }

    return {
        "job": {
            "content": [
                {
                    "reader": reader,
                    "writer": {
                        "name": "doriswriter",
                        "parameter": writer_parameter,
                    },
                }
            ],
            "setting": {
                "speed": {"channel": channel},
            },
        }
    }


def run_datax(job: dict, datax_config: dict, timeout: int = 3600) -> tuple[bool, str]:
    """把 job 写到临时文件并调用 datax.py 执行, 返回 (是否成功, 日志尾部)。"""
    datax_home = datax_config.get("home", "")
    if not datax_home:
        raise RuntimeError("未配置 DATAX_HOME, 无法执行 DataX; 可用 preview=true 只生成 job 配置")
    datax_py = os.path.join(datax_home, "bin", "datax.py")
    if not os.path.exists(datax_py):
        raise RuntimeError(f"找不到 DataX 执行脚本: {datax_py}")

    fd, path = tempfile.mkstemp(suffix=".json", prefix="datax_job_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(job, fp, ensure_ascii=False, indent=2)
        command = [datax_config.get("python", "python3"), datax_py, path]
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        tail = "\n".join(output.strip().splitlines()[-50:])
        return proc.returncode == 0, tail
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def sync_table_data(
    mysql_config: dict,
    doris_config: dict,
    datax_config: dict,
    database: str,
    table: str,
    *,
    doris_database: str | None = None,
    truncate: bool = True,
    channel: int = 3,
    force: bool = False,
    split_pk: str | None = None,
    preview: bool = False,
) -> dict:
    """先校验表结构一致, 再生成并执行 DataX 同步。"""
    check = check_tables(
        mysql_config,
        doris_config,
        database,
        [table],
        doris_database=doris_database,
    )
    table_check = check["tables"][table]

    result = {
        "table": table,
        "checked": True,
        "consistent": table_check["consistent"],
        "differences": table_check["differences"],
        "warnings": table_check["warnings"],
        "executed": False,
        "success": None,
        "log_tail": "",
    }

    columns = fetch_mysql_columns(mysql_config, database, table)
    job = build_job(
        mysql_config,
        doris_config,
        database,
        table,
        [col["name"] for col in columns],
        split_pk=split_pk,
        channel=channel,
        truncate=truncate,
    )

    if preview:
        result["job"] = job
        result["reason"] = "preview 模式, 未执行 DataX"
        return result

    if not table_check["consistent"] and not force:
        result["reason"] = "表结构不一致, 未执行 DataX 同步(如需强制执行请传 force=true)"
        return result

    ok, log_tail = run_datax(job, datax_config)
    result["executed"] = True
    result["success"] = ok
    result["log_tail"] = log_tail
    if not ok:
        result["reason"] = "DataX 执行失败, 详见 log_tail"
    return result
