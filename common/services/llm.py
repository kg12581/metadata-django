"""大模型分析: 调用 OpenAI 兼容的 chat/completions 接口。"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class LLMNotConfigured(Exception):
    pass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def chat(prompt: str, system: str | None = None, max_tokens: int = 1500) -> str:
    api_key = _env("LLM_API_KEY")
    if not api_key:
        raise LLMNotConfigured(
            "未配置 LLM_API_KEY; 可设置 LLM_BASE_URL / LLM_MODEL 指向任意 OpenAI 兼容服务"
        )
    base_url = _env("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = _env("LLM_MODEL", "gpt-4o-mini")
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
