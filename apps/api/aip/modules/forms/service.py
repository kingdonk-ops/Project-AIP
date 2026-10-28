"""Business logic for form templates and revisions (FORMS-01).

Every operation runs in one ``with_tenant(get_context())`` transaction; RLS keeps each tenant to
its own rows, so another tenant's ids read as 404 (``NotFoundError``), never 403. Uploading or
replacing a schema lints it first (any issue → 422 ``TEMPLATE_INVALID`` with ``issues``). Publishing
locks the template ``FOR UPDATE``, re-lints, hashes the canonical JSON, retires the current
published revision, freezes this one and bumps the template's ``sync_version`` — all in the one
transaction that also writes the ``form.revision_published`` outbox event, so a failure (a stale
``expectedSyncVersion``, a failed emit) leaves template, revisions and events untouched.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any, Final
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.forms import repository as repo
from aip.modules.forms.evaluator import EVALUATOR_VERSION, evaluate_answers, evaluation_as_json
from aip.modules.forms.events import FORM_REVISION_PUBLISHED, RevisionPublished
from aip.modules.forms.lint import LintIssue, lint_template
from aip.modules.forms.schemas import (
    EvaluateBody,
    LintIssueOut,
    LintResult,
    RevisionCreate,
    RevisionOut,
    RevisionReplace,
    TemplateCreate,
    TemplateDetail,
    TemplateListItem,
    TemplatePage,
    TemplateRecord,
    UploadResult,
)
from aip.modules.item_types.api import field_types
from aip.modules.terms.api import UnknownUnitError, to_si
from aip.platform.context import get_context, new_request_id
from aip.platform.db.errors import NotFoundError
from aip.platform.db.session import with_tenant
from aip.platform.events import Aggregate, emit
from aip.platform.http import DomainError

__all__ = ["FormsService"]

_UNIQUE_VIOLATION: Final = "23505"


def _new_id() -> UUID:
    return UUID(new_request_id())  # the platform's UUIDv7 generator


def _actor() -> UUID | None:
    return get_context().actor_id


def _field_type_keys() -> frozenset[str]:
    return frozenset(field_type.key for field_type in field_types())


def _known_unit(unit: str) -> bool:
    try:
        to_si(1, unit)
    except UnknownUnitError:
        return False
    return True


def _canonical_hash(schema: Mapping[str, Any]) -> str:
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _lint(schema: Mapping[str, Any]) -> list[LintIssue]:
    return lint_template(schema, field_types=_field_type_keys(), known_units=_known_unit)


def _lint_or_raise(schema: Mapping[str, Any]) -> None:
    issues = _lint(schema)
    if issues:
        raise DomainError(422, "TEMPLATE_INVALID", issues=[issue.as_dict() for issue in issues])


@asynccontextmanager
async def _tx() -> AsyncIterator[AsyncConnection]:
    async with with_tenant(get_context()) as conn:
        yield conn


@asynccontextmanager
async def _code_unique() -> AsyncIterator[None]:
    try:
        yield
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == _UNIQUE_VIOLATION:
            raise DomainError(409, "CODE_TAKEN") from None
        raise


def _template_record(row: dict[str, Any], current_revision_no: int | None) -> TemplateRecord:
    return TemplateRecord.model_validate({**row, "current_revision_no": current_revision_no})


def _revision_out(row: dict[str, Any]) -> RevisionOut:
    return RevisionOut.model_validate(row)


class FormsService:
    """Stateless; each method opens its own tenant transaction."""

    async def list_templates(
        self, *, kind: str | None, status: str | None, q: str | None, limit: int
    ) -> TemplatePage:
        async with _tx() as conn:
            rows = await repo.list_templates(conn, kind=kind, status=status, q=q, limit=limit)
        return TemplatePage(items=[TemplateListItem.model_validate(row) for row in rows])

    async def get_template(self, template_id: UUID) -> TemplateDetail:
        async with _tx() as conn:
            template = await repo.get_template(conn, template_id)
            if template is None:
                raise NotFoundError(f"form template {template_id} not found")
            revisions = await repo.revisions_for_template(conn, template_id)
            current_no = await repo.template_current_revision_no(conn, template_id)
        return TemplateDetail.model_validate(
            {**template, "current_revision_no": current_no, "revisions": revisions}
        )

    async def lint(self, schema: Mapping[str, Any]) -> LintResult:
        return LintResult(
            issues=[LintIssueOut.model_validate(issue.as_dict()) for issue in _lint(schema)]
        )

    async def upload_template(self, body: TemplateCreate) -> UploadResult:
        _lint_or_raise(body.schema_)
        tenant = get_context().tenant_id
        actor = _actor()
        async with _tx() as conn, _code_unique():
            template_id = _new_id()
            template = await repo.insert_template(
                conn,
                {
                    "id": template_id,
                    "tenant_id": tenant,
                    "code": body.code,
                    "name": body.name,
                    "kind": body.kind,
                    "status": "draft",
                    "created_by": actor,
                },
            )
            revision = await repo.insert_revision(
                conn,
                {
                    "id": _new_id(),
                    "tenant_id": tenant,
                    "template_id": template_id,
                    "revision_no": 1,
                    "status": "draft",
                    "schema": body.schema_,
                    "change_note": body.change_note,
                    "created_by": actor,
                },
            )
        return UploadResult(
            template=_template_record(template, None), revision=_revision_out(revision)
        )

    async def create_draft(self, template_id: UUID, body: RevisionCreate) -> RevisionOut:
        tenant = get_context().tenant_id
        actor = _actor()
        async with _tx() as conn:
            template = await repo.get_template(conn, template_id)
            if template is None:
                raise NotFoundError(f"form template {template_id} not found")
            if await repo.open_draft(conn, template_id) is not None:
                raise DomainError(409, "DRAFT_EXISTS")
            if body.schema_ is not None:
                schema = body.schema_
                _lint_or_raise(schema)
            else:
                current = await repo.current_published_revision(conn, template_id)
                if current is None:
                    raise DomainError(409, "NO_PUBLISHED_REVISION")
                schema = current["schema"]
            revision_no = await repo.max_revision_no(conn, template_id) + 1
            revision = await repo.insert_revision(
                conn,
                {
                    "id": _new_id(),
                    "tenant_id": tenant,
                    "template_id": template_id,
                    "revision_no": revision_no,
                    "status": "draft",
                    "schema": schema,
                    "change_note": body.change_note,
                    "created_by": actor,
                },
            )
        return _revision_out(revision)

    async def get_revision(self, revision_id: UUID) -> RevisionOut:
        async with _tx() as conn:
            revision = await repo.get_revision(conn, revision_id)
        if revision is None:
            raise NotFoundError(f"form revision {revision_id} not found")
        return _revision_out(revision)

    async def evaluate(self, revision_id: UUID, body: EvaluateBody) -> dict[str, Any]:
        """Evaluate ``answers`` against any revision of this tenant (drafts included, so a template
        can be tested before publishing). Another tenant's id → 404 (RLS hides it)."""
        async with _tx() as conn:
            revision = await repo.get_revision(conn, revision_id)
        if revision is None:
            raise NotFoundError(f"form revision {revision_id} not found")
        context = (
            body.context.model_dump(by_alias=True, exclude_none=True)
            if body.context is not None
            else None
        )
        evaluation = evaluate_answers(
            revision["schema"], body.answers, mode=body.mode, context=context
        )
        return evaluation_as_json(evaluation)

    async def replace_draft(self, revision_id: UUID, body: RevisionReplace) -> RevisionOut:
        _lint_or_raise(body.schema_)
        async with _tx() as conn:
            revision = await repo.get_revision(conn, revision_id)
            if revision is None:
                raise NotFoundError(f"form revision {revision_id} not found")
            if revision["status"] != "draft":
                raise DomainError(409, "REVISION_FROZEN")
            patch: dict[str, Any] = {"schema": body.schema_}
            if "change_note" in body.model_fields_set:
                patch["change_note"] = body.change_note
            updated = await repo.update_revision(conn, revision_id, patch)
        return _revision_out(updated)

    async def discard_draft(self, revision_id: UUID) -> None:
        async with _tx() as conn:
            revision = await repo.get_revision(conn, revision_id)
            if revision is None:
                raise NotFoundError(f"form revision {revision_id} not found")
            if revision["status"] != "draft":
                raise DomainError(409, "REVISION_FROZEN")
            await repo.soft_delete_revision(conn, revision_id)

    async def publish(self, revision_id: UUID, expected_sync_version: int | None) -> UploadResult:
        actor = _actor()
        async with _tx() as conn:
            located = await repo.get_revision(conn, revision_id)
            if located is None:
                raise NotFoundError(f"form revision {revision_id} not found")
            template = await repo.lock_template(conn, located["template_id"])
            if template is None:
                raise NotFoundError(f"form template {located['template_id']} not found")
            # Re-read under the template lock: a concurrent publish may already have frozen it.
            revision = await repo.get_revision(conn, revision_id)
            if revision is None or revision["status"] != "draft":
                raise DomainError(409, "REVISION_FROZEN")

            _lint_or_raise(revision["schema"])
            schema_hash = _canonical_hash(revision["schema"])

            current = await repo.current_published_revision(conn, template["id"])
            if current is not None and current["id"] != revision_id:
                await repo.update_revision(conn, current["id"], {"status": "superseded"})

            published = await repo.update_revision(
                conn,
                revision_id,
                {
                    "status": "published",
                    "schema_hash": schema_hash,
                    "evaluator_version": EVALUATOR_VERSION,
                    "published_at": func.now(),
                    "published_by": actor,
                },
            )

            expected = (
                template["sync_version"] if expected_sync_version is None else expected_sync_version
            )
            template = await repo.update_template(
                conn,
                template["id"],
                expected,
                {"current_revision_id": revision_id, "status": "active"},
            )

            payload = RevisionPublished(
                template_id=template["id"],
                revision_id=revision_id,
                revision_no=revision["revision_no"],
                code=template["code"],
                kind=template["kind"],
                schema_hash=schema_hash,
            ).model_dump(mode="json")
            await emit(
                conn,
                FORM_REVISION_PUBLISHED,
                1,
                Aggregate("form_template", template["id"]),
                payload,
            )
        return UploadResult(
            template=_template_record(template, revision["revision_no"]),
            revision=_revision_out(published),
        )
