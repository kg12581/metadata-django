from django.db import models


class DatabaseType(models.TextChoices):
    POSTGRESQL = "postgresql", "PostgreSQL"
    MYSQL = "mysql", "MySQL"


class SyncStatus(models.TextChoices):
    PENDING = "pending", "未同步"
    SYNCED = "synced", "已同步"
    ERROR = "error", "同步失败"


class MetadataDatabase(models.Model):
    """一个被采集的远端数据库(数据源)。"""

    name = models.CharField("名称", max_length=200, blank=True)
    db_type = models.CharField(
        "数据库类型",
        max_length=50,
        choices=DatabaseType.choices,
        default=DatabaseType.POSTGRESQL,
    )
    host = models.CharField("主机", max_length=255)
    port = models.PositiveIntegerField("端口", default=3306)
    user = models.CharField("用户名", max_length=100, blank=True)
    database_name = models.CharField("数据库名", max_length=200)
    schema_name = models.CharField("Schema", max_length=200, blank=True, default="")
    status = models.CharField(
        "同步状态",
        max_length=20,
        choices=SyncStatus.choices,
        default=SyncStatus.PENDING,
    )
    error_message = models.TextField("错误信息", blank=True, default="")
    last_sync_at = models.DateTimeField("最近同步时间", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "元数据库"
        verbose_name_plural = "元数据库"
        constraints = [
            models.UniqueConstraint(
                fields=["db_type", "host", "port", "database_name"],
                name="uniq_metadata_remote_db",
            )
        ]

    def __str__(self):
        return f"{self.db_type}://{self.host}:{self.port}/{self.database_name}"


class MetadataTable(models.Model):
    """远端库中的一张表或视图。"""

    database = models.ForeignKey(
        MetadataDatabase,
        verbose_name="元数据库",
        related_name="tables",
        on_delete=models.CASCADE,
    )
    schema_name = models.CharField("Schema", max_length=200)
    name = models.CharField("表名", max_length=200)
    table_type = models.CharField("表类型", max_length=50, blank=True, default="")
    comment = models.TextField("表注释", blank=True, default="")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        ordering = ["schema_name", "name"]
        verbose_name = "元数据表"
        verbose_name_plural = "元数据表"
        constraints = [
            models.UniqueConstraint(
                fields=["database", "schema_name", "name"],
                name="uniq_metadata_table",
            )
        ]

    def __str__(self):
        return f"{self.schema_name}.{self.name}"


class MetadataColumn(models.Model):
    """表中的一个字段。"""

    table = models.ForeignKey(
        MetadataTable,
        verbose_name="所属表",
        related_name="columns",
        on_delete=models.CASCADE,
    )
    name = models.CharField("字段名", max_length=200)
    ordinal_position = models.PositiveIntegerField("序号", default=1)
    data_type = models.CharField("数据类型", max_length=100)
    column_type = models.CharField("完整类型", max_length=255, blank=True, default="")
    column_default = models.TextField("默认值", null=True, blank=True)
    is_nullable = models.BooleanField("可空", default=True)
    max_length = models.PositiveIntegerField("最大长度", null=True, blank=True)
    numeric_precision = models.PositiveIntegerField("精度", null=True, blank=True)
    numeric_scale = models.PositiveIntegerField("小数位", null=True, blank=True)
    comment = models.TextField("字段注释", blank=True, default="")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        ordering = ["ordinal_position"]
        verbose_name = "元数据字段"
        verbose_name_plural = "元数据字段"
        constraints = [
            models.UniqueConstraint(
                fields=["table", "name"],
                name="uniq_metadata_column",
            )
        ]

    def __str__(self):
        return f"{self.table}.{self.name}"


class MetadataIndex(models.Model):
    """表上的索引。"""

    table = models.ForeignKey(
        MetadataTable,
        verbose_name="所属表",
        related_name="indexes",
        on_delete=models.CASCADE,
    )
    name = models.CharField("索引名", max_length=200)
    is_unique = models.BooleanField("唯一索引", default=False)
    is_primary = models.BooleanField("主键索引", default=False)
    column_names = models.JSONField("索引字段", default=list, blank=True)
    definition = models.TextField("索引定义", blank=True, default="")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "元数据索引"
        verbose_name_plural = "元数据索引"
        constraints = [
            models.UniqueConstraint(
                fields=["table", "name"],
                name="uniq_metadata_index",
            )
        ]

    def __str__(self):
        return f"{self.table}.{self.name}"


class MetadataConstraint(models.Model):
    """表上的约束(主键/外键/唯一/检查)。"""

    table = models.ForeignKey(
        MetadataTable,
        verbose_name="所属表",
        related_name="constraints",
        on_delete=models.CASCADE,
    )
    name = models.CharField("约束名", max_length=200)
    constraint_type = models.CharField("约束类型", max_length=50)
    column_names = models.JSONField("约束字段", default=list, blank=True)
    referenced_table = models.CharField("引用表", max_length=200, blank=True, default="")
    referenced_column = models.CharField("引用字段", max_length=200, blank=True, default="")
    definition = models.TextField("约束定义", blank=True, default="")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "元数据约束"
        verbose_name_plural = "元数据约束"
        constraints = [
            models.UniqueConstraint(
                fields=["table", "name"],
                name="uniq_metadata_constraint",
            )
        ]

    def __str__(self):
        return f"{self.table}.{self.name}"
