import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { App } from "../../app/App";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import "../../../tests/setup";

it("filters by host, shows route substitutions and budgets, and refreshes the published model catalog", async () => {
  const host = "11111111-1111-4111-8111-111111111111";
  const requests: string[] = [];
  let catalogReads = 0;
  const entry = (key: string, value: unknown) => ({ key, value, sensitivity: "public" });
  stubFetch(async input => {
    const url = new URL(String(input), location.origin);
    requests.push(url.pathname + url.search);
    switch (url.pathname) {
      case "/api/v1/me":
        return Response.json({ ...testIdentity, effective_permissions: ["runtime.read", "workspace.read", "config.read"] });
      case "/api/v1/hosts":
        return Response.json({ items: [{
          host_id: host, name: "Хост сборки", platform: { os: "linux", arch: "x86_64" }, state: "active",
        }], next: null });
      case "/api/v1/runtimes":
        return Response.json({ items: [] });
      case "/api/v1/runtimes/models":
        if (url.searchParams.get("prepare_for") === "model-a") {
          expect(url.searchParams.get("runtime_id")).toBe("codex");
          return Response.json({ models: [{ id: "model-a", guideline: { key: "public-model-guideline" } }] });
        }
        catalogReads += 1;
        return Response.json({ catalog_version: "catalog-" + catalogReads, stale: false,
          models: [{ id: "model-a", runtime_id: "codex", display_name: "Модель A", status: "active" }] });
      case "/api/v1/config/effective":
        if (url.searchParams.get("scope") === `host:${host}`) return Response.json({ keys: [
          entry("runtimes.host.route_substitutions", [{
            requested: { runtime_id: "codex", model_id: "model-a", effort: "high" },
            selected: { runtime_id: "claude", model_id: "model-b", effort: "medium" },
          }]),
        ] });
        return Response.json({ keys: [entry("budgets.run.max_usd", 23)] });
      default:
        return Response.json({ items: [], next: null });
    }
  });
  history.replaceState(null, "", "/runtimes");
  render(<App initialToken="operator" />);
  await screen.findByRole("option", { name: /Хост сборки/ });
  fireEvent.change(screen.getByLabelText("Хост"), { target: { value: host } });
  expect(await screen.findByRole("cell", { name: "claude / model-b / medium" })).toBeTruthy();
  expect(requests).toContain(`/api/v1/runtimes?host_id=${host}`);
  expect(screen.getByRole("link", { name: "Настройки хоста" }).getAttribute("href"))
    .toBe(`/settings?scope=host%3A${host}`);
  expect(await screen.findByText("23")).toBeTruthy();

  fireEvent.click(await screen.findByRole("button", { name: "Рекомендации · model-a" }));
  expect(await screen.findByText(/public-model-guideline/)).toBeTruthy();
  const before = catalogReads;
  fireEvent.click(screen.getByRole("button", { name: "Синхронизировать каталог" }));
  expect(await screen.findByText("Опубликованный каталог загружен.")).toBeTruthy();
  expect(catalogReads).toBeGreaterThan(before);
});
