from django.db import models


class DatabaseType(models.TextChoices):
    POSTGRESQL = "postgresql", "PostgreSQL"
    MYSQL = "mysql", "MySQL"
    ODPS = "odps", "MaxCompute(ODPS)"


class SyncStatus(models.TextChoices):
    PENDING = "pending", "未同步"
    SYNCED = "synced", "已同步"
    ERROR = "error", "同步失败"


class SourceType(models.TextChoices):
    MYSQL = "mysql", "MySQL"
    POSTGRESQL = "postgresql", "PostgreSQL"
    ORACLE = "oracle", "Oracle"
    HIVE = "hive", "Hive"
    DORIS = "doris", "Doris"
    SQLSERVER = "sqlserver", "SQL Server"
    KAFKA = "kafka", "Kafka"
    ODPS = "odps", "MaxCompute(ODPS)"
    OTHER = "other", "其他"


class ReconcileType(models.TextChoices):
    ROW_COUNT = "row_count", "行数对账"
    PK_SNAPSHOT = "pk_snapshot", "主键快照对账"
    FIELD_VALUE = "field_value", "字段值对账"
    METRIC = "metric", "业务指标对账"
    METADATA = "metadata", "元数据对账"


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


class MetadataSourceConfig(models.Model):
    """可配置的元数据源(JDBC/连接信息), 用于维护 mysql/pg/oracle/hive/doris 等。"""

    name = models.CharField("名称", max_length=200, unique=True)
    db_type = models.CharField(
        "类型",
        max_length=50,
        choices=SourceType.choices,
        default=SourceType.MYSQL,
    )
    jdbc_url = models.CharField("JDBC URL", max_length=1000, blank=True, default="")
    host = models.CharField("主机", max_length=255, blank=True, default="")
    port = models.PositiveIntegerField("端口", null=True, blank=True)
    database_name = models.CharField("数据库/服务名", max_length=200, blank=True, default="")
    schema_name = models.CharField("Schema", max_length=200, blank=True, default="")
    username = models.CharField("用户名", max_length=200, blank=True, default="")
    password = models.CharField("密码", max_length=500, blank=True, default="")
    remark = models.TextField("备注", blank=True, default="")
    enabled = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        ordering = ["db_type", "name"]
        verbose_name = "元数据源配置"
        verbose_name_plural = "元数据源配置"

    def __str__(self):
        return f"[{self.db_type}] {self.name}"


class ReconcileTask(models.Model):
    """对账任务: 源端 vs Doris 目标, 支持 5 种对账类型。"""

    name = models.CharField("任务名", max_length=200, unique=True)
    task_type = models.CharField(
        "对账类型", max_length=30, choices=ReconcileType.choices
    )
    source_config = models.ForeignKey(
        MetadataSourceConfig,
        verbose_name="源配置",
        related_name="reconcile_tasks",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    source_db_name = models.CharField("源库名", max_length=200, blank=True, default="")
    source_schema = models.CharField("源 Schema(PG)", max_length=200, blank=True, default="")
    target_db_name = models.CharField("Doris 目标库", max_length=200, blank=True, default="")
    tables = models.JSONField("对账表", default=list, blank=True)
    columns = models.JSONField("字段值对账列", default=list, blank=True)
    pk_columns = models.JSONField("主键快照主键列", default=list, blank=True)
    metric_sql = models.TextField("指标 SQL({table} 占位)", blank=True, default="")
    enabled = models.BooleanField("启用", default=True)
    remark = models.TextField("备注", blank=True, default="")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "对账任务"
        verbose_name_plural = "对账任务"

    def __str__(self):
        return f"[{self.get_task_type_display()}] {self.name}"


class ReconcileRun(models.Model):
    """对账任务执行记录。"""

    class RunStatus(models.TextChoices):
        PENDING = "pending", "等待"
        RUNNING = "running", "运行中"
        SUCCESS = "success", "成功"
        FAILED = "failed", "失败"

    task = models.ForeignKey(
        ReconcileTask,
        verbose_name="任务",
        related_name="runs",
        on_delete=models.CASCADE,
    )
    status = models.CharField(
        "状态", max_length=20, choices=RunStatus.choices, default=RunStatus.PENDING
    )
    summary = models.JSONField("汇总", default=dict, blank=True)
    details = models.JSONField("明细", default=list, blank=True)
    error = models.TextField("错误", blank=True, default="")
    duration_ms = models.PositiveIntegerField("耗时 ms", default=0)
    ran_at = models.DateTimeField("执行时间", auto_now_add=True)

    class Meta:
        ordering = ["-ran_at"]
        verbose_name = "对账执行"
        verbose_name_plural = "对账执行"

    def __str__(self):
        return f"{self.task.name} @ {self.ran_at:%Y-%m-%d %H:%M:%S} [{self.status}]"


class LineageEdge(models.Model):
    """SQL 血缘边: source_table -> target_table。"""

    source_table = models.CharField("源表", max_length=500)
    target_table = models.CharField("目标表", max_length=500)
    sql_file = models.CharField("来源 SQL 文件", max_length=500, blank=True, default="")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        ordering = ["target_table", "source_table"]
        verbose_name = "血缘关系"
        verbose_name_plural = "血缘关系"
        constraints = [
            models.UniqueConstraint(
                fields=["source_table", "target_table", "sql_file"],
                name="uniq_lineage_edge",
            )
        ]

    def __str__(self):
        return f"{self.source_table} -> {self.target_table}"


class AnalyticsEvent(models.Model):
    """埋点: 记录请求与关键操作, 用于运营看板。"""

    event_type = models.CharField("事件类型", max_length=20, default="request")
    method = models.CharField("方法", max_length=10, blank=True, default="")
    path = models.CharField("路径", max_length=500, blank=True, default="")
    status_code = models.PositiveIntegerField("状态码", null=True, blank=True)
    duration_ms = models.PositiveIntegerField("耗时 ms", default=0)
    username = models.CharField("用户", max_length=150, blank=True, default="")
    ip = models.CharField("IP", max_length=64, blank=True, default="")
    detail = models.JSONField("详情", default=dict, blank=True)
    created_at = models.DateTimeField("时间", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "埋点事件"
        verbose_name_plural = "埋点事件"
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["path"]),
            models.Index(fields=["status_code"]),
        ]

    def __str__(self):
        return f"{self.method} {self.path} -> {self.status_code} @ {self.created_at:%H:%M:%S}"


class ScriptRun(models.Model):
    """脚本运行历史。"""

    script_path = models.CharField("脚本路径", max_length=500)
    args = models.JSONField("参数", default=list, blank=True)
    status = models.CharField("状态", max_length=20, default="success")
    exit_code = models.IntegerField("退出码", null=True, blank=True)
    output = models.TextField("输出", blank=True, default="")
    duration_ms = models.PositiveIntegerField("耗时 ms", default=0)
    started_at = models.DateTimeField("开始时间", auto_now_add=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "脚本运行"
        verbose_name_plural = "脚本运行"

    def __str__(self):
        return f"{self.script_path} [{self.status}] @ {self.started_at:%H:%M:%S}"


class SchedulerJob(models.Model):
    """调度任务: 执行脚本管理中的 shell/python 或 ETL 脚本。"""

    class JobType(models.TextChoices):
        SCRIPT = "script", "脚本"
        ETL = "etl", "ETL"

    name = models.CharField("任务名", max_length=200, unique=True)
    job_type = models.CharField(
        "类型", max_length=20, choices=JobType.choices, default=JobType.SCRIPT
    )
    script_path = models.CharField("脚本路径", max_length=500, blank=True, default="")
    args = models.JSONField("参数", default=list, blank=True)
    cron_minute = models.PositiveIntegerField("分", default=0)
    cron_hour = models.PositiveIntegerField("时", default=2)
    timeout_seconds = models.PositiveIntegerField("超时秒", default=900)
    enabled = models.BooleanField("启用", default=True)
    remark = models.TextField("备注", blank=True, default="")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "调度任务"
        verbose_name_plural = "调度任务"

    def __str__(self):
        return f"[{self.get_job_type_display()}] {self.name}"

    def cron_fields(self) -> str:
        return f"{self.cron_minute} {self.cron_hour} * * *"


class SchedulerRun(models.Model):
    """调度任务执行历史。"""

    job = models.ForeignKey(
        SchedulerJob,
        verbose_name="任务",
        related_name="runs",
        on_delete=models.CASCADE,
    )
    status = models.CharField("状态", max_length=20, default="success")
    exit_code = models.IntegerField("退出码", null=True, blank=True)
    output = models.TextField("输出", blank=True, default="")
    duration_ms = models.PositiveIntegerField("耗时 ms", default=0)
    started_at = models.DateTimeField("开始时间", auto_now_add=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "调度执行"
        verbose_name_plural = "调度执行"

    def __str__(self):
        return f"{self.job.name} [{self.status}] @ {self.started_at:%H:%M:%S}"


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
