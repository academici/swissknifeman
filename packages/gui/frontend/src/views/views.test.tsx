import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ViewData } from "../contracts";
import { FakeTransport, Wrapper } from "../test/fakes";
import { ViewDataView } from "./ViewDataView";

const examples = import.meta.glob("../../../schemas/view-data/v1/examples/valid/*.json", { eager: true, import: "default" });
const IMPLEMENTED = ["resource-list", "status-table", "metric-group", "timeline", "markdown", "log-stream", "command-form",
  "resource-detail", "board", "dependency-graph", "schema-form"];

const ROUTE = { id: "gui-planner.item", title: "Item", path: "plans/:plan_id/items/:item_id", view: "resource-detail", scope: "item" };

function transport() {
  return new FakeTransport({
    "GET /v1/ui/contributions": { $schema: "urn:swissknifeman:gui:catalog:v1", host: { gui_protocol: { min: "1", max: "1" } },
      contributions: [{ owner: "gui-planner", source: { kind: "unit" }, document: { routes: [ROUTE] } }],
      rejected: [], digest: `sha256:${"0".repeat(64)}` },
    "GET /v1/commands": { $schema: "urn:swissknifeman:gui:run-api:v1", kind: "command_list", commands: [] },
    "GET /v1/runs/*": { $schema: "urn:swissknifeman:gui:run-api:v1", kind: "log_page", run_id: `run-${"a".repeat(32)}`,
      stream: "stdout", chunks: [], next_cursor: null },
  });
}

describe("host views render every valid view-data example", () => {
  const entries = Object.entries(examples) as Array<[string, ViewData]>;
  it("finds the examples", () => expect(entries.length).toBeGreaterThanOrEqual(11));
  for (const [file, data] of entries) {
    it(file.split("/").at(-1)!, () => {
      const { container } = render(
        <Wrapper transport={transport()}>
          <ViewDataView data={data} />
        </Wrapper>,
      );
      if (IMPLEMENTED.includes(data.view)) expect(container.querySelector(".placeholder")).toBeNull();
      else expect(container.querySelector(".placeholder")).not.toBeNull();
    });
  }

  it("shows cells, statuses and repairs as text", () => {
    const data = examples["../../../schemas/view-data/v1/examples/valid/status-table.json"] as ViewData;
    render(
      <Wrapper transport={transport()}>
        <ViewDataView data={data} onAction={() => undefined} />
      </Wrapper>,
    );
    expect(screen.getByText("node not found")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Repair" })).toBeTruthy();
  });

  it("renders hostile strings as text, not markup", () => {
    const data: ViewData = { $schema: "urn:swissknifeman:gui:view-data:v1", view: "resource-list",
      columns: [{ id: "name", title: "Name", type: "text" }],
      rows: [{ id: "r", cells: { name: "<img src=x onerror=alert(1)>" } }] };
    const { container } = render(
      <Wrapper transport={transport()}>
        <ViewDataView data={data} />
      </Wrapper>,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeTruthy();
  });

  const base = { $schema: "urn:swissknifeman:gui:view-data:v1" } as const;

  it("shows a board with counts, an empty column, status text and a link inside the app", async () => {
    const data: ViewData = { ...base, view: "board", columns: [
      { id: "todo", title: "To do", cards: [{ id: "P1.1", title: "First <b>x</b>", subtitle: "P1", status: "warn",
        link: { route: "gui-planner.item", params: { plan_id: "PLAN1", item_id: "P1.1" } } }] },
      { id: "done", title: "Done", cards: [] }] };
    const { container } = render(
      <Wrapper transport={transport()}>
        <ViewDataView data={data} projectId="proj-1" />
      </Wrapper>,
    );
    expect(screen.getByLabelText("To do, 1")).toBeTruthy();
    expect(screen.getByLabelText("Done, 0")).toBeTruthy();
    expect(screen.getByText("No items.")).toBeTruthy();
    expect(screen.getByText("warn")).toBeTruthy();
    expect(screen.getByText("First <b>x</b>")).toBeTruthy();
    expect(container.querySelector("b")).toBeNull();
    const link = await screen.findByRole("link", { name: "P1.1" });
    expect(link.getAttribute("href")).toBe("/x/gui-planner/plans/PLAN1/items/P1.1?project=proj-1");
  });

  it("makes a card with an unknown route plain text", () => {
    const data: ViewData = { ...base, view: "board", columns: [
      { id: "c", title: "C", cards: [{ id: "X", title: "t", link: { route: "evil.route", params: {} } }] }] };
    render(
      <Wrapper transport={transport()}>
        <ViewDataView data={data} projectId="proj-1" />
      </Wrapper>,
    );
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("X")).toBeTruthy();
  });

  it("draws a dependency graph, skips an edge to a missing node and lists the dependencies as text", () => {
    const data: ViewData = { ...base, view: "dependency-graph",
      nodes: [{ id: "A", label: "A first", status: "ok", group: "P1" }, { id: "B", label: "B second", status: "warn", group: "P2" },
        { id: "A", label: "A again", group: "P1" }],
      edges: [{ from: "A", to: "B", kind: "blocks" }, { from: "B", to: "A", kind: "related" }, { from: "A", to: "GONE", kind: "blocks" },
        { from: "GONE", to: "B", kind: "related" }] };
    const { container } = render(
      <Wrapper transport={transport()}>
        <ViewDataView data={data} />
      </Wrapper>,
    );
    expect(container.querySelectorAll("g.graph-node").length).toBe(2);
    expect(container.querySelectorAll("line").length).toBe(2);
    expect(container.querySelectorAll("line.graph-edge-related").length).toBe(1);
    expect(container.querySelector("svg")?.getAttribute("aria-label")).toBe("Dependency graph, 2 nodes, 2 edges");
    const rows = Array.from(container.querySelectorAll("tbody tr")).map((row) => Array.from(row.querySelectorAll("td")).map((cell) => cell.textContent));
    expect(rows).toEqual([["A first", "ok", "—", "B"], ["B second", "warn", "A", "—"]]);
  });

  it("renders an empty graph and many nodes without failing", () => {
    const empty: ViewData = { ...base, view: "dependency-graph", nodes: [], edges: [] };
    const { container, rerender } = render(
      <Wrapper transport={transport()}>
        <ViewDataView data={empty} />
      </Wrapper>,
    );
    expect(screen.getByText("Nothing to show.")).toBeTruthy();
    const nodes = Array.from({ length: 400 }, (_, i) => ({ id: `N${i}`, label: `Node ${i}`, group: `G${i % 5}` }));
    const edges = nodes.slice(1).map((node, i) => ({ from: `N${i}`, to: node.id, kind: "blocks" as const }));
    rerender(
      <Wrapper transport={transport()}>
        <ViewDataView data={{ ...base, view: "dependency-graph", nodes, edges }} />
      </Wrapper>,
    );
    expect(container.querySelectorAll("g.graph-node").length).toBe(400);
  });

  it("shows a resource detail by field type, markdown sections and actions", () => {
    const seen: string[] = [];
    const data: ViewData = { ...base, view: "resource-detail", title: "Item <i>x</i>", fields: [
      { label: "Status", value: "ok", type: "status" }, { label: "Done", value: 50, type: "progress" },
      { label: "At", value: "2026-10-16T10:00:00Z", type: "date" }, { label: "Owner", value: null, type: "text" }],
      sections: [{ title: "Goal", markdown: "Make **it** <script>bad()</script>" }],
      actions: [{ command: "gui-planner.item-reopen", input: { reason: "r" } }] };
    const { container } = render(
      <Wrapper transport={transport()}>
        <ViewDataView data={data} onAction={(action) => seen.push(action.command)} />
      </Wrapper>,
    );
    expect(screen.getByText("Item <i>x</i>")).toBeTruthy();
    expect(container.querySelector("i")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByLabelText("Done: 50%")).toBeTruthy();
    expect(container.querySelector("time")?.getAttribute("datetime")).toBe("2026-10-16T10:00:00Z");
    expect(container.querySelector("strong")?.textContent).toBe("it");
    screen.getByRole("button", { name: "gui-planner.item-reopen" }).click();
    expect(seen).toEqual(["gui-planner.item-reopen"]);
  });

  it("draws a progress cell of a list with an accessible label", () => {
    const data: ViewData = { ...base, view: "resource-list", columns: [{ id: "p", title: "P", type: "progress" }],
      rows: [{ id: "r", cells: { p: 25 } }] };
    render(
      <Wrapper transport={transport()}>
        <ViewDataView data={data} />
      </Wrapper>,
    );
    expect(screen.getByLabelText("25%")).toBeTruthy();
  });
});
