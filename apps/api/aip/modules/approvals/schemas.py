"""Workflow definition spec (APPROVALS-01): the shape of a versioned state machine.

``validate_spec`` is the only way in. It checks the structure with Pydantic, then the graph rules,
and reports every problem as a ``pydantic.ValidationError`` whose ``loc`` points at the exact
offending field (``("transitions", 0, "to")``), so an editor can highlight it:

- codes and actions are snake_case (``^[a-z][a-z0-9_]*$``); labels are term keys, never text;
- ``initial``, ``from`` and ``to`` are declared states; state codes are unique;
- ``(from, action)`` is unique; terminal states have no outgoing transitions;
- every state is reachable from ``initial``.

``guard`` (JSONLogic) must pass ``validate_guard`` (allow-listed operators, size limits),
reported at ``("transitions", i, "guard")``; the transition service evaluates it (APPROVALS-02
Part B).
``guardMessageKey`` is the term key shown when the guard is false; ``signoffAction`` names the
ADR 0010 sign-off policy a ``critical`` transition is checked against (``workflow.<action>`` when
absent). ``requiresComment`` (APPROVALS-05) makes the transition service refuse the action without a
non-blank comment (422 ``COMMENT_REQUIRED``).

The HTTP models (``InstanceStart``, ``TransitionRequest``, ``InstanceOut``, ``TransitionOut``,
``HistoryOut``, and the APPROVALS-05 preset models ``PresetOut``, ``PresetInstall`` and
``DefinitionOut``) use camelCase JSON and forbid unknown keys, so a client can never send a guard
outcome or any other server-decided field.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic.alias_generators import to_camel
from pydantic_core import InitErrorDetails, PydanticCustomError

from aip.modules.approvals.guards.jsonlogic import GuardError, validate_guard

__all__ = [
    "ApprovalsErrorBody",
    "AssuranceOut",
    "AvailableTransition",
    "DecisionOut",
    "DecisionStatus",
    "DefinitionOut",
    "DefinitionStatus",
    "HistoryOut",
    "InstanceOut",
    "InstanceStart",
    "PresetInstall",
    "PresetOut",
    "StateSpec",
    "TransitionOut",
    "TransitionRequest",
    "TransitionSpec",
    "WorkflowDefinition",
    "WorkflowDefinitionSpec",
    "WorkflowInstance",
    "validate_spec",
]

Code = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=63)]
TermKey = Annotated[str, Field(pattern=r"^[a-z0-9_.]+$", max_length=200)]
PermissionCode = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")]
SignoffAction = Annotated[
    str, Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$", max_length=100)
]
DefinitionStatus = Literal["draft", "active", "retired"]
DecisionStatus = Literal["applied", "pending_countersign"]


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class StateSpec(_Spec):
    code: Code
    label_key: TermKey = Field(alias="labelKey")
    terminal: bool = False


class TransitionSpec(_Spec):
    action: Code
    from_state: Code = Field(alias="from")
    to_state: Code = Field(alias="to")
    required_permission: PermissionCode = Field(alias="requiredPermission")
    guard: dict[str, Any] | None = None
    side_effects: tuple[dict[str, Any], ...] = Field(default=(), alias="sideEffects")
    critical: bool = False
    label_key: TermKey = Field(alias="labelKey")
    guard_message_key: TermKey | None = Field(default=None, alias="guardMessageKey")
    signoff_action: SignoffAction | None = Field(default=None, alias="signoffAction")
    requires_comment: bool = Field(default=False, alias="requiresComment")


class WorkflowDefinitionSpec(_Spec):
    states: tuple[StateSpec, ...] = Field(min_length=1)
    initial: Code
    transitions: tuple[TransitionSpec, ...]

    def to_json(self) -> dict[str, Any]:
        """The spec in its stored (camelCase) form."""
        return self.model_dump(mode="json", by_alias=True)


def _issue(loc: tuple[int | str, ...], message: str, value: object) -> InitErrorDetails:
    return {
        "type": PydanticCustomError("workflow_spec", "{message}", {"message": message}),
        "loc": loc,
        "input": value,
    }


def _graph_issues(spec: WorkflowDefinitionSpec) -> list[InitErrorDetails]:
    found: list[InitErrorDetails] = []
    declared: dict[str, StateSpec] = {}
    for i, state in enumerate(spec.states):
        if state.code in declared:
            found.append(
                _issue(("states", i, "code"), f"duplicate state: {state.code}", state.code)
            )
        declared.setdefault(state.code, state)
    if spec.initial not in declared:
        found.append(_issue(("initial",), f"undeclared state: {spec.initial}", spec.initial))

    seen: set[tuple[str, str]] = set()
    for i, t in enumerate(spec.transitions):
        for field, code in (("from", t.from_state), ("to", t.to_state)):
            if code not in declared:
                found.append(_issue(("transitions", i, field), f"undeclared state: {code}", code))
        source = declared.get(t.from_state)
        if source is not None and source.terminal:
            found.append(
                _issue(
                    ("transitions", i, "from"),
                    f"terminal state {t.from_state} cannot have outgoing transitions",
                    t.from_state,
                )
            )
        if (t.from_state, t.action) in seen:
            found.append(
                _issue(
                    ("transitions", i, "action"),
                    f"duplicate action {t.action} from state {t.from_state}",
                    t.action,
                )
            )
        seen.add((t.from_state, t.action))
        if t.guard is not None:
            try:
                validate_guard(t.guard)
            except GuardError as exc:
                found.append(_issue(("transitions", i, "guard"), str(exc), t.guard))

    if spec.initial in declared:
        reached = {spec.initial}
        queue = deque([spec.initial])
        while queue:
            state = queue.popleft()
            for t in spec.transitions:
                if t.from_state == state and t.to_state in declared and t.to_state not in reached:
                    reached.add(t.to_state)
                    queue.append(t.to_state)
        for i, state in enumerate(spec.states):
            if state.code not in reached and declared[state.code] is state:
                found.append(
                    _issue(("states", i, "code"), f"unreachable state: {state.code}", state.code)
                )
    return found


def validate_spec(data: object) -> WorkflowDefinitionSpec:
    """Parse and check a definition spec; raise ``ValidationError`` listing every issue."""
    spec = WorkflowDefinitionSpec.model_validate(data)
    issues = _graph_issues(spec)
    if issues:
        raise ValidationError.from_exception_data(WorkflowDefinitionSpec.__name__, issues)
    return spec


class WorkflowDefinition(BaseModel):
    """A stored definition version."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    record_type: str
    project_id: UUID | None
    key: str
    version: int
    status: DefinitionStatus
    spec: WorkflowDefinitionSpec
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime


class WorkflowInstance(BaseModel):
    """A record's workflow, pinned to the definition version it started under."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    definition_id: UUID
    version: int
    record_type: str
    record_id: UUID
    project_id: UUID | None
    current_state: str
    sync_version: int


class _Http(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
        frozen=True,
    )


class ApprovalsErrorBody(_Http):
    code: str
    message_key: str | None = None


class InstanceStart(_Http):
    record_type: Code
    record_id: UUID
    project_id: UUID | None = None


class TransitionRequest(_Http):
    action: Code
    comment: str | None = Field(default=None, max_length=2000)
    expected_sync_version: int | None = Field(default=None, ge=1)


class AvailableTransition(_Http):
    action: str
    to_state: str
    label_key: str
    critical: bool
    requires_comment: bool
    allowed: bool
    reason_key: str | None = None


class InstanceOut(_Http):
    id: UUID
    record_type: str
    record_id: UUID
    project_id: UUID | None
    definition_id: UUID
    definition_key: str
    version: int
    current_state: str
    sync_version: int
    pending_countersign: str | None = None
    available_transitions: list[AvailableTransition]


class AssuranceOut(_Http):
    level: int | None
    method: str | None
    authenticated_at: datetime | None
    device_id: UUID | None


class DecisionOut(_Http):
    id: UUID
    seq: int
    from_state: str
    to_state: str
    action: str
    actor_id: UUID | None
    on_behalf_of: UUID | None
    comment: str | None
    auth_strength: str | None
    status: DecisionStatus
    countersigns_id: UUID | None
    assurance: AssuranceOut
    guard_result: dict[str, Any] | None
    prev_hash: str
    entry_hash: str
    created_at: datetime


class TransitionOut(_Http):
    instance: InstanceOut
    decision: DecisionOut


class HistoryOut(_Http):
    entries: list[DecisionOut]
    chain_valid: bool
    broken_at_seq: int | None = None


class PresetOut(_Http):
    """A ``config/workflows`` preset: its key, record type and neutral codes (no display text)."""

    key: str
    record_type: str
    initial: str
    states: list[str]
    actions: list[str]


class PresetInstall(_Http):
    preset_key: Code
    project_id: UUID | None = None


class DefinitionOut(_Http):
    id: UUID
    key: str
    record_type: str
    project_id: UUID | None
    version: int
    status: DefinitionStatus
