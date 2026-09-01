"""元数据读取器基类。"""
from abc import ABC, abstractmethod


class MetadataReader(ABC):
    """从远端数据库读取 information_schema 元数据的统一接口。"""

    DB_TYPE = "base"

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        schema: str | None = None,
        timeout: int = 10,
    ):
        self.host = host
        self.port = int(port)
        self.user = user
        self.password = password
        self.database = database
        self.schema = schema
        self.timeout = timeout
        self._connection = None

    @abstractmethod
    def _connect(self):
        """建立并返回数据库连接。"""

    def connect(self):
        if self._connection is None:
            self._connection = self._connect()
        return self._connection

    @abstractmethod
    def list_schemas(self) -> list[str]:
        """返回所有业务 schema 名。"""

    @abstractmethod
    def list_tables(self, schema: str) -> list[dict]:
        """返回 schema 下的表: {schema, name, table_type, comment}。"""

    @abstractmethod
    def list_columns(self, schema: str, table: str) -> list[dict]:
        """返回表字段: {name, ordinal_position, data_type, column_type,
        column_default, is_nullable, max_length, numeric_precision,
        numeric_scale, comment}。"""

    @abstractmethod
    def list_indexes(self, schema: str, table: str) -> list[dict]:
        """返回表索引: {name, is_unique, is_primary, column_names, definition}。"""

    @abstractmethod
    def list_constraints(self, schema: str, table: str) -> list[dict]:
        """返回表约束: {name, constraint_type, column_names,
        referenced_table, referenced_column}。"""

    def read_all(self, schema: str | None = None) -> list[dict]:
        """读取 schema(默认全部)下所有表的完整元数据。"""
        schemas = [schema] if schema else self.list_schemas()
        tables: list[dict] = []
        for schema_name in schemas:
            for table in self.list_tables(schema_name):
                table_name = table["name"]
                table["columns"] = self.list_columns(schema_name, table_name)
                table["indexes"] = self.list_indexes(schema_name, table_name)
                table["constraints"] = self.list_constraints(schema_name, table_name)
                tables.append(table)
        return tables

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
