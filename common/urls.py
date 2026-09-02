from django.urls import path

from . import views

app_name = "common"

urlpatterns = [
    path("", views.index, name="index"),
    path("databases/", views.database_list, name="database-list"),
    path("databases/<int:pk>/export/", views.export_database_excel, name="database-export"),
    path("databases/<int:pk>/", views.database_detail, name="database-detail"),
    path("tables/<int:pk>/", views.table_detail, name="table-detail"),
    path("sync/", views.sync_database, name="database-sync"),
    path("datax/check/", views.datax_check, name="datax-check"),
    path("datax/sync/", views.datax_sync, name="datax-sync"),
    path("schema-sync/", views.schema_sync, name="schema-sync"),
    path("schema-sync/task/", views.schema_sync_task_detail, name="schema-sync-task"),
    path("schema-sync/task/save/", views.schema_sync_task_save, name="schema-sync-task-save"),
    path("schema-sync/run/", views.schema_sync_run_now, name="schema-sync-run"),
    path("schema-sync/log/", views.schema_sync_log_view, name="schema-sync-log"),
    path("etl/config/", views.etl_config_view, name="etl-config"),
    path("etl/config/save/", views.etl_config_save, name="etl-config-save"),
    path("etl/run/", views.etl_run, name="etl-run"),
    path("etl/log/", views.etl_log_view, name="etl-log"),
    path("flink-sql/files/", views.flink_sql_files, name="flink-sql-files"),
    path("flink-sql/file/", views.flink_sql_file, name="flink-sql-file"),
    path("flink-sync/jobs/", views.flink_sync_jobs, name="flink-sync-jobs"),
    path("flink-sync/generate/", views.flink_sync_generate, name="flink-sync-generate"),
    path("flink-sync/apply/", views.flink_sync_apply, name="flink-sync-apply"),
    path("sources/", views.source_list, name="source-list"),
    path("sources/create/", views.source_create, name="source-create"),
    path("sources/<int:pk>/update/", views.source_update, name="source-update"),
    path("sources/<int:pk>/delete/", views.source_delete, name="source-delete"),
    path("sources/<int:pk>/test/", views.source_test, name="source-test"),
    path("sources/<int:pk>/sync/", views.source_sync_metadata, name="source-sync"),
    path("sql-helper/options/", views.sql_helper_options, name="sql-helper-options"),
    path("sql-helper/tables/", views.sql_helper_tables, name="sql-helper-tables"),
    path("sql-helper/table/<int:pk>/", views.sql_helper_table, name="sql-helper-table"),
]
