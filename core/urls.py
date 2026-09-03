from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("common.ui_urls")),
    path("api/metadata/", include("api.urls")),
]
