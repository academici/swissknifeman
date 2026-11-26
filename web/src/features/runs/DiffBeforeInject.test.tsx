import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { App } from "../../app/App";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import "../../../tests/setup";

it("compares Hub manifest metadata and drops private episode rows from preview and text actions", async () => {
  const baseline = "11111111-1111-4111-8111-111111111111";
  const root = "/api/v1/projects/project-a/context-manifests/manifest-a";
  const forbidden = { block_type: "memory", classification: "HOST_PRIVATE", change: "added", included: true, pos: 99,
    source: "private-episode-text", source_ref: "private-episode-text" };
  const calls: string[] = [];
  stubFetch(async (input, init) => {
    const url = new URL(String(input), location.origin);
    const path = url.pathname;
    calls.push(path + url.search);
    expect(init?.method).toBe("GET");
    if (path === "/api/v1/me") return Response.json(testIdentity);
    if (path === "/api/v1/projects/project-a") return Response.json({ workspace_id: "workspace-a" });
    if (path === "/api/v1/workspaces/workspace-a") return Response.json({ title: "Scope" });
    if (path === "/api/v1/steps/step-a") return Response.json({ context_manifest_id: "manifest-a" });
    if (path === root) return Response.json({ state: "draft", route: {}, rows: [forbidden], excluded: [forbidden] });
    if (path === root + "/diff") {
      expect([...url.searchParams]).toEqual([["base_manifest_id", baseline]]);
      return Response.json({ blocks: [
        { block_type: "runtime_notes", source_ref: "guideline:public", change: "changed", tokens: { from: 12, to: 20 } },
        { block_type: "memory", source_ref: "memory:project-handoff", change: "added", tokens: { from: null, to: 80 } },
        { block_type: "memory", source_ref: "episode:also-private", change: "removed" },
        forbidden,
      ], counts: {}, tokens: {} });
    }
    return Response.json({ items: [], next: null });
  });
  history.replaceState(null, "", "/steps/step-a/context?project_id=project-a&workspace_id=workspace-a");
  render(<App initialToken="operator" />);
  const input = await screen.findByLabelText("ID базового манифеста");
  const submit = screen.getByRole("button", { name: "Сравнить манифесты" });
  expect(submit).toHaveProperty("disabled", true);
  expect(calls.some(path => path.includes("/diff"))).toBe(false);
  fireEvent.change(input, { target: { value: baseline } });
  fireEvent.click(submit);
  expect(await screen.findByRole("cell", { name: "Рекомендации для среды и модели" })).toBeTruthy();
  expect(screen.getByRole("cell", { name: "Память проекта" })).toBeTruthy();
  expect(screen.getByRole("cell", { name: "80" })).toBeTruthy();
  expect(document.body.textContent).not.toMatch(/private-episode-text|also-private/);
  expect(screen.queryByRole("button", { name: "Текст блока 99" })).toBeNull();
  expect(calls.some(path => /\/text|\/memory|episode/.test(path))).toBe(false);
});
