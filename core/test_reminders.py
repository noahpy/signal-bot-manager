import json
from datetime import date

from django.test import TestCase, override_settings

from core import reminders
from core.models import Chat, Job

P = [{"uuid": "u-leon", "name": "Leon"}, {"uuid": "u-lilli", "name": "Lilli"}]


def spec(**kw):
    base = {"title": "T", "people": P, "schedule": {"type": "weekly", "weekdays": [3]}}
    base.update(kw)
    return reminders.validate(base)


class SpecTests(TestCase):
    def test_weekly_tafel(self):
        s = spec(title="Tafel")  # Thursday, no lead
        self.assertEqual(reminders.reminders_due(s, date(2026, 11, 12))[0][0], date(2026, 11, 12))
        self.assertEqual(reminders.reminders_due(s, date(2026, 11, 13)), [])

    def test_monthly_first_all(self):
        s = spec(schedule={"type": "monthly", "day_of_month": 1})
        due = reminders.reminders_due(s, date(2026, 12, 1))
        self.assertEqual([p["name"] for p in due[0][1]], ["Leon", "Lilli"])

    def test_monthly_clamps_to_month_end(self):
        s = spec(schedule={"type": "monthly", "day_of_month": 31})
        self.assertTrue(reminders.reminders_due(s, date(2027, 2, 28)))

    def test_interval_rotation_with_lead(self):
        # Staubsaugbeutel: every 14 days from 09.11., alternating Leon/Lilli, 4 days ahead
        s = spec(assignment="rotate", lead_days=4,
                 schedule={"type": "interval", "every_days": 14, "start": "2026-11-09"})
        d1 = reminders.reminders_due(s, date(2026, 11, 5))
        self.assertEqual((d1[0][0], d1[0][1][0]["name"]), (date(2026, 11, 9), "Leon"))
        d2 = reminders.reminders_due(s, date(2026, 11, 19))
        self.assertEqual((d2[0][0], d2[0][1][0]["name"]), (date(2026, 11, 23), "Lilli"))
        d3 = reminders.reminders_due(s, date(2026, 12, 3))  # year-agnostic continuation
        self.assertEqual(d3[0][1][0]["name"], "Leon")

    def test_dates_explicit_people_across_year(self):
        s = spec(lead_days=4, schedule={"type": "dates", "dates": [
            {"date": "2027-01-02", "people": ["u-lilli"]}, {"date": "2026-12-15"}]})
        due = reminders.reminders_due(s, date(2026, 12, 29))
        self.assertEqual(due[0][1][0]["name"], "Lilli")
        self.assertEqual(len(reminders.reminders_due(s, date(2026, 12, 11))[0][1]), 2)

    def test_render_mentions_positions(self):
        s = spec(message_template="Hey {mentions}, {title} {timing}")
        members = [{"uuid": "u-leon", "name": "Leon F"}, {"uuid": "u-lilli", "name": "L"}]
        text, specs, warnings = reminders.render(s, date(2026, 11, 12), P, date(2026, 11, 12), members)
        self.assertEqual(text, "Hey @Leon, @Lilli, T heute fällig")
        self.assertEqual(specs, ["4:5:u-leon", "11:6:u-lilli"])
        self.assertEqual(warnings, [])
        _, specs, warnings = reminders.render(s, date(2026, 11, 12), P, date(2026, 11, 12), members[:1])
        self.assertEqual(len(specs), 1)
        self.assertEqual(len(warnings), 1)

    def test_validation_errors(self):
        for bad in [{}, {"title": "x", "schedule": {"type": "nope"}},
                    {"title": "x", "message_template": "{oops}", "schedule": {"type": "once", "date": "2026-01-01"}},
                    {"title": "x", "schedule": {"type": "interval", "every_days": 7}}]:
            with self.assertRaises(reminders.SpecError):
                reminders.validate(bad)


@override_settings(REMINDER_API_TOKEN="secret")
class ApiTests(TestCase):
    def setUp(self):
        self.chat = Chat.objects.create(chat_type="group", identifier="grp/abc==", name="H2F4")
        self.auth = {"HTTP_AUTHORIZATION": "Bearer secret"}

    def put(self, eid, body):
        return self.client.put(f"/api/v1/reminders/{eid}/", json.dumps(body),
                               content_type="application/json", **self.auth)

    def test_auth(self):
        self.assertEqual(self.client.get("/api/v1/groups/").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/groups/", HTTP_AUTHORIZATION="Bearer x").status_code, 401)
        r = self.client.get("/api/v1/groups/", **self.auth)
        self.assertEqual(r.json()["groups"][0]["name"], "H2F4")

    def test_upsert_idempotent_and_delete(self):
        body = {"group_id": "grp/abc==", "spec": {"title": "Tafel", "schedule": {"type": "weekly", "weekdays": [3]}}}
        self.assertEqual(self.put("abc", body).status_code, 200)
        body["spec"]["title"] = "Tafel 2"
        self.assertEqual(self.put("abc", body).status_code, 200)
        job = Job.objects.get(external_id="abc")
        self.assertEqual((job.name, job.triggers.count(), job.script_path), ("Tafel 2", 1, "reminder_runner.py"))
        self.assertEqual(job.triggers.first().cron_expression, "0 7,8 * * *")  # 09:00 Berlin, CEST/CET
        self.assertEqual(self.put("abc", {"group_id": "grp/abc==", "spec": {}}).status_code, 400)
        self.client.delete("/api/v1/reminders/abc/", **self.auth)
        self.assertFalse(Job.objects.filter(external_id="abc").exists())

    def test_preview(self):
        r = self.client.post("/api/v1/preview/", json.dumps({
            "spec": {"title": "Pfand", "people": P, "schedule": {"type": "monthly", "day_of_month": 1}},
            "from": "2026-11-15", "days": 40}), content_type="application/json", **self.auth)
        items = r.json()["items"]
        self.assertEqual([i["send_on"] for i in items], ["2026-12-01"])
        self.assertIn("@Leon", items[0]["text"])


class MemberNameTests(TestCase):
    def test_display_name_order_and_profile_fetch(self):
        from core import utils
        self.assertEqual(utils.contact_display_name(
            {"name": "", "profile": {"givenName": "Martin", "familyName": "W"}}), "Martin W")
        self.assertEqual(utils.contact_display_name({"nickName": "Tini", "profile": {"givenName": "Martin"}}), "Tini")
        self.assertEqual(utils.contact_display_name({"profile": {}}), "")

        class FakeSignal:
            calls = 0

            def get_group_members(self, gid):
                return [{"uuid": "u-1", "number": None}]

            def list_contacts(self, detailed=False):
                FakeSignal.calls += 1
                return [{"uuid": "u-1", "number": None, "profile": {"givenName": "Martin"}}]

        utils._contacts.update(at=0.0, by_uuid={})
        chat = Chat.objects.create(chat_type="group", identifier="grp/x==", name="G")
        sig = FakeSignal()
        self.assertEqual(utils.resolve_group_members(sig, chat)[0]["name"], "Martin")
        utils.resolve_group_members(sig, chat)
        self.assertEqual(FakeSignal.calls, 1)  # cached
