import type { APIRequestContext } from "@playwright/test";
import type { CreatePlanResult } from "../../src/api/generated/planning";
import type { EventConnection } from "./global-setup";
import { api, expect, ownerToken, projectId, signIn, test } from "./fixtures";

function observed(connections: EventConnection[], plan: string) {
  return connections.flatMap(({ events }) => events.filter(({ data, type }) => type === "PlanCreated" && data.includes(plan)));
}

async function proxy(request: APIRequestContext, action?: "disconnect" | "restore"): Promise<EventConnection[]> {
  const response = await request.fetch(`/__skm_e2e/events${action ? "/" + action : ""}`, {
    method: action ? "POST" : "GET",
    headers: { Authorization: `Bearer ${ownerToken()}` },
  });
  expect(response.ok()).toBe(true);
  return await response.json() as EventConnection[];
}

test("resumes the durable event stream at the last cursor after a socket disconnect", async ({ page, request }) => {
  const plans = `/projects/${projectId()}/plans`;
  await signIn(page, undefined, `/p/${projectId()}/plans`);
  await expect(page.getByRole("button", { name: "Создать план" })).toBeVisible();
  const create = (title: string) => api<CreatePlanResult>(request, "POST", plans, { title });
  const before = await create("Before connection loss");
  const firstPlan = page.getByRole("row", { name: /Before connection loss/ });
  await expect(firstPlan).toHaveCount(1);
  await expect.poll(async () => observed(await proxy(request), before.plan_id).length).toBe(1);

  const openConnections = await proxy(request, "disconnect");
  try {
    const cursor = openConnections.at(-1)?.events.at(-1)?.id;
    expect(cursor).toMatch(/^\d+$/);
    const during = await create("Created while disconnected");
    const after = await create("Second offline mutation");
    await expect(page.getByRole("row", { name: /Created while disconnected/ })).toHaveCount(0);

    await proxy(request, "restore");
    await expect(page.getByRole("row", { name: /Created while disconnected/ })).toHaveCount(1);
    await expect(page.getByRole("row", { name: /Second offline mutation/ })).toHaveCount(1);
    await expect(firstPlan).toHaveCount(1);

    const replay = (await proxy(request)).slice(openConnections.length);
    expect(replay[0]?.lastEventId).toBe(cursor);
    expect(observed(replay, before.plan_id)).toHaveLength(0);
    const missed = observed(replay, during.plan_id);
    const subsequent = observed(replay, after.plan_id);
    expect(missed).toHaveLength(1);
    expect(subsequent).toHaveLength(1);
    expect(Number(missed[0]?.id)).toBeGreaterThan(Number(cursor));
    expect(Number(subsequent[0]?.id)).toBeGreaterThan(Number(missed[0]?.id));
  } finally {
    await proxy(request, "restore");
  }
});
