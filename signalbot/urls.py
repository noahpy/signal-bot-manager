from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("webhook/", include("webhook.urls")),
    path("api/v1/", include("api.urls")),
    path("", include("dashboard.urls")),
]
