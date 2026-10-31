"""``PdfRenderer`` on Gotenberg 8 (Chromium) via httpx (STACK-02).

``POST {base_url}/forms/chromium/convert/html`` with the page as ``index.html`` plus optional
assets. The whole request is bounded by ``timeout_s`` and the response body by ``max_bytes``.

REPORTS-02: with ``page`` the request also carries Gotenberg's paper form fields (``paperWidth``,
``paperHeight``, the four margins as ``"<n>mm"``, ``landscape``, ``printBackground=true`` and
``preferCssPageSize=false``); without it the request is exactly the STACK-02 one (files only).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

import httpx

from aip.platform.capabilities.errors import RenderError, RenderTimeoutError, RenderTooLargeError
from aip.platform.capabilities.protocols import PageOptions
from aip.platform.capabilities.settings import DEFAULT_RENDER_MAX_BYTES, DEFAULT_RENDER_TIMEOUT_S

CONVERT_HTML_PATH = "/forms/chromium/convert/html"


def _check_asset_name(name: str) -> None:
    if (
        not name
        or name in (".", "..", "index.html")
        or "/" in name
        or "\\" in name
        or "\x00" in name
    ):
        raise ValueError(f"invalid asset file name: {name!r}")


def _mm(value: float) -> str:
    number = float(value)
    if number < 0:
        raise ValueError("page dimensions must not be negative")
    return f"{int(number)}mm" if number.is_integer() else f"{number!r}mm"


def page_fields(page: PageOptions) -> dict[str, str]:
    """The Gotenberg form fields for ``page``."""
    return {
        "paperWidth": _mm(page.paper_width_mm),
        "paperHeight": _mm(page.paper_height_mm),
        "marginTop": _mm(page.margin_top_mm),
        "marginRight": _mm(page.margin_right_mm),
        "marginBottom": _mm(page.margin_bottom_mm),
        "marginLeft": _mm(page.margin_left_mm),
        "landscape": "true" if page.landscape else "false",
        "printBackground": "true",
        "preferCssPageSize": "false",
    }


class GotenbergPdfRenderer:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_s: float = DEFAULT_RENDER_TIMEOUT_S,
        max_bytes: int = DEFAULT_RENDER_MAX_BYTES,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if timeout_s <= 0 or max_bytes <= 0:
            raise ValueError("timeout_s and max_bytes must be positive")
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.max_bytes = max_bytes
        self._transport = transport

    async def render_html(
        self,
        html: str,
        *,
        assets: Mapping[str, bytes] | None = None,
        page: PageOptions | None = None,
    ) -> bytes:
        files: list[tuple[str, tuple[str, bytes, str]]] = [
            ("files", ("index.html", html.encode("utf-8"), "text/html"))
        ]
        for name, content in (assets or {}).items():
            _check_asset_name(name)
            files.append(("files", (name, content, "application/octet-stream")))
        fields = page_fields(page) if page is not None else None
        try:
            async with asyncio.timeout(self.timeout_s):
                return await self._post(files, fields)
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise RenderTimeoutError(f"Gotenberg did not answer within {self.timeout_s}s") from exc
        except httpx.HTTPError as exc:
            raise RenderError(f"Gotenberg request failed: {exc}") from exc

    async def _post(
        self,
        files: list[tuple[str, tuple[str, bytes, str]]],
        fields: dict[str, str] | None,
    ) -> bytes:
        async with (
            httpx.AsyncClient(
                base_url=self.base_url, timeout=self.timeout_s, transport=self._transport
            ) as client,
            client.stream("POST", CONVERT_HTML_PATH, files=files, data=fields) as response,
        ):
            if response.status_code != 200:
                detail = (await response.aread())[:500].decode("utf-8", "replace")
                raise RenderError(f"Gotenberg returned HTTP {response.status_code}: {detail}")
            declared = response.headers.get("content-length")
            if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
                raise self._too_large()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > self.max_bytes:
                    raise self._too_large()
            return bytes(body)

    def _too_large(self) -> RenderTooLargeError:
        return RenderTooLargeError(f"rendered PDF exceeds the {self.max_bytes}-byte cap")
