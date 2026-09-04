import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// self-hosted, so a demo with no wifi still renders correctly
import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";
import "@fontsource-variable/newsreader";
import "./styles/global.css";

import App from "./App";
import { ThemeProvider } from "./context/ThemeContext";
import { ApiKeyProvider } from "./context/ApiKeyContext";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // a 401 will keep being a 401 — only retry things that might recover
      retry: (failureCount, error) =>
        failureCount < 2 && !/rejected|Rate limit/i.test(error.message),
      refetchOnWindowFocus: false,
    },
  },
});

const root = document.getElementById("root");
if (!root) throw new Error("No #root element in index.html");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ApiKeyProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </ApiKeyProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
);
