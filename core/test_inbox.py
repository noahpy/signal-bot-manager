import time
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from core import cleanup, inbox, listener
from core.models import Chat, Job, JobExecution


def envelope(text, group=None, source="+4917600000001", name="Leon", ts=None):
    data = {"message": text, "timestamp": ts or int(time.time() * 1000)}
    if group:
        data["groupInfo"] = {"groupId": group}
    return {"sourceNumber": source, "sourceName": name, "timestamp": data["timestamp"], "dataMessage": data}


@override_settings(MESSAGES_PAGE=True)
class InboxTests(TestCase):
    def setUp(self):
        inbox.clear()

    def test_group_dm_sync_and_expiry(self):
        inbox.add_envelope(envelope("hi group", group="g1"))
        inbox.add_envelope(envelope("hi bot"))
        inbox.add_envelope({"sourceNumber": "+49bot", "syncMessage": {"sentMessage": {
            "message": "from my phone", "destinationNumber": "+4917600000001", "timestamp": int(time.time() * 1000)}}})
        inbox.add_envelope(envelope("old", group="g1", ts=int((time.time() - 2 * 86400) * 1000)))
        self.assertEqual([m["text"] for m in inbox.messages("g1")], ["hi group"])
        self.assertEqual([(m["direction"], m["text"]) for m in inbox.messages("+4917600000001")],
                         [("in", "hi bot"), ("out", "from my phone")])
        inbox.add_outgoing("g1", "pong")
        self.assertEqual(inbox.summary()["g1"][0], 2)

    def test_listener_buffers_but_never_logs_text(self):
        with self.assertLogs("core.listener", level="INFO") as logs, \
                mock.patch("core.listener._match_triggers"):
            listener._handle_notification({"params": {"envelope": envelope("geheimer Text", group="g1")}})
        self.assertNotIn("geheimer", "\n".join(logs.output))
        self.assertEqual(inbox.messages("g1")[0]["text"], "geheimer Text")


class CleanupTests(TestCase):
    def test_old_job_runs_deleted(self):
        job = Job.objects.create(name="J", job_type="simple", message_template="x")
        old = JobExecution.objects.create(job=job)
        JobExecution.objects.filter(pk=old.pk).update(started_at="2020-01-01T00:00:00Z")
        new = JobExecution.objects.create(job=job)
        self.assertEqual(cleanup._delete_old_executions(), 1)
        self.assertEqual(list(JobExecution.objects.values_list("pk", flat=True)), [new.pk])


@override_settings(DASHBOARD_REQUIRE_LOGIN=True, MESSAGES_PAGE=True)
class MessagePageTests(TestCase):
    def setUp(self):
        inbox.clear()
        self.chat = Chat.objects.create(chat_type="group", identifier="g1", name="H2F4 Tasks")
        User.objects.create_superuser("admin", password="pw")
        self.client.login(username="admin", password="pw")

    def test_read_and_send(self):
        inbox.add_envelope(envelope("hallo <b>", group="g1"))
        r = self.client.get("/messages/")
        self.assertContains(r, "H2F4 Tasks")
        r = self.client.get(f"/messages/{self.chat.pk}/")
        self.assertContains(r, "hallo &lt;b&gt;")  # escaped
        with mock.patch("dashboard.message_views.SignalClient") as sc:
            r = self.client.post(f"/messages/{self.chat.pk}/send/", {"text": "Hi from the bot"})
        self.assertEqual(r.status_code, 302)
        sc.return_value.send_to_chat.assert_called_once_with(self.chat, "Hi from the bot")

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get("/messages/").status_code, 302)


@override_settings(DASHBOARD_REQUIRE_LOGIN=False, MESSAGES_PAGE=False)
class MessagePageDisabledTests(TestCase):
    def test_disabled_without_login(self):
        inbox.clear()
        inbox.add_envelope(envelope("privat", group="g1"))
        self.assertEqual(inbox.messages("g1"), [])  # nothing buffered
        self.assertEqual(self.client.get("/messages/").status_code, 404)
        self.assertNotContains(self.client.get("/"), "/messages/")
