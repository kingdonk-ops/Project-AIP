# Database & schema conventions — Tech stack advisor


- **note**: Forward-only raw-SQL Alembic migrations fit the stated conventions. Confirm RLS is on every table and the app role is non-owner so RLS applies. Use PgBouncer or RDS Proxy carefully with SET LOCAL tenancy.
