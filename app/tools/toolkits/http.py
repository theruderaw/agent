# app/tools/toolkits/http.py

import asyncio
import json
from typing import Any, TypedDict
from urllib.parse import urljoin, urlparse

import requests

from app import skills
from app.tools.base import Toolkit

_DEFAULT_TIMEOUT_SECONDS = 10
_MAX_BODY_BYTES = 5 * 1024 * 1024  # 5 MB response cap
_ALLOWED_SCHEMES = ("http", "https")
_MAX_REDIRECTS = 5


def _host_matches(host: str, pattern: str) -> bool:
    """Match a hostname against an allowlist entry.

    "example.com" matches only that exact host. "*.example.com" matches
    example.com itself and any subdomain of it.
    """
    host = host.lower()
    pattern = pattern.lower()

    if pattern.startswith("*."):
        suffix = pattern[2:]
        return host == suffix or host.endswith("." + suffix)

    return host == pattern


class HttpResponse(TypedDict):
    status: int
    headers: dict[str, str]
    body: Any
    url: str


class HttpTools(Toolkit):
    namespace = "http"
    skills = "research-skills"

    def __init__(
        self,
        allowed_hosts: list[str] | None = None,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ):
        """allowed_hosts is a list of exact hostnames or "*.domain" wildcard
        patterns this toolkit is permitted to contact. Defaults to an empty
        list, meaning every request is rejected until hosts are configured -
        this is a default-deny allowlist, not a blocklist of "bad" hosts.
        """
        self.allowed_hosts = allowed_hosts or []
        self.timeout = timeout
        self.session = requests.Session()

    def _validate_url(self, url: str) -> str:
        """Reject non-http(s) schemes and any host not on the configured allowlist."""
        parsed = urlparse(url)

        if parsed.scheme not in _ALLOWED_SCHEMES:
            raise ValueError(f"unsupported URL scheme: {parsed.scheme!r}")

        if not parsed.hostname:
            raise ValueError("URL must include a hostname")

        if not any(_host_matches(parsed.hostname, pattern) for pattern in self.allowed_hosts):
            raise ValueError(
                f"host not in allowlist: {parsed.hostname}. "
                f"Add it to allowed_hosts to permit this toolkit to contact it."
            )

        return url

    def _do_request(
        self,
        method: str,
        url: str,
        headers: dict | None = None,
        body: dict | None = None,
        timeout: float | None = None,
    ) -> HttpResponse:
        """Send an HTTP request; always called via asyncio.to_thread since requests is blocking."""
        validated_url = self._validate_url(url)
        effective_timeout = self.timeout if timeout is None else timeout

        # requests follows redirects automatically by default, which would
        # bypass _validate_url on the redirect target. We disable that and
        # follow redirects manually, re-validating each hop.
        response = self.session.request(
            method,
            validated_url,
            headers=headers,
            json=body,
            timeout=effective_timeout,
            allow_redirects=False,
            stream=True,
        )

        redirects_followed = 0
        while response.is_redirect and redirects_followed < _MAX_REDIRECTS:
            location = response.headers.get("Location")
            if not location:
                break

            response.close()
            next_url = self._validate_url(urljoin(response.url, location))

            response = self.session.request(
                method,
                next_url,
                headers=headers,
                json=body,
                timeout=effective_timeout,
                allow_redirects=False,
                stream=True,
            )
            redirects_followed += 1

        raw = response.raw.read(_MAX_BODY_BYTES + 1, decode_content=True)
        response.close()

        if len(raw) > _MAX_BODY_BYTES:
            raise ValueError("response body exceeds max allowed size")

        text = raw.decode(response.encoding or "utf-8", errors="replace") if raw else ""

        body_out: Any
        if not text:
            body_out = None
        else:
            try:
                body_out = json.loads(text)
            except json.JSONDecodeError:
                body_out = text

        return {
            "status": response.status_code,
            "headers": dict(response.headers),
            "body": body_out,
            "url": response.url,
        }

    async def get(
        self, url: str, headers: dict | None = None, timeout: float | None = None
    ) -> HttpResponse:
        """Send an HTTP GET request to the given URL."""
        return await asyncio.to_thread(self._do_request, "GET", url, headers, None, timeout)

    async def post(
        self,
        url: str,
        body: dict | None = None,
        headers: dict | None = None,
        timeout: float | None = None,
    ) -> HttpResponse:
        """Send an HTTP POST request with an optional JSON body."""
        return await asyncio.to_thread(self._do_request, "POST", url, headers, body, timeout)

    async def put(
        self,
        url: str,
        body: dict | None = None,
        headers: dict | None = None,
        timeout: float | None = None,
    ) -> HttpResponse:
        """Send an HTTP PUT request with an optional JSON body."""
        return await asyncio.to_thread(self._do_request, "PUT", url, headers, body, timeout)

    async def patch(
        self,
        url: str,
        body: dict | None = None,
        headers: dict | None = None,
        timeout: float | None = None,
    ) -> HttpResponse:
        """Send an HTTP PATCH request with an optional JSON body."""
        return await asyncio.to_thread(self._do_request, "PATCH", url, headers, body, timeout)

    async def delete(
        self, url: str, headers: dict | None = None, timeout: float | None = None
    ) -> HttpResponse:
        """Send an HTTP DELETE request to the given URL."""
        return await asyncio.to_thread(self._do_request, "DELETE", url, headers, None, timeout)

    async def head(
        self, url: str, headers: dict | None = None, timeout: float | None = None
    ) -> HttpResponse:
        """Send an HTTP HEAD request and return the response headers."""
        return await asyncio.to_thread(self._do_request, "HEAD", url, headers, None, timeout)

    async def options(
        self, url: str, headers: dict | None = None, timeout: float | None = None
    ) -> HttpResponse:
        """Send an HTTP OPTIONS request to discover allowed methods on the given URL."""
        return await asyncio.to_thread(self._do_request, "OPTIONS", url, headers, None, timeout)

    async def ping(self, url: str, timeout: float | None = None) -> bool:
        """Check whether a URL is reachable, returning False for both network failures and SSRF-blocked URLs."""
        try:
            await asyncio.to_thread(self._do_request, "HEAD", url, None, None, timeout)
            return True
        except Exception:
            return False


if __name__ == "__main__":
    import asyncio as _asyncio

    async def _main() -> None:
        tools = HttpTools(allowed_hosts=["example.com"])

        print("get (allowed host):", await tools.get("https://example.com"))
        print("ping (allowed host):", await tools.ping("https://example.com"))
        print("ping (not on allowlist):", await tools.ping("https://not-allowed.example.org"))
        print("ping (localhost, not on allowlist):", await tools.ping("http://localhost:8000/"))

    _asyncio.run(_main())