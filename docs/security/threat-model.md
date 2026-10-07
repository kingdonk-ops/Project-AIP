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
cites the ADR it relies on. A control is stated as established only when an **accepted** ADR, or an AGENTS.md hard
rule cited as such, establishes it. A control marked **(proposed, R<n>)** has no accepted ADR or task yet, and one
marked **(ADR 0006, proposed)** depends on an ADR the owner has not confirmed; each gap is named in *Residual risk*
and in [Open items](#open-items). Risk numbers `R1`…`R12` refer to the top risks in the security specialist review
([`docs/reviews/01-security.md`](../reviews/01-security.md)), which predates the Python decision; its NestJS/BullMQ
wording is translated with the table in ADR 0001. `R13` onwards are raised by this threat model.

### Controls every area relies on

- **Tenant isolation (R1, AGENTS.md hard rules, ADR 0002).** Every table has `tenant_id` and
  `FORCE ROW LEVEL SECURITY` (AGENTS.md hard rules), except the pre-login, non-RLS `login_directory` used for tenant
  resolution (ADR 0005). Every request and job runs inside `with_tenant`, which opens a transaction and calls
  `set_config('app.tenant_id', ..., true)` (transaction-local; session-level `SET` is banned). Policies use
  `NULLIF(current_setting('app.tenant_id', true), '')::uuid` in both `USING` and `WITH CHECK`, so an unset context
  fails closed. The runtime role `aip_app` is not the table owner and has no `BYPASSRLS`; `aip_owner` runs migrations
  only (ADR 0002). **(proposed, R1)** The same restriction for `aip_jobs`, with a CI check that no runtime role has
  `BYPASSRLS` or superuser. An import-linter rule bans engines or connections outside `aip/platform/db`.
- **Jobs carry tenant context (ADR 0003).** Every job payload carries `tenant_id` and the handler re-enters
  `with_tenant`. Jobs are enqueued in the same transaction as the domain change.
- **Sessions (ADR 0005).** Browsers never hold Keycloak tokens. The backend issues an opaque `__Host-` cookie backed
  by a `user_session` row (Postgres, Redis cache), revoked instantly on logout or SCIM deprovisioning.
- **Single authorisation path.** Authorisation goes only through the policy service plus RLS, deny by default
  (AGENTS.md hard rules; ACCESS tasks).
- **Licensing (ADR 0009).** Only permissive open-source or AWS components; GPL, AGPL and SSPL are denied, which also
  keeps AGPL code out of the sandbox images. The CI licence gate applies once STACK-04 lands; LGPL is allowed only
  after review (dynamically used, unmodified) per ADR 0009. See [`provenance-log.md`](provenance-log.md) for the
  clean-room record.

## Field PIN and magic link

### Assets

- Field-worker shift sessions and the device JWT (ES256) used for offline sync.
- Registered field devices: the device-bound private key and the hashed PIN.
- Single-use magic-link tokens sent to field workers.
- Inspection evidence, diary entries and sign-offs captured offline and synced later.

### Threats (STRIDE)

- **Spoofing:** a shared or shoulder-surfed PIN used on another worker's device; online PIN guessing; a magic link
  forwarded, phished, or pre-fetched by an email or chat link scanner; a stolen device used before it is revoked.
- **Spoofing (enrolment):** a rogue device enrolled for a worker by someone other than an authorised supervisor,
  giving a permanent `device_pin` factor.
- **Tampering:** offline records edited on the device before sync; replay of an old sync batch; the device clock
  set back so an offline sign-off carries a backdated `authenticated_at`.
- **Repudiation:** a worker denies a sign-off made on a shared device.
- **Information disclosure:** a magic-link token leaked through URL logs, browser history or `Referer`; offline data
  on a lost device; the pre-login `login_directory` used to enumerate tenants or valid emails.
- **Denial of service:** PIN lockout used to lock out a crew; link-issue endpoint used to spam inboxes.
- **Elevation of privilege:** a PIN-only credential used for an action that needs `aal2` (hold-point release).

### Controls

- Field sign-in is **device-bound key + PIN**; the PIN is hashed with argon2-cffi and is useless without the
  registered device key (ADR 0005).
- Magic links are **single-use and POST-confirmed**: opening the link shows a confirm page, and only the POST
  consumes the token, so link scanners and pre-fetchers cannot burn or use it (ADR 0005).
- Field sessions are short shift sessions; sync uses a device JWT (ES256), separate from the browser session cookie
  (ADR 0005).
- A registered company device key + PIN counts as two factors (`aal2`) for critical actions; every sign-off records
  `assurance_level`, `method`, `authenticated_at` and the device ID (ADR 0010).
- SCIM deprovisioning revokes sessions, devices and links in one transaction, target ≤ 60 s (ADR 0005).
- Synced records are written through `with_tenant` and RLS like any other write (ADR 0002).
- **(proposed, R3)** Numeric policy: link token ≥ 128-bit, stored hashed, 10–15 min TTL; PIN ≥ 6 digits; per-device
  and per-IP rate limits (`limits`, ADR 0005) with lockout and supervisor alert.
- **(proposed, R14)** Device enrolment: only a supervisor or tenant admin can register a field device, through an
  authenticated staff session; enrolment is audit-logged and the worker and admin are notified; devices are listed
  per worker and revocable; a device enrolled outside that flow is never trusted for `device_pin`.
- **(proposed, R15)** Offline clock tampering: the server records its own receipt time next to the device-supplied
  `authenticated_at` on every offline sign-off, flags skew beyond a tenant threshold for review, and reports show
  both times.
- **(proposed, R16)** `login_directory` lookups return the same response and timing whether or not an email domain
  or tenant slug exists, and are rate-limited per IP (`limits`, ADR 0005).

### Residual risk

- Credential numbers (token entropy and TTL, PIN length, lockout thresholds, idle and absolute session timeouts) are
  not yet fixed in an ADR (R3). Owner: IDENTITY tasks.
- Offline data on a lost device stays readable until the device is revoked; on-device encryption is set by the
  offline module.
- ADR 0010 counts device key + PIN as two factors (`aal2`). If a worker shares the PIN with someone who also has
  the device (e.g. a crew sharing one tablet), both factors are held by one other person and a sign-off can be made
  in the worker's name. This risk is not addressed by any ADR. Owner: product owner to accept or require per-worker
  devices or a passkey for critical actions; IDENTITY tasks.
- Device enrolment, offline clock skew and `login_directory` enumeration have no ADR or task (R14, R15, R16).

## Portal

### Assets

- Portal sessions for client and subcontractor users, held in a separate cookie and session store.
- Hold-point witness and counter-sign actions, and the records they produce.
- Shared project documents, drawings and inspection results visible to external parties.

### Threats (STRIDE)

- **Spoofing:** a portal magic link forwarded to someone else; phishing pages imitating the portal; session fixation
  (an attacker plants a session ID before the victim completes magic-link login); an open redirect after login used
  to send the user to a phishing page.
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
- Every portal query runs under `with_tenant` and RLS (ADR 0002), with policy-service checks for project scope
  (AGENTS.md hard rules).
- **(proposed, R3, SECURITY-11)** CSRF protection for cookie sessions, CORS allow-list, strict CSP, tokens never in
  URLs that reach logs or referrers.
- **(proposed, R17)** After magic-link login the portal discards any pre-login session and issues a new session ID
  (no session fixation), and post-login redirects accept only same-origin relative paths from an allow-list (no
  open redirect).
- **(proposed, R16)** The portal's tenant and email lookup gives uniform responses and is rate-limited, as for
  field sign-in.

### Residual risk

- The access matrix grants Client Reviewer `approve` and `create` rights beyond the decided portal scope
  (review contradictions). Trim before the portal is enabled for any customer.
- A dedicated portal threat-model review and pen test are required before enabling it for Rio Tinto (review,
  "PORTAL gating"); no task exists yet.
- Session fixation, open redirect and lookup enumeration protections are not specified anywhere yet (R16, R17).

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

- Any job an inbound item triggers carries `tenant_id` in its payload, and its handler re-enters `with_tenant`
  (ADR 0003, ADR 0002).
- Attachments are files, so they enter only through the upload pipeline (AGENTS.md hard rules).
- **(proposed, R10)** The receiver stores the raw item and enqueues its processing job in the same transaction; the
  tenant is resolved from the receiving address or endpoint, never from sender or message content; every accepted
  inbound event is written to the `domain_events` outbox so each change can be traced to its external source.
- **(proposed, R5)** Attachments pass quarantine, malware scan and sandboxed conversion before release; encryption
  under the tenant's KMS key (ADR 0006, proposed).
- **(proposed, R10)** Timestamped HMAC signatures with a replay window; per-integration secrets in Secrets Manager;
  request-size limits and rate limits per tenant; SPF/DKIM/DMARC evaluation recorded on inbound mail.
- **(proposed, R10)** All outbound calls go through one egress proxy with an allow-list and DNS-rebind protection.

### Residual risk

- No ADR yet covers webhook signing, replay windows or the egress proxy (review recommendation 9). Until then this
  area is the least specified and must not ship to production.
- Inbound tenant resolution (mapping a receiving address or webhook endpoint to a tenant) has no ADR yet (R10); a
  wrong mapping would write one tenant's mail into another tenant under a valid `with_tenant` context.
- Forged-but-DMARC-passing mail from a compromised customer mailbox is accepted; content is treated as untrusted data.

## Legal records

### Assets

- Signed inspection and ITP records, hold-point releases, approvals and their sign-off assurance metadata.
- The append-only audit log and domain-event outbox.
- PAdES-signed PDFs and the signing keys.

### Threats (STRIDE)

- **Spoofing:** a shared password used to sign; a signer impersonated by someone holding their session.
- **Tampering:** an operator or attacker with database access edits or deletes a signed record or audit row.
- **Repudiation:** a signer denies a sign-off; weak evidence of who signed and how they authenticated; an offline
  sign-off backdated through the device clock.
- **Information disclosure:** exports of legal records leaking across tenants.
- **Denial of service:** destruction of records through deletion or crypto-shred while under legal hold.
- **Elevation of privilege:** super-admin or support staff altering records (R7).

### Controls

- Critical actions (hold-point release, witness/counter-sign, ITP sign-off, record seal) require a fresh check at
  signing: passkey, device + PIN, TOTP or IdP MFA (`aal2` by default); the tenant minimum cannot go below `aal1`, and
  lowering it needs step-up and is audit-logged (ADR 0010).
- Every signature stores `assurance_level`, `method`, `authenticated_at` and device ID; reports and exports show
  them (ADR 0010).
- Append-only tables are created from the append-only migration template and migrations run as `aip_owner` only
  (ADR 0002 names the template; this is the intent). **(proposed, R6)** The template revokes UPDATE and DELETE from
  every runtime role, with a CI test that checks the grants.
- PDF signing runs with pyHanko inside a one-shot sandbox worker (ADR 0003, ADR 0009).
- Crypto-shred is always preceded by a legal-hold check; legal hold wins (ADR 0006, proposed).
- **(proposed, R15)** Offline sign-offs store the server receipt time beside the device-supplied `authenticated_at`;
  skew beyond a threshold is flagged on the record and in reports.
- **(proposed, R6)** Per-tenant hash chain in the audit module, head anchored to S3 Object Lock in a separate AWS
  account, RFC 3161 timestamps, offline verifier.

### Residual risk

- Tamper evidence is not yet independent of the database: the hash chain, anchoring and time authority have no ADR
  (R6). Until then a database superuser could rewrite history undetected.
- Retention periods per record type are unset, so Object Lock compliance mode cannot be enabled.
- Signing key custody (KMS sign-only role) is undecided.
- Crypto-shred and its "legal hold wins" rule depend on ADR 0006, which the owner has not confirmed (R2, R12). If it
  is rejected there is no crypto-shred and the hold/purge precedence must be set elsewhere.
- `authenticated_at` on offline sign-offs comes from the device clock; until R15 is built a backdated sign-off cannot
  be told apart from a genuine one.

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
- The quarantine and released S3 prefixes and their per-tenant KMS keys (ADR 0006, proposed).
- The worker hosts and the network they sit on.

### Threats (STRIDE)

- **Spoofing:** files with a misleading extension or content type; presigned URLs reused for another tenant (R5).
- **Tampering:** malware or crafted files exploiting converters (PDF, IFC, OCR, image libraries).
- **Repudiation:** no record of who uploaded a file.
- **Information disclosure:** stored XSS through SVG or HTML served from the app origin; EXIF GPS leaking site
  locations; a converter exfiltrating data over the network; cross-tenant object reads, including by a compromised
  sandbox container using over-broad S3 credentials.
- **Denial of service:** decompression bombs, huge files, converter hangs.
- **Elevation of privilege:** remote code execution in a converter reaching the API, database or other tenants' files.

### Controls

- Files enter only through the upload pipeline (AGENTS.md hard rules).
- Presigned PUTs set the tenant's KMS key (`x-amz-server-side-encryption-aws-kms-key-id`) and a per-tenant bucket
  policy rejects any other key, so every upload is encrypted under its tenant's KMS key and offboarding can
  crypto-shred it (ADR 0006, proposed).
- Conversion, OCR, IFC, image processing and PDF signing run in **one-shot sandbox containers** (ECS RunTask;
  `docker run` in dev) with **no network egress, non-root, a read-only filesystem, and CPU, memory and time caps**;
  files are passed by S3 key (ADR 0003).
- Sandbox jobs carry `tenant_id` and re-enter `with_tenant` (ADR 0003, ADR 0002).
- OCR uses Tesseract + pypdfium2 + pikepdf only; no Ghostscript or PyMuPDF (ADR 0009).
- **(proposed, R13)** Sandbox S3 access is scoped per job: each one-shot container gets either presigned URLs for
  exactly its input and output keys or short-lived credentials limited to that tenant's prefix, never the worker's
  broad role, so a compromised converter cannot read other tenants' objects.
- **(proposed, R5)** Quarantine bucket with release only by the scan worker; ClamAV; magic-byte checks; size and
  decompression caps; separate file-serving domain with `Content-Disposition: attachment` for active types; SVG/HTML
  sanitising; EXIF GPS stripped from shared copies.

### Residual risk

- ADR 0006 (per-tenant KMS key) is still **proposed**; if the owner rejects it, crypto-shred and this control fall
  back to prefix deletion (R2).
- The quarantine/scan/release state machine and the separate file domain are UPLOADS tasks not yet built (R5).
- A converter zero-day can still compromise one container. With no egress and a short lifetime the blast radius is
  one job's files only once per-job S3 scoping (R13) is built; until then it is whatever the container's S3
  credentials can reach.

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
| R12 | Legal hold vs purge vs crypto-shred precedence | ADR 0006 (proposed) states hold wins; full precedence ADR pending |
| R13 | Per-job, per-tenant-prefix S3 credentials or presigned URLs for sandbox workers | UPLOADS tasks; ADR 0003 follow-up |
| R14 | Field device enrolment: who registers and approves a device; rogue enrolment | identity credential-policy ADR; IDENTITY tasks |
| R15 | Offline clock tampering: server receipt time and skew flag on offline sign-offs | IDENTITY-07 / APPROVALS tasks; ADR 0010 follow-up |
| R16 | `login_directory` and portal lookup enumeration: uniform responses and rate limits | identity credential-policy ADR; IDENTITY tasks |
| R17 | Portal session fixation and open redirect after magic-link login | SECURITY-11; portal tasks |
