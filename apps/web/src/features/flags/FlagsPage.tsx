/**
 * Release flags settings page (DESIGN-15, ARCH-08). Lists every known flag with a switch that calls
 * `PUT /settings/flags/{flag}`. Without `tenant.flags.manage` the page shows the standard 403 state
 * and the list (which holds the API hooks) never mounts; the API refuses the change regardless.
 * A successful change is written into the shell's flags query, so gated nav items follow at once.
 */
import { usePlatformSetFlag, type FeatureFlag } from "@aip/api-client";
import { Checkbox, ErrorState, Label, LoadingState, toast } from "@aip/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { FLAGS_MANAGE, storeFlag, useFeatureFlags } from "../shell/flags";
import { t } from "../shell/t";

function flagName(flag: string): string {
  return t(`shell.flags.flag.${flag}`);
}

function FlagSwitch({ flag, busy, onChange }: { flag: FeatureFlag; busy: boolean; onChange: (enabled: boolean) => void }) {
  const id = `flag-${flag.flag}`;
  return (
    <li className="aip-flags__item">
      <Checkbox
        id={id}
        checked={flag.enabled}
        disabled={busy}
        aria-describedby={`${id}-hint`}
        onCheckedChange={(checked) => onChange(checked === true)}
      />
      <div>
        <Label htmlFor={id}>{flagName(flag.flag)}</Label>
        <p id={`${id}-hint`} className="aip-flags__hint">
          {t(`shell.flags.flag.${flag.flag}.description`)}
        </p>
      </div>
    </li>
  );
}

function FlagList() {
  const { flags, isPending, refetch } = useFeatureFlags();
  const queryClient = useQueryClient();
  const setFlag = usePlatformSetFlag();
  const [busy, setBusy] = useState(false);

  async function change(flag: string, enabled: boolean) {
    setBusy(true);
    const response = await setFlag.mutateAsync({ flag, data: { enabled } }).catch(() => undefined);
    setBusy(false);
    if (response?.status === 200) {
      storeFlag(queryClient, response.data);
      toast.success(enabled ? "shell.flags.turned_on" : "shell.flags.turned_off", { flag: flagName(flag) });
    } else {
      toast.error("shell.flags.change_failed");
    }
  }

  if (isPending) return <LoadingState variant="spinner" translate={t} />;
  if (!flags) return <ErrorState error={{ status: 500 }} onRetry={refetch} translate={t} />;
  return (
    <ul className="aip-flags" aria-label={t("shell.flags.list")}>
      {flags.map((flag) => (
        <FlagSwitch key={flag.flag} flag={flag} busy={busy} onChange={(enabled) => void change(flag.flag, enabled)} />
      ))}
    </ul>
  );
}

export function FlagsPage({ permissions }: { permissions: readonly string[] }) {
  return (
    <section className="aip-page" aria-labelledby="flags-title">
      <h1 id="flags-title">{t("shell.flags.title")}</h1>
      {permissions.includes(FLAGS_MANAGE) ? (
        <>
          <p>{t("shell.flags.intro")}</p>
          <FlagList />
        </>
      ) : (
        <ErrorState error={{ status: 403 }} onRetry={() => window.location.reload()} translate={t} />
      )}
    </section>
  );
}
