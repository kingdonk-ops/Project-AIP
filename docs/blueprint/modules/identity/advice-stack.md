# Users, sign-in & SSO — Tech stack advisor


- **note**: WorkOS covers SAML, OIDC and SCIM with a per-customer admin portal. Magic links, PINs and device binding are custom code in FastAPI, with hashed single-use tokens and POST confirmation to defeat email scanners.
