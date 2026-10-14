"""Monthly partition names for append-only tables (DATABASE-05).

Append-only evidence tables (``db/templates/append_only_table.sql.tpl``) are range-partitioned by
month into ``<table>_YYYY_MM`` plus ``<table>_default``. The SQL function
``aip_ensure_partitions`` creates the partitions; the ``ensure_partitions`` job
(``aip.platform.db.jobs``) calls it daily and uses these helpers to check that nothing is missing.

Months are UTC calendar months (ADR 0025). Standard library only, like the rest of the package
the migrator image ships.
"""

from __future__ import annotations

from collections.abc import Set
from datetime import date

__all__ = ["missing_partitions", "month_start", "partition_name"]


def month_start(day: date, months: int = 0) -> date:
    """The first day of the month ``months`` after the month of ``day``."""
    index = day.year * 12 + (day.month - 1) + months
    return date(index // 12, index % 12 + 1, 1)


def partition_name(table: str, day: date) -> str:
    """``audit_log`` and 2025-07-15 give ``audit_log_2025_07``."""
    return f"{table}_{day.year:04d}_{day.month:02d}"


def missing_partitions(
    existing: Set[str], today: date, months_ahead: int, *, table: str
) -> list[str]:
    """Partitions of ``table`` from this month to ``months_ahead`` months on that do not exist.

    Returned in month order. ``existing`` may hold any relation names; other tables' are ignored.
    """
    if months_ahead < 0:
        raise ValueError(f"months_ahead must not be negative, got {months_ahead}")
    wanted = (partition_name(table, month_start(today, n)) for n in range(months_ahead + 1))
    return [name for name in wanted if name not in existing]
