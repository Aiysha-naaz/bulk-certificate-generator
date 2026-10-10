import re
from datetime import date
from pydantic import BaseModel, Field, field_validator

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Recipient(BaseModel):
    """Validated per recipient so one bad row never rejects the whole request."""
    name: str = Field(min_length=1, max_length=100)
    email: str
    course: str | None = Field(default=None, max_length=150)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        if not EMAIL_RE.match(v):
            raise ValueError("invalid email")
        return v.lower()


class JobCreate(BaseModel):
    event_name: str = Field(min_length=1, max_length=200)
    issued_date: date | None = None
    # Raw dicts on purpose, validated one by one in the service.
    recipients: list[dict] = Field(min_length=1, max_length=5000)