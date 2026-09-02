"""Web 文档: 读取 docs/*.md 并渲染 HTML。"""
from __future__ import annotations

import markdown
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"


def list_docs() -> list[dict]:
    if not DOCS_DIR.exists():
        return []
    return [
        {
            "name": path.name,
            "title": path.name,
            "size": path.stat().st_size,
        }
        for path in sorted(DOCS_DIR.glob("*.md"))
    ]


def get_doc(name: str) -> dict:
    if "/" in name or "\\" in name or not name.endswith(".md"):
        raise ValueError("文档名不合法")
    path = DOCS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"文档不存在: {name}")
    raw = path.read_text(encoding="utf-8")
    html = markdown.markdown(
        raw,
        extensions=["tables", "fenced_code", "codehilite", "toc"],
    )
    return {"name": name, "raw": raw, "html": html}
