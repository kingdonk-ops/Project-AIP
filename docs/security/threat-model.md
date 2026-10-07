# Threat model

- **Task:** SECURITY-01 · **Owner:** security programme (`security` module) · **Date:** 2026-10-07
- **Status:** first version, written before schema design. Review it whenever an ADR in this document changes,
  before the portal is enabled for an external customer, and before the first pen test.
- **Shape is enforced:** `tools/ci/check_security_docs.py` (CI `docs` job, `make check-docs`) fails if any of the
  six threat areas below, or any of their four subsections, goes missing.

## Scope and method

The system is a multi-tenant construction quality platform: a FastAPI modular monolith (ADR 0001, 0004), Postgres 16
with pooled tenancy under row-level security (ADR 0002), Procrastinate jobs with a Postgres outbox and one-shot
sandboxed workers (ADR 0003), Keycloak for staff sign-in with app-issued sessions (ADR 0005), and three Vite
frontends: staff web, field PWA and the client/subcontractor portal on its own origin (ADR 0004, 0005).

Each area lists its assets, threats grouped by STRIDE (Spoofing, Tampering, Repudiation, Information disclosure,
Denial of service, Elevation of privilege), the controls that answer them, and the risk left over. Every control
cites the ADR it relies on. A control marked **(proposed)** has no accepted ADR or task yet; its gap is named in
*Residual risk* and in [Open items](#open-items). Risk numbers `R1`…`R12` refer to the top risks in the security
specialist review ([`docs/reviews/01-security.md`](../reviews/01-security.md)), which predates the Python decision;
its NestJS/BullMQ wording is translated with the table in ADR 0001.

### Controls every area relies on

- **Tenant isolation (R1, ADR 0002).** Every table has `tenant_id` and `FORCE ROW LEVEL SECURITY`. Every request and
  job runs inside `with_tenant`, which opens a transaction and calls `set_config('app.tenant_id', ..., true)`
  (transaction-local; session-level `SET` is banned). Policies use
  `NULLIF(current_setting('app.tenant_id', true), '')::uuid` in both `USING` and `WITH CHECK`, so an unset context
  fails closed. Runtime roles `aip_app` and `aip_jobs` are not table owners and have no `BYPASSRLS`; `aip_owner` runs
  migrations only. An import-linter rule bans engines or connections outside `aip/platform/db`.
- **Jobs carry tenant context (ADR 0003).** Every job payload carries `tenant_id` and the handler re-enters
  `with_tenant`. Jobs are enqueued in the same transaction as the domain change.
- **Sessions (ADR 0005).** Browsers never hold Keycloak tokens. The backend issues an opaque `__Host-` cookie backed
  by a `user_session` row (Postgres, Redis cache), revoked instantly on logout or SCIM deprovisioning.
- **Single authorisation path.** Authorisation goes only through the policy service plus RLS, deny by default
  (AGENTS.md hard rules; ACCESS tasks).
- **Licensing (ADR 0009).** Only permissive open-source or AWS components; AGPL/GPL are denied, which also keeps
  AGPL code out of the sandbox images. See [`provenance-log.md`](provenance-log.md) for the clean-room record.

## Field PIN and magic link

### Assets

- Field-worker shift sessions and the device JWT (ES256) used for offline sync.
- Registered field devices: the device-bound private key and the hashed PIN.
- Single-use magic-link tokens sent to field workers.
- Inspection evidence, diary entries and sign-offs captured offline and synced later.

### Threats (STRIDE)

- **Spoofing:** a shared or shoulder-surfed PIN used on another worker's device; online PIN guessing; a magic link
  forwarded, phished, or pre-fetched by an email or chat link scanner; a stolen device used before it is revoked.
- **Tampering:** offline records edited on the device before sync; replay of an old sync batch.
- **Repudiation:** a worker denies a sign-off made on a shared device.
- **Information disclosure:** a magic-link token leaked through URL logs, browser history or `Referer`; offline data
  on a lost device.
- **Denial of service:** PIN lockout used to lock out a crew; link-issue endpoint used to spam inboxes.
- **Elevation of privilege:** a PIN-only credential used for an action that needs `aal2` (hold-point release).

### Controls

- Field sign-in is **device-bound key + PIN**; the PIN is hashed with argon2-cffi and is useless without the
  registered device key (ADR 0005).
- Magic links are **single-use and POST-confirmed**: opening the link shows a confirm page, and only the POST
  consumes the token, so link scanners and pre-fetchers cannot burn or use it (ADR 0005).
- Field sessions are short shift sessions; sync uses a device JWT (ES256), separate from the browser session cookie
  (ADR 0005).
- Device + PIN counts as `aal2` for critical actions only on a registered device; every sign-off records
  `assurance_level`, `method`, `authenticated_at` and the device ID (ADR 0010).
- SCIM deprovisioning revokes sessions, devices and links in one transaction, target ≤ 60 s (ADR 0005).
- Synced records are written through `with_tenant` and RLS like any other write (ADR 0002).
- **(proposed, R3)** Numeric policy: link token ≥ 128-bit, stored hashed, 10–15 min TTL; PIN ≥ 6 digits; per-device
  and per-IP rate limits (`limits`, ADR 0005) with lockout and supervisor alert.

### Residual risk

- Credential numbers (token entropy and TTL, PIN length, lockout thresholds, idle and absolute session timeouts) are
  not yet fixed in an ADR (R3). Owner: IDENTITY tasks.
- Offline data on a lost device stays readable until the device is revoked; on-device encryption is set by the
  offline module.
- A PIN shared together with the device defeats the second factor; ADR 0010 accepts this for `aal2` on registered
  devices, and countersign remains the fallback.

## Portal

### Assets

- Portal sessions for client and subcontractor users, held in a separate cookie and session store.
- Hold-point witness and counter-sign actions, and the records they produce.
- Shared project documents, drawings and inspection results visible to external parties.

### Threats (STRIDE)

- **Spoofing:** a portal magic link forwarded to someone else; phishing pages imitating the portal.
- **Tampering:** cross-site request forgery against portal actions; an external user editing records outside the
  scope they were granted.
- **Repudiation:** a client denies a witness or counter-signature.
- **Information disclosure:** IDOR across projects or tenants; staff cookies sent to the portal origin (or the
  reverse); share links leaked through referrers.
- **Denial of service:** bulk link requests; expensive document rendering triggered from the portal.
- **Elevation of privilege:** portal roles granted rights beyond the decided first-release scope (read-only plus
  hold-point witness and counter-sign); a portal user reaching staff routes.

### Controls

- The portal runs on its **own origin** with its own cookie and session store, so staff `__Host-` cookies are never
  sent to it and portal sessions cannot call staff routes (ADR 0005, ADR 0004).
- Portal sign-in is a magic link on the portal origin; counter-signing needs a passkey (ADR 0005).
- Counter-signatures meet the tenant's assurance minimum or fall back to `pending_countersign`; both people and both
  assurance levels are on the record (ADR 0010).
- Every portal query runs under `with_tenant` and RLS, with policy-service checks for project scope (ADR 0002).
- **(proposed, R3, SECURITY-11)** CSRF protection for cookie sessions, CORS allow-list, strict CSP, tokens never in
  URLs that reach logs or referrers.

### Residual risk

- The access matrix grants Client Reviewer `approve` and `create` rights beyond the decided portal scope
  (review contradictions). Trim before the portal is enabled for any customer.
- A dedicated portal threat-model review and pen test are required before enabling it for Rio Tinto (review,
  "PORTAL gating"); no task exists yet.

## Inbound email and webhooks

### Assets

- Inbound email channels (e.g. RFI or diary-by-email) and their attachments.
- Webhook endpoints that receive events from integrations, and the per-integration shared secrets.
- Outbound webhook and connector configuration (target URLs, credentials).

### Threats (STRIDE)

- **Spoofing:** forged sender addresses; forged webhook calls without a valid signature.
- **Tampering:** webhook replay or reordering; malicious attachments entering storage.
- **Repudiation:** no record of which external system caused a change.
- **Information disclosure:** server-side request forgery (SSRF) through user-configured outbound URLs,
  including DNS rebinding to cloud metadata or internal services; prompt injection carried into AI features.
- **Denial of service:** mail or webhook floods; oversized payloads.
- **Elevation of privilege:** an inbound message routed to the wrong tenant because tenant resolution trusts the
  sender.

### Controls

- Inbound handling is asynchronous: the receiver stores the raw item and enqueues a job in the same transaction;
  the handler re-enters `with_tenant` with the tenant resolved from the receiving address or endpoint, never from
  message content (ADR 0003, ADR 0002).
- Attachments enter only through the upload pipeline (quarantine, scan, sandboxed conversion) and are encrypted
  under the tenant's KMS key (ADR 0006; see *File uploads and sandboxed workers*).
- Every accepted event is written to the `domain_events` outbox, giving an audit trail of what caused each change
  (ADR 0003).
- **(proposed, R10)** Timestamped HMAC signatures with a replay window; per-integration secrets in Secrets Manager;
  request-size limits and rate limits per tenant; SPF/DKIM/DMARC evaluation recorded on inbound mail.
- **(proposed, R10)** All outbound calls go through one egress proxy with an allow-list and DNS-rebind protection.

### Residual risk

- No ADR yet covers webhook signing, replay windows or the egress proxy (review recommendation 9). Until then this
  area is the least specified and must not ship to production.
- Forged-but-DMARC-passing mail from a compromised customer mailbox is accepted; content is treated as untrusted data.

## Legal records

### Assets

- Signed inspection and ITP records, hold-point releases, approvals and their sign-off assurance metadata.
- The append-only audit log and domain-event outbox.
- PAdES-signed PDFs and the signing keys.

### Threats (STRIDE)

- **Spoofing:** a shared password used to sign; a signer impersonated by someone holding their session.
- **Tampering:** an operator or attacker with database access edits or deletes a signed record or audit row.
- **Repudiation:** a signer denies a sign-off; weak evidence of who signed and how they authenticated.
- **Information disclosure:** exports of legal records leaking across tenants.
- **Denial of service:** destruction of records through deletion or crypto-shred while under legal hold.
- **Elevation of privilege:** super-admin or support staff altering records (R7).

### Controls

- Critical actions (hold-point release, witness/counter-sign, ITP sign-off, record seal) require a fresh check at
  signing: passkey, device + PIN, TOTP or IdP MFA (`aal2` by default); the tenant minimum cannot go below `aal1`, and
  lowering it needs step-up and is audit-logged (ADR 0010).
- Every signature stores `assurance_level`, `method`, `authenticated_at` and device ID; reports and exports show
  them (ADR 0010).
- Append-only tables have UPDATE and DELETE revoked for the runtime role, created from the append-only migration
  template and run as `aip_owner` only (ADR 0002).
- PDF signing runs with pyHanko inside a one-shot sandbox worker (ADR 0003, ADR 0009).
- Crypto-shred is always preceded by a legal-hold check; legal hold wins (ADR 0006).
- **(proposed, R6)** Per-tenant hash chain in the audit module, head anchored to S3 Object Lock in a separate AWS
  account, RFC 3161 timestamps, offline verifier.

### Residual risk

- Tamper evidence is not yet independent of the database: the hash chain, anchoring and time authority have no ADR
  (R6). Until then a database superuser could rewrite history undetected.
- Retention periods per record type are unset, so Object Lock compliance mode cannot be enabled.
- Signing key custody (KMS sign-only role) is undecided.

## AI

### Assets

- Tenant documents, transcripts and records sent to models as context.
- Prompts, completions and the AI data-flow register.
- Tool permissions granted to AI agents.

### Threats (STRIDE)

- **Spoofing:** content in a document or email posing as system instructions (prompt injection).
- **Tampering:** an agent tool call that changes records because injected text told it to.
- **Repudiation:** AI-generated content presented as a person's work without a record.
- **Information disclosure:** tenant data sent to a model vendor outside Australia or retained by the vendor;
  retrieval returning another tenant's or another project's documents; health or incident data sent unredacted.
- **Denial of service:** runaway token spend per tenant.
- **Elevation of privilege:** an agent acting with more rights than the requesting user.

### Controls

- AI calls go only through the AI gateway (AGENTS.md hard rules); no module calls a model vendor directly.
- Retrieval (pgvector) runs under `with_tenant` and RLS, so context comes only from the requesting tenant
  (ADR 0002).
- Textract and other AI-adjacent services are off by default per tenant and routed through the AI/data-flow register
  (ADR 0009).
- **(proposed, R8)** AI off by default per tenant; Bedrock in ap-southeast-2 with zero retention for AU tenants;
  redaction driven by data-classification tags before sending; agent tools read-only and executed with the user's
  own permissions; per-tenant token budgets.

### Residual risk

- The owner decision "Direct model vendor API" conflicts with the AU-residency position and the Bedrock
  recommendation (R8). No AI gateway ADR exists yet; this area must not process tenant data until one does.
- Prompt injection cannot be fully prevented; the mitigation is read-only tools and a person confirming every
  write.

## File uploads and sandboxed workers

### Assets

- Uploaded files (photos, drawings, PDFs, IFC models, email attachments) and their derived renditions.
- The quarantine and released S3 prefixes and their per-tenant KMS keys.
- The worker hosts and the network they sit on.

### Threats (STRIDE)

- **Spoofing:** files with a misleading extension or content type; presigned URLs reused for another tenant (R5).
- **Tampering:** malware or crafted files exploiting converters (PDF, IFC, OCR, image libraries).
- **Repudiation:** no record of who uploaded a file.
- **Information disclosure:** stored XSS through SVG or HTML served from the app origin; EXIF GPS leaking site
  locations; a converter exfiltrating data over the network; cross-tenant object reads.
- **Denial of service:** decompression bombs, huge files, converter hangs.
- **Elevation of privilege:** remote code execution in a converter reaching the API, database or other tenants' files.

### Controls

- Files enter only through the upload pipeline (AGENTS.md hard rules). Presigned PUTs set the tenant's KMS key
  (`x-amz-server-side-encryption-aws-kms-key-id`) and a per-tenant bucket policy rejects any other key, so **every
  upload is encrypted under its tenant's KMS key** and offboarding can crypto-shred it (ADR 0006).
- Conversion, OCR, IFC, image processing and PDF signing run in **one-shot sandbox containers** (ECS RunTask;
  `docker run` in dev) with **no network egress, non-root, a read-only filesystem, and CPU, memory and time caps**;
  files are passed by S3 key (ADR 0003).
- Sandbox jobs carry `tenant_id` and re-enter `with_tenant` (ADR 0003, ADR 0002).
- OCR uses Tesseract + pypdfium2 + pikepdf only; no Ghostscript or PyMuPDF (ADR 0009).
- **(proposed, R5)** Quarantine bucket with release only by the scan worker; ClamAV; magic-byte checks; size and
  decompression caps; separate file-serving domain with `Content-Disposition: attachment` for active types; SVG/HTML
  sanitising; EXIF GPS stripped from shared copies.

### Residual risk

- ADR 0006 (per-tenant KMS key) is still **proposed**; if the owner rejects it, crypto-shred and this control fall
  back to prefix deletion (R2).
- The quarantine/scan/release state machine and the separate file domain are UPLOADS tasks not yet built (R5).
- A converter zero-day can still compromise one container; the blast radius is one job's files, bounded by no egress
  and a short lifetime.

## Open items

| Ref | Gap | Where it should be settled |
|---|---|---|
| R2 | Per-tenant KMS key is proposed, not accepted | ADR 0006 (owner to confirm) |
| R3 | Numbers for bearer credentials and session timeouts | new identity credential-policy ADR; IDENTITY tasks |
| R5 | Upload quarantine, scan and file-serving domain | UPLOADS tasks |
| R6 | Independent tamper evidence (hash chain, anchoring, TSA) | new audit ADR; AUDIT tasks |
| R7 | Super-admin and support access without standing data access | new support-access ADR; TENANCY-06 |
| R8 | AI provider, region and gateway | new AI gateway ADR |
| R9 | Supply chain (SBOM, scanning, signed images) | STACK-04, SECURITY-08 (to be converted per ADR 0001) |
| R10 | Webhook signing, replay window, egress proxy | new outbound/egress ADR |
| R11 | Synthetic data only outside AWS; secrets management | OPS tasks |
| R12 | Legal hold vs purge vs crypto-shred precedence | ADR 0006 states hold wins; full precedence ADR pending |
