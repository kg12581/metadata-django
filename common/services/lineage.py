"""从 SQL 中提取血缘: INSERT INTO ... SELECT FROM / CREATE TABLE AS SELECT。"""
from __future__ import annotations

import re

import sqlparse

from ..models import LineageEdge

_IDENT = r"(?:`[^`]+`|\"[^\"]+\"|[A-Za-z_][A-Za-z0-9_$]*)"
_INSERT_RE = re.compile(
    rf"INSERT\s+(?:IGNORE\s+)?INTO\s+(?P<target>{_IDENT}(?:\.{_IDENT})*)",
    re.IGNORECASE,
)
_CREATE_RE = re.compile(
    rf"CREATE\s+(?:EXTERNAL\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<target>{_IDENT}(?:\.{_IDENT})*)\s+AS\s+SELECT",
    re.IGNORECASE,
)
_FROM_RE = re.compile(r"\bFROM\s+", re.IGNORECASE)
_SOURCE_RE = re.compile(
    rf"(?:FROM|JOIN)\s+(?P<table>{_IDENT}(?:\.{_IDENT})*)",
    re.IGNORECASE,
)
_STOP_RE = re.compile(r"\b(?:WHERE|GROUP|ORDER|LIMIT|HAVING|QUALIFY)\b", re.IGNORECASE)


def normalize_table(name: str) -> str:
    return name.replace("`", "").replace('"', "")


def parse_sql(sql_text: str) -> list[dict]:
    """返回 [{target, sources:[...]}]。支持常见 INSERT...SELECT 与 CTAS。"""
    results = []
    for statement in sqlparse.split(sql_text or ""):
        if not statement.strip():
            continue
        target = None
        match = _INSERT_RE.search(statement)
        if match:
            target = normalize_table(match.group("target"))
        else:
            match = _CREATE_RE.search(statement)
            if match:
                target = normalize_table(match.group("target"))
        if not target:
            continue
        from_pos = _FROM_RE.search(statement)
        if not from_pos:
            continue
        tail = statement[from_pos.start():]
        stop = _STOP_RE.search(tail)
        segment = tail[: stop.start()] if stop else tail
        sources = []
        for source in _SOURCE_RE.finditer(segment):
            table = normalize_table(source.group("table"))
            if table.lower() not in ("dual",) and table not in sources:
                sources.append(table)
        if sources:
            results.append({"target": target, "sources": sources})
    return results


def save_lineage(sql_file: str, sql_text: str) -> list[dict]:
    edges = []
    for item in parse_sql(sql_text):
        for source in item["sources"]:
            edge, _ = LineageEdge.objects.get_or_create(
                source_table=source,
                target_table=item["target"],
                sql_file=sql_file or "",
            )
            edges.append({"source": edge.source_table, "target": edge.target_table})
    return edges


def graph() -> dict:
    edges = list(LineageEdge.objects.all().order_by("target_table", "source_table"))
    nodes = sorted({t for e in edges for t in (e.source_table, e.target_table)})
    return {
        "nodes": nodes,
        "edges": [
            {"source": e.source_table, "target": e.target_table, "sql_file": e.sql_file}
            for e in edges
        ],
    }
