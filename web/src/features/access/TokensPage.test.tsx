import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { App } from "../../app/App";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import "../../../tests/setup";

it("issues scoped credentials once, copies exchange data and revokes an exchanged token", async () => {
  const workspace = { workspace_id: "workspace-a", title: "Команда" };
  const projects = [
    { project_id: "project-a", workspace_id: workspace.workspace_id, title: "Первый проект" },
    { project_id: "project-b", workspace_id: workspace.workspace_id, title: "Второй проект" },
  ];
  const exchanged = { token_id: "token-a", name: "pairing-old", state: "active", prefix: "skm_old" };
  const expiry = "2026-11-23T12:00:00Z";
  const pairing = { workspace_id: workspace.workspace_id, pairing_id: "pairing-a", pairing_secret: "skm_pair_secret" };
  const posts: { path: string; body: unknown; idempotency: string | null }[] = [];
  let revoked = false;
  stubFetch(async (input, init) => {
    const url = new URL(String(input), location.origin);
    const path = url.pathname;
    if (init?.method === "POST") {
      posts.push({ path, body: typeof init.body === "string" ? JSON.parse(init.body) : null,
        idempotency: new Headers(init.headers).get("Idempotency-Key") });
      if (path === "/api/v1/tokens") return Response.json({ token_id: "issued-a", secret: "skm_once", expires_at: expiry });
      if (path === "/api/v1/auth/pairing") return Response.json({ ...pairing, expires_at: expiry });
      if (path === "/api/v1/tokens/token-a/revoke") { revoked = true; return Response.json({}); }
    }
    if (path === "/api/v1/me") {
      const scope = url.searchParams.get("scope_id");
      return Response.json({ ...testIdentity, effective_permissions: [
        scope === "project-a" ? "project.read" : scope === "project-b" ? "context.read" : "token.own",
      ] });
    }
    if (path === "/api/v1/workspaces") return Response.json({ items: [workspace], next: null });
    if (path === "/api/v1/workspaces/workspace-a/projects") return Response.json({ items: projects, next: null });
    if (path === "/api/v1/tokens") {
      expect(url.searchParams.get("include_inactive")).toBe("false");
      return Response.json({ items: revoked ? [] : [exchanged], next: null });
    }
    throw new Error(`Unexpected request ${path}`);
  });
  const user = userEvent.setup();
  const clipboard = vi.spyOn(navigator.clipboard, "writeText");
  history.replaceState(null, "", "/admin/tokens");
  render(<App initialToken="operator" />);
  expect(await screen.findByRole("link", { name: "Токены", current: "page" })).toBeTruthy();
  await screen.findByRole("option", { name: workspace.title });
  await user.selectOptions(screen.getByLabelText("Рабочее пространство"), workspace.workspace_id);
  for (const project of projects) {
    await screen.findByRole("option", { name: project.title });
    await user.selectOptions(screen.getByLabelText("Проект токена"), project.project_id);
    await user.click(screen.getByRole("button", { name: "Добавить проект" }));
  }
  await user.click(await screen.findByRole("checkbox", { name: "project.read" }));
  expect(screen.getByRole("button", { name: "Создать токен" })).toHaveProperty("disabled", true);
  await user.click(await screen.findByRole("checkbox", { name: "context.read" }));
  await user.type(screen.getByLabelText("Название токена"), "Multi project");
  await user.click(screen.getByRole("button", { name: "Создать токен" }));
  let dialog = within(await screen.findByRole("dialog", { name: "Секрет токена" }));
  expect(dialog.getByLabelText("Секрет токена")).toHaveProperty("value", "skm_once");
  await user.click(dialog.getByRole("button", { name: "Копировать секрет" }));
  expect(clipboard).toHaveBeenCalledWith("skm_once");
  await user.click(dialog.getByRole("button", { name: "Закрыть" }));
  expect(screen.queryByDisplayValue("skm_once")).toBeNull();
  expect(posts[0]).toEqual({ path: "/api/v1/tokens", idempotency: null, body: {
    name: "Multi project", scope_grants: [
      { scope_id: "project-a", permissions: ["project.read"] },
      { scope_id: "project-b", permissions: ["context.read"] },
    ],
  } });

  await user.selectOptions(screen.getByLabelText("Способ выдачи"), "pairing");
  await user.click(screen.getByRole("button", { name: "Создать код сопряжения" }));
  dialog = within(await screen.findByRole("dialog", { name: "Одноразовый код сопряжения" }));
  expect(dialog.getByText("/api/v1/auth/pairing/exchange")).toBeTruthy();
  await user.click(dialog.getByRole("button", { name: "Копировать JSON для обмена" }));
  expect(clipboard).toHaveBeenCalledWith(JSON.stringify(pairing, null, 2));
  expect(posts[1]).toEqual({ path: "/api/v1/auth/pairing", idempotency: null, body: {
    workspace_id: workspace.workspace_id, principal_id: testIdentity.principal.principal_id, ttl_seconds: 900,
    scope_grants: { "project-a": ["project.read"], "project-b": ["context.read"] },
  } });
  await user.click(dialog.getByRole("button", { name: "Закрыть" }));
  expect(screen.queryByDisplayValue(pairing.pairing_secret)).toBeNull();

  await user.click(screen.getByRole("button", { name: "Отозвать pairing-old" }));
  dialog = within(await screen.findByRole("dialog", { name: "Отзыв токена" }));
  await user.click(dialog.getByRole("button", { name: "Подтвердить отзыв" }));
  await waitFor(() => expect(screen.queryByRole("button", { name: "Отозвать pairing-old" })).toBeNull());
  expect(posts[2]).toMatchObject({ path: "/api/v1/tokens/token-a/revoke", idempotency: expect.any(String) });
  expect(JSON.stringify(sessionStorage)).not.toMatch(/skm_once|skm_pair_secret/);
});
