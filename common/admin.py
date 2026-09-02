from django.contrib import admin

from .models import (
    MetadataColumn,
    MetadataConstraint,
    MetadataDatabase,
    MetadataIndex,
    MetadataSourceConfig,
    MetadataTable,
)


@admin.register(MetadataDatabase)
class MetadataDatabaseAdmin(admin.ModelAdmin):
    list_display = ("name", "db_type", "host", "port", "database_name", "status", "last_sync_at")
    list_filter = ("db_type", "status")
    search_fields = ("name", "host", "database_name")


class MetadataColumnInline(admin.TabularInline):
    model = MetadataColumn
    extra = 0
    fields = ("name", "ordinal_position", "data_type", "is_nullable", "comment")


@admin.register(MetadataTable)
class MetadataTableAdmin(admin.ModelAdmin):
    list_display = ("database", "schema_name", "name", "table_type", "updated_at")
    list_filter = ("database", "schema_name")
    search_fields = ("name", "comment")
    inlines = [MetadataColumnInline]


@admin.register(MetadataColumn)
class MetadataColumnAdmin(admin.ModelAdmin):
    list_display = ("table", "name", "ordinal_position", "data_type", "is_nullable")
    list_filter = ("table__database",)
    search_fields = ("name", "comment")


@admin.register(MetadataIndex)
class MetadataIndexAdmin(admin.ModelAdmin):
    list_display = ("table", "name", "is_unique", "is_primary", "column_names")
    list_filter = ("is_unique", "is_primary")


@admin.register(MetadataConstraint)
class MetadataConstraintAdmin(admin.ModelAdmin):
    list_display = ("table", "name", "constraint_type", "column_names", "referenced_table")
    list_filter = ("constraint_type",)


@admin.register(MetadataSourceConfig)
class MetadataSourceConfigAdmin(admin.ModelAdmin):
    list_display = ("name", "db_type", "host", "port", "database_name", "username", "enabled", "updated_at")
    list_filter = ("db_type", "enabled")
    search_fields = ("name", "host", "database_name", "jdbc_url")
