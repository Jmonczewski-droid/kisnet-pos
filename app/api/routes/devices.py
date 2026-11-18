"""Device management (admin) and the endpoints a paired monitor uses."""
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_owner
from app.models import Device, Employee
from app.schemas.device import DeviceEdit, DeviceIn, PairIn
from app.services import devices as service
from app.services import printing
from app.services.admin import AdminError
from app.services.tickets import bump_track, tickets_for_track

router = APIRouter()
admin_only = require_owner  # device management is database management: owner only


def _run(action, *args):
    try:
        return service.device_out(action(*args))
    except AdminError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail)


# --- Admin: the Devices screen --------------------------------------------------------------

@router.get("/admin/devices")
def get_devices(include_archived: bool = False, _: Employee = Depends(admin_only), db: Session = Depends(get_db)):
    return service.list_devices(db, include_archived=include_archived)


@router.post("/admin/devices", status_code=201)
def create_device(data: DeviceIn, _: Employee = Depends(admin_only), db: Session = Depends(get_db)):
    """Add a printer (network address) or a monitor (comes back with a one-time pairing code)."""
    return _run(service.add_device, db, data)


@router.patch("/admin/devices/{device_id}")
def edit_device(device_id: int, data: DeviceEdit, _: Employee = Depends(admin_only), db: Session = Depends(get_db)):
    return _run(service.update_device, db, device_id, data)


@router.post("/admin/devices/{device_id}/deactivate")
def deactivate(device_id: int, _: Employee = Depends(admin_only), db: Session = Depends(get_db)):
    return _run(service.deactivate_device, db, device_id)


@router.post("/admin/devices/{device_id}/reactivate")
def reactivate(device_id: int, _: Employee = Depends(admin_only), db: Session = Depends(get_db)):
    return _run(service.reactivate_device, db, device_id)


@router.post("/admin/devices/{device_id}/archive")
def archive(device_id: int, _: Employee = Depends(admin_only), db: Session = Depends(get_db)):
    return _run(service.archive_device, db, device_id)


@router.post("/admin/devices/{device_id}/pairing-code")
def pairing_code(device_id: int, _: Employee = Depends(admin_only), db: Session = Depends(get_db)):
    """New one-time code for a monitor. Disconnects whatever screen was paired before."""
    return _run(service.new_pairing_code, db, device_id)


@router.post("/admin/devices/{device_id}/unpair")
def unpair(device_id: int, _: Employee = Depends(admin_only), db: Session = Depends(get_db)):
    return _run(service.unpair_device, db, device_id)


@router.post("/admin/devices/{device_id}/test")
def test_print(device_id: int, _: Employee = Depends(admin_only), db: Session = Depends(get_db)):
    """Print a test page (a sample receipt on receipt printers). 502 if the printer cannot be reached."""
    return _run(service.test_print, db, device_id)


@router.get("/admin/server-address")
def server_address(request: Request, _: Employee = Depends(admin_only)):
    """Where other devices on the network can open the POS."""
    port = request.url.port or (443 if request.url.scheme == "https" else 80)
    return {"scheme": request.url.scheme, "port": port, "addresses": service.lan_addresses()}


@router.get("/admin/receipt-preview", response_class=PlainTextResponse)
def receipt_preview(_: Employee = Depends(admin_only)):
    """The receipt template filled in with sample data, as plain text."""
    try:
        template = printing.load_receipt_template()
    except OSError:
        raise HTTPException(status_code=500, detail="The receipt template file could not be read")
    return printing.to_text(printing.receipt_lines(template, printing.SAMPLE_RECEIPT_FIELDS,
                                                   printing.SAMPLE_RECEIPT_ITEMS))


# --- Monitors: connect and show tickets -----------------------------------------------------

def current_device(db: Session = Depends(get_db), authorization: str = Header(None)) -> Device:
    scheme, _, token = (authorization or "").partition(" ")
    device = service.device_by_token(db, token) if scheme == "Bearer" and token else None
    if not device:
        raise HTTPException(status_code=401, detail="This device is not connected")
    return device


def _me(device: Device) -> dict:
    return {"id": device.id, "name": device.name, "jobs": service.device_jobs(device), "platform": device.platform}


@router.post("/devices/pair")
def pair(data: PairIn, request: Request, db: Session = Depends(get_db)):
    """A screen trades the code shown on the Devices screen for its own token."""
    try:
        device, token = service.pair(db, data.code, request.headers.get("user-agent", ""))
    except AdminError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail)
    return {"token": token, "device": _me(device)}


@router.get("/devices/me")
def device_me(device: Device = Depends(current_device)):
    return _me(device)


@router.get("/devices/tickets")
def device_tickets(device: Device = Depends(current_device), db: Session = Depends(get_db)):
    """Open tickets for each track this monitor shows. Calling this also counts as the monitor checking in."""
    jobs = service.device_jobs(device)
    return {"device": _me(device), "tracks": {track: tickets_for_track(db, track) for track in jobs}}


@router.post("/devices/tickets/{order_id}/{track}/bump")
def device_bump(order_id: int, track: str, device: Device = Depends(current_device), db: Session = Depends(get_db)):
    if track not in service.device_jobs(device):
        raise HTTPException(status_code=403, detail="This monitor does not show that track")
    return bump_track(db, order_id, track)


@router.post("/devices/disconnect")
def device_disconnect(device: Device = Depends(current_device), db: Session = Depends(get_db)):
    service.disconnect(db, device)
    return {"disconnected": True}
