// TESTING-09: the id that makes one run's walking-skeleton data unique (`E2E-<runId>`).
// On GitHub Actions it is `<run id>-<attempt>`, so a re-run never collides with its first attempt;
// locally it is the current time in milliseconds (13 digits).
export function runId(env: NodeJS.ProcessEnv = process.env, now: () => number = Date.now): string {
  const run = env.GITHUB_RUN_ID;
  return run ? `${run}-${env.GITHUB_RUN_ATTEMPT ?? "1"}` : String(now());
}
