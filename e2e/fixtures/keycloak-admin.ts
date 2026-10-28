// TESTING-12: the Keycloak admin REST API, for the journeys that must look at (or end) the aip
// realm's SSO sessions directly. CI passes the compose stack's bootstrap admin (public dev-only
// values, as for the realm users); the demo has no such secret, so only `@skeleton` journeys use
// this. Never skip when a variable is missing: a missing variable is a broken setup.
import { expect, request, type APIRequestContext } from "@playwright/test";

export interface KeycloakAdminConfig {
  url: string;
  username: string;
  password: string;
}

function required(env: NodeJS.ProcessEnv, name: string): string {
  const value = env[name]?.trim();
  if (!value) throw new Error(`Missing ${name}`);
  return value;
}

export function keycloakAdminConfig(env: NodeJS.ProcessEnv = process.env): KeycloakAdminConfig {
  return {
    url: required(env, "E2E_KEYCLOAK_URL").replace(/\/+$/, ""),
    username: required(env, "E2E_KEYCLOAK_ADMIN"),
    password: required(env, "E2E_KEYCLOAK_ADMIN_PASSWORD"),
  };
}

const REALM = "aip";

/** A thin admin client. Each call takes a fresh token: master-realm admin tokens live 60 s. */
export class KeycloakAdmin {
  private constructor(
    private readonly http: APIRequestContext,
    private readonly config: KeycloakAdminConfig,
  ) {}

  static async connect(config: KeycloakAdminConfig = keycloakAdminConfig()): Promise<KeycloakAdmin> {
    return new KeycloakAdmin(await request.newContext({ baseURL: config.url }), config);
  }

  async dispose(): Promise<void> {
    await this.http.dispose();
  }

  private async token(): Promise<string> {
    const response = await this.http.post("/realms/master/protocol/openid-connect/token", {
      form: { grant_type: "password", client_id: "admin-cli", username: this.config.username, password: this.config.password },
    });
    expect(response.status(), "the Keycloak admin signs in").toBe(200);
    return ((await response.json()) as { access_token: string }).access_token;
  }

  private async call(method: "GET" | "POST", path: string): Promise<unknown> {
    const response = await this.http.fetch(`/admin/realms/${REALM}${path}`, {
      method,
      headers: { authorization: `Bearer ${await this.token()}` },
    });
    expect(response.ok(), `Keycloak admin ${method} ${path} answers ${response.status()}`).toBe(true);
    return response.status() === 204 ? null : response.json();
  }

  /** The aip realm user id for `email` (the brokered account the first sign-in created). */
  async userId(email: string): Promise<string> {
    const users = (await this.call("GET", `/users?email=${encodeURIComponent(email)}&exact=true`)) as { id: string }[];
    const [user] = users;
    expect(users, `the aip realm has exactly one user ${email}`).toHaveLength(1);
    return user?.id ?? "";
  }

  /** The ids of the user's live SSO sessions in the aip realm. */
  async sessionIds(userId: string): Promise<string[]> {
    const sessions = (await this.call("GET", `/users/${encodeURIComponent(userId)}/sessions`)) as { id: string }[];
    return sessions.map((s) => s.id).sort();
  }

  /** Like `sessionIds`, by email; none when the user has never signed in (no brokered account yet). */
  async sessionIdsFor(email: string): Promise<string[]> {
    const users = (await this.call("GET", `/users?email=${encodeURIComponent(email)}&exact=true`)) as { id: string }[];
    const [user] = users;
    return user ? this.sessionIds(user.id) : [];
  }

  /** Admin "Sign out" of every session of the user; Keycloak sends back-channel logout to the API. */
  async logoutUser(userId: string): Promise<void> {
    await this.call("POST", `/users/${encodeURIComponent(userId)}/logout`);
  }
}
