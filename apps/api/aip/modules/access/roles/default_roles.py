"""The 11 default tenant roles, as data from ``docs/blueprint/05-access-matrix.md`` (ACCESS-02).

``MATRIX`` maps a module id to the level each tenant role has on it, in ``ROLE_CODES`` order.
Super Admin is the operator realm (ADR 0017) and API Client is IDENTITY-06 scopes, so neither is
here. ``default_permissions`` expands each level over the permission catalogue:

- a permission's verb is the last segment of its code (``project.view`` -> ``view``);
- levels are cumulative: view gives read; create adds create; edit adds update, delete and move;
  approve adds approve, sign and invite; admin adds manage and export (``LEVEL_VERBS``; ``move``
  and ``invite`` are the ACCESS-07 amendment to ADR 0027);
- a verb no level names is granted only at ``admin`` (fail closed), and a matrix module with no
  catalogue entries is skipped with a log line;
- ``platform.*`` codes (operator-only, ADR 0029) are never granted to a tenant role;
- Client Reviewer is read-only plus sign-off (owner decision 2026-10-10, see the matrix note), so
  for ``SIGN_OFF_ONLY_ROLES`` the ``approve`` level adds only ``SIGN_OFF_VERBS`` (approve and
  sign, not invite) on top of view.

Display names are the term keys ``access.role.<code>.name``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from typing import Final, Literal

__all__ = [
    "EXTERNAL_ONLY_PREFIXES",
    "LEVELS",
    "LEVEL_VERBS",
    "MATRIX",
    "OPERATOR_ONLY_PREFIX",
    "ROLE_CODES",
    "SIGN_OFF_ONLY_ROLES",
    "SIGN_OFF_VERBS",
    "Level",
    "default_permissions",
    "expand_level",
    "level_of_verb",
    "never_role_held",
    "role_name_key",
]

logger = logging.getLogger(__name__)

Level = Literal["none", "view", "create", "edit", "approve", "admin"]
LEVELS: Final[tuple[Level, ...]] = ("none", "view", "create", "edit", "approve", "admin")

# Operator-only permission codes (ADR 0029: the ops module's platform namespace). Tenant roles,
# default or custom, can never hold them: they act across tenants.
OPERATOR_ONLY_PREFIX: Final = "platform."

# External permission codes (PORTAL-01): given only by portal grants (PortalGrantProvider),
# never by a role, so a staff role can never act as the client (sign off, witness, download).
EXTERNAL_ONLY_PREFIXES: Final = ("portal.record.", "portal.report.")


def never_role_held(code: str) -> bool:
    """A code no tenant role may hold: operator-only or external-only."""
    return code.startswith((OPERATOR_ONLY_PREFIX, *EXTERNAL_ONLY_PREFIXES))


# The verbs each level adds on top of the levels below it.
LEVEL_VERBS: Final[Mapping[Level, frozenset[str]]] = {
    "none": frozenset(),
    "view": frozenset({"read", "view"}),
    "create": frozenset({"create"}),
    "edit": frozenset({"update", "delete", "edit", "archive", "move"}),
    "approve": frozenset({"approve", "sign", "invite"}),
    "admin": frozenset({"manage", "export"}),
}

ROLE_CODES: Final[tuple[str, ...]] = (
    "tenant_admin",
    "project_manager",
    "qaqc_manager",
    "hse_officer",
    "supervisor",
    "inspector",
    "field_worker",
    "document_controller",
    "client_reviewer",
    "subcontractor",
    "auditor",
)

SIGN_OFF_ONLY_ROLES: Final[frozenset[str]] = frozenset({"client_reviewer"})
# What the ``approve`` level gives a sign-off-only role: sign-off, never invite (ADR 0027 §4).
SIGN_OFF_VERBS: Final[frozenset[str]] = frozenset({"approve", "sign"})

# Generated from the access matrix table (columns Tenant Admin .. Auditor); keep in sync with it.
MATRIX: Final[Mapping[str, tuple[Level, ...]]] = {
    "arch": (
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
    ),  # Architecture & module boundaries
    "stack": (
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
    ),  # Tech stack
    "database": (
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
    ),  # Database & schema conventions
    "tenancy": (
        "admin",
        "view",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "view",
    ),  # Tenancy, organisations & data residency
    "security": (
        "view",
        "none",
        "view",
        "view",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "view",
    ),  # Security & compliance programme
    "ops": (
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
    ),  # Operations, hosting & deployment
    "design": (
        "admin",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
    ),  # Design system & app shell
    "testing": (
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
    ),  # Testing & quality engineering
    "terms": (
        "admin",
        "view",
        "view",
        "none",
        "none",
        "none",
        "none",
        "view",
        "none",
        "none",
        "view",
    ),  # Terminology dictionary & localisation
    "ai_gov": (
        "admin",
        "none",
        "view",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "view",
    ),  # AI governance & data controls
    "identity": (
        "admin",
        "view",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "view",
    ),  # Users, sign-in & SSO
    "access": (
        "admin",
        "edit",
        "view",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "view",
    ),  # Roles, permissions & teams
    "projects": (
        "admin",
        "admin",
        "view",
        "view",
        "view",
        "view",
        "view",
        "view",
        "view",
        "view",
        "view",
    ),  # Projects, sites & classification
    "portal": (
        "admin",
        "approve",
        "edit",
        "none",
        "none",
        "none",
        "none",
        "edit",
        "view",
        "view",
        "view",
    ),  # Client & subcontractor portal
    "assets": (
        "admin",
        "edit",
        "edit",
        "view",
        "edit",
        "create",
        "view",
        "view",
        "view",
        "view",
        "view",
    ),  # Asset hierarchy & registers
    "item_types": (
        "admin",
        "view",
        "edit",
        "none",
        "none",
        "none",
        "none",
        "view",
        "none",
        "none",
        "view",
    ),  # Content types, item types & attributes
    "components": (
        "admin",
        "edit",
        "approve",
        "view",
        "edit",
        "create",
        "create",
        "view",
        "view",
        "create",
        "view",
    ),  # Traceability graph: components, materials & certificates
    "scope_work": (
        "admin",
        "approve",
        "edit",
        "view",
        "edit",
        "view",
        "view",
        "view",
        "view",
        "view",
        "view",
    ),  # Scopes of work (RSW), disciplines & tasks
    "offline": (
        "admin",
        "view",
        "view",
        "view",
        "create",
        "create",
        "create",
        "none",
        "none",
        "create",
        "none",
    ),  # Offline field app & sync
    "forms": (
        "admin",
        "view",
        "admin",
        "edit",
        "view",
        "view",
        "view",
        "view",
        "none",
        "none",
        "view",
    ),  # Form & template designer
    "inspections": (
        "admin",
        "approve",
        "approve",
        "view",
        "approve",
        "create",
        "create",
        "view",
        "approve",
        "create",
        "view",
    ),  # Inspections, ITPs & hold points
    "eligibility": (
        "admin",
        "edit",
        "approve",
        "edit",
        "edit",
        "view",
        "view",
        "edit",
        "view",
        "create",
        "view",
    ),  # Certificates, competency & calibration gate
    "issues": (
        "admin",
        "approve",
        "approve",
        "approve",
        "approve",
        "create",
        "create",
        "view",
        "view",
        "edit",
        "view",
    ),  # Issues, NCRs & corrective actions
    "punchlist": (
        "admin",
        "approve",
        "approve",
        "view",
        "edit",
        "create",
        "create",
        "view",
        "view",
        "edit",
        "view",
    ),  # Punch list & defects liability
    "qms": (
        "admin",
        "view",
        "admin",
        "view",
        "view",
        "none",
        "none",
        "view",
        "none",
        "none",
        "view",
    ),  # Quality roll-up & audits
    "rules": (
        "admin",
        "view",
        "edit",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "view",
    ),  # Rules & validation engine
    "commissioning": (
        "admin",
        "approve",
        "approve",
        "view",
        "edit",
        "create",
        "view",
        "view",
        "view",
        "create",
        "view",
    ),  # Commissioning
    "report_engine": (
        "admin",
        "approve",
        "approve",
        "create",
        "create",
        "create",
        "none",
        "create",
        "approve",
        "none",
        "view",
    ),  # Report engine & published records
    "safety": (
        "admin",
        "approve",
        "view",
        "admin",
        "create",
        "create",
        "create",
        "view",
        "none",
        "create",
        "view",
    ),  # Safety & HSE
    "temporary_works": (
        "admin",
        "approve",
        "view",
        "approve",
        "edit",
        "create",
        "view",
        "view",
        "view",
        "create",
        "view",
    ),  # Temporary works register
    "diary": (
        "admin",
        "approve",
        "view",
        "view",
        "approve",
        "create",
        "create",
        "view",
        "view",
        "create",
        "view",
    ),  # Site diary & field reports
    "voice_phone": (
        "admin",
        "edit",
        "view",
        "none",
        "create",
        "create",
        "create",
        "none",
        "none",
        "none",
        "view",
    ),  # Voice notes & phone log
    "logistics": (
        "admin",
        "approve",
        "view",
        "view",
        "edit",
        "view",
        "create",
        "view",
        "view",
        "create",
        "view",
    ),  # Site logistics & mobilisation
    "equipment": (
        "admin",
        "edit",
        "edit",
        "view",
        "edit",
        "view",
        "create",
        "view",
        "none",
        "create",
        "view",
    ),  # Equipment & fleet
    "inventory": (
        "admin",
        "edit",
        "view",
        "none",
        "edit",
        "create",
        "create",
        "view",
        "view",
        "create",
        "view",
    ),  # Stock, consumables & materials
    "resources": (
        "admin",
        "approve",
        "view",
        "view",
        "edit",
        "view",
        "view",
        "none",
        "none",
        "none",
        "view",
    ),  # Resources & crews (basic)
    "schedule": (
        "admin",
        "approve",
        "view",
        "view",
        "edit",
        "view",
        "view",
        "view",
        "view",
        "view",
        "view",
    ),  # Schedule & look-ahead (basic)
    "documents": (
        "admin",
        "edit",
        "edit",
        "create",
        "create",
        "create",
        "create",
        "admin",
        "view",
        "create",
        "view",
    ),  # Document library & control
    "markup": (
        "admin",
        "create",
        "create",
        "create",
        "create",
        "create",
        "create",
        "create",
        "view",
        "create",
        "view",
    ),  # Markup, viewer & plan room
    "approvals": (
        "admin",
        "approve",
        "approve",
        "approve",
        "approve",
        "view",
        "none",
        "approve",
        "approve",
        "view",
        "view",
    ),  # Workflow & approvals engine
    "signing": (
        "admin",
        "approve",
        "approve",
        "approve",
        "approve",
        "create",
        "create",
        "approve",
        "approve",
        "create",
        "view",
    ),  # E-signatures & tamper-evident records
    "transmittals": (
        "admin",
        "approve",
        "view",
        "none",
        "none",
        "none",
        "none",
        "admin",
        "view",
        "view",
        "view",
    ),  # Transmittals & correspondence
    "ingestion": (
        "admin",
        "view",
        "none",
        "none",
        "none",
        "none",
        "none",
        "admin",
        "none",
        "none",
        "view",
    ),  # Inbound capture & connectors
    "uploads": (
        "admin",
        "create",
        "create",
        "create",
        "create",
        "create",
        "create",
        "create",
        "view",
        "create",
        "none",
    ),  # Upload & file processing pipeline
    "comments": (
        "admin",
        "create",
        "create",
        "create",
        "create",
        "create",
        "create",
        "create",
        "view",
        "create",
        "view",
    ),  # Comments, mentions & notifications
    "meetings": (
        "admin",
        "approve",
        "edit",
        "create",
        "create",
        "view",
        "none",
        "view",
        "view",
        "create",
        "view",
    ),  # Meetings & AI minutes
    "rfi_submittals": (
        "admin",
        "approve",
        "approve",
        "none",
        "create",
        "create",
        "none",
        "approve",
        "view",
        "create",
        "view",
    ),  # RFIs & submittals
    "interfaces": (
        "admin",
        "approve",
        "edit",
        "none",
        "edit",
        "none",
        "none",
        "view",
        "view",
        "create",
        "view",
    ),  # Interface management
    "tasks": (
        "admin",
        "approve",
        "create",
        "create",
        "approve",
        "create",
        "create",
        "create",
        "view",
        "create",
        "view",
    ),  # Tasks, deadlines & my work
    "procurement": (
        "admin",
        "approve",
        "view",
        "none",
        "create",
        "none",
        "none",
        "view",
        "none",
        "none",
        "view",
    ),  # Supplier catalogue, requisitions & POs
    "cost_items": (
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
    ),  # Cost items & schedule of rates (thin)
    "change": (
        "admin",
        "approve",
        "edit",
        "none",
        "create",
        "none",
        "none",
        "view",
        "view",
        "create",
        "view",
    ),  # Change orders, variations & MOC (basic)
    "contacts": (
        "admin",
        "edit",
        "view",
        "view",
        "view",
        "view",
        "none",
        "edit",
        "none",
        "none",
        "view",
    ),  # Contacts & companies
    "ref_packs": (
        "admin",
        "view",
        "view",
        "none",
        "none",
        "none",
        "none",
        "view",
        "none",
        "none",
        "view",
    ),  # Regional reference data packs
    "handover": (
        "admin",
        "approve",
        "approve",
        "view",
        "edit",
        "view",
        "none",
        "admin",
        "view",
        "create",
        "view",
    ),  # Handover, data books & submissions
    "service": (
        "admin",
        "approve",
        "edit",
        "view",
        "edit",
        "create",
        "create",
        "view",
        "view",
        "create",
        "view",
    ),  # Service & maintenance
    "prefab": (
        "admin",
        "approve",
        "approve",
        "none",
        "edit",
        "create",
        "create",
        "view",
        "view",
        "create",
        "view",
    ),  # Prefab & off-site manufacture
    "reporting": (
        "admin",
        "edit",
        "edit",
        "view",
        "view",
        "view",
        "none",
        "view",
        "view",
        "none",
        "view",
    ),  # Dashboards & KPI reporting
    "audit": (
        "view",
        "view",
        "view",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "view",
    ),  # Audit trail, activity & timeline
    "search": (
        "view",
        "view",
        "view",
        "view",
        "view",
        "view",
        "view",
        "view",
        "view",
        "view",
        "view",
    ),  # Search, retrieval & saved views
    "ai_assistant": (
        "admin",
        "view",
        "view",
        "view",
        "view",
        "view",
        "none",
        "view",
        "none",
        "none",
        "none",
    ),  # AI assistant & agents
    "integrations": (
        "admin",
        "view",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "view",
    ),  # Integrations & webhooks
    "data_io": (
        "admin",
        "create",
        "view",
        "none",
        "none",
        "none",
        "none",
        "create",
        "none",
        "none",
        "view",
    ),  # Data import, export & backup
    "cases": (
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
        "none",
    ),  # User-authored playbooks
}


def role_name_key(code: str) -> str:
    return f"access.role.{code}.name"


def level_of_verb(verb: str) -> Level:
    """The lowest level that grants ``verb``; an unknown verb needs ``admin`` (fail closed)."""
    for level in LEVELS:
        if verb in LEVEL_VERBS[level]:
            return level
    return "admin"


def expand_level(level: Level, verbs: Sequence[str]) -> list[str]:
    """The ``verbs`` (in their given order) that ``level`` grants, cumulatively."""
    rank = LEVELS.index(level)
    return [verb for verb in verbs if LEVELS.index(level_of_verb(verb)) <= rank]


def default_permissions(
    catalogue: Iterable[tuple[str, str]], matrix: Mapping[str, Sequence[Level]] = MATRIX
) -> dict[str, frozenset[str]]:
    """Each default role's permission codes, from ``(code, module_id)`` catalogue pairs."""
    by_module: dict[str, list[str]] = {}
    for code, module_id in catalogue:
        if never_role_held(code):
            continue
        by_module.setdefault(module_id, []).append(code)
    granted: dict[str, set[str]] = {role: set() for role in ROLE_CODES}
    skipped: list[str] = []
    for module_id, levels in matrix.items():
        codes = by_module.get(module_id)
        if not codes:
            skipped.append(module_id)
            continue
        for role, level in zip(ROLE_CODES, levels, strict=True):
            granted[role].update(
                code for code in codes if _grants(role, level, code.rsplit(".", 1)[-1])
            )
    if skipped:
        logger.info("access matrix modules without catalogue permissions skipped: %s", skipped)
    return {role: frozenset(codes) for role, codes in granted.items()}


def _grants(role: str, level: Level, verb: str) -> bool:
    needed = level_of_verb(verb)
    if role in SIGN_OFF_ONLY_ROLES and level == "approve":
        return needed == "view" or verb in SIGN_OFF_VERBS
    return LEVELS.index(needed) <= LEVELS.index(level)
