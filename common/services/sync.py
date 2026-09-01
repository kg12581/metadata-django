"""把远端数据库元数据同步到 Django 表。"""
from __future__ import annotations

from datetime import datetime

from django.db import models, transaction
from django.utils import timezone

from ..models import (
    MetadataColumn,
    MetadataConstraint,
    MetadataDatabase,
    MetadataIndex,
    MetadataTable,
)
from ..readers import get_reader


def _sync_table(database: MetadataDatabase, table_data: dict) -> tuple[int, int, int]:
    table, _ = MetadataTable.objects.update_or_create(
        database=database,
        schema_name=table_data["schema"],
        name=table_data["name"],
        defaults={
            "table_type": table_data.get("table_type", ""),
            "comment": table_data.get("comment", ""),
        },
    )

    column_count = index_count = constraint_count = 0

    column_names = set()
    for column_data in table_data.get("columns", []):
        column_names.add(column_data["name"])
        MetadataColumn.objects.update_or_create(
            table=table,
            name=column_data["name"],
            defaults={
                "ordinal_position": column_data.get("ordinal_position", 1),
                "data_type": column_data.get("data_type", ""),
                "column_type": column_data.get("column_type", ""),
                "column_default": column_data.get("column_default"),
                "is_nullable": column_data.get("is_nullable", True),
                "max_length": column_data.get("max_length"),
                "numeric_precision": column_data.get("numeric_precision"),
                "numeric_scale": column_data.get("numeric_scale"),
                "comment": column_data.get("comment", ""),
            },
        )
        column_count += 1
    table.columns.exclude(name__in=column_names).delete()

    index_names = set()
    for index_data in table_data.get("indexes", []):
        index_names.add(index_data["name"])
        MetadataIndex.objects.update_or_create(
            table=table,
            name=index_data["name"],
            defaults={
                "is_unique": index_data.get("is_unique", False),
                "is_primary": index_data.get("is_primary", False),
                "column_names": list(index_data.get("column_names", [])),
                "definition": index_data.get("definition", ""),
            },
        )
        index_count += 1
    table.indexes.exclude(name__in=index_names).delete()

    constraint_names = set()
    for constraint_data in table_data.get("constraints", []):
        constraint_names.add(constraint_data["name"])
        MetadataConstraint.objects.update_or_create(
            table=table,
            name=constraint_data["name"],
            defaults={
                "constraint_type": constraint_data.get("constraint_type", ""),
                "column_names": list(constraint_data.get("column_names", [])),
                "referenced_table": constraint_data.get("referenced_table", ""),
                "referenced_column": constraint_data.get("referenced_column", ""),
                "definition": constraint_data.get("definition", ""),
            },
        )
        constraint_count += 1
    table.constraints.exclude(name__in=constraint_names).delete()

    return column_count, index_count, constraint_count


def sync_metadata(config: dict) -> tuple[MetadataDatabase, dict]:
    """同步远端元数据到 Django 表, 返回 (数据库记录, 统计信息)。"""
    db_type = config["db_type"]
    database, _ = MetadataDatabase.objects.update_or_create(
        db_type=db_type,
        host=config["host"],
        port=config["port"],
        database_name=config["database"],
        defaults={
            "name": config.get("name")
            or f"{db_type}://{config['host']}:{config['port']}/{config['database']}",
            "user": config["user"],
            "schema_name": config.get("schema") or "",
            "status": "pending",
            "error_message": "",
        },
    )

    stats = {"tables": 0, "columns": 0, "indexes": 0, "constraints": 0}
    try:
        reader = get_reader(
            db_type,
            host=config["host"],
            port=config["port"],
            user=config["user"],
            password=config["password"],
            database=config["database"],
            schema=config.get("schema"),
        )
        with reader:
            remote_tables = reader.read_all(schema=config.get("schema"))

        with transaction.atomic():
            seen = set()
            for table_data in remote_tables:
                seen.add((table_data["schema"], table_data["name"]))
                column_count, index_count, constraint_count = _sync_table(
                    database, table_data
                )
                stats["tables"] += 1
                stats["columns"] += column_count
                stats["indexes"] += index_count
                stats["constraints"] += constraint_count

            # 清理远端已不存在的表
            stale_filter = models.Q(pk__in=[])
            for schema_name, table_name in seen:
                stale_filter |= models.Q(schema_name=schema_name, name=table_name)
            database.tables.exclude(stale_filter).delete()

        database.status = "synced"
        database.error_message = ""
        database.last_sync_at = timezone.now()
        database.save(update_fields=["status", "error_message", "last_sync_at", "updated_at"])
    except Exception as exc:
        database.status = "error"
        database.error_message = str(exc)
        database.save(update_fields=["status", "error_message", "updated_at"])
        raise

    return database, stats
