"""Registry entry point for the ops module (ARCH-02).

Empty on purpose: the health probes in ``health.py`` are mounted directly by ``aip.main`` so that
disabling modules can never remove them (OPS-04).
"""

from fastapi import APIRouter

router = APIRouter()
