# E-signatures & tamper-evident records (`signing`)

- **Group:** Documents & records
- **Phase:** P2

What it is
A jurisdiction-neutral signature workflow and attestation registry that gives inspections, diaries, approvals and published records legally defensible signatures and tamper-evident storage. It is provider-neutral: it binds signer, qualification, document hash and time, and integrates external e-signature providers rather than building one. Suggested phase P2. In AIP it was deferred until a report engine exists (SIMPLIFICATIONS 'E-signatures' row); a profile signature card already exists.

What it does
- In-app sign-off stores an attestation (signer identity, auth strength, IP, trusted time source, document SHA-256, statement and consent text) chained into the append-only audit log.
- The PDF is sealed with PAdES using KMS-held keys, with long-term validation data so seals stay verifiable after certificates expire.
- External parties sign through DocuSign or Adobe Sign via a provider abstraction. The signed artefact hash, signer authentication method and consent text are stored, and provider webhooks are verified.
- Corrections are superseding entries, never edits. Any edit after signing voids the seal and forces a superseding version and re-sign.
- Records under retention or legal hold go to S3 Object Lock.
- Routine sign-offs use in-app attestations. High-value ITP hold points are never plain click-to-sign: they need at least step-up MFA.
- Only users with a valid, in-date certificate for the discipline can sign a given hold point (signer delegation and competency link).
- Offline sign-off is supported: the attestation and device time are captured on site, sealing is deferred, and both device time and server-verified time are recorded on sync.

Features
- Signature image captured on profile and applied to reports as visible signature blocks (date, name, role)
- Attestation record: who, auth strength, IP, timestamp, document SHA-256
- PAdES PDF seal with KMS keys
- External e-signature provider integration (DocuSign, Adobe Sign)
- Verification page and manifest for any signed PDF
- S3 Object Lock for records under retention or legal hold
- Signature meaning and consent statement library, configurable per record type and market, tenant-editable
- Step-up re-authentication policy per signature requirement (MFA or PIN re-entry for hold points and certificate sign-off)
- Signature invalidation on content change
- Offline-captured sign-off with deferred sealing
- Signed evidence bundle export: PDF, attestation manifest, hash list and verification instructions, with an independent verifier script
- Signer delegation and competency link to in-date discipline certificates
- Actions: request, sign, decline, void, verify

Interactions
- Report engine and published records: signature blocks
- Audit trail, activity and timeline: hash chain, with periodic anchoring to S3 Object Lock (compliance mode) or an external timestamp
- Site diary and field reports: daily seal
- Inspections, ITPs and hold points: multi-party sign-off
- Handover, data books and submissions: signed packs
- Shared approval engine for routing; file_approvals can invoke it at final approval; record_publishing, inspections and closeout request signatures
- Reads documents, users, projects and certificates; emits signing.completed to notifications and cde

Data
- SignatureRequirement: document version, required signers, order, meaning (author, review, approve), step-up policy
- Attestation: signer, auth method and strength, IP, timestamp (device and server time where offline), document hash, statement; append-only and hash-chained
- ProviderEnvelope: DocuSign or similar reference
- Consent statement library entries per record type and market
- Audit store permissions are separate from application admin so a compromised admin cannot rewrite history

Pages
- Signer inbox
- Signature request setup
- Attestation register with verification
- Signature manifest view
- Public or token-based verification page

Decisions and notes
- Owner accepted: consent statement library, step-up policy, invalidation on change, offline deferred sealing, evidence bundle export, delegation and competency link.
- Use pyHanko with KMS keys and stay on Python; node-signpdf is weaker.
- PAdES keys sit in KMS with dedicated roles.
- Legal weight depends on key custody and verifiability.
- Avoid claiming legal validity across jurisdictions (AU, NZ, UK, Asia differ) without advice; confirm Electronic Transactions Act implications with counsel and check customer contract requirements.
- Competitor gap: signatures inside inspection sign-off with credential and eligibility checks.
- Supports IRAP and ISO 27001 logging controls.
- Terminology is renamable per market.

Open questions
- Retention periods must be settled before enabling Object Lock compliance mode, because it cannot be undone. What are they per record type?
- Which independent trusted time authority will be used?
- Does the owner want bulk signing of routine records such as daily diaries (seen in market, not yet accepted)?
- Do Kaefer's contract requirements dictate a specific signature standard or provider?

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-stack.md`](advice-stack.md) — Tech stack advisor
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
