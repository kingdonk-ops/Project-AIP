# Tenancy, organisations & data residency — Tech stack advisor


- **note**: Pooled RLS plus a siloed Terraform stack from one codebase is realistic. Per-tenant KMS keys and crypto-shredding are sound, but keep legal hold exceptions in mind when shredding.
