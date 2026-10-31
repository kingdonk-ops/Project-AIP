"""Gotenberg PdfRenderer adapter (STACK-02, REPORTS-02).

Integration tests run against a real Gotenberg started with the compose sandbox flags
(``conftest.GOTENBERG_COMMAND``: no JavaScript, Chromium may load only the request's own files). A
few edge cases that a real server cannot produce on demand (a body without Content-Length, a 5xx)
and the exact multipart fields use ``httpx.MockTransport``.
"""

from __future__ import annotations

import email.parser
import email.policy
import io
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from pypdf import PdfReader

from aip.platform.capabilities import (
    PageOptions,
    RenderError,
    RenderTimeoutError,
    RenderTooLargeError,
    get_object_store,
    get_pdf_renderer,
    tenant_key,
)
from aip.platform.capabilities.adapters.gotenberg import GotenbergPdfRenderer

from .conftest import S3Backend

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
T1 = uuid.UUID("11111111-1111-4111-8111-111111111111")


# --- against a real Gotenberg -------------------------------------------------------------------


async def test_render_html_returns_small_pdf(gotenberg_url: str) -> None:
    renderer = GotenbergPdfRenderer(gotenberg_url)
    pdf = await renderer.render_html("<h1>Hi</h1>")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) < 1024 * 1024


async def test_render_html_with_assets(gotenberg_url: str) -> None:
    renderer = GotenbergPdfRenderer(gotenberg_url)
    html = '<link rel="stylesheet" href="style.css"><h1 class="t">Styled</h1>'
    pdf = await renderer.render_html(html, assets={"style.css": b".t { color: red; }"})
    assert pdf.startswith(b"%PDF")
    assert "Styled" in PdfReader(io.BytesIO(pdf)).pages[0].extract_text()


async def test_tiny_timeout_raises_render_timeout(gotenberg_url: str) -> None:
    renderer = GotenbergPdfRenderer(gotenberg_url, timeout_s=0.001)
    with pytest.raises(RenderTimeoutError):
        await renderer.render_html("<h1>Hi</h1>")


async def test_size_cap_raises_render_too_large(gotenberg_url: str) -> None:
    renderer = GotenbergPdfRenderer(gotenberg_url, max_bytes=100)
    with pytest.raises(RenderTooLargeError):
        await renderer.render_html("<h1>Hi</h1>")


# --- asset names and HTTP edge cases ------------------------------------------------------------


@pytest.mark.parametrize("name", ["index.html", "../x.css", "a/b.css", "", ".."])
async def test_rejects_unsafe_asset_names(name: str) -> None:
    renderer = GotenbergPdfRenderer("http://gotenberg.invalid")
    with pytest.raises(ValueError):
        await renderer.render_html("<p>x</p>", assets={name: b"x"})


def _renderer(
    transport: httpx.MockTransport, max_bytes: int = 25 * 1024 * 1024
) -> GotenbergPdfRenderer:
    return GotenbergPdfRenderer("http://gotenberg.test", max_bytes=max_bytes, transport=transport)


async def test_posts_index_html_to_chromium_route() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"%PDF-1.4 ok")

    pdf = await _renderer(httpx.MockTransport(handler)).render_html("<h1>Hi</h1>")
    assert pdf == b"%PDF-1.4 ok"
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/forms/chromium/convert/html"
    body = seen[0].read()
    assert b'filename="index.html"' in body
    assert b"<h1>Hi</h1>" in body


async def test_streamed_body_over_cap_without_content_length() -> None:
    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(10):
            yield b"x" * 64

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=chunks())

    with pytest.raises(RenderTooLargeError):
        await _renderer(httpx.MockTransport(handler), max_bytes=200).render_html("<p>x</p>")


async def test_server_error_raises_render_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"chromium crashed")

    with pytest.raises(RenderError) as excinfo:
        await _renderer(httpx.MockTransport(handler)).render_html("<p>x</p>")
    assert not isinstance(excinfo.value, (RenderTimeoutError, RenderTooLargeError))
    assert "503" in str(excinfo.value)


# --- render, store, download (the e2e journey) --------------------------------------------------


async def test_render_store_and_download_report(
    gotenberg_url: str, rustfs: S3Backend, clean_capability_env: pytest.MonkeyPatch
) -> None:
    """Fixture report -> get_pdf_renderer() -> get_object_store() -> presigned GET -> text."""
    bucket = rustfs.create_bucket()
    for name, value in rustfs.env(bucket).items():
        clean_capability_env.setenv(name, value)
    clean_capability_env.setenv("PDF_RENDERER", "gotenberg")
    clean_capability_env.setenv("GOTENBERG_URL", gotenberg_url)

    html = (FIXTURES / "report.html").read_text(encoding="utf-8")
    pdf = await get_pdf_renderer().render_html(html)
    store = get_object_store()
    key = tenant_key(T1, "reports", f"{uuid.uuid4().hex}.pdf")
    await store.put(key, pdf, content_type="application/pdf")
    url = await store.presign_get(key, expires_s=60)
    async with httpx.AsyncClient() as client:
        response = await client.get(url.url, headers=url.headers)
    assert response.status_code == 200
    downloaded = response.content
    assert downloaded.startswith(b"%PDF")
    text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(downloaded)).pages)
    assert "FX-0001" in text


# --- REPORTS-02: page options -------------------------------------------------------------------

_PAGE_FIELDS = (
    "paperWidth",
    "paperHeight",
    "marginTop",
    "marginRight",
    "marginBottom",
    "marginLeft",
    "landscape",
    "printBackground",
    "preferCssPageSize",
)


def _form_fields(request: httpx.Request) -> dict[str, list[str]]:
    """The multipart body as ``{name: [value or filename, ...]}``."""
    raw = f"Content-Type: {request.headers['content-type']}\r\n\r\n".encode() + request.read()
    message = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(raw)
    fields: dict[str, list[str]] = {}
    for part in message.iter_parts():
        name = str(part.get_param("name", header="content-disposition"))
        filename = part.get_filename()
        value = filename if filename else part.get_content()
        fields.setdefault(name, []).append(str(value))
    return fields


async def _capture(page: PageOptions | None) -> dict[str, list[str]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"%PDF-1.4 ok")

    await _renderer(httpx.MockTransport(handler)).render_html("<p>x</p>", page=page)
    return _form_fields(seen[0])


async def test_page_options_become_gotenberg_form_fields() -> None:
    fields = await _capture(PageOptions(210, 297, True, 12, 10, 12, 10))
    assert fields["files"] == ["index.html"]
    assert {name: fields[name] for name in _PAGE_FIELDS} == {
        "paperWidth": ["210mm"],
        "paperHeight": ["297mm"],
        "marginTop": ["12mm"],
        "marginRight": ["10mm"],
        "marginBottom": ["12mm"],
        "marginLeft": ["10mm"],
        "landscape": ["true"],
        "printBackground": ["true"],
        "preferCssPageSize": ["false"],
    }


async def test_fractional_margins_and_portrait() -> None:
    fields = await _capture(PageOptions(297, 420, False, 12.5, 0, 0, 0))
    assert (fields["paperWidth"], fields["marginTop"], fields["landscape"]) == (
        ["297mm"],
        ["12.5mm"],
        ["false"],
    )


async def test_without_page_options_only_files_are_sent() -> None:
    assert await _capture(None) == {"files": ["index.html"]}


async def test_a_real_landscape_page(gotenberg_url: str) -> None:
    renderer = GotenbergPdfRenderer(gotenberg_url)
    pdf = await renderer.render_html(
        "<p>wide</p>", page=PageOptions(210, 297, True, 10, 10, 10, 10)
    )
    box = PdfReader(io.BytesIO(pdf)).pages[0].mediabox
    assert abs(float(box.width) - 842) <= 1 and abs(float(box.height) - 595) <= 1


# --- REPORTS-02: the sandboxed Chromium (compose flags) -----------------------------------------


def _text(pdf: bytes) -> str:
    return "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


async def test_chromium_runs_no_javascript(gotenberg_url: str) -> None:
    html = "<p id=\"x\">JS OFF</p><script>document.getElementById('x').textContent='JS ON'</script>"
    text = _text(await GotenbergPdfRenderer(gotenberg_url).render_html(html))
    assert "JS OFF" in text
    assert "JS ON" not in text


async def test_chromium_cannot_read_local_files(gotenberg_url: str) -> None:
    html = '<p>frame</p><iframe src="file:///etc/passwd" width="600" height="400"></iframe>'
    text = _text(await GotenbergPdfRenderer(gotenberg_url).render_html(html))
    assert "frame" in text
    assert "root:" not in text


async def test_chromium_cannot_reach_the_network(gotenberg_url: str) -> None:
    html = (
        '<p>frame</p><iframe src="http://127.0.0.1:3000/health" width="600" height="400"></iframe>'
    )
    text = _text(await GotenbergPdfRenderer(gotenberg_url).render_html(html))
    assert "frame" in text
    assert "status" not in text
