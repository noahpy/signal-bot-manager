"""Utilities for signal-bot job scripts.

Script authors can import helpers from here:
    from core.utils import send_to_all, format_table
"""

from core.signal_client import SignalClient


def send_to_all(signal_client, chats, message, attachments=None):
    for chat in chats:
        signal_client.send_to_chat(chat, message, attachments)


def format_table(headers, rows):
    if not rows:
        return "(empty)"
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    def _fmt_row(cells):
        return " | ".join(str(c).ljust(w) for c, w in zip(cells, col_widths))

    lines = [_fmt_row(headers)]
    lines.append("-+-".join("-" * w for w in col_widths))
    for row in rows:
        lines.append(_fmt_row(row))
    return "\n".join(lines)
