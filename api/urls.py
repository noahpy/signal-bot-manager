from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    path("status/", views.status),
    path("groups/", views.groups),
    path("groups/sync/", views.groups_sync),
    path("groups/members/", views.group_members),  # ?id=<group id> (base64 contains '/')
    path("preview/", views.preview),
    path("reminders/", views.reminder_list),
    path("reminders/<str:external_id>/", views.reminder_detail),
    path("reminders/<str:external_id>/run/", views.reminder_run),
    path("reminders/<str:external_id>/executions/", views.reminder_executions),
]
