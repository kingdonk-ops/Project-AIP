import "@aip/ui/tokens.css";
import "@aip/ui/styles.css";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createAppRouter } from "./router";

const router = createAppRouter();
const container = document.getElementById("root");
if (!container) throw new Error("#root element missing");

createRoot(container).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
