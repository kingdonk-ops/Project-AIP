"""Universal record links (ARCH-08): relate any record to any other record and to an asset.

::

    async with with_tenant(get_context()) as conn:
        await LinkService().link(conn, RecordRef("defect", d), RecordRef("ncr", n), "follows")
        chain = await LinkService().traverse(conn, RecordRef("defect", d))
"""

from aip.platform.links.service import MAX_DEPTH, LinkService, RecordRef

__all__ = ["MAX_DEPTH", "LinkService", "RecordRef"]
