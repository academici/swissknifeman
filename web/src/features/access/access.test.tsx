import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import type { Uuid } from "../../api/generated/kernel";
import { App } from "../../app/App";
import { tokenStore } from "../auth/tokenStore";

const principalId = "56c44502-acd3-417d-8c7c-be9e61406c0f" as Uuid;
const scopeId = "11111111-1111-4111-8111-111111111111" as Uuid;

const principal = {
  principal_id: principalId,
  kind: "human",
  display_name: "Аня",
  state: "active",
};

const membership = {
  scope_id: scopeId,
  scope_kind: "project",
  principal_id: principalId,
  display_name: "Аня",
  role: "viewer",
  granted_at: "2026-01-01T00:00:00.000Z",
};

function open(path: string) {
  tokenStore.set("admin-token");
  history.replaceState(null, "", path);
  render(<App initialToken="admin-token" />);
}

describe("principals and members", () => {
  it("lists, creates and disables a principal, then changes and revokes a role", async () => {
    const calls: { path: string; method: string; body: string | null; csrf: string | null }[] = [];
    stubFetch(async (input, init) => {
      const url = new URL(String(input), location.origin);
      const method = init?.method ?? "GET";
      calls.push({
        path: url.pathname,
        method,
        body: typeof init?.body === "string" ? init.body : null,
        csrf: new Headers(init?.headers).get("X-SKM-CSRF"),
      });
      if (url.pathname === "/api/v1/me") {
        return Response.json({
          ...testIdentity,
          effective_permissions: ["principal.manage", "membership.manage", "project.read"],
          permissions_by_scope: { [scopeId]: ["membership.manage", "project.read"] },
        });
      }
      if (url.pathname === "/api/v1/principals" && method === "GET") {
        return Response.json({ items: [principal], next: null });
      }
      if (url.pathname === "/api/v1/principals" && method === "POST") {
        return Response.json({ principal_id: principalId, row_version: 2 }, { status: 201 });
      }
      if (url.pathname === `/api/v1/principals/${principalId}` && method === "GET") {
        return Response.json({
          ...principal,
          created_at: "2026-01-01T00:00:00.000Z",
          row_version: 4,
          identities: [],
        }, { headers: { ETag: 'W/"v4"' } });
      }
      if (url.pathname === `/api/v1/principals/${principalId}/disable`) {
        expect(new Headers(init?.headers).get("If-Match")).toBe('W/"v4"');
        return Response.json({ principal_id: principalId, row_version: 5 });
      }
      if (url.pathname === "/api/v1/memberships" && method === "GET") {
        return Response.json({ items: [membership], next: null });
      }
      if (url.pathname === "/api/v1/memberships" && method === "POST") {
        return Response.json({ scope_id: scopeId, principal_id: principalId, role: "member" }, { status: 201 });
      }
      if (url.pathname === `/api/v1/memberships/${scopeId}/${principalId}` && method === "DELETE") {
        return Response.json({ scope_id: scopeId, principal_id: principalId, removed: true });
      }
      if (url.pathname === "/api/v1/projects/project-a") {
        return Response.json({
          project_id: "project-a", workspace_id: "ws-a", title: "Пример", state: "active", row_version: 1,
        });
      }
      if (url.pathname === "/api/v1/workspaces/ws-a") {
        return Response.json({ workspace_id: "ws-a", title: "Пространство", slug: "example", state: "active", project_count: 1, row_version: 1 });
      }
      return Response.json({ items: [], next: null });
    });
    open("/admin/principals");
    expect(await screen.findByRole("cell", { name: "Аня" })).toBeTruthy();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Отображаемое имя"), "Борис");
    await user.click(screen.getByRole("button", { name: "Создать принципала" }));
    await waitFor(() => expect(calls.some((call) => call.path === "/api/v1/principals" && call.method === "POST")).toBe(true));
    expect(calls.find((call) => call.method === "POST" && call.path === "/api/v1/principals")?.body).toContain("Борис");

    await user.click(screen.getByRole("button", { name: "Отключить" }));
    await user.type(screen.getByRole("textbox"), "ушёл из команды");
    await user.click(screen.getByRole("button", { name: "Подтвердить" }));
    await waitFor(() => expect(calls.some((call) => call.path.endsWith("/disable"))).toBe(true));

    await user.click(screen.getByRole("button", { name: "Роли" }));
    await user.selectOptions(await screen.findByLabelText("Роль Аня"), "member");
    await waitFor(() => expect(calls.some((call) => call.path === "/api/v1/memberships" && call.method === "POST" && call.body?.includes("\"role\":\"member\""))).toBe(true));
    await user.click(screen.getByRole("button", { name: "Отозвать" }));
    await waitFor(() => expect(calls.some((call) => call.method === "DELETE")).toBe(true));
  });

  it("manages project members from the project page", async () => {
    const methods: string[] = [];
    stubFetch(async (input, init) => {
      const url = new URL(String(input), location.origin);
      const method = init?.method ?? "GET";
      if (url.pathname === "/api/v1/memberships") methods.push(method);
      if (url.pathname === "/api/v1/me") {
        return Response.json({
          ...testIdentity,
          effective_permissions: ["membership.manage", "project.read"],
          permissions_by_scope: { "project-a": ["membership.manage", "project.read"], "ws-a": ["project.read"] },
        });
      }
      if (url.pathname === "/api/v1/projects/project-a") {
        return Response.json({
          project_id: "project-a", workspace_id: "ws-a", title: "Пример", state: "active", description: "", row_version: 1,
        });
      }
      if (url.pathname === "/api/v1/workspaces/ws-a") {
        return Response.json({ workspace_id: "ws-a", slug: "example", title: "Пространство", state: "active" });
      }
      if (url.pathname === "/api/v1/memberships" && method === "GET") {
        return Response.json({ items: [{ ...membership, scope_id: "project-a" }], next: null });
      }
      if (url.pathname === "/api/v1/memberships" && method === "POST") {
        return Response.json({ scope_id: "project-a", principal_id: principalId, role: "member" }, { status: 201 });
      }
      return Response.json({ items: [], next: null });
    });
    open("/p/project-a");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "Members" }));
    const member = await screen.findByRole("row", { name: /Аня/u });
    expect(within(member).getByText(principalId)).toBeTruthy();
    await user.click(within(member).getByRole("button", { name: "Копировать идентификатор" }));
    const principalInput = screen.getByLabelText<HTMLInputElement>("Идентификатор принципала");
    await user.click(principalInput);
    await user.paste();
    expect(principalInput.value).toBe(principalId);
    await user.click(screen.getByRole("button", { name: "Назначить роль" }));
    await waitFor(() => expect(methods).toContain("POST"));
  });
});
