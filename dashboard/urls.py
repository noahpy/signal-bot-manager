from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.index, name="index"),
    path("jobs/", views.job_list, name="job_list"),
    path("jobs/new/", views.job_create, name="job_create"),
    path("jobs/<int:pk>/", views.job_detail, name="job_detail"),
    path("jobs/<int:pk>/edit/", views.job_edit, name="job_edit"),
    path("jobs/<int:pk>/delete/", views.job_delete, name="job_delete"),
    path("jobs/<int:pk>/toggle/", views.job_toggle, name="job_toggle"),
    path("jobs/<int:pk>/run/", views.job_run, name="job_run"),
    path("jobs/<int:pk>/logs/", views.job_logs_partial, name="job_logs_partial"),
    path("link/", views.link_account, name="link_account"),
    path("link/start/", views.link_start, name="link_start"),
    path("link/status/", views.link_status, name="link_status"),
    path("register/", views.register_account, name="register_account"),
    path("register/<str:action>/", views.register_action, name="register_action"),
    path("devices/add/", views.device_add, name="device_add"),
    path("chats/", views.chat_list, name="chat_list"),
    path("chats/sync/", views.chat_sync, name="chat_sync"),
]
