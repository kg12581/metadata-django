from django.contrib import admin
from django.urls import include, path
from common.views import health_check

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", health_check, name="healthz"),
    path("", include("common.ui_urls")),
    path("api/metadata/", include("api.urls")),
]
