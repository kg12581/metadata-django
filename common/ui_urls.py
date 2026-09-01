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
    path("databases/<int:pk>/", views.database_detail_ui, name="database-detail"),
    path("tables/<int:pk>/", views.table_detail_ui, name="table-detail"),
]
