import random
import re
from urllib.request import urlopen

from core.utils import reply


KUCHEN_REZEPTE = [
    "https://www.einfachbacken.de/rezepte/zebrakuchen-einfach-selbstgemacht",
    "https://www.einfachbacken.de/rezepte/zitronenkuchen-erfrischend-saftig",
    "https://www.lecker.de/quarkkuchen-das-10-minuten-rezept-78459.html",
    "https://www.lecker.de/einfache-muffins-mit-schokostueckchen-129135.html",
    "https://emmikochteinfach.de/saftiges-bananenbrot-ganz-einfach/",
    "https://www.chefkoch.de/rezepte/1692201277528566/Die-schnellsten-und-besten-Muffins-ueberhaupt.html",
    "https://www.einfachbacken.de/rezepte/saftiger-karottenkuchen-einfach-und-schnell",
    "https://www.chefkoch.de/rezepte/1511921256558799/Erdbeerkuchen-mit-Schmand-Vanillecreme.html",
    "https://www.chefkoch.de/rezepte/1218391227356456/Der-beste-Kaesekuchen-der-Welt.html",
    "https://www.chefkoch.de/rezepte/1140221220253617/Supersaftiger-Apfelkuchen.html",
]

WILL_NICHT_RESPONSES = [
    "Will nicht ist leider kein Task.",
    "„Ich kann, weil ich will, was ich muss.“ – Immanuel Kant",
    "Wollen ist Freiheit, so aber nicht die Flur-Tasks - Martin",
    "Wenn Freiheit überhaupt etwas bedeutet, dann das Recht, anderen Leuten auf ihre Flurtasks aufmerksam zu machen.",
    "Die einzige Möglichkeit, großartige Arbeit zu leisten, ist zu tun, was einem zugeteilt wurde.",
    "Wille ist nicht das was den Flur sauber hält - es sind die Tasks.",
    "Schopenhauer besagt: Der Mensch kann tun, was er will, aber er kann nicht wollen, was er will. Doch er kann immer noch tun, was er nicht will.",
    "Wo ein Wille ist, ist auch ein Weg. Wo kein Wille ist, ist auch ein Weg aber es gibt Kuchen.",
    "Der Wille gestaltet den Menschen, zum Erfolg braucht er jedoch Mut, Ausdauer und das Erledigen seiner Tasks.",
    "Pessimismus ist Sache des Gemüts, Optimismus Willenssache.",
    "Unser Flur ist unser Garten, und unser Wille der Gärtner - aber der Gärtner steht under Festanstellung."
]


def _fetch_zitat_des_tages(log):
    try:
        html = urlopen("https://www.zitate.de/", timeout=10).read().decode("utf-8")
        match = re.search(
            r'<div id="zitat-des-tages">\s*<img[^>]*>\s*<p>(.*?)</p>\s*<p[^>]*>\s*<small>(.*?)</small>',
            html, re.DOTALL,
        )
        if match:
            quote = re.sub(r"<[^>]+>", "", match.group(1)).strip()
            quote = quote.replace("&bdquo;", "„").replace("&ldquo;", "“")
            quote = quote.replace("&rdquo;", "”").replace("&amp;", "&")
            author = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            author = author.replace("&amp;", "&")
            return f"{quote}\n\n{author}"
    except Exception as e:
        log.warning("Failed to fetch Zitat des Tages: %s", e)
    return None


def run(ctx):
    ctx.log.info("=== Auto Reply ===")
    message = ctx.trigger_context.get("message", "")
    sender = ctx.trigger_context.get("sender")
    ctx.log.info("Received from %s: %s", sender, message[:100])

    chat = ctx.target_chats[0]
    msg_lower = message.lower()

    if "will nicht" in msg_lower:
        response = random.choice(WILL_NICHT_RESPONSES)
        ctx.log.info("Matched 'will nicht', replying: %s", response[:50])
        reply(ctx.signal, chat, response, ctx.trigger_context)
        return

    if "kuchen" in msg_lower:
        picks = random.sample(KUCHEN_REZEPTE, 2)
        response = f"Du willst (vielleicht musst) Kuchen backen? Hier sind zwei Kuchen Rezepte:\n{picks[0]}\n{picks[1]}"
        ctx.log.info("Matched 'kuchen', replying with recipes")
        reply(ctx.signal, chat, response, ctx.trigger_context)
        return

    if "zitat" in msg_lower:
        zitat = _fetch_zitat_des_tages(ctx.log)
        if zitat:
            ctx.log.info("Matched 'zitat', replying with Zitat des Tages")
            reply(ctx.signal, chat, f"Zitat des Tages:\n\n{zitat}", ctx.trigger_context)
        else:
            reply(ctx.signal, chat, "Konnte das Zitat des Tages leider nicht laden :(", ctx.trigger_context)
        return

    ctx.log.info("No matching rule, ignoring message")
