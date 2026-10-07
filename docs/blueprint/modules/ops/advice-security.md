# Operations, hosting & deployment — Security advisor


- **note**: Coolify is fine for local, dev and demo with synthetic data, but production and staging belong on AWS from IaC. Add WAF, private subnets, secrets manager, centralised logs without PII, tested PITR restores and a patch cadence. Document admin access paths with MFA and session logging.
