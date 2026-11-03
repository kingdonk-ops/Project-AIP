# Merged-PR review against specs and ADRs (2026-11-03)

- **Scope:** the 29 task PRs merged from 2026-10-28 to 2026-11-03 (#158 to #233), checked on `origin/main` at
  `5785b3b`. Dependabot, CI-only and vulnerability-exception PRs are out of scope: they have no task spec or ADR to
  check against.
- **Method:**
  - Read-only. Six review agents worked in parallel, one per module group. Each read the PR diff, the task spec
    (`tracking/tasks/<ID>.md`), the ADRs for that module, `07-task-conventions.md` and the hard rules in `AGENTS.md`.
  - Precedence as in `AGENTS.md`: the latest accepted ADR, then `01-decisions.md`, then the task spec, then the module
    docs.
  - Every blocking and major finding marked **verified** was re-checked in the code by the coordinating agent. The
    others are as reported by the agents.
  - Test suites were not run.
- **Severity:** **blocking** breaks an accepted ADR, a hard rule or a spec acceptance criterion; **major** is a real
  gap in behaviour, security or test proof; **minor** is drift, tracking or a small test gap.
- **Status (2026-11-03):** the owner decided B1, B2 and B3 and accepted ADR 0036 (D1, D2, D4) the same day. Every other finding has a follow-up
  task in §5, is covered by an existing task, or is accepted as built.

---

## Summary

| Area | PRs | Verdict |
|---|---|---|
| Access | #158, #163, #230, #231 | #158 conformant; #163 and #230 minor gaps; #231 significant deviation, now resolved by ADR 0042's acceptance |
| Identity and portal | #159, #216, #222, #223 | #159 conformant; #216, #222 minor gaps; #223 one blocking acceptance gap |
| Approvals | #213, #217, #219 (ADR 0041), #220 | #213, #220 conformant; #217 one major gap; ADR 0041 consistent with one minor deviation |
| Inspections and database | #218, #226, #227, #229 | #218, #227 conformant; #226 minor; #229 one ADR clash (moved to PORTAL-06) and minor gaps |
| Reports and test infra | #210, #215, #232, #233 | #232 conformant; #210, #233 minor; #215 one major spec gap |
| Assets, forms, item types, design | #160, #191, #195, #198, #203, #214, #221, #228 | #160, #198, #203, #228 conformant; #191, #221 minor; #195 and #214 test-proof gaps |

16 of 29 PRs are conformant or have only minor gaps. No PR broke the tenant-isolation rules (`tenant_id`, FORCE RLS,
cross-tenant 404) on a tenant table.

---

## 1. Blocking

| ID | PR | Finding | Verified | Resolution |
|---|---|---|---|---|
| B1 | #231 ACCESS-09 | `default_role_level` and `default_role_level_change` have no `tenant_id` and no RLS; `default_role_level` has a composite text key and a reset hard-deletes its row (`migrations/versions/202611021000_access_default_role_template.py:36-91`). Breaks the `AGENTS.md` table rule. Only the then-proposed ADR 0042 justified it. | yes | **Owner, 2026-11-03: ADR 0042 accepted** with an explicit, two-table exception. |
| B2 | #231 ACCESS-09 | `POST /api/v1/platform/default-roles/sync` re-seeds existing tenants' system roles without a support-access grant (`access/roles/template_routes.py:191-227`). Breaks ADR 0020 point 3 (accepted). | yes | **Owner, 2026-11-03:** ADR 0020 point 3 amended by ADR 0042. The push only re-seeds uncustomised system roles. |
| B3 | #229 INSPECTIONS-03 | ADR 0039 #43 (accepted) has INSPECTIONS-03 notify the client inspector with the project's `witness_notice_hours` and record it on the witness point. Nothing is sent or recorded; `ready` only sets `ready_at` (`inspections/itp.py:405-406`). The task spec had moved notification out of scope. | yes | **Owner, 2026-11-03:** moved to PORTAL-06 (email naming the requester's person and company, what is inspected, a portal link to accept, reject or reschedule, and the associated documents and codes). ADR 0039 amended; PORTAL-06 spec expanded. |
| B4 | #223 PORTAL-07 | The register treats any non-200 as the generic `portal.admin.error` (`apps/web/src/features/portal/PortalUsersRegister.tsx:47-51`). Acceptance: "the API's 403 shows the denied state". The e2e checks only the detail 404 and the hidden nav item. | yes | PORTAL-09 |

## 2. Major

| ID | PR | Finding | Verified | Follow-up |
|---|---|---|---|---|
| M1 | #215 REPORTS-04 | List, get and download check only `report.view` on the project (`report_engine/render_service.py:229, 264, 279`), while requesting a render also needs the record's own view permission (`entry.view_permission`, lines 149 and 195). A user with `report.view` but without `inspection.view` can download inspection PDFs, including the internal variant. The code follows the spec, so the spec has the gap. | yes | REPORTS-07 |
| M2 | #217 APPROVALS-04 | `complete_route` (`approvals/transition.py:588`) never checks the target transition's `requires_comment`; the normal path does (`transition.py:443`). A route ending in `retire` or `assign_with_comment` completes with no comment. Breaks ADR 0040 point 1 ("through the transition service's own steps"). | yes | APPROVALS-14 |
| M3 | #216 PORTAL-01 | `read_access_days` (`portal/service.py:114-118`) looks for `ProjectsApi.get_setting`, which does not exist yet, so every grant gets 180 days. Acceptance: "A grant's period comes from its project's `portal_access_days`". Started before its PROJECTS-04 dependency; the fallback is recorded on the board. | yes | PROJECTS-04 (row note added) |
| M4 | #214 DESIGN-15 | The cross-tenant e2e mocks both tenants' flags APIs with `page.route` (`e2e/web/release-flags.spec.ts:1-5, 31`), so "tenant B's flag unchanged" can never fail. Real isolation is only proven by `apps/api/tests/platform/flags/test_flags.py`. | yes | TESTING-14 |
| M5 | #163 ACCESS-04 | A project-level team manager can add themselves to a team holding a non-privileged role they do not hold (`access/teams/service.py:205-221`). Breaks ADR 0020 point 2 ("can never grant more than the grantor holds"). | agent | ACCESS-08 step 3 (already tracked; needs the owner decision) |
| M6 | #229 INSPECTIONS-03 | Any `itp.sign` holder can countersign, including another inspector; ADR 0010 says "a supervisor with the required assurance and permission". `signatory_role` is taken from the caller unchecked (`inspections/itp.py:450`). | agent | INSPECTIONS-11 |
| M7 | #195 ITEMTYPES-03 | Acceptance: "no axe violations at desktop and 390 px widths". The e2e runs only in the desktop `web` skeleton project (`e2e/playwright.config.ts:66`) and nothing sets 390 px; both axe checks count only serious and critical violations. | agent | TESTING-14 |

## 3. Minor

| ID | PR | Finding | Follow-up |
|---|---|---|---|
| L1 | #210 | A POST reusing a known `Idempotency-Key` checks only `report.view`, not `report.create` (`render_service.py:131-135`; verified). The key is tenant-wide, not per user. | REPORTS-07 |
| L2 | #210 | A missing pinned file raises `RecordNotFound` from `build_snapshot` (`snapshots.py:148-149`), which no handler maps, so the route answers 500, not 404. | REPORTS-07 |
| L3 | #210 | The pinning test checks the v2 marker is absent but not that the v1 marker is present (`test_render_pdf.py:166-192`). | REPORTS-07 |
| L4 | #233 | The client variant's snapshot still holds `respondedBy`, `internalTag`, the inspection id and `schemaHash` (`providers/inspection.py:284, 306, 314, 324`); only the template hides them. The integration test does not check the internal tag. | REPORTS-07 |
| L5 | #233 | `style.css` uses generic `sans-serif`, not an embedded OFL font (ADR 0014), so output depends on the Gotenberg image's fonts. | REPORTS-07 |
| L6 | #229 | `signatoryRole: "client"` gets a generic validation 422, not `CLIENT_SIGNOFF_NOT_AVAILABLE`; the code and its term key do not exist. | INSPECTIONS-11 |
| L7 | #226 | `inspection_responses` has no FK to `inspections` (`202611011400_inspections_responses.py:104-107`). It was left off for the bug DATABASE-09 fixed and never added back. | INSPECTIONS-11 |
| L8 | #219/#226 | ADR 0041 §6: a supervisor with `approvals.inspection.review` may save answers during supervisor review. The code also requires `inspection.respond` (`inspections/policies.py:60`). | INSPECTIONS-11 |
| L9 | #217 | No en-AU term for `approvals.route.pending` (`transition.py:114`). | APPROVALS-14 |
| L10 | #217 | A finishing decision writes before the transition checks (`routes_engine/service.py:319-323`); the transaction rolls back on refusal, so nothing survives. | APPROVALS-14 (reorder) |
| L11 | #222 | Portal 404s (`portal/routes.py:355`, `RouteHiddenError`) carry no `Cache-Control: no-store`; step 3 says every portal response does. | PORTAL-09 |
| L12 | #223 | No unit-level axe check on the register; `projectId` combined with `status=invited` untested (`test_admin_filters_db.py:64-75`). | PORTAL-09 |
| L13 | #163 | A cached grant can outlive its `valid_to` by up to 300 s; the `user.deactivated` subscriber has no publisher until IDENTITY-05; "team not found" 404 vs "not allowed" 403 lets same-tenant users probe team ids; cache docstrings cite ADR 0039 instead of a cache ADR, and no ADR records the Redis policy-cache decisions. | ACCESS-08 (notes added) |
| L14 | #158 | The portal test asserts QA/QC Manager and Document Controller lack `portal.user.invite` but not Client Reviewer. | ACCESS-08 (note added) |
| L15 | #230 | No `PROGRESS.md` line; the ADR 0027 index row did not mention the 2026-11-02 amendment. | fixed in this PR |
| L16 | #231, #216, #229 | Board drift: ACCESS-09 still `review`; the PORTAL-01 row still said "named internal approver" (ADR 0036 removed it); the demo round 3 heading still said "row 2 ready now". | fixed in this PR |
| L17 | #220 | `config/workflows/README.md` still said INSPECTIONS-09 adds "skip supervisor review", which ADR 0041 §5 replaced with `submit_report`. | fixed in this PR |

**Accepted as built** (spec drift recorded, no change needed): REPORTS-04 terms named `report.register.*` rather than
`reports.*`; APPROVALS-04 exports `route` rather than `steps`; APPROVALS-09 changed the golden runners (a `comment`
option, disclosed in the PR); PORTAL-02 edited identity tests to follow its own `/me` 404 rule and points Keycloak
`baseUrl` at `/signin` and back-channel logout at `APP_BACKCHANNEL_ORIGIN` (mirrors `aip-api`); FORMS-10 emits
`UNKNOWN_REFERENCE` (not `UNKNOWN_FIELD`) and bumps `EVALUATOR_VERSION` to 2 with unchanged verdicts; FORMS-03 shows
only the visible required marker on multi-select, photo and signature groups (ARIA does not allow `aria-required` on
a plain group); ACCESS-09 template edits write history, not a domain event (ADR 0042 point 4, now accepted).

**Unverified:** whether the operator-only `platform.roles.manage` routes should need step-up (aal2). Nothing requires
it today; decide when OPS-12 issues operator principals (ACCESS-10).

## 4. Where the documents disagree

| ID | Conflict | Resolution |
|---|---|---|
| D1 | **ADR 0036 is still `proposed`** ("accepted at the PLAN-R1 phase-entry review" in its body), yet REPORTS, PORTAL, FORMS-10 and ASSETS-02 build on it. | **Owner, 2026-11-03: ADR 0036 accepted.** |
| D2 | ADR 0005 (accepted) gives portal users a magic link and a separate session store; ADR 0036 choice 7 replaced the magic link, and the code shares `user_session` keyed by `audience`. | ADR 0005's portal row marked superseded by ADR 0036. |
| D3 | REPORTS-02 and REPORTS-03 say sealing is open (ADR 0036 §5); accepted ADR 0039 decided PAdES with a KMS key plus S3 Object Lock, but keeps hash-only reports until before AWS go-live. The code matches both. ADR 0039 #49 ("completed reports are locked and added to the documents list of their inspection") has no task. | REPORTS-02 wording updated; REPORTS-08 added for #49; signing stays after R1. |
| D4 | ADR 0036 §9 says a host module owns later versions of its record type's preset; ADR 0041 had APPROVALS-10 publish the next inspection preset. | ADR 0041 is later and wins; ADR 0036 §9 amended. |
| D5 | Witness notice period: ADR 0039 and ADR 0036 say the project's `witness_notice_hours`; INSPECTIONS-03 built a per-step `notice_hours`. | PORTAL-06 spec reconciles them. |
| D6 | Who countersigns an ITP sign-off: ADR 0010 says a supervisor; the INSPECTIONS-03 spec says any `itp.sign` holder. | ADR wins: INSPECTIONS-11. |
| D7 | ACCESS-04 step 5 relies on `user.deactivated`, but IDENTITY-05 (which publishes it) is not a dependency. | ACCESS-08 note. |
| D8 | IDENTITY-10's test expected `GET /api/v1/me` with a portal cookie to answer 200; PORTAL-02 makes every staff route 404 to a portal session. | PORTAL-02 is later and wins; as built. |
| D9 | REPORTS-03 triggers on `completed`; ADR 0041 names the state `performed`. | Code follows the ADR; recorded in REPORTS-03 "As built". |
| D10 | The INSPECTIONS-03 spec still describes a `submit` guard with `missingRequiredCount` (replaced by its ADR 0041 banner) and says client sign-off waits on OPEN-QUESTIONS #42, answered 2026-10-18. | Historical spec of a done task; superseded by ADR 0041 and INSPECTIONS-11. |

## 5. Follow-up tasks (on the board under "Review 13 follow-ups")

| ID | Covers | Size |
|---|---|---|
| [REPORTS-07](../../tracking/tasks/REPORTS-07.md) | M1, L1 to L5: record-level view check on list, get and download; create check on idempotent replay; 404 for a missing pinned file; client snapshot strips internal fields; embedded OFL font; test gaps | S |
| [REPORTS-08](../../tracking/tasks/REPORTS-08.md) | D3: completed inspection reports added to their inspection's documents list (ADR 0039 #49) | S |
| [APPROVALS-14](../../tracking/tasks/APPROVALS-14.md) | M2, L9, L10: route completion enforces the comment rule, checks before writes, missing term | XS |
| [PORTAL-09](../../tracking/tasks/PORTAL-09.md) | B4, L11, L12: register denied state, `no-store` on every portal response, test gaps | XS |
| [INSPECTIONS-11](../../tracking/tasks/INSPECTIONS-11.md) | M6, L6 to L8: supervisor-only countersign, server-derived signatory role, `CLIENT_SIGNOFF_NOT_AVAILABLE`, responses FK, supervisor edit per ADR 0041 §6 | S |
| [TESTING-14](../../tracking/tasks/TESTING-14.md) | M4, M7: real cross-tenant release-flags e2e, ITEMTYPES-03 axe at 390 px | S |

| [INSPECTIONS-12](../../tracking/tasks/INSPECTIONS-12.md) and [PORTAL-06](../../tracking/tasks/PORTAL-06.md) | B3: witness bookings, staff API and events (part A), then the client email and portal pages (part B); open owner questions in PORTAL-06 | M + M |

Existing tasks updated: **ACCESS-08** (M5, L13, L14, D7 notes),
**PROJECTS-04** (M3: PORTAL-01 must read `portal_access_days` once `get_setting` ships).
