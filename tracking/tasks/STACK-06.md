# STACK-06 — Mailer capability: SMTP adapter (Coolify, dev) and SES adapter (AWS)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`stack`](../../docs/blueprint/modules/stack/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | STACK-02, OPS-02 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/stack/README.md`](../../docs/blueprint/modules/stack/README.md)
3. ADRs: 0003 (jobs and outbox), 0005 (Keycloak sends its own verify and reset mails)
4. `apps/api/aip/platform/capabilities/` (protocols, settings, adapter selection)

## Spec

Give the backend one way to send transactional email (invites, digests, notifications): a `Mailer`
protocol selected by `MAILER=smtp|ses`, so Coolify and dev use any SMTP server (Mailpit in compose)
and AWS uses Amazon SES in `ap-southeast-2`.

- **files**:
  - apps/api/aip/platform/capabilities/protocols.py (add `Mailer`, `EmailMessage`)
  - apps/api/aip/platform/capabilities/adapters/smtp.py
  - apps/api/aip/platform/capabilities/adapters/ses.py
  - apps/api/aip/platform/capabilities/settings.py
  - apps/api/tests/platform/capabilities/test_mailer.py
  - infra/docker-compose.yml (API `MAILER=smtp`, `SMTP_HOST=mailpit`)
- **steps**:
  - 1. `Mailer.send(message)` takes from, to, subject, text and optional HTML, plus a `tenant_id` tag
    and an idempotency key. No attachments in this task.
  - 2. SMTP adapter (aiosmtplib or stdlib in a thread): STARTTLS when `SMTP_STARTTLS=true`, credentials
    as `SecretStr`.
  - 3. SES adapter (aioboto3 `sesv2.send_email`): credentials from the default chain (ECS task role),
    optional `SES_CONFIGURATION_SET`, tenant tag as a message tag.
  - 4. Sending runs in a worker job (queue `default`), never inside the request; a failed send retries
    with backoff and lands in the job's failed state, not lost.
  - 5. Logs carry the message id and tenant, never the recipient address or body (PII scrubber).
  - 6. Document in the compose file and `.env.example` how Keycloak's `KC_SMTP_*` points at SES SMTP
    (`email-smtp.ap-southeast-2.amazonaws.com:587`) in AWS.
- **acceptance**:
  - With `MAILER=smtp` the compose stack delivers a test mail to Mailpit.
  - With `MAILER=ses` against LocalStack (`--profile aws`, add `ses` to `SERVICES`) the send succeeds.
  - An unknown `MAILER` value fails at startup (`UnknownAdapterError`).
- **tests**:
  - **unit**:
    - Settings with `MAILER=ses` select the SES adapter; `MAILER=nope` raises.
    - A log line from a send contains no `@` address.
  - **integration**:
    - Testcontainers Mailpit: send, then the Mailpit API lists one message with the subject.
    - LocalStack SES: send returns a message id.
    - A send job that fails twice then succeeds is delivered once.
