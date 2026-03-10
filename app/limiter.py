"""
Rate Limiter — Shared slowapi Limiter instance.

Extracted into its own module to avoid circular imports
(main.py imports routers, routers need the limiter).

Usage in routers:
    from app.limiter import limiter

    @router.get("/endpoint")
    @limiter.limit("10/minute")
    def my_endpoint(request: Request):
        ...
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# In-memory rate limiting per client IP.
# Limits are applied per-endpoint via @limiter.limit() decorators.
limiter = Limiter(key_func=get_remote_address)
