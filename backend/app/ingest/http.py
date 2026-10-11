"""Polite HTTP: rate limit, on-disk cache, retries with backoff."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import httpx

from ..config import settings

_last = 0.0


def client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": settings().user_agent},
        timeout=30,
        follow_redirects=True,
    )


def get_cached(
    url: str,
    *,
    method: str = "GET",
    data: dict | None = None,
    max_age_s: float | None = None,
    delay: float | None = None,
) -> str:
    """Fetch with a disk cache keyed on method+url+data. max_age_s=None caches forever."""
    global _last
    key = hashlib.sha256(f"{method} {url} {sorted((data or {}).items())}".encode()).hexdigest()
    path: Path = settings().cache_dir / f"{key}.html"
    if path.exists() and (max_age_s is None or time.time() - path.stat().st_mtime < max_age_s):
        return path.read_text(encoding="utf-8")

    wait = (settings().http_delay_s if delay is None else delay) - (time.time() - _last)
    if wait > 0:
        time.sleep(wait)
    backoff = 2.0
    with client() as c:
        for attempt in range(4):
            try:
                r = c.request(method, url, data=data)
                _last = time.time()
                if r.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError("retryable", request=r.request, response=r)
                r.raise_for_status()
                path.write_text(r.text, encoding="utf-8")
                return r.text
            except (httpx.TransportError, httpx.HTTPStatusError):
                if attempt == 3:
                    raise
                time.sleep(backoff)
                backoff *= 2
    raise RuntimeError("unreachable")
