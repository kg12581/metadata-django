#!/usr/bin/env python3
"""MySQL -> Doris 表数据同步脚本 (DataX)。

流程:
  1. 调用 Django 接口校验 MySQL 与 Doris 表结构是否一致
  2. 校验通过 (consistent=true) 才执行 DataX 同步
  3. 校验不通过则打印差异并退出(除非 --force)

用法示例:
  python tools/datax_sync.py --database ai_chatbot --table analytics_event --doris-database test_db

可选:
  --job-file 指定现成 job JSON(默认从 Django 接口获取并保存到 datax/jobs/)
  --no-run   只校验 + 生成 job, 不执行 DataX
  --force    跳过结构校验
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JOB_DIR = PROJECT_ROOT / "datax" / "jobs"


def api_post(api_url: str, path: str, payload: dict) -> tuple[int, dict]:
    url = api_url.rstrip("/") + path
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"code": exc.code, "message": body, "data": None}
    except urllib.error.URLError as exc:
        return 0, {"message": f"无法连接 Django 服务: {exc.reason}"}


def fetch_preview_job(
    api_url: str,
    database: str,
    table: str,
    doris_database: str | None,
    truncate: bool,
    channel: int,
    split_pk: str | None,
) -> dict:
    """通过 Django 接口 preview 模式获取 DataX job 配置。"""
    payload = {
        "database": database,
        "table": table,
        "doris_database": doris_database,
        "preview": True,
        "truncate": truncate,
        "channel": channel,
    }
    if split_pk:
        payload["split_pk"] = split_pk
    status, body = api_post(api_url, "/api/metadata/datax/sync/", payload)
    if status != 200:
        raise RuntimeError(f"获取 DataX job 失败({status}): {body.get('message')}")
    results = (body.get("data") or {}).get("results", [])
    if not results or "job" not in results[0]:
        raise RuntimeError("接口未返回 DataX job 配置: " + json.dumps(body, ensure_ascii=False))
    return results[0]["job"]


def print_differences(table_result: dict) -> None:
    for diff in table_result.get("differences", []):
        print("  -", json.dumps(diff, ensure_ascii=False))
    for warn in table_result.get("warnings", []):
        print("  !", json.dumps(warn, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="校验 MySQL/Doris 表结构一致后, 执行 DataX 同步表数据"
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("DJANGO_API_URL", "http://127.0.0.1:8000"),
        help="Django 服务地址(默认 http://127.0.0.1:8000)",
    )
    parser.add_argument("--database", required=True, help="MySQL 源库")
    parser.add_argument("--table", required=True, help="表名")
    parser.add_argument("--doris-database", default=None, help="Doris 目标库(默认取服务端 DORIS_DATABASE)")
    parser.add_argument("--force", action="store_true", help="跳过结构校验直接同步")
    parser.add_argument("--truncate", dest="truncate", action="store_true", default=True, help="同步前 TRUNCATE 目标表(默认开启)")
    parser.add_argument("--no-truncate", dest="truncate", action="store_false", help="不 TRUNCATE 目标表")
    parser.add_argument("--channel", type=int, default=3, help="DataX 并发通道数(默认 3)")
    parser.add_argument("--split-pk", default=None, help="分片主键(可选)")
    parser.add_argument("--job-file", default=None, help="指定现成 DataX job JSON(默认从 Django 接口获取)")
    parser.add_argument("--datax-home", default=os.environ.get("DATAX_HOME", ""), help="DataX 安装目录")
    parser.add_argument("--datax-python", default=os.environ.get("DATAX_PYTHON", "python3"), help="执行 datax.py 的解释器")
    parser.add_argument("--timeout", type=int, default=3600, help="DataX 执行超时秒数(默认 3600)")
    parser.add_argument("--no-run", action="store_true", help="只校验 + 生成 job JSON, 不执行 DataX")
    args = parser.parse_args()

    # 1) 调用 Django 接口校验表结构
    if not args.force:
        print(f"[1/3] 校验表结构: {args.database}.{args.table} -> Doris {args.doris_database or '(服务端默认库)'}")
        status, body = api_post(
            args.api_url,
            "/api/metadata/datax/check/",
            {
                "database": args.database,
                "table": args.table,
                "doris_database": args.doris_database,
            },
        )
        if status != 200:
            print("校验接口调用失败:", body.get("message", body), file=sys.stderr)
            return 1
        table_result = ((body.get("data") or {}).get("tables") or {}).get(args.table, {})
        if not table_result.get("consistent"):
            print("表结构不一致, 拒绝同步:", file=sys.stderr)
            print_differences(table_result)
            print("如需强制执行请加 --force", file=sys.stderr)
            return 1
        print("表结构一致 ✓")
    else:
        print("[1/3] 已跳过结构校验 (--force)")

    # 2) 准备 DataX job JSON
    if args.job_file:
        job_file = Path(args.job_file)
        if not job_file.exists():
            print(f"job 文件不存在: {job_file}", file=sys.stderr)
            return 1
        print(f"[2/3] 使用现有 job: {job_file}")
    else:
        print("[2/3] 从 Django 接口获取 DataX job 配置 ...")
        job = fetch_preview_job(
            args.api_url,
            args.database,
            args.table,
            args.doris_database,
            args.truncate,
            args.channel,
            args.split_pk,
        )
        DEFAULT_JOB_DIR.mkdir(parents=True, exist_ok=True)
        job_file = DEFAULT_JOB_DIR / f"{args.database}_{args.table}.json"
        job_file.write_text(
            json.dumps(job, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[2/3] job 已生成: {job_file}")

    if args.no_run:
        print("[3/3] --no-run, 未执行 DataX")
        return 0

    # 3) 执行 DataX
    if not args.datax_home:
        print("未配置 DATAX_HOME, 无法执行 DataX(可用 --no-run 只生成 job)", file=sys.stderr)
        return 1
    datax_py = Path(args.datax_home) / "bin" / "datax.py"
    if not datax_py.exists():
        print(f"找不到 DataX 执行脚本: {datax_py}", file=sys.stderr)
        return 1

    command = [args.datax_python, str(datax_py), str(job_file)]
    print(f"[3/3] 执行 DataX: {' '.join(command)}")
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        print(f"DataX 执行超时(>{args.timeout}s)", file=sys.stderr)
        return 1

    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    print("\n".join(output.strip().splitlines()[-50:]))
    if proc.returncode != 0:
        print(f"DataX 执行失败, exit code = {proc.returncode}", file=sys.stderr)
        return proc.returncode
    print("DataX 同步完成 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
