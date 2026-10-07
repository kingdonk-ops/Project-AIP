# apps/sandbox

Hardened, network-less Python worker images for IFC, OCR, PDF signing and image processing (ADR 0003).
They run as one-shot containers launched by Procrastinate jobs and share the `aip` Python codebase.

`Dockerfile` is the hardened base image (STACK-05): Python 3.12 slim, UID 10001, no setuid binaries.
Build it with `docker compose -f infra/docker-compose.yml --profile sandbox build sandbox` and run each
job as `docker run --rm --network none --read-only --tmpfs /tmp --user 10001 --cap-drop ALL aip-sandbox:dev ...`.
The workers arrive with the UPLOADS (e.g. UPLOADS-04 thumbnails/EXIF) and OCR (ADR 0009) tasks.
