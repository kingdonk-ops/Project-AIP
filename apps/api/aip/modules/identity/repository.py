"""Data access for identity.

Repositories receive the tenant-bound connection from ``with_tenant`` and never create their own
(ADR 0002).
"""
