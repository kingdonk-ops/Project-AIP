# Integrations & webhooks — Security advisor


- **note**: Outbound connectors and webhooks create SSRF and data-leak paths. Use an egress allowlist, signed payloads, per-integration scopes and a delivery log. Store client credentials in a secrets manager and rotate them.
