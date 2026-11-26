import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { ApiError } from "../transport/ApiError";
import type { Method, StreamFilter, StreamHandlers, Subscription, Transport } from "../transport/Transport";
import { TransportContext } from "../transport/context";

export interface Call {
  method: Method;
  path: string;
  body: unknown;
}

type Answer = unknown | ((call: Call) => unknown);

/** A Transport for tests: answers by "METHOD path", records every call and subscription. */
export class FakeTransport implements Transport {
  calls: Call[] = [];
  subscriptions: Array<{ filter: StreamFilter; handlers: StreamHandlers; closed: boolean }> = [];
  epoch: string | null = null;

  constructor(private readonly answers: Record<string, Answer>) {}

  async request<T>(method: Method, path: string, body?: unknown): Promise<T> {
    const call = { method, path, body };
    this.calls.push(call);
    const key = Object.keys(this.answers).find((candidate) => candidate === `${method} ${path}`) ??
      Object.keys(this.answers).find((candidate) => `${method} ${path}`.startsWith(candidate.replace(/\*$/, "")) && candidate.endsWith("*"));
    if (key === undefined) throw new ApiError(404, { code: "NOT_FOUND", message: `no fake answer for ${method} ${path}` });
    const answer = this.answers[key];
    const value = typeof answer === "function" ? (answer as (call: Call) => unknown)(call) : answer;
    if (value instanceof ApiError) throw value;
    return value as T;
  }

  subscribe(filter: StreamFilter, handlers: StreamHandlers): Subscription {
    const entry = { filter, handlers, closed: false };
    this.subscriptions.push(entry);
    return { close: () => (entry.closed = true) };
  }

  setEpoch(epoch: string): void {
    this.epoch = epoch;
  }
}

export function Wrapper({ transport, children, path = "/" }: { transport: Transport; children: ReactNode; path?: string }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <TransportContext.Provider value={transport}>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>{children}</MemoryRouter>
      </QueryClientProvider>
    </TransportContext.Provider>
  );
}
