# ADR 0009: No licensed or copyleft components; OCR with Tesseract, Textract optional

- **Status:** accepted (owner, 2026-10-07: "I don't want to be licensing it, use open source or aws")
- **Date:** 2026-10-07
- **Affects:** STACK-04 (licence policy), apps/sandbox (OCR, PDF), documents, ingestion, report_engine

## Context

OCRmyPDF needs Ghostscript, which is AGPL. Commercial Ghostscript needs a paid licence. The owner wants
neither, so we use only permissively licensed open source or AWS services.

## Decision

- **Licence policy (enforced by STACK-04 in CI):**
  - **Allowed:** MIT, BSD, Apache-2.0, ISC, PSF, MPL-2.0.
  - **Review:** LGPL. It's acceptable only when the library is dynamically used and unmodified, e.g. IfcOpenShell.
  - **Denied:** GPL, AGPL, SSPL and anything else that needs a paid licence.
- **OCR:** runs in the `apps/sandbox/ocr` image.
  - **Tesseract** (Apache-2.0) recognises the text.
  - **pypdfium2** (Apache-2.0/BSD) renders PDF pages to images.
  - Tesseract's own `pdf` output produces the text layer, and **pikepdf** (MPL-2.0) merges it back into the original PDF.
  - **No OCRmyPDF, no Ghostscript, no PyMuPDF** (AGPL).
- **Hard scans:** handwriting, poor-quality photos and tables use **AWS Textract** in ap-southeast-2.
  - It's off by default per tenant, routed through the AI/data-flow register, and pay-per-use with no licence.
  - On Coolify/dev the Textract adapter is stubbed.
- **Other picks that already comply:** Gotenberg (Apache-2.0), pyHanko (MIT) for PDF signing, PDF.js (Apache-2.0),
  Konva (MIT), Keycloak (Apache-2.0), Procrastinate (MIT), Postgres (PostgreSQL licence).

## Consequences

Tesseract's accuracy on poor scans is below Textract's, so the Textract fallback is the quality valve.
Any new dependency outside the allow-list needs an ADR.
