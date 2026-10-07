# Page specs for `signing`

#### Signer inbox `/signing/inbox` (E-signatures & tamper-evident records)

Signatures waiting for the user.

- **layout**: Table with filters and a review panel.
- **sections**:
  - Filters (status, meaning, record type, due)
  - Inbox table (record, meaning, requested by, required by, auth needed, status)
  - Document review panel
- **actions**:
  - Review and sign
  - Decline
  - Delegate
  - Sign selected (routine types only)
- **access**: Named signers and delegates; competency gate checked per signer

#### Sign document `/signing/sign/:requirementId` (E-signatures & tamper-evident records)

Review the exact document version and apply an attestation.

- **layout**: Document viewer with a right panel showing hash, meaning, consent statement and competency result.
- **sections**:
  - Document and hash
  - Consent statement
  - Competency check
  - Step-up authentication
  - Signature block preview
- **actions**:
  - Sign
  - Decline with reason
  - Delegate
  - Save for later
- **access**: Assigned signer with valid in-date certificate where required

#### Signature requests `/signing/requests` (E-signatures & tamper-evident records)

Track requests raised by the user or project.

- **layout**: Table with row drawer.
- **sections**:
  - Requests table (record, version hash, signers, order, status, created)
  - Request detail drawer
- **actions**:
  - Remind
  - Void
  - Verify
  - View
- **access**: signing.request; void needs signing.manage

#### Signature request setup `/signing/requests/new` (E-signatures & tamper-evident records)

Create a requirement against a document version.

- **layout**: Stepper form.
- **sections**:
  - Document version picker
  - Signers and order
  - Meaning
  - Step-up policy
  - Provider (in-app, DocuSign, Adobe)
- **actions**:
  - Send request
  - Save draft
  - Cancel
- **access**: signing.request

#### Attestation register `/signing/attestations` (E-signatures & tamper-evident records)

Searchable append-only register of attestations with validity state.

- **layout**: Table with filter bar and detail drawer.
- **sections**:
  - Table (signer, record, meaning, auth strength, device time, server time, hash, valid)
  - Manifest view
  - Audit chain position
- **actions**:
  - Verify
  - Export evidence bundle
  - View manifest
  - Filter
- **access**: signing.audit; auditors read-only

#### Public verification page `/verify/:token` (E-signatures & tamper-evident records)

Let third parties verify a signed PDF without logging in.

- **layout**: Minimal public page served from the separate portal domain.
- **sections**:
  - Upload or token lookup
  - Verification result
  - Signer and time details
  - Manifest download
- **actions**:
  - Verify file
  - Download manifest
  - Download verifier instructions
- **access**: Anyone with a valid token; rate-limited, no tenant data beyond the signature

#### Mobile signing `/m/signing` (E-signatures & tamper-evident records)

Sign on site including offline attestations with deferred sealing.

- **layout**: Mobile review screen with signature step and offline banner.
- **sections**:
  - Pending signatures
  - Document summary and hash
  - Step-up prompt
  - Offline queue status
- **actions**:
  - Sign
  - Decline
  - Queue offline attestation
- **access**: Assigned signers; offline allowed only for permitted types

#### Signing settings `/settings/signing` (E-signatures & tamper-evident records)

Configure meanings, consent text, step-up, providers, keys and retention.

- **layout**: Tabbed settings.
- **sections**:
  - Signature meanings
  - Consent statement library
  - Step-up policy per record type
  - Provider connections
  - KMS key and seal config
  - Retention and Object Lock
  - Trusted time source
  - Offline signing
  - Bulk signing allowed types
  - Terminology labels
- **actions**:
  - Save
  - Test provider
  - Add consent statement
- **access**: signing.admin; Object Lock changes need security admin sign-off
