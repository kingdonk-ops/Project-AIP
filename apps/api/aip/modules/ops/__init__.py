"""Operations module: health probes (OPS-04, mounted directly by ``aip.main``) and job records
(OPS-01). Only the published interface (``api``) is exported."""

from . import api

__all__ = ["api"]
