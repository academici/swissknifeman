// @vitest-environment jsdom
import "../../../tests/setup";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import type { ReviewRoiView } from "../../api/generated/execution";
import type { Uuid } from "../../api/generated/kernel";
import { App } from "../../app/App";

const runId = "018f2322-6c2c-7c89-a169-6bb6ab1adfd1" as Uuid;
const apiPath = `/api/v1/runs/${runId}/analytics/review-roi`;
const report: ReviewRoiView = {
  run_id: runId,
  completed_agent_reviews: 2,
  completed_human_reviews: 0,
  unique_findings: 4,
  resolved_findings: 3,
  rejected_findings: 1,
  finished_reviewer_steps: 5,
  priced_reviewer_steps: 3,
  observed_cost_usd: "0.001500",
  timed_reviewer_steps: 4,
  observed_duration_ms: 750,
};

function open(respond: () => Response, hasRuns = true) {
  const requests: string[] = [];
  stubFetch(async (input, init) => {
    const url = new URL(String(input), location.origin);
    switch (url.pathname) {
      case "/api/v1/me": return Response.json(testIdentity);
      case "/api/v1/projects/project-a": return Response.json({ project_id: "project-a", workspace_id: "ws-a" });
      case "/api/v1/workspaces/ws-a": return Response.json({ workspace_id: "ws-a", title: "Workspace" });
      case "/api/v1/workspaces/ws-a/projects": return Response.json({ items: [], next: null });
      case "/api/v1/workspaces": return Response.json({ items: [], next: null });
      case "/api/v1/projects/project-a/runs": return Response.json({
        items: hasRuns ? [{ run_id: runId, plan_alias: "PLAN1", kind: "plan" }] : [], next_after: null,
      });
      case apiPath:
        requests.push(init?.method ?? "GET");
        return respond();
      default: throw new Error("Unexpected request " + url.pathname);
    }
  });
  history.replaceState(null, "", "/p/project-a/analytics");
  render(<App initialToken="test-token" />);
  return requests;
}

describe("AnalyticsPage", () => {
  it("loads the selected run and displays observed outcomes and coverage", async () => {
    const requests = open(() => Response.json(report));
    const select = await screen.findByRole("combobox", { name: "Запуск" });
    expect(requests).toEqual([]);
    expect(screen.getByRole("link", { name: "Аналитика" }).getAttribute("href")).toBe("/p/project-a/analytics");
    await userEvent.setup().selectOptions(select, runId);
    expect(await screen.findByText("0.001500")).toBeTruthy();
    expect(screen.getByText("3 из 5")).toBeTruthy();
    expect(screen.getByText("4 из 5")).toBeTruthy();
    expect(screen.getByText("Устранённые замечания").nextElementSibling?.textContent).toBe("3");
    expect(requests).toEqual(["GET"]);
  });

  it("shows an empty project without requesting a run report", async () => {
    const requests = open(() => Response.json(report), false);
    expect(await screen.findByText("Нет запусков.")).toBeTruthy();
    expect(requests).toEqual([]);
  });

  it("distinguishes missing measurements from measured zero", async () => {
    open(() => Response.json({
      ...report,
      observed_cost_usd: null, priced_reviewer_steps: 0,
      observed_duration_ms: 0, timed_reviewer_steps: 1,
    }));
    await userEvent.setup().selectOptions(await screen.findByRole("combobox", { name: "Запуск" }), runId);
    expect(await screen.findByText("Нет данных")).toBeTruthy();
    expect(screen.getByText("Зафиксированное время работы, мс").nextElementSibling?.textContent).toBe("0");
  });

  it("displays an access error for the selected run", async () => {
    open(() => Response.json({ code: "FORBIDDEN", category: "forbidden", request_id: "req-review-roi" }, {
      status: 403, headers: { "Content-Type": "application/problem+json" },
    }));
    await userEvent.setup().selectOptions(await screen.findByRole("combobox", { name: "Запуск" }), runId);
    expect(await screen.findByText("FORBIDDEN")).toBeTruthy();
  });
});
