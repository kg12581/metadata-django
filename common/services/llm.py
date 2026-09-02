"""大模型分析: 调用 OpenAI 兼容的 chat/completions 接口。"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from ..config import load_dotenv


class LLMNotConfigured(Exception):
    pass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def chat(prompt: str, system: str | None = None, max_tokens: int = 1500) -> str:
    load_dotenv()  # 每次调用前刷新 .env(支持运行中修改 key 后直接生效)
    api_key = _env("LLM_API_KEY") or _env("DEEPSEEK_API_KEY")
    if not api_key:
        raise LLMNotConfigured(
            "未配置 LLM_API_KEY / DEEPSEEK_API_KEY; 默认对接 DeepSeek, "
            "可在 .env 设置 LLM_BASE_URL / LLM_MODEL 指向任意 OpenAI 兼容服务"
        )
    base_url = _env("LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
    model = _env("LLM_MODEL", "deepseek-chat")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {"model": model, "messages": messages, "temperature": 0.2, "max_tokens": max_tokens}
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"LLM 调用失败 HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')[:300]}") from exc
    return (body.get("choices") or [{}])[0].get("message", {}).get("content", "")


def analyze_sql(sql_text: str, metadata: str = "") -> str:
    system = (
        "你是一名资深大数据工程师, 擅长 SQL 优化、可读性与数仓建模。"
        "请用中文简洁回答, 输出: 1) SQL 做什么; 2) 潜在问题; 3) 优化建议。"
    )
    prompt = f"SQL:\n```sql\n{sql_text}\n```\n\n相关元数据(字段/注释):\n{metadata or '无'}"
    return chat(prompt, system=system)


def analyze_metadata(metadata_text: str) -> str:
    system = (
        "你是一名数据治理专家, 请基于表/字段元数据评估: 命名规范、类型合理性、"
        "主键/索引建议、数据字典注释缺失点。用中文简洁列出。"
    )
    return chat(f"元数据:\n{metadata_text}", system=system)


def sql_assist(request_text: str, mode: str, metadata: str = "") -> str:
    """AI 辅助写 SQL: generate / optimize / explain 三种模式。"""
    mode = mode or "generate"
    system = (
        "你是一名资深大数据工程师与 SQL 专家, 熟悉 MySQL/PostgreSQL/Doris/Hive 语法差异。"
        "请直接给出可直接执行的 SQL, 放在 ```sql 代码块中, 并附 2-3 句中文要点说明。"
        "若字段信息不足, 基于常见表结构给出合理假设并在说明中注明。"
    )
    if mode == "optimize":
        prompt = (
            f"请优化以下 SQL, 指出问题并给出优化后的 SQL:\n```sql\n{request_text}\n```"
        )
    elif mode == "explain":
        prompt = f"请用中文解释以下 SQL 的用途、逻辑和执行顺序:\n```sql\n{request_text}\n```"
    else:
        prompt = (
            f"根据需求生成 SQL: {request_text}\n\n"
            f"可参考的表结构元数据:\n{metadata or '(未提供, 请自行假设合理表结构)'}"
        )
    return chat(prompt, system=system, max_tokens=2000)


def spark_to_hive_sql(code: str, language: str, metadata: str = "") -> str:
    """AI 把 Java/Scala/Python 写的 Spark 代码转换为 Hive SQL。

    不写死解析规则: 完整代码交由 LLM 理解并生成等价 Hive SQL。
    """
    language = (language or "python").lower()
    if language not in ("java", "scala", "python"):
        language = "python"
    system = (
        "你是一名精通 Spark 与 Hive 的大数据工程师。用户会粘贴一段 Spark 代码"
        "(Java/Scala/Python 的 DataFrame/RDD API 或 Spark SQL 均可)。"
        "请把它转换为等价的 Hive SQL: "
        "1) 先用 1-2 句中文说明这段代码在做什么; "
        "2) 再给出可直接在 Hive 执行的 SQL(放 ```sql 代码块中); "
        "3) 若代码含 Spark 特有能力(Hive 不支持), 用 SQL/子查询/临时表等价实现并注明; "
        "4) 不要硬编码猜测表结构, 依据代码中的表/字段名生成。"
    )
    prompt = (
        f"语言: {language}\n\nSpark 代码:\n```{language}\n{code}\n```\n\n"
        f"可参考的表结构元数据:\n{metadata or '(未提供)'}"
    )
    return chat(prompt, system=system, max_tokens=2500)
