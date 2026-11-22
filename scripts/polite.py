"""Polite HTTP client: one request per second, sequential, identifying UA, bounded retries.

Every network call in this repo goes through `get()`. Nothing else may open a socket.
"""
import time

import requests

USER_AGENT = "ombudsman-data-research/0.1 (+contact: tim@hellotim.co.za)"
MIN_INTERVAL = 1.05  # seconds between request starts (rule: <= 1 req/s)
MAX_RETRIES = 2      # retries after the first attempt
BACKOFF = (3.0, 8.0)  # seconds before retry 1, retry 2
TIMEOUT = (20, 180)   # connect, read

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})
_last_start = 0.0
request_count = 0


def _throttle():
    global _last_start
    wait = _last_start + MIN_INTERVAL - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_start = time.monotonic()


class FetchError(Exception):
    def __init__(self, url, reason, attempts):
        super().__init__(reason)
        self.url = url
        self.reason = reason
        self.attempts = attempts


def get(url, *, accept_status=(200,)):
    """GET with throttle + retry. Returns the Response (body fully read). Raises FetchError."""
    global request_count
    last_reason = None
    for attempt in range(MAX_RETRIES + 1):
        if attempt:
            time.sleep(BACKOFF[attempt - 1])
        _throttle()
        request_count += 1
        try:
            r = _session.get(url, timeout=TIMEOUT, allow_redirects=True)
            _ = r.content  # read fully inside the try
        except requests.RequestException as e:
            last_reason = f"{type(e).__name__}: {str(e)[:200]}"
            continue
        if r.status_code in accept_status:
            return r
        last_reason = f"HTTP {r.status_code}"
        if r.status_code in (404, 410):
            break  # permanent; don't waste retries
    raise FetchError(url, last_reason, attempt + 1)
