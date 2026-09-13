"""Public-page fetch borrowed from AiSoul SoftSoul research.

Only public http(s) URLs are allowed. Local/private addresses and unsafe
redirects fail fast. Transport is injectable so crawls stay testable.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
import ipaddress
import re
import socket
from typing import Any, Callable
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


TransportFn = Callable[[str, float, int], dict[str, Any]]


@dataclass
class PageFetchResult:
    url: str
    final_url: str
    available: bool
    title: str = ""
    text: str = ""
    content_type: str = ""
    status_code: int = 0
    fetched_at: str = ""
    word_count: int = 0
    content_sha256: str = ""
    page_count: int = 0
    segments: list[dict[str, Any]] = field(default_factory=list)
    truncated: bool = False
    source_mode: str = "unknown"
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _ReadableHTML(HTMLParser):
    _SKIP = {"script", "style", "noscript", "svg", "canvas", "nav", "footer", "form"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._title_depth = 0
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self._SKIP:
            self._skip_depth += 1
        if tag == "title":
            self._title_depth += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title" and self._title_depth:
            self._title_depth -= 1

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if not value:
            return
        if self._title_depth:
            self.title_parts.append(value)
        if not self._skip_depth and not self._title_depth:
            self.text_parts.append(value)


def assert_public_url(url: str, *, resolve_dns: bool = False) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("only public http/https URLs may be fetched")
    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("local addresses are not allowed")
    addresses: list[str] = []
    try:
        addresses.append(str(ipaddress.ip_address(host)))
    except ValueError:
        if resolve_dns:
            addresses.extend({item[4][0] for item in socket.getaddrinfo(host, parsed.port or 443)})
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError(f"non-public address is not allowed: {address}")


class _SafeRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        target = urljoin(req.full_url, newurl)
        assert_public_url(target, resolve_dns=True)
        return super().redirect_request(req, fp, code, msg, headers, target)


def _http_transport(url: str, timeout: float, max_bytes: int) -> dict[str, Any]:
    assert_public_url(url, resolve_dns=True)
    request = Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,text/plain;q=0.8",
            "User-Agent": "JoyOPC-MarketCrawler/0.3 (+local-opc)",
        },
    )
    with build_opener(_SafeRedirects()).open(request, timeout=timeout) as response:
        final_url = response.geturl()
        assert_public_url(final_url, resolve_dns=True)
        raw = response.read(max_bytes + 1)
        return {
            "final_url": final_url,
            "status_code": int(getattr(response, "status", 200)),
            "content_type": str(response.headers.get("Content-Type") or ""),
            "content": raw[:max_bytes],
            "truncated": len(raw) > max_bytes,
        }


def _decode_html(content: bytes, content_type: str) -> tuple[str, str, list[dict[str, Any]]]:
    charset = "utf-8"
    marker = "charset="
    if marker in content_type.lower():
        charset = content_type.lower().split(marker, 1)[1].split(";", 1)[0].strip(" \"'") or charset
    try:
        decoded = content.decode(charset, errors="replace")
    except LookupError:
        decoded = content.decode("utf-8", errors="replace")
    parser = _ReadableHTML()
    parser.feed(decoded)
    parts = [part for part in parser.text_parts if part]
    segments = [
        {"locator": f"html:p{index}", "kind": "paragraph", "text": part}
        for index, part in enumerate(parts, start=1)
    ]
    return " ".join(parser.title_parts).strip(), "\n".join(parts).strip(), segments


def _decode_pdf(content: bytes) -> tuple[str, str, list[dict[str, Any]]]:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(content))
    title = str((reader.metadata or {}).get("/Title") or "")
    segments = []
    for index, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or "").strip()
        if page_text:
            segments.append({"locator": f"pdf:page:{index}", "kind": "page", "page": index, "text": page_text})
    text = "\n\n".join(segment["text"] for segment in segments)
    return title.strip(), text.strip(), segments


def fetch_page(
    url: str,
    *,
    transport: TransportFn | None = None,
    timeout: float = 20.0,
    max_bytes: int = 3_000_000,
    max_chars: int = 80_000,
    source_mode: str | None = None,
) -> dict[str, Any]:
    mode = source_mode or ("simulation" if transport is not None else "live")
    mode = mode if mode in {"live", "simulation", "mock"} else "unknown"
    try:
        assert_public_url(url, resolve_dns=False)
        payload = (transport or _http_transport)(url, float(timeout), int(max_bytes))
        content = payload.get("content", b"")
        if isinstance(content, str):
            content = content.encode("utf-8")
        if not isinstance(content, bytes):
            raise TypeError("page transport content must be bytes or str")
        content_type = str(payload.get("content_type") or "").lower()
        final_url = str(payload.get("final_url") or url)
        assert_public_url(final_url, resolve_dns=False)
        if "pdf" in content_type or final_url.lower().endswith(".pdf") or content.startswith(b"%PDF"):
            title, text, segments = _decode_pdf(content)
            normalized_type = "application/pdf"
        elif "html" in content_type or b"<html" in content[:1000].lower():
            title, text, segments = _decode_html(content, content_type)
            normalized_type = "text/html"
        else:
            title = ""
            text = content.decode("utf-8", errors="replace").strip()
            normalized_type = content_type.split(";", 1)[0] or "text/plain"
            parts = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
            segments = [
                {"locator": f"text:p{index}", "kind": "paragraph", "text": part}
                for index, part in enumerate(parts, start=1)
            ]
        text = "\n".join(line for line in (" ".join(part.split()) for part in text.splitlines()) if line)
        truncated = bool(payload.get("truncated")) or len(text) > max_chars
        text = text[:max_chars]
        bounded_segments = []
        consumed = 0
        for segment in segments:
            segment_text = str(segment.get("text") or "").strip()
            if not segment_text or consumed >= max_chars:
                continue
            segment_text = segment_text[: max_chars - consumed]
            bounded_segments.append({**segment, "text": segment_text})
            consumed += len(segment_text)
        result = PageFetchResult(
            url=url,
            final_url=final_url,
            available=bool(text),
            title=title,
            text=text,
            content_type=normalized_type,
            status_code=int(payload.get("status_code") or 200),
            fetched_at=datetime.now(timezone.utc).isoformat(),
            word_count=len(text.split()),
            content_sha256=sha256(content).hexdigest(),
            page_count=len(segments) if normalized_type == "application/pdf" else 1,
            segments=bounded_segments,
            truncated=truncated,
            source_mode=mode,
            error="" if text else "页面没有可提取正文",
        )
    except Exception as exc:
        result = PageFetchResult(
            url=url,
            final_url=url,
            available=False,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            source_mode=mode,
            error=f"{type(exc).__name__}: {exc}",
        )
    return result.to_dict()
