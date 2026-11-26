import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type PropsWithChildren } from "react";
import { useNavigate } from "react-router";
import { parseAuthSession, readCsrfCookie, type AuthMaterial, type AuthMode } from "../../api/authMaterial";
import { ApiError } from "../../api/errors";
import type { WhoAmIView } from "../../api/generated/access";
import { readWhoAmI, useWhoAmI, whoAmIKey } from "../../api/hooks/access";
import { closeAllStreams } from "../../api/streamRegistry";
import { HttpTransport, type Transport } from "../../api/transport";
import { tokenStore } from "../../features/auth/tokenStore";
import { clearSavedScope } from "./ScopeProvider";

const logoutFailureMessage = "Не удалось завершить сеанс. Повторите выход — серверная сессия ещё активна.";

// One retry, then surface the failure. A 401 means the cookie session is already gone.
async function revokeAdminSession(csrfToken: string | null): Promise<void> {
  const logout = new HttpTransport({
    getAuth: () => ({ mode: "admin_login", token: null, csrfToken }),
  });
  let failure: unknown;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      await logout.request("POST", "/api/v1/auth/logout", { body: {} });
      return;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return;
      failure = error;
    }
  }
  throw failure instanceof Error ? failure : new Error(logoutFailureMessage);
}

type Phase =
  | { readonly kind: "probing" }
  | { readonly kind: "anonymous" }
  | { readonly kind: "token"; readonly token: string }
  | { readonly kind: "session"; readonly mode: "none" | "admin_login"; readonly csrfToken: string | null };

interface AuthState {
  readonly serverMode: "none" | "admin_login" | null;
  readonly phase: Phase;
}

export type AuthStatus = "probing" | "anonymous" | "authenticated";

interface Auth {
  token: string | null;
  mode: AuthMode | null;
  status: AuthStatus;
  me: WhoAmIView | undefined;
  identityError: Error | null;
  refreshIdentity(): void;
  transport: Transport;
  sessionGeneration: number;
  sessionActionPending: boolean;
  logoutError: string | null;
  signIn(token: string): Promise<void>;
  signInWithPassword(password: string): Promise<void>;
  continueLocal(): Promise<boolean>;
  reloadSession(): Promise<void>;
  signOut(expectedGeneration?: number): Promise<void>;
}

const AuthContext = createContext<Auth | null>(null);

function identityKeyOf(phase: Phase): string {
  if (phase.kind === "token") return `token:${phase.token}`;
  if (phase.kind === "session") return `session:${phase.mode}`;
  return phase.kind;
}

function materialOf(phase: Phase, csrfToken: string | null): AuthMaterial {
  if (phase.kind === "token") return { mode: "token", token: phase.token, csrfToken: null };
  if (phase.kind === "session") return { mode: phase.mode, token: null, csrfToken };
  return { mode: "token", token: null, csrfToken: null };
}

function isActive(phase: Phase): boolean {
  return phase.kind === "token" || phase.kind === "session";
}

export function AuthProvider({ initialToken, children }: PropsWithChildren<{ initialToken: string | null }>) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const initial = useRef<AuthState>(initialToken === null
    ? { serverMode: null, phase: { kind: "probing" } }
    : { serverMode: null, phase: { kind: "token", token: initialToken } }).current;
  const [state, setState] = useState<AuthState>(initial);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [sessionActionPending, setSessionActionPending] = useState(false);
  // Monotonic session epoch. Unauthorized handlers capture the value from the
  // render that issued the request and ignore a 401 after reload or re-login.
  const [sessionGeneration, setSessionGeneration] = useState(0);
  const sessionGenerationRef = useRef(0);
  const currentState = useRef(state);
  const csrfRef = useRef<string | null>(state.phase.kind === "session" ? state.phase.csrfToken : null);
  const epoch = useRef(0);
  const changingSession = useRef(false);
  const csrfRefresh = useRef(false);
  const currentSignIn = useRef<AbortController | null>(null);

  const commit = useCallback((next: AuthState) => {
    csrfRef.current = next.phase.kind === "session" ? next.phase.csrfToken : null;
    currentState.current = next;
    setState(next);
  }, []);

  const advanceSession = useCallback(() => {
    sessionGenerationRef.current += 1;
    setSessionGeneration(sessionGenerationRef.current);
  }, []);

  const signOut = useCallback(async (expectedGeneration?: number) => {
    if (typeof expectedGeneration === "number" && expectedGeneration !== sessionGenerationRef.current) return;
    if (changingSession.current) return;
    changingSession.current = true;
    setSessionActionPending(true);
    try {
      const { phase } = currentState.current;
      // A 401 handler passes the generation of the already rejected session.
      if (phase.kind === "session" && phase.mode === "admin_login" && expectedGeneration === undefined) {
        const generation = sessionGenerationRef.current;
        setLogoutError(null);
        try {
          await revokeAdminSession(phase.csrfToken ?? readCsrfCookie());
        } catch {
          setLogoutError(logoutFailureMessage);
          return;
        }
        if (sessionGenerationRef.current !== generation) return;
      }
      advanceSession();
      epoch.current += 1;
      currentSignIn.current?.abort();
      currentSignIn.current = null;
      closeAllStreams();
      tokenStore.clear();
      clearSavedScope();
      queryClient.clear();
      setLogoutError(null);
      commit({ serverMode: currentState.current.serverMode, phase: { kind: "anonymous" } });
      void navigate("/login", { replace: true });
    } finally {
      changingSession.current = false;
      setSessionActionPending(false);
    }
  }, [advanceSession, commit, navigate, queryClient]);

  const refreshCsrf = useCallback(() => {
    const phase = currentState.current.phase;
    if (csrfRefresh.current || phase.kind !== "session" || phase.mode !== "admin_login") return;
    csrfRefresh.current = true;
    const reader = new HttpTransport({
      getAuth: () => ({ mode: "admin_login", token: null, csrfToken: null }),
    });
    void reader.request<{ csrf_token?: string }>("GET", "/api/v1/auth/csrf")
      .then((response) => {
        const token = response.data?.csrf_token;
        const latest = currentState.current;
        if (typeof token !== "string" || !token || latest.phase.kind !== "session") return;
        if (latest.phase.csrfToken === token) return;
        commit({ ...latest, phase: { ...latest.phase, csrfToken: token } });
      })
      .catch(() => undefined)
      .finally(() => { csrfRefresh.current = false; });
  }, [commit]);

  const identityKey = identityKeyOf(state.phase);
  const transport = useMemo(() => {
    const snapshotKey = identityKey;
    const generation = sessionGeneration;
    return new HttpTransport({
      getAuth: () => materialOf(currentState.current.phase, csrfRef.current),
      onUnauthorized: () => {
        if (sessionGenerationRef.current !== generation) return;
        const phase = currentState.current.phase;
        if (isActive(phase) && identityKeyOf(phase) === snapshotKey) void signOut(generation);
      },
      onForbidden: () => { refreshCsrf(); },
    });
  }, [identityKey, refreshCsrf, sessionGeneration, signOut]);

  const authenticated = isActive(state.phase);
  const identity = useWhoAmI(transport, authenticated);

  const discover = useCallback(async (signal: AbortSignal) => {
    const seen = epoch.current;
    const probe = new HttpTransport({
      getAuth: () => ({ mode: "none", token: null, csrfToken: null }),
    });
    const finish = (next: AuthState) => {
      if (signal.aborted || seen !== epoch.current) return;
      if (currentState.current.phase.kind !== "probing") return;
      if (isActive(next.phase)) advanceSession();
      commit(next);
    };
    try {
      const { data } = await probe.request<unknown>("GET", "/api/v1/auth/session", { signal });
      const session = parseAuthSession(data);
      if (!session) {
        finish({ serverMode: currentState.current.serverMode, phase: { kind: "anonymous" } });
        return;
      }
      finish({
        serverMode: session.mode,
        phase: { kind: "session", mode: session.mode, csrfToken: readCsrfCookie() },
      });
    } catch {
      finish({ serverMode: currentState.current.serverMode, phase: { kind: "anonymous" } });
    }
  }, [advanceSession, commit]);

  useEffect(() => {
    if (initialToken !== null) return;
    const controller = new AbortController();
    void discover(controller.signal);
    return () => controller.abort();
  }, [discover, initialToken]);

  function releaseProbe(seen: number) {
    if (seen !== epoch.current) return;
    if (currentState.current.phase.kind !== "probing") return;
    commit({ serverMode: currentState.current.serverMode, phase: { kind: "anonymous" } });
  }

  async function signIn(input: string) {
    const token = input.trim();
    if (!token) throw new TypeError("Введите токен доступа");
    advanceSession();
    epoch.current += 1;
    const seen = epoch.current;
    const generation = sessionGenerationRef.current;
    currentSignIn.current?.abort();
    const attempt = new AbortController();
    currentSignIn.current = attempt;
    const candidate = new HttpTransport({
      getAuth: () => ({ mode: "token", token, csrfToken: null }),
      onUnauthorized: () => {
        if (sessionGenerationRef.current !== generation) return;
        if (currentSignIn.current === attempt) void signOut(generation);
      },
    });
    try {
      // Validate outside the cache so candidate credentials never become query or mutation variables.
      const me = await readWhoAmI(candidate, attempt.signal);
      attempt.signal.throwIfAborted();
      if (seen !== epoch.current) return;
      tokenStore.set(token);
      queryClient.clear();
      queryClient.setQueryData(whoAmIKey, me);
      setLogoutError(null);
      advanceSession();
      commit({ serverMode: currentState.current.serverMode, phase: { kind: "token", token } });
    } catch (error) {
      releaseProbe(seen);
      throw error;
    } finally {
      if (currentSignIn.current === attempt) currentSignIn.current = null;
    }
  }

  async function signInWithPassword(password: string) {
    const secret = password.trim();
    if (!secret) throw new TypeError("Введите пароль");
    advanceSession();
    epoch.current += 1;
    const seen = epoch.current;
    currentSignIn.current?.abort();
    const attempt = new AbortController();
    currentSignIn.current = attempt;
    try {
      const csrfTransport = new HttpTransport({
        getAuth: () => ({ mode: "admin_login", token: null, csrfToken: null }),
      });
      const issued = await csrfTransport.request<{ csrf_token?: string }>("GET", "/api/v1/auth/csrf", { signal: attempt.signal });
      const csrf = issued.data?.csrf_token;
      if (typeof csrf !== "string" || !csrf) throw new Error("Не удалось получить CSRF");
      const loginTransport = new HttpTransport({
        getAuth: () => ({ mode: "admin_login", token: null, csrfToken: csrf }),
      });
      const logged = await loginTransport.request<{ csrf_token?: string; display_name?: string }>(
        "POST", "/api/v1/auth/login", { body: { password: secret }, signal: attempt.signal },
      );
      const nextCsrf = typeof logged.data?.csrf_token === "string" ? logged.data.csrf_token : csrf;
      const meTransport = new HttpTransport({
        getAuth: () => ({ mode: "admin_login", token: null, csrfToken: nextCsrf }),
      });
      const me = await readWhoAmI(meTransport, attempt.signal);
      attempt.signal.throwIfAborted();
      if (seen !== epoch.current) return;
      tokenStore.clear();
      queryClient.clear();
      queryClient.setQueryData(whoAmIKey, me);
      setLogoutError(null);
      advanceSession();
      commit({ serverMode: "admin_login", phase: { kind: "session", mode: "admin_login", csrfToken: nextCsrf } });
    } catch (error) {
      releaseProbe(seen);
      throw error;
    } finally {
      if (currentSignIn.current === attempt) currentSignIn.current = null;
    }
  }

  async function continueLocal(): Promise<boolean> {
    if (currentState.current.phase.kind === "probing" && currentSignIn.current) return false;
    epoch.current += 1;
    const seen = epoch.current;
    currentSignIn.current?.abort();
    const attempt = new AbortController();
    currentSignIn.current = attempt;
    if (currentState.current.phase.kind !== "probing") {
      commit({ ...currentState.current, phase: { kind: "probing" } });
    }
    try {
      await discover(attempt.signal);
    } finally {
      if (currentSignIn.current === attempt) currentSignIn.current = null;
      if (seen === epoch.current && currentState.current.phase.kind === "probing") {
        commit({ serverMode: currentState.current.serverMode, phase: { kind: "anonymous" } });
      }
    }
    return isActive(currentState.current.phase);
  }

  async function reloadSession() {
    if (changingSession.current) return;
    const phase = currentState.current.phase;
    if (phase.kind !== "session" || phase.mode !== "admin_login") {
      throw new Error("Нет сеанса администратора");
    }
    changingSession.current = true;
    setSessionActionPending(true);
    advanceSession();
    const generation = sessionGenerationRef.current;
    let unauthorized = false;
    try {
      const { data } = await transport.request<{ csrf_token?: string }>("POST", "/api/v1/auth/session/reload", { body: {} });
      const nextCsrf = data?.csrf_token;
      if (typeof nextCsrf !== "string" || !nextCsrf) throw new Error("Некорректный ответ обновления сеанса");
      const latest = currentState.current;
      if (sessionGenerationRef.current !== generation || latest.phase.kind !== "session" || latest.phase.mode !== "admin_login") return;
      // Requests issued during the reload may still have used the old cookie.
      advanceSession();
      commit({ ...latest, phase: { ...latest.phase, csrfToken: nextCsrf } });
    } catch (error) {
      unauthorized = error instanceof ApiError && error.status === 401;
      throw error;
    } finally {
      changingSession.current = false;
      setSessionActionPending(false);
      if (unauthorized) void signOut(generation);
    }
    void identity.refetch();
  }

  const mode: AuthMode | null = state.phase.kind === "token"
    ? "token"
    : state.phase.kind === "session"
      ? state.phase.mode
      : state.serverMode;
  const status: AuthStatus = state.phase.kind === "probing"
    ? "probing"
    : authenticated ? "authenticated" : "anonymous";

  return (
    <AuthContext.Provider value={{
      token: state.phase.kind === "token" ? state.phase.token : null,
      mode,
      status,
      me: authenticated ? identity.data : undefined,
      identityError: authenticated ? identity.error : null,
      refreshIdentity: () => { void identity.refetch(); },
      transport,
      sessionGeneration,
      sessionActionPending,
      logoutError,
      signIn,
      signInWithPassword,
      continueLocal,
      reloadSession,
      signOut,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): Auth {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("AuthProvider is missing");
  return auth;
}
