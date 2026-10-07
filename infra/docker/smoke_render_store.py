"""STACK-02 e2e on the compose stack, run inside the ``api`` container (CI ``compose`` job).

    docker compose -f infra/docker-compose.yml exec -T api \
        python - < infra/docker/smoke_render_store.py

Renders the fixture report through ``get_pdf_renderer()`` (Gotenberg), stores it through
``get_object_store()`` (RustFS), downloads it through a presigned GET and checks the bytes. It uses
the API container's own environment, so it proves the stack's wiring, not just the adapters. The
text check (``FX-0001`` in the PDF) runs from the host with pypdf, in the same CI job.
"""

from __future__ import annotations

import asyncio
import sys
import uuid

import httpx

from aip.platform.capabilities import get_object_store, get_pdf_renderer, tenant_key

TENANT = uuid.UUID("00000000-0000-4000-8000-00000000000a")  # kaefer-demo fixture tenant
HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Smoke</title></head>
<body><h1>Compose smoke report</h1><p>Reference FX-0001</p></body></html>"""


async def main() -> int:
    pdf = await get_pdf_renderer().render_html(HTML)
    assert pdf.startswith(b"%PDF"), "renderer did not return a PDF"
    store = get_object_store()
    key = tenant_key(TENANT, "smoke", f"{uuid.uuid4().hex}.pdf")
    await store.put(key, pdf, content_type="application/pdf")
    presigned = await store.presign_get(key, expires_s=60)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(presigned.url, headers=presigned.headers)
    assert response.status_code == 200, f"presigned GET returned {response.status_code}"
    assert response.content == pdf, "downloaded bytes differ from the stored PDF"
    await store.delete(key)
    print(f"render-store-download ok: {len(pdf)} bytes via {key}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
