import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type PropsWithChildren } from "react";
import { ApiError } from "../../api/errors";

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: (failures, error) =>
          failures < 3 && !(error instanceof ApiError && [401, 403, 404].includes(error.status)),
        retryDelay: (attempt) => 1_000 * 2 ** attempt,
      },
      mutations: { retry: false, networkMode: "always" },
    },
  });
}

export function QueryProvider({ children }: PropsWithChildren) {
  const [client] = useState(createQueryClient);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
