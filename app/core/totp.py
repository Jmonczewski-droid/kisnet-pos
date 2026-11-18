"""Time-based one-time passwords (RFC 6238), the open standard every authenticator app uses.

Works with any authenticator app, including open-source ones such as Aegis, 2FAS and Ente Auth.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from typing import Optional
from urllib.parse import quote

PERIOD_SECONDS = 30
DIGITS = 6
ISSUER = "KISnet-POS"


def new_secret() -> str:
    """A random 160-bit key in the base32 form authenticator apps expect."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def current_step(at: Optional[float] = None) -> int:
    return int((time.time() if at is None else at) // PERIOD_SECONDS)


def code_for_step(secret: str, step: int) -> str:
    key = base64.b32decode(secret, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10 ** DIGITS).zfill(DIGITS)


def matching_step(secret: str, code: str, at: Optional[float] = None, after_step: Optional[int] = None) -> Optional[int]:
    """The time step a code belongs to, or None if it is wrong.

    Accepts the current code and the ones just before and after it (clocks are never exactly in step).
    Steps at or before `after_step` are refused, so a code cannot be used twice.
    """
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(code) != DIGITS:
        return None
    now = current_step(at)
    for step in (now, now - 1, now + 1):
        if after_step is not None and step <= after_step:
            continue
        if hmac.compare_digest(code_for_step(secret, step), code):
            return step
    return None


def provisioning_uri(secret: str, account: str) -> str:
    """The otpauth:// link an authenticator app reads from a QR code."""
    label = quote(f"{ISSUER}:{account}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(ISSUER)}&digits={DIGITS}&period={PERIOD_SECONDS}"


def qr_svg(uri: str) -> str:
    """The link as a QR code (inline SVG)."""
    import io
    import segno
    out = io.BytesIO()
    segno.make(uri, error="m").save(out, kind="svg", scale=5, border=2, xmldecl=False, svgns=True, nl=False)
    return out.getvalue().decode("utf-8")
