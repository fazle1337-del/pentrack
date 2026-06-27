"""Shared rate limiter (issue #6).

In-process fixed-window limiter (slowapi/limits, memory storage) — no external
store, so it works the same on single-instance Umbrel and Azure ACR. Defined in
its own module so both the route decorator (routers/auth.py) and app wiring
(main.py) import the same Limiter instance.
"""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

settings = get_settings()


def client_ip(request: Request) -> str:
    """Real client IP for keying. Requests arrive via nginx (and an outer HTTPS
    proxy), so request.client.host is a proxy address; prefer the left-most
    X-Forwarded-For entry, which is the original client."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(
    key_func=client_ip,
    enabled=settings.login_rate_limit_enabled,
)
