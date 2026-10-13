/**
 * Active sessions (IDENTITY-03): the caller's live sessions with device, IP and last activity,
 * and a "Sign out" action per row. Signing out the current session ends it like Logout; the
 * API's 401 then sends the user to sign in again.
 */
import {
  getIdentityListMySessionsQueryKey,
  identityRevokeMySession,
  useIdentityListMySessions,
  type SessionOut,
} from "@aip/api-client";
import { Button, Spinner, Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@aip/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { t } from "../shell/t";

function device(session: SessionOut): string {
  return session.userAgent?.trim() || t("identity.sessions.unknownDevice");
}

function when(value: string): string {
  return new Intl.DateTimeFormat("en-AU", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export function ActiveSessionsPage() {
  const queryClient = useQueryClient();
  const list = useIdentityListMySessions();
  const [pending, setPending] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  async function signOut(id: string) {
    setPending(id);
    setFailed(false);
    try {
      const response = await identityRevokeMySession(id);
      if (response.status !== 204) setFailed(true);
    } catch {
      setFailed(true);
    } finally {
      setPending(null);
      await queryClient.invalidateQueries({ queryKey: getIdentityListMySessionsQueryKey() });
    }
  }

  const sessions = list.data?.status === 200 ? list.data.data.items : [];
  return (
    <section className="aip-page" aria-labelledby="sessions-title">
      <h1 id="sessions-title">{t("identity.sessions.title")}</h1>
      <p>{t("identity.sessions.intro")}</p>
      {failed && <p role="alert">{t("identity.sessions.revokeFailed")}</p>}
      {list.isPending ? (
        <p role="status">
          <Spinner label={t("identity.sessions.loading")} />
        </p>
      ) : list.isError || (list.data && list.data.status !== 200) ? (
        <p role="alert">{t("identity.sessions.error")}</p>
      ) : (
        <Table>
          <TableCaption>{t("identity.sessions.title")}</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">{t("identity.sessions.device")}</TableHead>
              <TableHead scope="col">{t("identity.sessions.ip")}</TableHead>
              <TableHead scope="col">{t("identity.sessions.lastSeen")}</TableHead>
              <TableHead scope="col">{t("identity.sessions.signedIn")}</TableHead>
              <TableHead scope="col">{t("identity.sessions.actions")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sessions.map((s) => (
              <TableRow key={s.id}>
                <TableCell>
                  {device(s)}
                  {s.current && <strong>{` (${t("identity.sessions.current")})`}</strong>}
                </TableCell>
                <TableCell>{s.ip ?? "—"}</TableCell>
                <TableCell>{when(s.lastSeenAt)}</TableCell>
                <TableCell>{when(s.createdAt)}</TableCell>
                <TableCell>
                  <Button
                    variant="secondary"
                    disabled={pending !== null}
                    aria-label={t("identity.sessions.signOutLabel", { device: device(s) })}
                    onClick={() => void signOut(s.id)}
                  >
                    {pending === s.id ? t("identity.sessions.signingOut") : t("identity.sessions.signOut")}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </section>
  );
}
