# Brief


PRODUCT BRIEF
- Audience: EPC / megaproject teams, Engineering & inspection firms, Main contractors
- Segment: Business (mid-market)
- Delivery: Hybrid
- Identity: SSO via SAML 2.0, SCIM provisioning, MFA enforced, Email + password, Magic link / PIN
- Regions: Australia, New Zealand, Asia, UK
- Compliance: SOC 2 Type II, ISO 27001, IRAP (AU government), Australian Privacy Act, Records retention / legal hold
- Scale: 500-5,000 users
- Notes: Kaefer for first customer on their construction remediation projects for Rio Tinto, then Aquire other customers and branch out to different markets so the system needs to be easily customisable, change terms,names, to suit different markets. Use one to many style system, asset centric with asset hiarchy tree,

Tech stack: TypeScript end to end
- Backend: Node 22, NestJS, Drizzle or Prisma, Zod
- Data: PostgreSQL, Redis, BullMQ for jobs
- Frontend: Next.js or React + Vite, TanStack, Radix-based components
- Identity: WorkOS or Auth0 for SSO and SCIM, or self-hosted Keycloak
- BIM: Python sidecar for IFC (IfcOpenShell) and CAD conversion
- Hosting: Containers on Coolify, AWS ECS or Azure Container Apps

Notes: Will run it on my own hosting using coolify but on launch it will be using Amazon servers
