// TESTING-09: the two fixture tenants' users (kaefer-demo and tenant-b), from the environment only.
// CI passes the dev realm users; the demo deploy passes GitHub environment secrets. Never hard-code
// credentials here, and never skip when one is missing: a missing variable is a broken setup.
export interface TenantUser {
  /** Fixture tenant slug, for messages only. */
  tenant: "kaefer-demo" | "tenant-b";
  email: string;
  password: string;
}

function required(env: NodeJS.ProcessEnv, name: string): string {
  const value = env[name]?.trim();
  if (!value) throw new Error(`Missing ${name}`);
  return value;
}

export function tenantUsers(env: NodeJS.ProcessEnv = process.env): { a: TenantUser; b: TenantUser } {
  return {
    a: { tenant: "kaefer-demo", email: required(env, "E2E_USER_A"), password: required(env, "E2E_PASS_A") },
    b: { tenant: "tenant-b", email: required(env, "E2E_USER_B"), password: required(env, "E2E_PASS_B") },
  };
}

/** TESTING-12: the kaefer-demo viewer, a seeded user who holds no role (so no `project.create`). */
export function viewerUser(env: NodeJS.ProcessEnv = process.env): TenantUser {
  return { tenant: "kaefer-demo", email: required(env, "E2E_USER_VIEWER"), password: required(env, "E2E_PASS_VIEWER") };
}
