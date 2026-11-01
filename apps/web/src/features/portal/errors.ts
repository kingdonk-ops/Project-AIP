/**
 * The portal admin API's error answers as terms (PORTAL-07). PORTAL-01 answers a domain error as
 * `{code, ...extra}` (`PROJECT_CLOSED` names its `projectId`, `ASSET_NOT_FOUND` its `assetId`);
 * identity's invite errors keep their own codes; a missing or other tenant's record is 404
 * `NOT_FOUND`. Every known code has a `portal.error.<code>` term.
 */
import { t } from "../shell/t";

const KNOWN_CODES: ReadonlySet<string> = new Set([
  "PROJECT_CLOSED",
  "ASSET_NOT_FOUND",
  "REVOKED",
  "GRANT_EXISTS",
  "PORTAL_USER_EXISTS",
  "INVALID_STATUS",
  "INVALID_CURSOR",
  "USER_EXISTS",
  "USER_DEACTIVATED",
  "EMAIL_IN_OTHER_TENANT",
  "EMAIL_DOMAIN_SSO",
  "INVALID_EMAIL",
]);

/** Codes that belong on the email input of the invite form. */
export const EMAIL_CODES: ReadonlySet<string> = new Set([
  "PORTAL_USER_EXISTS",
  "USER_EXISTS",
  "USER_DEACTIVATED",
  "EMAIL_IN_OTHER_TENANT",
  "EMAIL_DOMAIN_SSO",
  "INVALID_EMAIL",
]);

export interface ApiError {
  code: string;
  projectId?: string;
  assetId?: string;
}

/** The `{code, projectId?, assetId?}` of an error body, else `null`. */
export function apiError(body: unknown): ApiError | null {
  if (typeof body !== "object" || body === null) return null;
  const { code, projectId, assetId } = body as Record<string, unknown>;
  if (typeof code !== "string") return null;
  return {
    code,
    ...(typeof projectId === "string" ? { projectId } : {}),
    ...(typeof assetId === "string" ? { assetId } : {}),
  };
}

/** The term key of a known code, else the generic "could not save". */
export function errorKey(code: string | undefined): string {
  return code && KNOWN_CODES.has(code) ? `portal.error.${code.toLowerCase()}` : "portal.admin.error_save";
}

/** The message of a known code, else the generic "could not save" with the request reference. */
export function errorMessage(code: string | undefined, requestId: string | null): string {
  if (code && KNOWN_CODES.has(code)) return t(`portal.error.${code.toLowerCase()}`);
  return requestId ? `${t("portal.admin.error_save")} ${t("portal.admin.request_id", { id: requestId })}` : t("portal.admin.error_save");
}
