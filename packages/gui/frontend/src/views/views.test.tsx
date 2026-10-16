import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ViewData } from "../contracts";
import { FakeTransport, Wrapper } from "../test/fakes";
import { ViewDataView } from "./ViewDataView";

const examples = import.meta.glob("../../../schemas/view-data/v1/examples/valid/*.json", { eager: true, import: "default" });
const IMPLEMENTED = ["resource-list", "status-table", "metric-group", "timeline", "markdown", "log-stream", "command-form"];

function transport() {
  return new FakeTransport({
    "GET /v1/ui/contributions": { $schema: "urn:swissknifeman:gui:catalog:v1", host: { gui_protocol: { min: "1", max: "1" } },
      contributions: [], rejected: [], digest: `sha256:${"0".repeat(64)}` },
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
});
