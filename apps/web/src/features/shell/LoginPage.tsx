import { Button, FormField, Icon, Input, Panel } from "@aip/ui";
import { useId, useState, type SyntheticEvent } from "react";
import { safeNext } from "./safe-next";
import { useSessionPort } from "./session-context";
import { t } from "./t";

export interface LoginSearch {
  next?: string;
  invited?: 1;
  signed_out?: 1;
  expired?: 1;
  error?: "failed";
}

const FAILURE_KEYS = {
  invalid_email: "shell.login.invalidEmail",
  rate_limited: "shell.login.rateLimited",
  unavailable: "shell.login.unavailable",
} as const;

/**
 * Sign-in entry. The SPA never collects a password, OTP or passkey: both the `sso` and `password`
 * answers redirect the browser to Keycloak (IDENTITY-01), whose themed pages collect credentials.
 * Failure wording is generic so it cannot be used to enumerate tenants or users.
 * DESIGN-18: the form sits in a white `Panel` on the off-white canvas, the notice is a tinted info or
 * danger strip with its icon (solid outline in high contrast), and the email field has a decorative
 * leading icon, as DESIGN-09 does for the register search.
 */
export function LoginPage({ search }: { search: LoginSearch }) {
  const port = useSessionPort();
  const [email, setEmail] = useState("");
  const [failure, setFailure] = useState<keyof typeof FAILURE_KEYS | null>(null);
  const [busy, setBusy] = useState(false);
  const headingId = useId();

  async function onSubmit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    setFailure(null);
    setBusy(true);
    const outcome = await port.startLogin(email.trim(), safeNext(search.next));
    if (outcome.ok) {
      window.location.assign(outcome.redirectUrl);
      return;
    }
    setBusy(false);
    setFailure(outcome.reason);
  }

  const notice = search.invited
    ? t("shell.login.invited")
    : search.signed_out
      ? t("shell.login.signedOut")
      : search.expired
        ? t("shell.login.expired")
        : search.error
          ? t("shell.login.failed")
          : null;

  const tone = search.error ? "danger" : "info";

  return (
    <main className="shell-login">
      <Panel className="shell-login__panel" aria-labelledby={headingId}>
        <h1 id={headingId} className="shell-login__title">
          {t("shell.login.title")}
        </h1>
        {notice ? (
          <p
            className={`shell-login__notice shell-login__notice--${tone}`}
            role={search.error ? "alert" : "status"}
          >
            <Icon name={search.error ? "alert" : "info"} size={16} className="shell-login__notice-icon" />
            <span>{notice}</span>
          </p>
        ) : null}
        <form onSubmit={(event) => void onSubmit(event)} noValidate>
          <FormField
            label={t("shell.login.email")}
            hint={t("shell.login.emailHint")}
            {...(failure ? { error: t(FAILURE_KEYS[failure]) } : {})}
          >
            {(control) => (
              <Input
                {...control}
                icon="user"
                name="email"
                type="text"
                inputMode="email"
                autoComplete="username"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            )}
          </FormField>
          <Button type="submit" disabled={busy || email.trim() === ""}>
            {busy ? t("shell.login.submitting") : t("shell.login.submit")}
          </Button>
        </form>
      </Panel>
    </main>
  );
}
