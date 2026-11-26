// @vitest-environment jsdom
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import "../../../tests/setup";
import { App } from "../../app/App";

it("shows an expired predecessor and keeps the draft until a new confirmed submission", async () => {
  const writes: unknown[] = [];
  const scopes: string[] = [];
  const historyReads: string[] = [];
  stubFetch(async (input, init) => {
    const url = new URL(String(input), location.origin);
    if (url.pathname === "/api/v1/me") return Response.json({
      ...testIdentity,
      permissions_by_scope: { work: ["memory.write"] },
      effective_permissions: url.searchParams.get("scope_id") === "proj" ? ["memory.write"] : [],
    });
    if (init?.method === "POST") {
      writes.push(JSON.parse(String(init.body)));
      if (writes.length > 1) return Response.json({ entry_id: "replacement" }, { status: 201 });
      return Response.json({ code: "VERSION_CONFLICT", category: "conflict" }, {
        status: 409, headers: { "Content-Type": "application/problem+json" },
      });
    }
    if (url.pathname.endsWith("/memory/entries")) {
      historyReads.push(url.searchParams.get("include_expired") ?? "");
      return Response.json(url.searchParams.has("after") ? {
        items: [{ id: "current", kind: "active_handoff", state: "live", body: "Pool restarted", expires_at: "2000-01-01T00:00:00Z" }],
      } : { items: [{ id: "old", kind: "active_handoff", state: "superseded" }], next_cursor: "next" });
    }
    if (url.pathname.endsWith("/memory")) {
      scopes.push(url.searchParams.get("include_shared") ?? "");
      return Response.json({ items: [{ id: "old", kind: "active_handoff", body: "Hold", scope: { kind: "project" } }] });
    }
    return Response.json({ workspace_id: "work" });
  });
  history.replaceState(null, "", "/memory?project_id=proj&workspace_id=work");
  render(<App initialToken="test" />);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("checkbox", { name: "Включить общую память" }));
  await waitFor(() => expect(scopes).toContain("true"));
  expect(scopes[0]).toBe("false");
  await user.click(await screen.findByRole("button", { name: "Изменить передачу" }));
  await user.type(screen.getByRole("textbox", { name: "Текст передачи" }), " please");
  await user.click(screen.getByRole("button", { name: "Сохранить" }));
  await screen.findByRole("heading", { name: "Конфликт изменений" });
  await screen.findByText(/Pool restarted/);
  expect(historyReads).toEqual(["true", "true"]);
  expect(writes).toEqual([expect.objectContaining({ expected_handoff_id: "old", body: "Hold please" })]);
  const draft = screen.getByRole("textbox", { name: "Текст передачи" });
  expect(draft).toHaveProperty("value", "Hold please");
  await user.type(draft, "; verify the restarted pool");
  expect(writes).toHaveLength(1);
  await user.click(screen.getByRole("button", { name: "Сохранить с учётом текущей версии" }));
  await screen.findByText("Передача сохранена.");
  expect(writes[1]).toEqual(expect.objectContaining({
    expected_handoff_id: "current", body: "Hold please; verify the restarted pool",
  }));
});

it("hides write actions when the token is narrowed to another project", async () => {
  stubFetch(async input => {
    const url = new URL(String(input), location.origin);
    if (url.pathname.endsWith("/me")) return Response.json({
      ...testIdentity,
      token: { scope_id: "other", permissions: ["memory.write"] },
      permissions_by_scope: { work: ["memory.write"], other: ["memory.write"] },
      effective_permissions: url.searchParams.has("scope_id") ? [] : ["memory.write"],
    });
    return Response.json({ items: [{ id: "current", kind: "active_handoff", body: "Read only", scope: { kind: "project" } }] });
  });
  history.replaceState(null, "", "/memory?project_id=proj&workspace_id=work");
  render(<App initialToken="test" />);
  await screen.findByText("Read only");
  expect(screen.queryByRole("button", { name: "Новая передача" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Изменить передачу" })).toBeNull();
});

it("retains the current project when an earlier recall resolves late", async () => {
  let finishFirst!: (reply: Response) => void;
  const first = new Promise<Response>(resolve => { finishFirst = resolve; });
  const response = (body: string) => Response.json({ items: [{ id: body, kind: "fact", scope: { kind: "project" }, body }] });
  let requested = false;
  stubFetch(async input => {
    const url = new URL(String(input), location.origin);
    if (url.pathname.endsWith("/me")) return Response.json(testIdentity);
    if (url.pathname.includes("/first/memory")) { requested = true; return first; }
    return response("Current project");
  });
  history.replaceState(null, "", "/memory?project_id=first&workspace_id=w");
  render(<App initialToken="test" />);
  await waitFor(() => expect(requested).toBe(true));
  history.pushState(null, "", "/memory?project_id=second&workspace_id=w");
  await act(async () => { window.dispatchEvent(new PopStateEvent("popstate")); });
  await screen.findByText("Current project");
  await act(async () => { finishFirst(response("Previous project")); await first; });
  expect(screen.queryByText("Previous project")).toBeNull();
  expect(screen.getByText("Current project")).toBeTruthy();
});
