from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import DEVICE_KINDS, PRINTER_JOBS

HOST_PATTERN = r"^[A-Za-z0-9]([A-Za-z0-9.\-]{0,251}[A-Za-z0-9])?$"  # an IP address or a hostname


def _known_jobs(value):
    unknown = [job for job in value if job not in PRINTER_JOBS]
    if unknown:
        raise ValueError(f"unknown job(s): {', '.join(unknown)}")
    return list(dict.fromkeys(value))  # drop repeats, keep order


class DeviceIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    kind: str
    jobs: List[str] = Field(..., min_length=1)
    host: Optional[str] = Field(None, pattern=HOST_PATTERN)
    port: Optional[int] = Field(None, ge=1, le=65535)

    @field_validator("kind")
    @classmethod
    def known_kind(cls, value):
        if value not in DEVICE_KINDS:
            raise ValueError(f"kind must be one of {', '.join(DEVICE_KINDS)}")
        return value

    @field_validator("jobs")
    @classmethod
    def known_jobs(cls, value):
        return _known_jobs(value)


class DeviceEdit(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=60)
    jobs: Optional[List[str]] = Field(None, min_length=1)
    host: Optional[str] = Field(None, pattern=HOST_PATTERN)
    port: Optional[int] = Field(None, ge=1, le=65535)

    @field_validator("jobs")
    @classmethod
    def known_jobs(cls, value):
        return _known_jobs(value) if value is not None else value


class PairIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=12)
