import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrowserRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import { whoAmIKey } from "../../api/hooks/access";
import { App, AppRoutes } from "../../app/App";
import { AuthProvider, useAuth } from "../../app/providers/AuthProvider";
import { createQueryClient } from "../../app/providers/QueryProvider";
import { tokenStore } from "./tokenStore";

function deferredResponse() {
  let reply: (response: Response) => void = () => { throw new Error("Missing pending request"); };
  const response = new Promise<Response>((resolve) => { reply = resolve; });
  return { response, reply };
}

function openWithProbe(initialToken: string | null) {
  const client = createQueryClient();
  let auth: ReturnType<typeof useAuth> | undefined;
  function Probe() {
    auth = useAuth();
    return <AppRoutes />;
  }
  const app = render(
    <BrowserRouter>
      <QueryClientProvider client={client}>
        <AuthProvider initialToken={initialToken}><Probe /></AuthProvider>
      </QueryClientProvider>
    </BrowserRouter>,
  );
  return {
    client,
    auth: () => {
      if (!auth) throw new Error("Auth provider did not render");
      return auth;
    },
    dispose: () => {
      app.unmount();
      client.clear();
    },
  };
}

describe("token fragment", () => {
  it("stores a token once, strips the fragment immediately, and preserves the path and query", () => {
    history.replaceState({ previous: true }, "", "/w/example?view=recent#token=secret%2Bvalue");
    expect(tokenStore.ingestFragment()).toBe("secret+value");
    expect(location.pathname + location.search).toBe("/w/example?view=recent");
    expect(location.hash).toBe("");
    expect(location.href).not.toContain("secret");
    expect(history.state).toBeNull();
    expect(sessionStorage.getItem("skm.token")).toBe("secret+value");
    expect(localStorage.length).toBe(0);

    tokenStore.clear();
    expect(tokenStore.ingestFragment()).toBeNull();
  });

  it("preserves unrelated fragments and strips an empty token without replacing the session", () => {
    tokenStore.set("existing");
    history.replaceState(null, "", "/#main");
    expect(tokenStore.ingestFragment()).toBe("existing");
    expect(location.hash).toBe("#main");
    history.replaceState(null, "", "/#token=");
    expect(tokenStore.ingestFragment()).toBe("existing");
    expect(location.hash).toBe("");
  });

  it("uses the launch token to request /me and render the requested route", async () => {
    const fetch = stubFetch();
    history.replaceState(null, "", "/settings?scope=instance#token=startup-token");
    render(<App initialToken={tokenStore.ingestFragment()} />);
    expect(location.hash).toBe("");
    await screen.findByRole("heading", { name: "Настройки", level: 1 });
    expect(location.pathname + location.search).toBe("/settings?scope=instance");
    expect(new Headers(fetch.mock.calls[0]?.[1]?.headers).get("Authorization")).toBe("Bearer startup-token");
  });
});

describe("login and sign-out", () => {
  it("redirects a protected route to login, validates the pasted token, and opens Home", async () => {
    const fetch = stubFetch();
    const user = userEvent.setup();
    history.replaceState(null, "", "/p/project-a/plans");
    render(<App initialToken={null} />);
    const field = await screen.findByLabelText("Токен доступа");
    expect(field.getAttribute("type")).toBe("password");
    expect(location.pathname).toBe("/login");
    await waitFor(() => expect(fetch.mock.calls.some(([path]) => path === "/api/v1/auth/session")).toBe(true));
    expect(fetch.mock.calls.some(([path]) => path === "/api/v1/me")).toBe(false);

    await user.type(field, " valid-token ");
    await user.click(screen.getByRole("button", { name: "Войти" }));

    await screen.findByRole("heading", { name: "Главная", level: 1 });
    expect(location.pathname).toBe("/");
    expect(location.href).not.toContain("valid-token");
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.getItem("skm.token")).toBe("valid-token");
    const identity = fetch.mock.calls.find(([path]) => path === "/api/v1/me");
    expect(identity?.[1]?.method).toBe("GET");
    expect(new Headers(identity?.[1]?.headers).get("Authorization")).toBe("Bearer valid-token");
    expect(identity?.[1]?.credentials).toBe("omit");
  });

  it("clears invalid tokens and shows a safe login error even if a problem echoes the secret", async () => {
    const fetch = stubFetch(async () => Response.json({ code: "UNAUTHENTICATED", category: "unauthenticated", detail: "bad-token" }, {
      status: 401, headers: { "Content-Type": "application/problem+json" },
    }));
    const user = userEvent.setup();
    history.replaceState(null, "", "/login");
    render(<App initialToken={null} />);
    const input = await screen.findByLabelText<HTMLInputElement>("Токен доступа");
    await user.type(input, "bad-token");
    await user.click(screen.getByRole("button", { name: "Войти" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Токен недействителен");
    expect(input.value).toBe("");
    expect(document.body.textContent).not.toContain("bad-token");
    expect(sessionStorage.getItem("skm.token")).toBeNull();
    expect(location.pathname).toBe("/login");
    expect(fetch.mock.calls.filter(([path]) => path === "/api/v1/me")).toHaveLength(1);
  });

  it("clears persisted credentials, cached queries and mutations on a 401", async () => {
    const fetch = stubFetch();
    tokenStore.set("expired-token");
    const probe = openWithProbe("expired-token");
    try {
      await screen.findByRole("heading", { name: "Главная", level: 1 });
      probe.client.setQueryData(["private", "project"], { old: true });
      probe.client.getMutationCache().build(probe.client, {});
      fetch.mockResolvedValueOnce(new Response(null, { status: 401 }));
      await act(async () => {
        await expect(probe.auth().transport.request("GET", "/api/v1/plans")).rejects.toMatchObject({ status: 401 });
      });

      await screen.findByRole("heading", { name: "Вход в SKM" });
      expect(location.pathname).toBe("/login");
      expect(tokenStore.get()).toBeNull();
      expect(probe.auth().token).toBeNull();
      expect(sessionStorage.getItem("skm.scope")).toBeNull();
      expect(probe.client.getQueryData(whoAmIKey)).toBeUndefined();
      expect(probe.client.getQueryData(["private", "project"])).toBeUndefined();
      expect(probe.client.getMutationCache().getAll()).toEqual([]);
    } finally {
      probe.dispose();
    }
  });

  it("keeps the login form and discards the token when a success response lacks an identity", async () => {
    stubFetch(async () => Response.json({ ok: true }));
    const user = userEvent.setup();
    history.replaceState(null, "", "/login");
    render(<App initialToken={null} />);
    await user.type(await screen.findByLabelText("Токен доступа"), "unverified-token");
    await user.click(screen.getByRole("button", { name: "Войти" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Не удалось проверить токен");
    expect(tokenStore.get()).toBeNull();
    expect(location.pathname).toBe("/login");
  });

  it("drops stale 401s from a previous session after signing in again", async () => {
    const fetch = stubFetch();
    tokenStore.set("first-session");
    const probe = openWithProbe("first-session");
    try {
      await screen.findByRole("heading", { name: "Главная", level: 1 });
      let reply: (response: Response) => void = () => { throw new Error("Missing pending request"); };
      const delayed = new Promise<Response>((resolve) => { reply = resolve; });
      fetch.mockReturnValueOnce(delayed);
      const stale = probe.auth().transport.request("GET", "/api/v1/plans");

      await act(async () => {
        await probe.auth().signIn("second-session");
      });
      await waitFor(() => expect(probe.auth().me).toEqual(testIdentity));
      reply(new Response(null, { status: 401 }));
      await expect(stale).rejects.toMatchObject({ status: 401 });

      expect(probe.auth().token).toBe("second-session");
      expect(tokenStore.get()).toBe("second-session");
      expect(location.pathname).toBe("/");
    } finally {
      probe.dispose();
    }
  });

  it("signs in with the admin password, fences stale 401s during reload, and excludes concurrent logout", async () => {
    const beforeReload = deferredResponse();
    const duringReload = deferredResponse();
    const reloadReply = deferredResponse();
    const logoutReply = deferredResponse();
    const fetch = stubFetch(async (input, init) => {
      const url = String(input);
      const headers = new Headers(init?.headers);
      if (url === "/api/v1/auth/session") return Response.json({ code: "UNAUTHENTICATED" }, { status: 401 });
      if (url === "/api/v1/auth/csrf") return Response.json({ csrf_token: "skm_csrf_login" });
      if (url === "/api/v1/auth/login") {
        expect(headers.get("X-SKM-CSRF")).toBe("skm_csrf_login");
        expect(init?.credentials).toBe("include");
        expect(headers.get("Authorization")).toBeNull();
        expect(init?.body).toBe(JSON.stringify({ password: "secret-password" }));
        return Response.json({
          session_id: "s", principal_id: "p", kind: "human", display_name: "Администратор",
          expires_at: "2026-01-02T00:00:00Z", csrf_token: "skm_csrf_session",
        });
      }
      if (url === "/api/v1/me") return Response.json(testIdentity);
      if (url === "/api/v1/plans?before-reload") return beforeReload.response;
      if (url === "/api/v1/plans?during-reload") return duringReload.response;
      if (url === "/api/v1/auth/session/reload") {
        expect(headers.get("X-SKM-CSRF")).toBe("skm_csrf_session");
        expect(init?.credentials).toBe("include");
        return reloadReply.response;
      }
      if (url === "/api/v1/auth/logout") {
        expect(headers.get("X-SKM-CSRF")).toBe("skm_csrf_rotated");
        expect(init?.credentials).toBe("include");
        return logoutReply.response;
      }
      if (url === "/api/v1/plans") {
        expect(headers.get("X-SKM-CSRF")).toBe("skm_csrf_rotated");
        expect(headers.get("Authorization")).toBeNull();
        return Response.json({ ok: true });
      }
      return Response.json({ ok: true });
    });
    const user = userEvent.setup();
    history.replaceState(null, "", "/login");
    const probe = openWithProbe(null);
    try {
      await user.type(await screen.findByLabelText("Пароль администратора"), "secret-password");
      await user.click(screen.getByRole("button", { name: "Войти по паролю" }));
      await screen.findByRole("heading", { name: "Главная", level: 1 });
      expect(probe.auth().mode).toBe("admin_login");
      expect(probe.auth().token).toBeNull();
      expect(sessionStorage.getItem("skm.token")).toBeNull();
      expect(document.body.textContent).not.toContain("secret-password");

      const generation = probe.auth().sessionGeneration;
      const staleBefore = probe.auth().transport.request("GET", "/api/v1/plans?before-reload");
      const reload = screen.getByRole<HTMLButtonElement>("button", { name: "Обновить сеанс" });
      const logout = screen.getByRole<HTMLButtonElement>("button", { name: "Выйти" });
      await user.click(reload);
      expect(probe.auth().sessionGeneration).toBeGreaterThan(generation);
      expect(reload.disabled).toBe(true);
      expect(logout.disabled).toBe(true);
      const staleDuring = probe.auth().transport.request("GET", "/api/v1/plans?during-reload");
      await act(async () => {
        beforeReload.reply(new Response(null, { status: 401 }));
        await expect(staleBefore).rejects.toMatchObject({ status: 401 });
        await probe.auth().signOut();
      });
      expect(location.pathname).toBe("/");
      expect(fetch.mock.calls.filter(([path]) => path === "/api/v1/auth/logout")).toHaveLength(0);
      await act(async () => {
        reloadReply.reply(Response.json({ csrf_token: "skm_csrf_rotated" }));
      });
      await waitFor(() => expect(logout.disabled).toBe(false));
      await act(async () => {
        duringReload.reply(new Response(null, { status: 401 }));
        await expect(staleDuring).rejects.toMatchObject({ status: 401 });
      });
      expect(location.pathname).toBe("/");
      await probe.auth().transport.request("POST", "/api/v1/plans", { body: { title: "x" } });

      await user.click(logout);
      expect(reload.disabled).toBe(true);
      expect(logout.disabled).toBe(true);
      await act(async () => { await probe.auth().reloadSession(); });
      expect(fetch.mock.calls.filter(([path]) => path === "/api/v1/auth/session/reload")).toHaveLength(1);
      await act(async () => { logoutReply.reply(Response.json({ status: "logged_out" })); });
      await screen.findByRole("heading", { name: "Вход в SKM" });
      expect(fetch.mock.calls.filter(([path]) => path === "/api/v1/auth/logout")).toHaveLength(1);
    } finally {
      probe.dispose();
    }
  });

  it("enters without a token when the server mode is none and closes streams on sign-out", async () => {
    const signals: AbortSignal[] = [];
    stubFetch(async (input, init) => {
      const url = String(input);
      if (url === "/api/v1/auth/session") {
        return Response.json({
          authenticated: true, mode: "none", auth_method: "none", principal_id: "p",
          kind: "human", display_name: "Локальный владелец", session_id: null, expires_at: null,
        });
      }
      if (url === "/api/v1/me") return Response.json(testIdentity);
      if (url.startsWith("/api/v1/events") || url.includes("/live")) {
        expect(init?.credentials).toBe("include");
        expect(new Headers(init?.headers).get("Authorization")).toBeNull();
        if (init?.signal) signals.push(init.signal);
        return new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
        });
      }
      return new Response(null, { status: 204 });
    });
    history.replaceState(null, "", "/");
    const probe = openWithProbe(null);
    try {
      await screen.findByRole("heading", { name: "Главная", level: 1 });
      expect(probe.auth().mode).toBe("none");
      expect(probe.auth().token).toBeNull();
      probe.auth().transport.events({ workspaceId: "ws-a" }, { onEvent: () => undefined });
      probe.auth().transport.live("attempt-a", { onEvent: () => undefined });
      await waitFor(() => expect(signals.length).toBe(2));
      await userEvent.click(screen.getByRole("button", { name: "Выйти" }));
      await screen.findByRole("heading", { name: "Вход в SKM" });
      expect(probe.auth().status).toBe("anonymous");
      expect(probe.auth().token).toBeNull();
      expect(signals.every((signal) => signal.aborted)).toBe(true);
    } finally {
      probe.dispose();
    }
  });

  it("keeps the session on 403 and signs out on 401", async () => {
    const fetch = stubFetch();
    tokenStore.set("valid-token");
    const probe = openWithProbe("valid-token");
    try {
      await screen.findByRole("heading", { name: "Главная", level: 1 });
      fetch.mockResolvedValueOnce(Response.json(
        { code: "FORBIDDEN", category: "forbidden", detail: "no" },
        { status: 403, headers: { "Content-Type": "application/problem+json" } },
      ));
      await act(async () => {
        await expect(probe.auth().transport.request("POST", "/api/v1/plans", { body: {} })).rejects.toMatchObject({ status: 403 });
      });
      expect(probe.auth().token).toBe("valid-token");
      expect(location.pathname).toBe("/");
      fetch.mockResolvedValueOnce(new Response(null, { status: 401 }));
      await act(async () => {
        await expect(probe.auth().transport.request("GET", "/api/v1/plans")).rejects.toMatchObject({ status: 401 });
      });
      await screen.findByRole("heading", { name: "Вход в SKM" });
      expect(probe.auth().token).toBeNull();
    } finally {
      probe.dispose();
    }
  });

  it("signs out through the shell and returns to login", async () => {
    stubFetch();
    tokenStore.set("valid-token");
    render(<App initialToken="valid-token" />);
    await userEvent.click(await screen.findByRole("button", { name: "Выйти" }));
    await screen.findByRole("heading", { name: "Вход в SKM" });
    expect(tokenStore.get()).toBeNull();
    expect(location.pathname).toBe("/login");
  });
});
