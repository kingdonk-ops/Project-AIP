import "@aip/ui/tokens.css";
import "@aip/ui/styles.css";
import "./features/shell/shell.css";
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createQueryClient } from "./features/shell/query-client";
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

  function onSessionExpired() {
    const { pathname, href } = router.state.location;
    if (pathname === "/login") return;
    queryClient.clear();
    void router.navigate({ to: "/login", search: { expired: 1, next: href } });
  }

  const queryClient = createQueryClient(onSessionExpired);
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
