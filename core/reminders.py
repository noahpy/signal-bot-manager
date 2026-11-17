"""Declarative reminder specs (v1), as created by signal-bot-reminder-generator.

Pure logic (no Signal / DB access) so it can be unit tested and used for previews.

Spec format::

    {
      "version": 1,
      "title": "Staubsaugbeutel entleeren",
      "message_template": "Hey {mentions}, eine Erinnerung für \"{title}\" – {timing} :)",
      "timezone": "Europe/Berlin",
      "send_time": "09:00",
      "people": [{"uuid": "...", "name": "Leon"}, {"uuid": "...", "name": "Lilli"}],
      "assignment": "all" | "rotate",          # rotate = round-robin, one person per occurrence
      "lead_days": 4,                           # remind N days before the occurrence
      "schedule": {
        "type": "once" | "weekly" | "monthly" | "interval" | "dates",
        "date": "2026-12-24",                   # once
        "weekdays": [0, 3],                     # weekly (0 = Monday)
        "every_weeks": 1,                       # weekly, optional
        "day_of_month": 1,                      # monthly (clamped to the month's last day)
        "months": [1, 2, 12],                   # monthly, optional subset of months
        "every_days": 14,                       # interval
        "start": "2026-11-09",                  # weekly/monthly/interval: first possible date + rotation anchor
        "until": null,                          # optional last date (inclusive)
        "dates": [{"date": "2026-11-09", "people": ["uuid"]}]   # dates: explicit list, people optional
      }
    }
"""

import calendar
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCHEDULE_TYPES = ("once", "weekly", "monthly", "interval", "dates")
DEFAULT_TEMPLATE = 'Hey {mentions}, eine Erinnerung für "{title}" – {timing} :)'
WEEKDAYS_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MAX_PEOPLE = 100
MAX_DATES = 1000


class SpecError(ValueError):
    pass


def _parse_date(value, field):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise SpecError(f"{field}: expected a date like 2026-11-09, got {value!r}")


def _parse_time(value):
    try:
        return time.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise SpecError(f"send_time: expected HH:MM, got {value!r}")


def validate(spec, default_tz="Europe/Berlin"):
    """Validate and normalise a spec. Returns a cleaned copy or raises SpecError."""
    if not isinstance(spec, dict):
        raise SpecError("spec must be an object")
    out = {"version": 1}
    title = str(spec.get("title", "")).strip()
    if not title:
        raise SpecError("title is required")
    out["title"] = title[:200]
    tmpl = str(spec.get("message_template") or DEFAULT_TEMPLATE)
    if len(tmpl) > 2000:
        raise SpecError("message_template too long")
    try:
        tmpl.format(**{k: "" for k in ("mentions", "names", "title", "date", "weekday", "days_until", "timing")})
    except (KeyError, IndexError, ValueError) as e:
        raise SpecError(f"message_template: unknown or broken placeholder ({e})")
    out["message_template"] = tmpl
    tz = spec.get("timezone") or default_tz
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise SpecError(f"unknown timezone {tz!r}")
    out["timezone"] = tz
    out["send_time"] = _parse_time(spec.get("send_time") or "09:00").strftime("%H:%M")

    people = spec.get("people") or []
    if not isinstance(people, list) or len(people) > MAX_PEOPLE:
        raise SpecError("people must be a list")
    clean_people = []
    for p in people:
        if not isinstance(p, dict) or not (p.get("uuid") or p.get("number") or p.get("name")):
            raise SpecError("each person needs a uuid, number or name")
        clean_people.append({k: str(p[k]) for k in ("uuid", "number", "name") if p.get(k)})
    out["people"] = clean_people

    assignment = spec.get("assignment") or "all"
    if assignment not in ("all", "rotate"):
        raise SpecError("assignment must be 'all' or 'rotate'")
    out["assignment"] = assignment
    try:
        lead = int(spec.get("lead_days") or 0)
    except (TypeError, ValueError):
        raise SpecError("lead_days must be a number")
    if not 0 <= lead <= 60:
        raise SpecError("lead_days must be between 0 and 60")
    out["lead_days"] = lead

    sched = spec.get("schedule") or {}
    stype = sched.get("type")
    if stype not in SCHEDULE_TYPES:
        raise SpecError(f"schedule.type must be one of {', '.join(SCHEDULE_TYPES)}")
    cs = {"type": stype}
    if sched.get("start"):
        cs["start"] = _parse_date(sched["start"], "schedule.start").isoformat()
    if sched.get("until"):
        cs["until"] = _parse_date(sched["until"], "schedule.until").isoformat()
    if stype == "once":
        cs["date"] = _parse_date(sched.get("date"), "schedule.date").isoformat()
    elif stype == "weekly":
        wds = sched.get("weekdays")
        if not wds or not all(isinstance(w, int) and 0 <= w <= 6 for w in wds):
            raise SpecError("schedule.weekdays must be a non-empty list of 0..6 (0 = Monday)")
        cs["weekdays"] = sorted(set(wds))
        cs["every_weeks"] = max(1, int(sched.get("every_weeks") or 1))
        if cs["every_weeks"] > 1 and "start" not in cs:
            raise SpecError("schedule.start is required when every_weeks > 1")
    elif stype == "monthly":
        dom = sched.get("day_of_month")
        if not isinstance(dom, int) or not 1 <= dom <= 31:
            raise SpecError("schedule.day_of_month must be 1..31")
        cs["day_of_month"] = dom
        months = sched.get("months")
        if months:
            if not all(isinstance(m, int) and 1 <= m <= 12 for m in months):
                raise SpecError("schedule.months must be 1..12")
            cs["months"] = sorted(set(months))
    elif stype == "interval":
        every = sched.get("every_days")
        if not isinstance(every, int) or not 1 <= every <= 366:
            raise SpecError("schedule.every_days must be 1..366")
        if "start" not in cs:
            raise SpecError("schedule.start is required for interval schedules")
        cs["every_days"] = every
    elif stype == "dates":
        entries = sched.get("dates") or []
        if not entries or len(entries) > MAX_DATES:
            raise SpecError("schedule.dates must be a non-empty list")
        clean = []
        for e in entries:
            if isinstance(e, str):
                e = {"date": e}
            item = {"date": _parse_date(e.get("date"), "schedule.dates[].date").isoformat()}
            if e.get("people"):
                item["people"] = [str(x) for x in e["people"]]
            clean.append(item)
        cs["dates"] = sorted(clean, key=lambda x: x["date"])
    out["schedule"] = cs
    if out["assignment"] == "rotate" and not out["people"] and stype != "dates":
        raise SpecError("rotation needs at least one person")
    return out


# --- occurrence computation -------------------------------------------------

def _person_key(p):
    return p.get("uuid") or p.get("number") or p.get("name")


def _matches(sched, d):
    """Does date d match a recurring schedule (ignoring start/until)?"""
    t = sched["type"]
    if t == "once":
        return d.isoformat() == sched["date"]
    if t == "weekly":
        if d.weekday() not in sched["weekdays"]:
            return False
        if sched.get("every_weeks", 1) > 1:
            start = date.fromisoformat(sched["start"])
            start_monday = start - timedelta(days=start.weekday())
            weeks = ((d - timedelta(days=d.weekday())) - start_monday).days // 7
            return weeks % sched["every_weeks"] == 0
        return True
    if t == "monthly":
        if sched.get("months") and d.month not in sched["months"]:
            return False
        last = calendar.monthrange(d.year, d.month)[1]
        return d.day == min(sched["day_of_month"], last)
    if t == "interval":
        start = date.fromisoformat(sched["start"])
        return d >= start and (d - start).days % sched["every_days"] == 0
    return False


def _in_window(sched, d):
    if sched.get("start") and d < date.fromisoformat(sched["start"]):
        return False
    if sched.get("until") and d > date.fromisoformat(sched["until"]):
        return False
    return True


def _occurrence_index(sched, d):
    """0-based index of occurrence d since the schedule's anchor, for rotation."""
    t = sched["type"]
    if t == "interval":
        return (d - date.fromisoformat(sched["start"])).days // sched["every_days"]
    anchor = date.fromisoformat(sched["start"]) if sched.get("start") else None
    if t == "monthly":
        if anchor is None:
            return d.year * 12 + d.month  # stable but arbitrary rotation
        n, cur = 0, anchor
        # count matching months between anchor and d
        y, m = anchor.year, anchor.month
        while (y, m) < (d.year, d.month):
            last = calendar.monthrange(y, m)[1]
            cur = date(y, m, min(sched["day_of_month"], last))
            if cur >= anchor and _matches(sched, cur):
                n += 1
            m += 1
            if m > 12:
                y, m = y + 1, 1
        return n
    if t == "weekly":
        if anchor is None:
            anchor = date(2024, 1, 1)  # a Monday; arbitrary fixed anchor
        n, cur = 0, anchor
        while cur < d:
            if _matches(sched, cur):
                n += 1
            cur += timedelta(days=1)
        return n
    return 0


def _assignees(spec, d, explicit=None, index=0):
    people = spec["people"]
    by_key = {_person_key(p): p for p in people}
    if explicit:
        return [by_key.get(k, {"uuid": k} if "-" in k else {"name": k}) for k in explicit]
    if not people:
        return []
    if spec["assignment"] == "rotate":
        return [people[index % len(people)]]
    return list(people)


def occurrences_on(spec, d):
    """Occurrences (date, assignees) that fall on date d."""
    sched = spec["schedule"]
    if sched["type"] == "dates":
        res = []
        for i, e in enumerate(sched["dates"]):
            if e["date"] == d.isoformat():
                res.append((d, _assignees(spec, d, e.get("people"), i)))
        return res
    if _in_window(sched, d) and _matches(sched, d):
        return [(d, _assignees(spec, d, None, _occurrence_index(sched, d)))]
    return []


def reminders_due(spec, today):
    """Reminders to send on `today`: occurrences on today + lead_days."""
    return occurrences_on(spec, today + timedelta(days=spec["lead_days"]))


def upcoming(spec, start, days=60):
    """List of (remind_date, occurrence_date, assignees) for the next `days` days."""
    res = []
    for i in range(days):
        day = start + timedelta(days=i)
        for occ, people in reminders_due(spec, day):
            res.append((day, occ, people))
    return res


def local_now(spec):
    return datetime.now(ZoneInfo(spec["timezone"]))


def send_time_reached(spec, now):
    return now.time() >= time.fromisoformat(spec["send_time"])


# --- rendering ----------------------------------------------------------------

def timing_text(occ, today):
    days = (occ - today).days
    if days == 0:
        return "heute fällig"
    if days == 1:
        return f"morgen fällig ({occ.strftime('%d.%m.')})"
    if days < 0:
        return f"seit dem {occ.strftime('%d.%m.')} fällig"
    return f"fällig am {WEEKDAYS_DE[occ.weekday()]}, {occ.strftime('%d.%m.')} (in {days} Tagen)"


def render(spec, occ, assignees, today, members=None):
    """Build (text, mention_specs, warnings).

    members: current Signal group members [{uuid, number, name}] or None (preview; mentions
    are then rendered as '@Name' without mention specs).
    """
    from core.utils import mention  # pure helper, no DB access

    warnings = []
    member_ids = None
    if members is not None:
        member_ids = {m.get("uuid") for m in members} | {m.get("number") for m in members}
        member_ids.discard(None)
        names_by_id = {}
        for m in members:
            for k in ("uuid", "number"):
                if m.get(k):
                    names_by_id[m[k]] = m.get("name")

    placeholders = []  # (text, builder or None)
    for p in assignees:
        display = p.get("name") or p.get("number") or "?"
        target = p.get("uuid") or p.get("number")
        if member_ids is not None and target and target in member_ids:
            text, builder = mention(target, "@" + (display or names_by_id.get(target) or "?"))
            placeholders.append((text, builder))
        else:
            if member_ids is not None and target:
                warnings.append(f"{display} is not (anymore) in the group – sent without @mention")
            placeholders.append(("@" + display if member_ids is None else display, None))

    mentions_str = ", ".join(t for t, _ in placeholders) if placeholders else "alle"
    fields = {
        "mentions": mentions_str,
        "names": ", ".join(p.get("name") or "?" for p in assignees) or "alle",
        "title": spec["title"],
        "date": occ.strftime("%d.%m.%Y"),
        "weekday": WEEKDAYS_DE[occ.weekday()],
        "days_until": (occ - today).days,
        "timing": timing_text(occ, today),
    }
    # Render with a unique marker for {mentions} so we can compute exact positions.
    marker = "\x00MENTIONS\x00"
    rendered = spec["message_template"].format(**{**fields, "mentions": marker})
    specs = []
    parts = rendered.split(marker)
    text = parts[0]
    for part in parts[1:]:
        pos = len(text.encode("utf-16-le")) // 2
        for i, (t, builder) in enumerate(placeholders):
            if i:
                text += ", "
                pos += 2
            if builder:
                specs.append(builder(pos))
            text += t
            pos += len(t.encode("utf-16-le")) // 2
        if not placeholders:
            text += "alle"
        text += part
    return text, specs, warnings
