"""Device management: printers and monitors, pairing, and sending print jobs."""
import secrets
from datetime import timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.constants import RECEIPT_JOB, TRACKS
from app.core.security import hash_token, new_token
from app.core.time import utcnow
from app.db.base import SessionLocal
from app.models import Device, Order, Party
from app.services import printing
from app.services.admin import AdminError

PAIRING_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L
PAIRING_CODE_LENGTH = 6
PAIRING_MINUTES = 10
ONLINE_SECONDS = 20  # a monitor checks in every 2 seconds; quiet for this long means offline


def device_jobs(device: Device) -> List[str]:
    return [job for job in (device.jobs or "").split(",") if job]


def device_status(device: Device) -> str:
    if device.archived_at is not None:
        return "archived"
    return "active" if device.active else "inactive"


def _pairing_open(device: Device) -> bool:
    return bool(device.pairing_code and device.pairing_expires_at and device.pairing_expires_at > utcnow())


def device_connection(device: Device) -> str:
    """Printer: untested / ok / error. Monitor: not paired / waiting / online / offline."""
    if device.kind == "printer":
        if device.last_error:
            return "error"
        return "ok" if device.last_seen_at else "untested"
    if device.token_hash:
        seen = device.last_seen_at
        return "online" if seen and (utcnow() - seen).total_seconds() <= ONLINE_SECONDS else "offline"
    return "waiting" if _pairing_open(device) else "not paired"


def device_out(device: Device) -> dict:
    pairing = _pairing_open(device)
    return {
        "id": device.id, "name": device.name, "kind": device.kind, "jobs": device_jobs(device),
        "host": device.host, "port": device.port, "platform": device.platform,
        "status": device_status(device), "connection": device_connection(device),
        "last_seen_at": device.last_seen_at, "last_error": device.last_error,
        "pairing_code": device.pairing_code if pairing else None,
        "pairing_expires_at": device.pairing_expires_at if pairing else None,
    }


def list_devices(session: Session, include_archived: bool = False) -> List[dict]:
    query = session.query(Device).order_by(Device.kind, Device.name)
    if not include_archived:
        query = query.filter(Device.archived_at.is_(None))
    return [device_out(device) for device in query.all()]


def _editable(session: Session, device_id: int) -> Device:
    device = session.get(Device, device_id)
    if not device:
        raise AdminError(404, "Device not found")
    if device.archived_at is not None:
        raise AdminError(409, "Archived devices cannot be changed")
    return device


def _check_name_free(session: Session, name: str, device_id: Optional[int] = None) -> None:
    query = session.query(Device).filter(Device.name == name)
    if device_id is not None:
        query = query.filter(Device.id != device_id)
    if query.first():
        raise AdminError(409, "A device with this name already exists")


def _check_jobs(kind: str, jobs: List[str]) -> None:
    if kind == "monitor" and RECEIPT_JOB in jobs:
        raise AdminError(422, "A monitor shows tickets; only a printer can print receipts")


def add_device(session: Session, data) -> Device:
    name = data.name.strip()
    _check_name_free(session, name)
    _check_jobs(data.kind, data.jobs)
    if data.kind == "printer" and not data.host:
        raise AdminError(422, "A printer needs its network address")
    device = Device(
        location_id=1, name=name, kind=data.kind, jobs=",".join(data.jobs),
        host=data.host if data.kind == "printer" else None,
        port=(data.port or 9100) if data.kind == "printer" else None,
        active=True, created_at=utcnow(),
    )
    session.add(device)
    session.flush()
    if device.kind == "monitor":
        _new_code(session, device)
    session.commit()
    session.refresh(device)
    return device


def update_device(session: Session, device_id: int, data) -> Device:
    device = _editable(session, device_id)
    if data.name is not None:
        _check_name_free(session, data.name.strip(), device_id)
        device.name = data.name.strip()
    if data.jobs is not None:
        _check_jobs(device.kind, data.jobs)
        device.jobs = ",".join(data.jobs)
    if device.kind == "printer":
        if data.host is not None:
            device.host = data.host
        if data.port is not None:
            device.port = data.port
    session.commit()
    session.refresh(device)
    return device


def _unpair(device: Device) -> None:
    device.token_hash = None
    device.pairing_code = None
    device.pairing_expires_at = None
    device.platform = None


def deactivate_device(session: Session, device_id: int) -> Device:
    device = _editable(session, device_id)
    if not device.active:
        raise AdminError(409, "Already inactive")
    device.active = False
    session.commit()
    return device


def reactivate_device(session: Session, device_id: int) -> Device:
    device = _editable(session, device_id)
    if device.active:
        raise AdminError(409, "Already active")
    device.active = True
    session.commit()
    return device


def archive_device(session: Session, device_id: int) -> Device:
    device = session.get(Device, device_id)
    if not device:
        raise AdminError(404, "Device not found")
    if device.archived_at is not None:
        raise AdminError(409, "Already archived")
    device.active = False
    device.archived_at = utcnow()
    _unpair(device)
    session.commit()
    return device


def lan_addresses() -> List[str]:
    """This server's address on the local network, for phones, tablets and screens to connect to.

    Asks the operating system which interface it would use to reach the network; nothing is sent.
    """
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("10.255.255.255", 1))
            address = probe.getsockname()[0]
    except OSError:
        return []
    return [] if address.startswith("127.") else [address]


# --- Monitors: pairing ---------------------------------------------------------------------

def _new_code(session: Session, device: Device) -> None:
    while True:
        code = "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(PAIRING_CODE_LENGTH))
        if not session.query(Device).filter(Device.pairing_code == code).first():
            break
    device.pairing_code = code
    device.pairing_expires_at = utcnow() + timedelta(minutes=PAIRING_MINUTES)


def new_pairing_code(session: Session, device_id: int) -> Device:
    """Issue a fresh one-time code. Any screen already paired as this monitor is disconnected."""
    device = _editable(session, device_id)
    if device.kind != "monitor":
        raise AdminError(422, "Only monitors are paired with a code")
    _unpair(device)
    _new_code(session, device)
    session.commit()
    return device


def unpair_device(session: Session, device_id: int) -> Device:
    device = _editable(session, device_id)
    if device.kind != "monitor":
        raise AdminError(422, "Only monitors are paired")
    _unpair(device)
    session.commit()
    return device


def platform_from_user_agent(user_agent: str) -> str:
    agent = (user_agent or "").lower()
    if "android" in agent:
        return "Android"
    if any(word in agent for word in ("iphone", "ipad", "ipod", "macintosh", "mac os")):
        return "Apple"
    if any(word in agent for word in ("windows", "linux", "cros")):
        return "PC"
    return "Other"


def pair(session: Session, code: str, user_agent: str = ""):
    """Trade a one-time pairing code for a device token. Returns (device, token)."""
    code = (code or "").strip().upper()
    device = session.query(Device).filter(Device.pairing_code == code).first() if code else None
    if not device or not _pairing_open(device) or not device.active or device.archived_at is not None:
        raise AdminError(404, "That code is not valid. Ask a manager for a new one.")
    token = new_token()
    device.token_hash = hash_token(token)
    device.pairing_code = None
    device.pairing_expires_at = None
    device.platform = platform_from_user_agent(user_agent)
    device.last_seen_at = utcnow()
    session.commit()
    return device, token


def device_by_token(session: Session, token: str) -> Optional[Device]:
    """The active, paired monitor for this token; also records that it checked in."""
    device = session.query(Device).filter(Device.token_hash == hash_token(token)).first()
    if not device or not device.active or device.archived_at is not None:
        return None
    device.last_seen_at = utcnow()
    session.commit()
    return device


def disconnect(session: Session, device: Device) -> None:
    """The monitor itself signs off."""
    _unpair(device)
    session.commit()


# --- Printers ------------------------------------------------------------------------------

def _print(device: Device, lines) -> bool:
    """Send one printout; record success or the reason for failure on the device. Does not commit."""
    try:
        printing.send_raw(device.host, device.port or 9100, printing.to_escpos(lines))
    except OSError as error:
        device.last_error = f"{utcnow().isoformat(timespec='seconds')} {error}"[:300]
        return False
    device.last_seen_at = utcnow()
    device.last_error = None
    return True


def test_print(session: Session, device_id: int) -> Device:
    device = _editable(session, device_id)
    if device.kind != "printer":
        raise AdminError(422, "Only printers can run a test print")
    jobs = device_jobs(device)
    lines = printing.test_page_lines(device.name, jobs)
    if RECEIPT_JOB in jobs:
        lines = printing.receipt_lines(printing.load_receipt_template(), printing.SAMPLE_RECEIPT_FIELDS,
                                       printing.SAMPLE_RECEIPT_ITEMS)
    ok = _print(device, lines)
    session.commit()
    if not ok:
        raise AdminError(502, f"Could not reach the printer: {device.last_error}")
    return device


def _active_printers(session: Session) -> List[Device]:
    return (session.query(Device)
            .filter(Device.kind == "printer", Device.active.is_(True), Device.archived_at.is_(None))
            .order_by(Device.id).all())


def print_order_lines(order_id: int, item_ids: List[int]) -> int:
    """Print kitchen/bar tickets for the given lines of an order on every printer that handles their track.

    Runs after the response has been sent, with its own database session. A printer that cannot be
    reached never blocks or fails an order. Returns the number of tickets printed.
    """
    if not item_ids:
        return 0
    session = SessionLocal()
    try:
        printers = _active_printers(session)
        order = session.get(Order, order_id) if printers else None
        if not order:
            return 0
        wanted = set(item_ids)
        items = [item for item in order.items if item.id in wanted]
        printed = 0
        for printer in printers:
            for track in device_jobs(printer):
                lines = [item for item in items if item.category == track]
                if track in TRACKS and lines:
                    ticket = printing.ticket_lines(track, order.party.seat, order.party.party_name, utcnow(), lines)
                    printed += _print(printer, ticket)
        session.commit()
        return printed
    finally:
        session.close()


def receipt_for_party(session: Session, party: Party):
    """The template fields and item lines for one party's receipt."""
    items, total, count, last_order = [], 0, 0, None
    for order in party.orders:
        last_order = order
        for item in order.items:
            if item.voided:
                continue
            line_total = item.unit_price_cents * item.qty
            items.append((item.qty, item.name, line_total))
            total += line_total
            count += item.qty
    when = printing.local_time(party.closed_at or utcnow())
    fields = {
        "seat": party.seat, "party_name": party.party_name, "party_size": party.party_size,
        "server_name": party.server.name if party.server else "",
        "date": when.strftime("%m/%d/%Y"), "time": when.strftime("%I:%M %p").lstrip("0"),
        "order_number": last_order.id if last_order else party.id,
        "item_count": count, "total": printing.money(total),
    }
    return fields, items


def print_receipt(party_id: int) -> int:
    """Print the guest receipt for a party on every receipt printer. Returns how many printed."""
    session = SessionLocal()
    try:
        printers = [p for p in _active_printers(session) if RECEIPT_JOB in device_jobs(p)]
        party = session.get(Party, party_id) if printers else None
        if not party:
            return 0
        fields, items = receipt_for_party(session, party)
        try:
            template = printing.load_receipt_template()
        except OSError as error:
            for printer in printers:
                printer.last_error = f"Receipt template could not be read: {error}"[:300]
            session.commit()
            return 0
        lines = printing.receipt_lines(template, fields, items)
        printed = sum(_print(printer, lines) for printer in printers)
        session.commit()
        return printed
    finally:
        session.close()
