import { render, screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import { FakeTransport, Wrapper } from "../test/fakes";
import { ContributionRoute } from "./ContributionRoute";

const DETAIL = { $schema: "urn:swissknifeman:gui:view-data:v1", view: "resource-detail", title: "Plan one", fields: [] };

function transport() {
  const route = (id: string, path: string, scope: string) => ({ id: `gui-planner.${id}`, title: id, path, view: "resource-detail", scope,
    query: "gui-planner.overview" });
  return new FakeTransport({
    "GET /v1/ui/contributions": { $schema: "urn:swissknifeman:gui:catalog:v1", host: { gui_protocol: { min: "1", max: "1" } },
      contributions: [{ owner: "gui-planner", source: { kind: "unit" }, document: { routes: [
        route("overview", "plans/:plan_id", "plan"), route("item", "plans/:plan_id/items/:item_id", "item"),
        route("plan-no-id", "plans-all", "plan")] } }],
      rejected: [], digest: `sha256:${"0".repeat(64)}` },
    "POST /v1/queries/*": DETAIL,
  });
}

function open(path: string, fake: FakeTransport) {
  return render(
    <Wrapper transport={fake} path={path}>
      <Routes>
        <Route path="/x/:owner/*" element={<ContributionRoute />} />
      </Routes>
    </Wrapper>,
  );
}

describe("ContributionRoute", () => {
  it("sends the plan and item of the path in the context of the query", async () => {
    const fake = transport();
    open("/x/gui-planner/plans/PLAN1/items/P1.2?project=proj-1", fake);
    await screen.findByText("Plan one");
    const call = fake.calls.find((entry) => entry.path.startsWith("/v1/queries/"))!;
    expect(call.body).toEqual({ context: { project_id: "proj-1", plan_id: "PLAN1", item_id: "P1.2" },
      params: { plan_id: "PLAN1", item_id: "P1.2" } });
  });

  it("sends only the plan for a plan page", async () => {
    const fake = transport();
    open("/x/gui-planner/plans/PLAN1?project=proj-1", fake);
    await screen.findByText("Plan one");
    expect(fake.calls.find((entry) => entry.path.startsWith("/v1/queries/"))!.body).toEqual({
      context: { project_id: "proj-1", plan_id: "PLAN1" }, params: { plan_id: "PLAN1" } });
  });

  it("says what is missing for a plan page without a plan id in the path and does not query", async () => {
    const fake = transport();
    open("/x/gui-planner/plans-all?project=proj-1", fake);
    await screen.findByText("This page needs plan_id in its path.");
    await waitFor(() => expect(fake.calls.some((entry) => entry.path.startsWith("/v1/queries/"))).toBe(false));
  });
});
