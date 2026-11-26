// @vitest-environment jsdom
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import "../../../tests/setup";
import { App } from "../../app/App";

const detail = {
  id: "candidate", trigger: "<script>Pool</script>\u202e", action: "Wait\u001b",
  state: "candidate", confidence: 0.51, confidence_tier: "moderate",
  n_total: 20, known_outcome_total: 12, unknown_outcome_total: 8, exposed_total: 5,
  independent_known_total: 7, exposure_unknown_total: 2, days_since: 3, freshness: 0.95,
  row_version: 7, gates: { candidate: { support_min: 0.6 } }, reviews: [], similar: [],
  proposals: [
    { id: "p1", source_candidate_id: "other", relation: "conflict", trigger: "Opposite", action: "Avoid" },
    { id: "p2", source_candidate_id: "third", relation: "update", trigger: "Similar", action: "Try" },
  ],
};
const scope = "/learning?workspace_id=work";
const readyTimeout = { timeout: 5_000 };
const testTimeout = 15_000;

it.each(["human", "service", "worker"] as const)("shows source evidence and gates curation for %s", async kind => {
  let version: string | null = null;
  let key: string | null = null;
  let promoted = false;
  stubFetch(async (input, init) => {
    const url = new URL(String(input), location.origin);
    if (url.pathname === "/api/v1/me") return Response.json({
      ...testIdentity, modules: { ...testIdentity.modules, learning: true },
      principal: { ...testIdentity.principal, kind },
      effective_permissions: url.searchParams.get("scope_id") === "work" ? ["lesson.curate"] : [],
    });
    if (url.pathname.endsWith("/promote") && init?.method === "POST") {
      const headers = new Headers(init.headers);
      version = headers.get("If-Match");
      key = headers.get("Idempotency-Key");
      promoted = true;
      return Response.json({ lesson_id: "lesson" }, { status: 201 });
    }
    if (url.pathname.endsWith("/lesson-candidates")) {
      expect(url.searchParams.get("states")).toBe("candidate");
      return Response.json({ items: [{ candidate_id: detail.id, display_key: "LC-1", trigger: detail.trigger }] });
    }
    if (url.pathname.endsWith("/signals")) return Response.json({ items: [] });
    if (url.pathname.endsWith("/candidate")) return Response.json({
      ...detail, ...(promoted && { state: "promoted", row_version: 8 }),
    });
    return Response.json({ items: [] });
  });
  history.replaceState(null, "", scope);
  render(<App initialToken="test" />);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "LC-1 <script>Pool</script>\\u202e" }, readyTimeout));
  await screen.findByRole("heading", { name: "<script>Pool</script>\\u202e" });
  for (const label of [
    "Source association", "Покрытие исходов", "Неизвестные исходы", "Урок уже показывался", "Актуальность",
  ]) expect(screen.getByText(label)).toBeTruthy();
  for (const name of ["Пороги", "CONFLICT", "UPDATE"]) expect(screen.getByRole("heading", { name })).toBeTruthy();

  if (kind !== "human") {
    expect(screen.queryByRole("button", { name: "Создать урок" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Рецензировать" })).toBeNull();
    expect(version).toBeNull();
    return;
  }
  await user.click(await screen.findByRole("button", { name: "Создать урок" }));
  await screen.findByRole("alertdialog", { name: "Создать урок" });
  await user.click(screen.getByRole("button", { name: "Подтвердить создание" }));
  await screen.findByText("promoted");
  expect(version).toBe('W/"v7"');
  expect(key).toMatch(/^web-/);
}, testTimeout);

it("keeps the previous candidate visible when promotion conflicts", async () => {
  stubFetch(async (input, init) => {
    const url = new URL(String(input), location.origin);
    if (url.pathname === "/api/v1/me") return Response.json({
      ...testIdentity, modules: { ...testIdentity.modules, learning: true },
      effective_permissions: ["lesson.curate"],
    });
    if (url.pathname.endsWith("/promote") && init?.method === "POST") {
      return Response.json({
        code: "VERSION_CONFLICT", category: "conflict", detail: "Version changed", request_id: "promotion-conflict",
      }, { status: 409, headers: { "Content-Type": "application/problem+json" } });
    }
    if (url.pathname.endsWith("/lesson-candidates")) return Response.json({
      items: [{ candidate_id: detail.id, display_key: "LC-1", trigger: "Pool" }],
    });
    if (url.pathname.endsWith("/candidate")) return Response.json(detail);
    return Response.json({ items: [] });
  });
  history.replaceState(null, "", scope);
  render(<App initialToken="test" />);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "LC-1 Pool" }, readyTimeout));
  await user.click(await screen.findByRole("button", { name: "Создать урок" }));
  await user.click(await screen.findByRole("button", { name: "Подтвердить создание" }));
  const conflict = within(await screen.findByRole("alert"));
  expect(conflict.getByRole("heading", { name: "Конфликт изменений" })).toBeTruthy();
  expect(conflict.getByText("VERSION_CONFLICT")).toBeTruthy();
  expect(conflict.getByText(/Version changed/)).toBeTruthy();
  expect(conflict.getByText("promotion-conflict")).toBeTruthy();
  expect(screen.getByRole("heading", { name: "<script>Pool</script>\\u202e" })).toBeTruthy();
}, testTimeout);

it("does not mount candidate queries when learning is disabled", async () => {
  let queried = false;
  stubFetch(async input => {
    const url = new URL(String(input), location.origin);
    if (url.pathname.includes("lesson-candidates")) queried = true;
    return Response.json({ ...testIdentity, modules: { ...testIdentity.modules, learning: false } });
  });
  history.replaceState(null, "", scope);
  render(<App initialToken="test" />);
  await screen.findByRole("heading", { name: /не найден/i }, readyTimeout);
  expect(screen.queryByRole("link", { name: "Обучение" })).toBeNull();
  expect(queried).toBe(false);
}, testTimeout);
