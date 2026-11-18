"""Builds kitchen/bar tickets and guest receipts and sends them to network printers.

Printers are reached over the network on their raw printing port (usually 9100) and are sent
ESC/POS, the command set nearly every thermal receipt and kitchen printer understands. The server
does the printing, so it works the same whether the stations are PCs, Android tablets or iPads.
"""
import re
import socket
from pathlib import Path
from typing import Iterable, List, Tuple
from zoneinfo import ZoneInfo

from datetime import timezone

from app.core.config import settings
from app.core.constants import CATEGORY_LABELS

WIDTH = 42  # characters per line on 80 mm paper in the standard font
PRINT_TIMEOUT_SECONDS = 3.0

Line = Tuple[str, str]  # (style, text); style is "left", "center" or "title"

_INIT = b"\x1b@"
_LEFT, _CENTER = b"\x1ba\x00", b"\x1ba\x01"
_BOLD_ON, _BOLD_OFF = b"\x1bE\x01", b"\x1bE\x00"
_BIG, _NORMAL = b"\x1d!\x11", b"\x1d!\x00"
_FEED_AND_CUT = b"\n\n\n\n\x1dV\x00"


def money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def local_time(naive_utc):
    """Stored timestamps are naive UTC; show them in the restaurant's own time."""
    return naive_utc.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.BUSINESS_TIMEZONE))


def divider() -> Line:
    return ("left", "-" * WIDTH)


def two_columns(left: str, right: str) -> str:
    """Left text at the left edge, right text at the right edge; the left text is cut if both do not fit."""
    if not right:
        return left[:WIDTH]
    room = WIDTH - len(right) - 1
    if room < 1:
        return (left + " " + right)[:WIDTH]
    return left[:room].ljust(room) + " " + right


def to_text(lines: Iterable[Line]) -> str:
    """Plain-text picture of a printout (used for previews and tests)."""
    out = []
    for style, text in lines:
        out.append(text.center(WIDTH).rstrip() if style in ("center", "title") else text)
    return "\n".join(out) + "\n"


def to_escpos(lines: Iterable[Line]) -> bytes:
    """ESC/POS bytes for a printout, ending with a paper cut."""
    data = bytearray(_INIT)
    for style, text in lines:
        encoded = text.encode("cp437", errors="replace") + b"\n"
        if style == "title":
            data += _CENTER + _BOLD_ON + _BIG + encoded + _NORMAL + _BOLD_OFF + _LEFT
        elif style == "center":
            data += _CENTER + encoded + _LEFT
        else:
            data += encoded
    data += _FEED_AND_CUT
    return bytes(data)


def send_raw(host: str, port: int, data: bytes) -> None:
    """Send bytes to a network printer. Raises OSError if it cannot be reached."""
    with socket.create_connection((host, port), timeout=PRINT_TIMEOUT_SECONDS) as connection:
        connection.sendall(data)


def ticket_lines(track: str, seat: str, party_name: str, sent_at, items) -> List[Line]:
    """A kitchen or bar ticket for the lines of one order on one track."""
    lines: List[Line] = [
        ("title", CATEGORY_LABELS.get(track, track).upper()),
        ("title", seat),
        ("center", party_name),
        ("center", local_time(sent_at).strftime("%I:%M %p").lstrip("0")),
        divider(),
    ]
    for item in items:
        flag = "VOID" if item.voided else "CHANGED" if item.changed else ""
        lines.append(("left", two_columns(f"{item.qty} x {item.name}", flag)))
        if item.notes:
            lines.append(("left", f"   > {item.notes}"[:WIDTH]))
    lines.append(divider())
    return lines


def test_page_lines(device_name: str, jobs: List[str]) -> List[Line]:
    return [
        ("title", "KISnet-POS"),
        ("center", "Printer test"),
        divider(),
        ("left", f"Printer: {device_name}"[:WIDTH]),
        ("left", f"Prints:  {', '.join(jobs)}"[:WIDTH]),
        divider(),
        ("center", "If you can read this, it works."),
    ]


def load_receipt_template() -> str:
    return Path(settings.RECEIPT_TEMPLATE).read_text(encoding="utf-8")


def receipt_lines(template: str, fields: dict, items) -> List[Line]:
    """Fill in the receipt template. `items` are (qty, name, line_total_cents) tuples."""
    lines: List[Line] = []
    for raw in template.splitlines():
        if raw.startswith("#"):
            continue
        text = raw.rstrip()
        stripped = text.strip()
        if stripped == "{items}":
            for qty, name, cents in items:
                lines.append(("left", two_columns(f"{qty} {name}", money(cents))))
            continue
        if stripped and set(stripped) == {"-"}:
            lines.append(divider())
            continue
        style = "left"
        if text.startswith("!"):
            style, text = "title", text[1:].strip()
        elif text.startswith("^"):
            style, text = "center", text[1:].strip()
        if not text and not lines:
            continue  # no blank paper before the first printed line
        # Unknown {words} are left as typed so a typo is visible on the printout
        text = re.sub(r"\{(\w+)\}", lambda m: str(fields.get(m.group(1), m.group(0))), text)
        if style == "left" and " | " in text:
            left, right = text.split(" | ", 1)
            text = two_columns(left.strip(), right.strip())
        lines.append((style, text[:WIDTH]))
    return lines


SAMPLE_RECEIPT_FIELDS = {
    "seat": "B2", "party_name": "Smith", "party_size": 4, "server_name": "Michael Brooks",
    "date": "11/17/2026", "time": "6:42 PM", "order_number": 1042, "item_count": 5, "total": "$47.50",
}
SAMPLE_RECEIPT_ITEMS = [(2, "House Burger", 2400), (1, "Caesar Salad", 950), (2, "Draft Beer", 1400)]
