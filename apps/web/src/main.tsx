import "@aip/ui/tokens.css";
import "@aip/ui/styles.css";
import "./features/shell/shell.css";
import "./features/projects/projects.css";
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createQueryClient } from "./features/shell/query-client";
import { installSessionExpiry } from "./features/identity/csrf-fetch";
import { resolveSessionPort } from "./features/shell/session";
import { SessionPortProvider } from "./features/shell/session-context";
import { createAppRouter } from "./router";

const container = document.getElementById("root");
if (!container) throw new Error("#root element missing");
const root = createRoot(container);

// `data-density` drives the density tokens; compact is the default (index.html sets it too).
document.documentElement.dataset.density ??= "compact";

async function start() {
  const sessionPort = await resolveSessionPort();

  let checking = false;
  // A 401 from a data call: ask the session port before sending the user to /login, so one
  // failed request cannot sign out a live session. With the dev stub (no API session at all, so
  // every API call is 401) the session stays and the page shows its own error state.
  function onSessionExpired() {
    if (checking || router.state.location.pathname === "/login") return;
    checking = true;
    void sessionPort
      .getSession()
      .catch(() => null)
      .then((session) => {
        checking = false;
        if (session) return;
        const { pathname, href } = router.state.location;
        if (pathname === "/login") return;
        queryClient.clear();
        void router.navigate({ to: "/login", search: { expired: 1, next: href } });
      });
  }

  const queryClient = createQueryClient(onSessionExpired);
  // IDENTITY-03: the API's 401 SESSION_EXPIRED (signalled by the generated client's fetch).
  installSessionExpiry(onSessionExpired);
  const router = createAppRouter({ queryClient, sessionPort });

  root.render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <SessionPortProvider port={sessionPort}>
          <RouterProvider router={router} />
        </SessionPortProvider>
      </QueryClientProvider>
    </StrictMode>,
  );
}

void start();
