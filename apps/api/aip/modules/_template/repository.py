"""Data access for __module__.

Repositories receive the tenant-bound connection from ``with_tenant`` and never create their own
(ADR 0002).
"""
