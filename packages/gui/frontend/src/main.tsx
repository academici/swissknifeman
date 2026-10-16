import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App } from "./app/App";
import { ApiError } from "./transport/ApiError";
import { HttpTransport } from "./transport/HttpTransport";
import { TransportContext } from "./transport/context";
import "./styles.css";

const transport = new HttpTransport();
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (count, error) => (error instanceof ApiError ? error.retryable && count < 2 : count < 1),
      refetchOnWindowFocus: false,
    },
  },
});

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <TransportContext.Provider value={transport}>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      </TransportContext.Provider>
    </StrictMode>,
  );
}
