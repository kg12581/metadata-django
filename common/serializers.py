"""模型 -> dict 的序列化辅助函数。"""
from .models import MetadataDatabase, MetadataTable


def column_to_dict(column) -> dict:
    return {
        "id": column.id,
        "name": column.name,
        "ordinal_position": column.ordinal_position,
        "data_type": column.data_type,
        "column_type": column.column_type,
        "column_default": column.column_default,
        "is_nullable": column.is_nullable,
        "max_length": column.max_length,
        "numeric_precision": column.numeric_precision,
        "numeric_scale": column.numeric_scale,
        "comment": column.comment,
    }


def index_to_dict(index) -> dict:
    return {
        "id": index.id,
        "name": index.name,
        "is_unique": index.is_unique,
        "is_primary": index.is_primary,
        "column_names": index.column_names,
        "definition": index.definition,
    }


def constraint_to_dict(constraint) -> dict:
    return {
        "id": constraint.id,
        "name": constraint.name,
        "constraint_type": constraint.constraint_type,
        "column_names": constraint.column_names,
        "referenced_table": constraint.referenced_table,
        "referenced_column": constraint.referenced_column,
        "definition": constraint.definition,
    }


def table_to_dict(table: MetadataTable, include_children: bool = False) -> dict:
    data = {
        "id": table.id,
        "database_id": table.database_id,
        "schema_name": table.schema_name,
        "name": table.name,
        "table_type": table.table_type,
        "comment": table.comment,
    }
    if include_children:
        data["columns"] = [column_to_dict(c) for c in table.columns.all()]
        data["indexes"] = [index_to_dict(i) for i in table.indexes.all()]
        data["constraints"] = [constraint_to_dict(c) for c in table.constraints.all()]
    else:
        data["column_count"] = table.columns.count()
    return data


def database_to_dict(
    database: MetadataDatabase, include_tables: bool = False
) -> dict:
    data = {
        "id": database.id,
        "name": database.name,
        "db_type": database.db_type,
        "host": database.host,
        "port": database.port,
        "user": database.user,
        "database_name": database.database_name,
        "schema_name": database.schema_name,
        "status": database.status,
        "error_message": database.error_message,
        "last_sync_at": database.last_sync_at.isoformat()
        if database.last_sync_at
        else None,
        "created_at": database.created_at.isoformat(),
        "updated_at": database.updated_at.isoformat(),
        "table_count": database.tables.count(),
    }
    if include_tables:
        data["tables"] = [table_to_dict(t) for t in database.tables.all()]
    return data
