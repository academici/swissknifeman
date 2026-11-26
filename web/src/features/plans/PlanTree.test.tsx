import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { App } from "../../app/App";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";

it("joins the paged outline by identity in server order, selects unitless items and uses server preview lanes", async () => {
  const tree = { phases: [{ key: "P1", items: [{ key: "P1.9", units: [] }, { key: "P1.1", units: [{ key: "P1.1/U1" }] }] }] };
  const rows = [
    ["p", "P1", "phase", "Phase"], ["single", "P1.9", "item", "Alone"], ["parent", "P1.1", "item", "Parent"],
    ["stable-unit", "P1.1/U1", "unit", "Unit"], ["req", "R1", "requirement", "Required"],
  ].map(([entity_id, display_key, entity_kind, title], position) => ({ entity_id, display_key, entity_kind, title, position }));
  const paths: URL[] = [];
  stubFetch(async (input) => {
    const url = new URL(String(input), location.origin);
    paths.push(url);
    const path = url.pathname;
    if (path === "/api/v1/me") return Response.json(testIdentity);
    if (path === "/api/v1/events") return new Response(new ReadableStream(), { headers: { "Content-Type": "text/event-stream" } });
    if (path === "/api/v1/workspaces/ws") return Response.json({});
    if (path === "/api/v1/plans/plan") return Response.json({
      plan_id: "plan", workspace_id: "ws", project_id: "project", alias: "PLAN1", title: "Title",
      current_revision_no: 1, current_revision_id: "rev", open_drafts: 0, lifecycle_state: "active",
    });
    if (path.endsWith("/revisions")) return Response.json({ items: [{ revision_id: "rev", revision_no: 1 }], next_cursor: null });
    if (path.endsWith("/revisions/rev")) return Response.json({ tree }, { headers: { "SKM-Events-Cursor": "17" } });
    if (path.endsWith("/entities")) {
      expect(url.searchParams.get("revision_id")).toBe("rev");
      return Response.json(url.searchParams.has("after") ? { items: rows.slice(2), next_cursor: null } : { items: rows.slice(0, 2), next_cursor: "next" });
    }
    if (path.includes("/entities/")) {
      const row = rows.find((r) => r.display_key === decodeURIComponent(path.split("/").at(-1)!));
      return Response.json({ ...row, document: { summary: "**Details**" }, links: {} });
    }
    if (path.endsWith("/ready-preview")) return Response.json({
      lanes: [{ kind: "task", tasks: ["P1.9"], route: null, batch_key: null }], limit: 3,
      waiting: [], conflicts: [], deferred: [], route_groups: [],
    });
    throw new Error(path);
  });
  sessionStorage.setItem("skm.scope", JSON.stringify({ workspaceId: "ws", projectId: "project" }));
  history.replaceState(null, "", "/plans/plan");
  render(<App initialToken="test" />);
  const phase = await screen.findByText("P1 · Phase", { selector: "summary" }, { timeout: 5000 });
  fireEvent.click(phase);
  const nodes = within(phase.closest("details")!);
  await userEvent.click(nodes.getByRole("button", { name: "P1.9 · Alone" }));
  expect(await screen.findByText("single", { selector: "code" })).toBeTruthy();
  expect(await screen.findByText("Details", { selector: "strong" })).toBeTruthy();
  const parent = nodes.getByText("P1.1 · Parent", { selector: "summary" });
  expect(nodes.getByRole("button", { name: "P1.9 · Alone" }).compareDocumentPosition(parent) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  fireEvent.click(parent);
  await userEvent.click(nodes.getByRole("button", { name: "P1.1/U1 · Unit" }));
  expect(await screen.findByText("stable-unit", { selector: "code" })).toBeTruthy();
  expect(paths.some((url) => url.pathname.endsWith("/revisions/rev/entities/P1.1%2FU1"))).toBe(true);
  await waitFor(() => expect(paths.find((url) => url.pathname.endsWith("/events"))?.searchParams.get("after")).toBe("17"));
  await userEvent.click(screen.getByRole("tab", { name: "Предпросмотр" }));
  expect(await screen.findByText("task · P1.9")).toBeTruthy();
  await userEvent.type(screen.getByRole("textbox", { name: "Считать разрешёнными" }), "  Security review , , Release approval  ");
  await userEvent.click(screen.getByRole("button", { name: "Показать предпросмотр" }));
  await waitFor(() => expect(paths.filter((url) => url.pathname.endsWith("/ready-preview")).at(-1)
    ?.searchParams.getAll("assume_granted")).toEqual(["Security review", "Release approval"]));
});
