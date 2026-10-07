# Database & schema conventions — Security advisor


- **note**: Verify tenant_id and RLS on all existing AIP tables, and make the app role non-owner without BYPASSRLS. Validate JSONB against per-type schemas server-side. Keep migrations on a separate privileged role, and make sure append-only tables cannot be altered by the app role.
