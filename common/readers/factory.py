from .base import MetadataReader
from .clickhouse import ClickHouseReader
from .db2 import DB2Reader
from .mysql import MySQLReader
from .odps import ODPSReader
from .oracle import OracleReader
from .postgresql import PostgreSQLReader

READERS: dict[str, type[MetadataReader]] = {
    PostgreSQLReader.DB_TYPE: PostgreSQLReader,
    MySQLReader.DB_TYPE: MySQLReader,
    ODPSReader.DB_TYPE: ODPSReader,
    OracleReader.DB_TYPE: OracleReader,
    ClickHouseReader.DB_TYPE: ClickHouseReader,
    DB2Reader.DB_TYPE: DB2Reader,
    # 国产数据库协议兼容: OceanBase(MySQL 协议), GaussDB/DWS(PostgreSQL 协议)
    "oceanbase": MySQLReader,
    "gaussdb": PostgreSQLReader,
    "dws": PostgreSQLReader,
    "opengauss": PostgreSQLReader,
}


def get_reader(db_type: str, **kwargs) -> MetadataReader:
    """按数据库类型创建元数据读取器。"""
    reader_cls = READERS.get((db_type or "").lower())
    if reader_cls is None:
        raise ValueError(
            f"不支持的数据库类型: {db_type!r}, 可用: {', '.join(READERS)}"
        )
    return reader_cls(**kwargs)
