from .base import MetadataReader
from .mysql import MySQLReader
from .odps import ODPSReader
from .postgresql import PostgreSQLReader

READERS: dict[str, type[MetadataReader]] = {
    PostgreSQLReader.DB_TYPE: PostgreSQLReader,
    MySQLReader.DB_TYPE: MySQLReader,
    ODPSReader.DB_TYPE: ODPSReader,
    # 国产数据库协议兼容: OceanBase(MySQL 协议), GaussDB/DWS(PostgreSQL 协议)
    "oceanbase": MySQLReader,
    "gaussdb": PostgreSQLReader,
    "dws": PostgreSQLReader,
}


def get_reader(db_type: str, **kwargs) -> MetadataReader:
    """按数据库类型创建元数据读取器。"""
    reader_cls = READERS.get((db_type or "").lower())
    if reader_cls is None:
        raise ValueError(
            f"不支持的数据库类型: {db_type!r}, 可用: {', '.join(READERS)}"
        )
    return reader_cls(**kwargs)
