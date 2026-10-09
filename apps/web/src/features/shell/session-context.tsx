import { createContext, useContext, type ReactNode } from "react";
import type { SessionPort } from "./session";

const SessionPortContext = createContext<SessionPort | null>(null);

/** Supplies the session port to the shell and login page (main.tsx in the app, a fake in tests). */
export function SessionPortProvider({ port, children }: { port: SessionPort; children: ReactNode }) {
  return <SessionPortContext.Provider value={port}>{children}</SessionPortContext.Provider>;
}

export function useSessionPort(): SessionPort {
  const port = useContext(SessionPortContext);
  if (!port) throw new Error("useSessionPort must be used inside <SessionPortProvider>");
  return port;
}
