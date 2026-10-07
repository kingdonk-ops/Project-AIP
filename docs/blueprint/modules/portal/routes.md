# Page specs for `portal`

#### External users `/admin/portal/users` (Client & subcontractor portal)

Internal admin register of external users and their status.

- **layout**: DataTable with status filters and a detail drawer.
- **sections**:
  - Table: name, email, company, party role, invited by, approved by, status, last sign-in, grants
  - Filters: project, company, status
  - Pending approvals tab
- **actions**:
  - Invite
  - Approve or reject
  - Revoke
  - Extend expiry
  - Resend invite
  - Export
- **access**: portal.admin; approvers see their own pending items.

#### Invite external user `/admin/portal/users/new` (Client & subcontractor portal)

Create an invitation with scoped grants.

- **layout**: Single form with grant builder and an approval summary.
- **sections**:
  - Identity: email, name, company, party role
  - Projects
  - Internal owner (approver)
  - Expiry
  - Grant builder: project, asset subtree, module, action, download policy
- **actions**:
  - Submit for approval
  - Save draft
  - Cancel
- **access**: portal.invite (project manager or delegated admin).

#### External user detail `/admin/portal/users/:id` (Client & subcontractor portal)

Review one external user's onboarding, grants and activity.

- **layout**: Header with status and tabs.
- **sections**:
  - Profile and status
  - Company and certificate onboarding gate
  - Grants
  - Sessions and devices
  - Audit trail
  - Pending actions
- **actions**:
  - Edit grants
  - Revoke session
  - Revoke access
  - Extend expiry
  - Reset PIN
- **access**: portal.admin.

#### Share packs `/admin/portal/share-packs` (Client & subcontractor portal)

Manage time-limited read-only bundles.

- **layout**: Table and a create drawer.
- **sections**:
  - Pack list: scope, contents, expiry, views
  - Contents builder
  - Access log
- **actions**:
  - Create
  - Revoke
  - Extend
  - Copy link
  - Export access log
- **access**: portal.sharepack.manage.

#### Portal settings `/admin/portal/settings` (Client & subcontractor portal)

Configure the portal per tenant, off by default.

- **layout**: Sectioned settings form with a branding preview.
- **sections**:
  - Enable portal
  - Origin and domain
  - Session and idle timeout
  - Magic link TTL and PIN lockout
  - Rate limits and WAF profile
  - Download policy and watermark
  - Witness waive notice period
  - Invitation approval rules
  - Visible modules
  - Per-client branding and terminology
  - Enterprise SSO connection if adopted
- **actions**:
  - Enable or disable
  - Save
  - Preview branding
  - Test email
- **access**: Tenant admin with portal.settings.

#### Portal sign-in `portal:/signin` (Client & subcontractor portal)

Magic link and PIN entry on the separate origin.

- **layout**: Minimal centred card using client branding.
- **sections**:
  - Email entry
  - Link confirmation (POST click-through)
  - PIN entry with lockout message
  - Expired link state
- **actions**:
  - Request link
  - Confirm sign-in
  - Enter PIN
- **access**: Invited external users; unauthenticated.

#### Portal home: needs my action `portal:/` (Client & subcontractor portal)

Inbox of items awaiting the external user.

- **layout**: Branded header, action inbox list and summary tiles.
- **sections**:
  - Needs my action
  - Upcoming hold and witness points
  - Recent shares
  - Expiring access notice
- **actions**:
  - Open item
  - Counter-sign
  - Respond
  - Upload
  - Confirm or waive witness
- **access**: External users with at least one grant.

#### Portal asset tree `portal:/assets` (Client & subcontractor portal)

Read-only view of granted assets with status and documents.

- **layout**: Tree panel and detail pane.
- **sections**:
  - Tree limited to granted subtrees
  - Status and open items
  - Documents and reports
- **actions**:
  - Browse
  - Download if the policy allows
  - Comment
- **access**: External users with an asset grant.

#### Portal action page `portal:/actions/:type/:id` (Client & subcontractor portal)

Complete a counter-sign, NCR response, upload or witness decision.

- **layout**: Focused single-column record view with an action panel.
- **sections**:
  - Record summary
  - Evidence and attachments
  - Action form
  - Audit notice
- **actions**:
  - Counter-sign
  - Reject with comment
  - Submit response
  - Upload evidence
  - Confirm attendance
  - Waive with notice
- **access**: External users with the matching action grant; subcontractors need a passed onboarding gate.

#### Asset condition dashboard `portal:/dashboard` (Client & subcontractor portal)

Read-only defect trends by area for clients.

- **layout**: KPI strip and chart grid.
- **sections**:
  - Condition summary
  - Defect trends by area
  - Status by subtree
- **actions**:
  - Filter by area and date
  - Export if permitted
- **access**: Client party role with a dashboard grant.

#### Share pack viewer `portal:/share/:token` (Client & subcontractor portal)

Open a time-limited bundle without a full account.

- **layout**: Branded viewer with a contents list and preview pane.
- **sections**:
  - Pack contents
  - Viewer with watermark
  - Expiry notice
- **actions**:
  - View
  - Download if the policy allows
- **access**: Holders of a valid token; no account needed.
