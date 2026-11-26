import { notifyManager, useQueryClient } from "@tanstack/react-query";
import {
  createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState,
  type PropsWithChildren,
} from "react";
import { invalidateEvent } from "../../api/invalidation";
import { keys, type QueryScope } from "../../api/keys";
import { readWithEvents } from "../../api/stream";
import type { Response, Subscription } from "../../api/transport";
import { useAuth } from "./AuthProvider";
import { useScope } from "./ScopeProvider";
import { useToast } from "./ToastProvider";

interface StreamContextValue {
  stale: boolean;
  connectAtHead(): void;
  readWithEvents<T>(read: () => Promise<Response<T>>, signal?: AbortSignal): Promise<Response<T>>;
}

interface Feed {
  cursor: number | null;
  stopped: boolean;
  subscription: Subscription | null;
}

interface Session {
  scope: QueryScope;
  enabled: boolean;
  feed: Feed | null;
}

interface Disconnection {
  since: number;
}

const StreamContext = createContext<StreamContextValue | null>(null);

export function StreamProvider({ children, staleAfterSeconds = 30 }: PropsWithChildren<{ staleAfterSeconds?: number }>) {
  const { token, status, transport } = useAuth();
  const { scope: { workspaceId, projectId }, projectCursor } = useScope();
  const queryClient = useQueryClient();
  const toast = useToast();
  const active = useRef<Session | null>(null);
  const previousScope = useRef<QueryScope | null>(null);
  const [disconnected, setDisconnected] = useState<Disconnection | null>(null);
  const [staleConnection, setStaleConnection] = useState<Disconnection | null>(null);

  useLayoutEffect(() => {
    const scope = { workspaceId, projectId };
    const previous = previousScope.current;
    if (previous !== null && previous.workspaceId !== workspaceId) {
      queryClient.removeQueries({ queryKey: keys.workspace(previous.workspaceId) });
    } else if (previous !== null && previous.projectId !== projectId) {
      queryClient.removeQueries({ queryKey: keys.scope(previous) });
    }
    previousScope.current = scope;
    const session: Session = { scope, enabled: status === "authenticated" && workspaceId !== null, feed: null };
    active.current = session;
    setDisconnected(null);
    return () => {
      active.current = null;
      session.feed?.subscription?.close();
    };
  }, [workspaceId, projectId, token, status, queryClient]);

  useEffect(() => {
    if (disconnected === null) return;
    const elapsed = Date.now() - disconnected.since;
    const remaining = staleAfterSeconds * 1_000 - elapsed;
    const timer = setTimeout(() => setStaleConnection(disconnected), Math.max(0, remaining + 1));
    return () => clearTimeout(timer);
  }, [disconnected, staleAfterSeconds]);

  const open = useCallback((session: Session, after?: number) => {
    const { workspaceId } = session.scope;
    if (!session.enabled || workspaceId === null) return;
    const previous = session.feed;
    const feed: Feed = { cursor: after ?? null, stopped: false, subscription: null };
    session.feed = feed;
    previous?.subscription?.close();
    const current = () => active.current === session && session.feed === feed;
    const scheduleInvalidation = (invalidate: () => void) => {
      // A fast replay can arrive before the GET result is committed to the cache.
      notifyManager.schedule(() => {
        if (current()) invalidate();
      });
    };
    setDisconnected((state) => state ?? { since: Date.now() });
    feed.subscription = transport.events({ workspaceId, ...(after === undefined ? {} : { after }) }, {
      onCursor: (cursor) => {
        if (current()) feed.cursor = cursor;
      },
      onConnectionChange: (connected) => {
        if (current()) setDisconnected((state) => connected ? null : state ?? { since: Date.now() });
      },
      onStopped: () => { feed.stopped = true; },
      onEvent: (event) => scheduleInvalidation(() => invalidateEvent(queryClient, session.scope, event, toast)),
      onSnapshotRequired: () => scheduleInvalidation(() => { void queryClient.invalidateQueries(); }),
    });
  }, [queryClient, toast, transport]);

  const connectAtHead = useCallback(() => {
    const session = active.current;
    if (session?.feed === null) open(session);
  }, [open]);

  const readInScope = useCallback(<T,>(read: () => Promise<Response<T>>, signal?: AbortSignal) => {
    const session = active.current;
    return readWithEvents(read, signal, (eventsCursor) => {
      if (session !== active.current) throw new DOMException("Scope changed during read", "AbortError");
      if (!session?.enabled) return true;
      const { feed } = session;
      // The project GET resolves the workspace before the feed can open. Replay from
      // the earlier snapshot on first connect, then compare fresh reads to the live cursor.
      const cursor = feed === null && projectCursor !== null
        ? Math.min(projectCursor, eventsCursor ?? projectCursor)
        : eventsCursor;
      if (cursor === undefined) return true;
      if (feed === null || feed.stopped || feed.cursor === null) {
        // A stopped feed or unresolved head cannot guarantee replay after this GET.
        open(session, cursor);
        return true;
      }
      return feed.cursor <= cursor;
    });
  }, [open, projectCursor]);

  const stale = disconnected !== null && staleConnection === disconnected
    && Date.now() - disconnected.since > staleAfterSeconds * 1_000;

  return (
    <StreamContext.Provider value={{ stale, connectAtHead, readWithEvents: readInScope }}>
      {children}
    </StreamContext.Provider>
  );
}

export function useStream() {
  const value = useContext(StreamContext);
  if (!value) throw new Error("StreamProvider is missing");
  return value;
}
