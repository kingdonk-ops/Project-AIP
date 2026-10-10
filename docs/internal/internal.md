# Internal and company systems

Everything the company runs **around** Project-AIP: sales, contracts, invoicing, support, the public website,
compliance, and the external services the product itself depends on. Decided in [ADR 0017](../adr/0017-company-systems-and-contract-link.md)
(proposed, owner to confirm). The product's own design lives in `docs/blueprint/`.

> **Rules for this file.** This repository is **public** (checked 2026-10-10). Write structure and decisions only:
> no credentials, account ids, customer names, prices or contract terms. Those live in the company systems below.
> Making the repository private is an owner action tracked in [`tracking/OPEN-QUESTIONS.md`](../../tracking/OPEN-QUESTIONS.md).
> Tool names and licences are candidates as reported on 2026-10-10; re-check the licence and current status when one is adopted.

## 1. Boundary

| Data | Lives in | Never in |
|---|---|---|
| Tenant business data (inspections, assets, documents) | Product database and storage (AWS Sydney) | Any company system |
| Plan, term, seat limits, renewal date, `contract_ref`, monthly usage counts | Product (`tenant_subscription`, `tenant_usage`; ADR 0008) | |
| Prices, discounts, invoices, payments, contract PDFs, contacts | Company systems (CRM, contracts, accounting) | The product database |
| Support tickets and customer emails | Support desk (corp AWS account) | Public repository |

The product never holds prices or payment data. Plan structure and limits are in ADR 0008; the figures are set here, outside the repository. Company systems never hold tenant business data; a support
ticket that needs it uses the customer-approved, time-boxed support-access grant (TENANCY-06).

Company staff sign in through the **corporate identity provider**, not the product's Keycloak. Company
systems get their own AWS account and share no database with the product.

## 2. Systems register

Status: **proposed** = a recommendation awaiting the owner's choice, **decided** = recorded in an ADR.

| Function | Candidate | Licence (reported) | Runs on | Holds customer data | Product touchpoint | Status |
|---|---|---|---|---|---|---|
| CRM, quotes | Twenty (alt: EspoCRM) | AGPL-3.0 | corp account, Sydney | Yes (contacts) | Won deal supplies the tenant name and `contract_ref` | proposed |
| Contracts and e-signature | DocuSeal (alt: Documenso) | AGPL-3.0 | corp account | Yes (contracts) | Signed contract → `contract_ref`; never embedded in the product | proposed |
| Invoicing and accounting | Xero (AU GST and BAS) | Commercial | SaaS | Yes | Annual invoice from the contract; true-up from usage export | proposed |
| Subscription automation | None at launch (ADR 0008: contract billing, no payment provider) | n/a | n/a | n/a | Revisit Lago or ERPNext only with self-serve or metered billing | decided |
| Support desk and tickets | Zammad (alt: Chatwoot) | AGPL-3.0 (Chatwoot MIT core) | corp account | Yes | Support-access grants (TENANCY-06) | decided (owner 2026-10-10) |
| Help pages and product docs | Starlight (Astro), docs in the monorepo | MIT | static, web account | No | Versioned with releases | decided (owner 2026-10-10) |
| Marketing website | Astro, static | MIT | S3 + CloudFront, web account | No | None | decided (owner 2026-10-10) |
| Status page | Upptime or Uptime Kuma, off production infrastructure | MIT | separate provider | No | Reads `/health` (OPS-04) | decided (owner 2026-10-10) |
| Trust centre | Provided by the GRC tool | n/a | `trust.` subdomain | No | Publishes the sub-processor list | decided (owner 2026-10-10) |
| Compliance (GRC) | Comp AI, open source (owner 2026-10-10; alternatives CISO Assistant, Probo) | AGPL-3.0 | corp account | Evidence only | SECURITY-03 to 05 shrink: use the tool for the control catalogue, evidence and access reviews | decided |
| ISMS policies | Markdown in a private `isms` repo; PR approval is the approval record | n/a | GitHub | No | None | proposed |
| Company files and identity | Microsoft 365 Business Premium (Entra, Intune MDM) | Commercial | SaaS | Yes | None | proposed |
| Password manager | Bitwarden Teams | AGPL / commercial | SaaS | No | None | proposed |
| Website analytics | Umami | MIT | web account | No | None | proposed |
| On-call alerting | Free tier of a pager service | Commercial | SaaS | No | OPS-04 alerts | proposed |

**Licence handling.** [ADR 0011](../adr/0011-licence-policy-details.md) denies AGPL for what the product ships. An
unmodified AGPL tool run as a separate internal service is not shipped, so it is allowed. Do not embed, link or
bundle any of these into the product image or repo; inspection and hold-point sign-off stays in-app (ADR 0010).

**Consolidation options (owner to choose).**

- **D, lighter (leaning default for launch):** CRM + DocuSeal + Xero, joined by webhooks. Three small tools, each replaceable.
- **A, one console:** ERPNext + Frappe CRM + Helpdesk (GPLv3) with DocuSeal beside it. Subscriptions with seat quantity and auto-invoices are built in, at the cost of operating a larger system that is itself in audit scope.
- Odoo Community lacks subscriptions and e-signature (Enterprise only), so it does not meet the no-paid-licence rule.

## 3. Customer lifecycle and the product link

| Step | Company system | Product feature | Task |
|---|---|---|---|
| Quote and deal | CRM | none | none |
| Signed contract | Contracts (assigns `contract_ref`) | none | none |
| Provision tenant | Operator console | Wizard takes `contract_ref`, plan, term, seats, region; refuses a production term without it | TENANCY-05, ENT-01 |
| Sandbox first | | Sandbox tenant, config-bundle promotion to production | ADR 0008 |
| In-term | | Read-only plan and usage page `/settings/billing`; operator changes plan | ENT-01 |
| Month end | Accounting | Monthly `tenant_usage` snapshot; operator export (counts only) | ENT-01, ENT-02 |
| Renewal | CRM reminder | `renewal_date` visible to operators and the tenant admin | ENT-01 |
| Offboard | Contracts, accounting | Export, crypto-shred, deletion certificate | TENANCY-07 |

Data crossing the boundary, in both directions, is deliberately small:

- **In:** `contract_ref` (opaque id such as `C-2026-0042`), tenant slug and name, plan code and version, term, start, end and renewal dates, seat limits per user class, add-ons, region. Entered by an operator; a contract webhook may pre-fill the wizard later (ENT-02), never create a tenant by itself.
- **Out:** per month and tenant: active users per class, storage, job count, AI spend. No names or business data.

## 4. Hosting and domains

- AWS organisation accounts: management, security and log archive, prod, staging, backup (separate, Vault Lock), corp, web. Prod and staging follow OPS-07 to OPS-10.
- Hosts: `app.` product, `ops.` operator console (own origin, ADR 0017), `docs.` help, `support.` desk, `status.` (different provider), `trust.`, apex marketing site.
- Coolify (bytedock) is for dev and demo with **synthetic data only** (ADR 0007, OPS-11). Real data on it breaks the AU-residency claim and puts it in audit scope.

## 5. External services the product uses (sub-processor candidates)

| Service | Use | Status |
|---|---|---|
| AWS Sydney: ECS Fargate, RDS Postgres, ElastiCache or Valkey, S3, ECR, CloudFront, WAF | Hosting | decided |
| AWS KMS, one key per tenant | Envelope encryption | ADR 0006, proposed |
| AWS Secrets Manager, CloudTrail, GuardDuty, Security Hub, Backup (copy to Melbourne) | Security and recovery | decided, OPS-10 |
| AWS Textract | Optional OCR | ADR 0009, optional |
| AI model provider: Bedrock Sydney (default) and the direct vendor API (optional, per tenant) | AI assistant | decided, ADR 0019; verify in-region processing |
| Power BI (customer-owned) | A customer reads a read-only reporting feed with their own licences; no Microsoft service is run by us | later `professional` feature (ADR 0008 C) |
| Power BI Embedded or dedicated capacity | Paid Azure capacity, Microsoft as sub-processor, residency questions | **deferred**, owner decision and ADR needed |
| Transactional email (SES implied) | Invites, notifications | **undecided** |
| Error tracking (self-hosted Sentry or CloudWatch RUM) | Client errors, OPS-05 | **undecided** |
| GitHub: code, Actions, cosign | Build and signing | decided; in audit scope, not a data processor |
| Customer identity providers (Entra, Okta) | Federation | the customer's, not ours |

Anything in this table that processes customer data goes on the published sub-processor list before the first pilot.

## 6. Compliance programme

- **Frameworks that matter for the markets:** SOC 2 Type I, then ISO 27001; Australian Privacy Act (APPs) and Notifiable Data Breaches; IRAP later. UK GDPR only if there are UK users. HIPAA is dropped (no health data, owner 2026-10-10) and must not be claimed.
- **Do not build the GRC tool.** It is a product in itself and would put home-built code in the audit. Comp AI is chosen (Q6 answered). Start the evidence clock first and book the auditor.
- Auditors also cover people and devices: onboarding and offboarding, MDM, access reviews, vendor register, incident response.

## 7. Gaps to close before the first paying pilot

- Corporate identity with MFA, MDM on laptops, password manager.
- Onboarding and offboarding checklists, security awareness training, policy acceptance.
- Legal set: MSA, DPA, SLA, support schedule, privacy policy, terms of service, sub-processor list.
- Assurance: external penetration test (AU CREST provider), cyber and professional indemnity insurance, `security.txt` and disclosure page.
- On-call rota and alert routing.
- **Intellectual property.** Before incorporating or selling, obtain written confirmation of who owns the code, and check the employment agreement's IP and outside-work clauses. This is a legal question for the owner's lawyer, not this repository.

Open decisions are in [`tracking/OPEN-QUESTIONS.md`](../../tracking/OPEN-QUESTIONS.md) (items 17, 20, 21, 22 and 23).
