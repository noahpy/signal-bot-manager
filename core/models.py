import uuid

from django.db import models
from django.utils import timezone


class SignalAccount(models.Model):
    phone_number = models.CharField(max_length=20, blank=True)
    device_name = models.CharField(max_length=100, default="signal-bot")
    linked = models.BooleanField(default=False)
    linked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.phone_number or "(unlinked)"


class Chat(models.Model):
    class ChatType(models.TextChoices):
        CONTACT = "contact"
        GROUP = "group"

    chat_type = models.CharField(max_length=10, choices=ChatType.choices)
    identifier = models.CharField(max_length=200, unique=True)
    name = models.CharField(max_length=200, blank=True)
    synced_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name or self.identifier


class Job(models.Model):
    class JobType(models.TextChoices):
        SCRIPT = "script"
        SIMPLE = "simple"

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    job_type = models.CharField(max_length=10, choices=JobType.choices)
    enabled = models.BooleanField(default=True)
    script_path = models.CharField(max_length=500, blank=True)
    message_template = models.TextField(blank=True)
    target_chats = models.ManyToManyField(Chat, blank=True, related_name="jobs")
    reply_to_trigger_chat = models.BooleanField(
        default=False,
        help_text="Send to the chat that triggered the job instead of (or in addition to) the target chats.",
    )
    config_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Trigger(models.Model):
    class TriggerType(models.TextChoices):
        CRON = "cron"
        MESSAGE = "message"
        WEBHOOK = "webhook"

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="triggers")
    trigger_type = models.CharField(max_length=10, choices=TriggerType.choices)
    cron_expression = models.CharField(max_length=100, blank=True)
    pattern = models.CharField(max_length=500, blank=True)
    listen_chats = models.ManyToManyField(Chat, blank=True)
    webhook_token = models.CharField(
        max_length=100, blank=True, unique=True, null=True, default=None
    )
    enabled = models.BooleanField(default=True)
    last_fired_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.trigger_type == self.TriggerType.WEBHOOK and not self.webhook_token:
            self.webhook_token = uuid.uuid4().hex
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_trigger_type_display()} trigger for {self.job.name}"


class JobExecution(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        RUNNING = "running"
        SUCCESS = "success"
        FAILED = "failed"

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="executions")
    trigger = models.ForeignKey(
        Trigger, on_delete=models.SET_NULL, null=True, blank=True
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    log_output = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    trigger_context = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.job.name} @ {self.started_at:%Y-%m-%d %H:%M}"


class KeyValue(models.Model):
    namespace = models.CharField(max_length=200)
    key = models.CharField(max_length=200)
    value = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("namespace", "key")]

    def __str__(self):
        return f"{self.namespace}:{self.key}"
