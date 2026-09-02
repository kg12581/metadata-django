"""前端页面路由。"""
from django.urls import path

from . import views

app_name = "ui"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("schema-sync/", views.schema_sync_page, name="schema-sync-page"),
    path("datax/", views.datax_page, name="datax-page"),
    path("etl/", views.etl_page, name="etl-page"),
    path("flink-sql/", views.flink_sql_page, name="flink-sql-page"),
    path("sources/", views.sources_page, name="sources-page"),
    path("sql-helper/", views.sql_helper_page, name="sql-helper-page"),
    path("ai-sql/", views.ai_sql_page, name="ai-sql-page"),
    path("spark2sql/", views.spark_to_hive_page, name="spark-to-hive-page"),
    path("reconcile/", views.reconcile_page, name="reconcile-page"),
    path("docs/", views.docs_page, name="docs-page"),
    path("sql-files/", views.sql_files_page, name="sql-files-page"),
    path("lineage/", views.lineage_page, name="lineage-page"),
    path("ops/", views.ops_page, name="ops-page"),
    path("scripts/", views.scripts_page, name="scripts-page"),
    path("databases/<int:pk>/", views.database_detail_ui, name="database-detail"),
    path("tables/<int:pk>/", views.table_detail_ui, name="table-detail"),
]
