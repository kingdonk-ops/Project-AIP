"""Domain events identity publishes and subscribes to (via the outbox, ADR 0003).

``identity.signoff_policy.changed`` v1 (IDENTITY-04 Part D): a tenant admin changed the minimum
assurance or the step-up window of a critical action. ``before`` is null for a first setting.
The audit module records it (ADR 0010: lowering a minimum is a privileged, audited change).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from aip.platform.events import register_event

__all__ = ["SIGNOFF_POLICY_CHANGED", "SignoffPolicyChangedEvent", "SignoffPolicyValues"]

SIGNOFF_POLICY_CHANGED = "identity.signoff_policy.changed"


class _Camel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
    )


class SignoffPolicyValues(_Camel):
    min_aal: int
    step_up_max_age_min: int


class SignoffPolicyChangedEvent(_Camel):
    action_code: str
    before: SignoffPolicyValues | None = None
    after: SignoffPolicyValues


register_event(SIGNOFF_POLICY_CHANGED, 1, SignoffPolicyChangedEvent, "identity")
