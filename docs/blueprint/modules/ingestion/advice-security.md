# Inbound capture & connectors — Security advisor


- **note**: Inbound email, webhooks and watched folders let outsiders inject content. Keep it disabled by default, verify senders and HMAC with replay windows, and create drafts only. Run all channels through the same quarantine pipeline and rate-limit per alias.
