from django.urls import path

from . import views

app_name = "webhook"

urlpatterns = [
    path("<str:token>/", views.webhook_trigger, name="trigger"),
]
