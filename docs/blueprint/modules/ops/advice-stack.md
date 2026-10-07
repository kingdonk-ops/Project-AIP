# Operations, hosting & deployment — Tech stack advisor


- **note**: Do IaC for AWS from the start, but keep Fargate and RDS footprints small until real load arrives. Use ADOT/OpenTelemetry, Sentry, and a Postgres-backed job state table; Procrastinate or arq both fit.
