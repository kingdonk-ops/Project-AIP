# apps/sandbox

Hardened, network-less Python worker images for IFC, OCR, PDF signing and image processing (ADR 0003).
They run as one-shot containers launched by Procrastinate jobs and share the `aip` Python codebase.

Placeholder created by ARCH-01. The base image arrives with STACK-05; the workers arrive with the
UPLOADS (e.g. UPLOADS-04 thumbnails/EXIF) and OCR (ADR 0009) tasks.
