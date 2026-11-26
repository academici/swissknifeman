import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import { App } from "../../app/App";

it("records a design brief with project research and pins it to the draft", async () => {
  const project = "/api/v1/projects/project";
  const plan = "/api/v1/plans/plan";
  const queryId = "01900000-0000-7000-8000-000000000001";
  const documentId = "01900000-0000-7000-8000-000000000002";
  const versionId = "01900000-0000-7000-8000-000000000003";
  const digest = "sha256:" + "a".repeat(64);
  const writes: { path: string; body: unknown; headers: Headers }[] = [];
  const profileReads: URL[] = [];
  stubFetch(async (input, init) => {
    const url = new URL(String(input), location.origin);
    const path = url.pathname;
    if (init?.method === "POST" || init?.method === "PATCH") {
      writes.push({ path, body: JSON.parse(String(init.body)), headers: new Headers(init.headers) });
      if (path === project + "/plans") return Response.json({ plan_id: "plan", alias: "PLAN1", draft_id: null, edit_version: null });
      if (path === plan + "/design-briefs") return Response.json({ plan_id: "plan", design_brief_id: "brief" });
      if (path === plan + "/drafts") return Response.json({ draft_id: "draft", plan_id: "plan", edit_version: 1 });
      if (path === plan + "/drafts/draft") return Response.json({ draft_id: "draft", plan_id: "plan", edit_version: 2 });
    }
    switch (path) {
      case "/api/v1/me": return Response.json({ ...testIdentity, permissions_by_scope: { project: ["plan.create", "plan.edit", "context.research"] } });
      case "/api/v1/workspaces/ws": return Response.json({});
      case project: return Response.json({ project_id: "project", workspace_id: "ws" });
      case project + "/plans": return Response.json({ items: [], next_cursor: null });
      case "/api/v1/extensions/resources": return Response.json({ items: [], next_cursor: null });
      case "/api/v1/config/effective":
        profileReads.push(url);
        return Response.json({ keys: [
          { key: "context.research.profile.sources", value: ["docs"] },
          { key: "context.research.profile.max_documents", value: 3 },
          { key: "context.research.allow_deep", value: false },
        ] });
      case project + "/research-queries/" + queryId: return Response.json({
        result: { status: "ok", query_id: queryId, documents: [
          { document_id: documentId, content_digest: digest, origin: "repo:docs", excerpt: "Use the API" },
          { document_id: versionId, content_digest: digest, origin: "answer:summary", excerpt: "Synthetic" },
        ] },
      });
      default: throw new Error(path);
    }
  });
  history.replaceState(null, "", "/p/project/plans");
  render(<App initialToken="test" />);
  await userEvent.click(await screen.findByRole("button", { name: "Создать план" }));
  const create = within(await screen.findByRole("dialog", { name: "Создать план" }));
  await userEvent.type(create.getByRole("textbox", { name: "Название плана" }), "Ship new API");
  await userEvent.click(create.getByRole("checkbox", { name: "Заполнить дизайн-бриф" }));
  await userEvent.click(create.getByRole("button", { name: "Создать" }));

  const intake = within(await screen.findByRole("dialog", { name: "Дизайн-бриф" }));
  await intake.findByText("docs");
  expect(profileReads[0]?.searchParams.get("scope")).toBe("project:project");
  expect(profileReads[0]?.searchParams.get("keys")).toContain("context.research.profile.sources");
  expect(intake.queryByRole("checkbox", { name: "Углублённое исследование" })).toBeNull();
  await userEvent.type(intake.getByRole("textbox", { name: "Вопрос для исследования" }), "What's changed?");
  await userEvent.click(intake.getByRole("button", { name: "Подготовить запуск RAG на хосте" }));
  expect(intake.getByText(/skm plan research/).textContent).toBe(
    `skm plan research --json --project 'project' -- 'plan' 'What'"'"'s changed?'`,
  );
  await userEvent.type(intake.getByRole("textbox", { name: "ID результата исследования" }), queryId);
  await userEvent.click(intake.getByRole("button", { name: "Загрузить результат RAG" }));
  await userEvent.click(await intake.findByRole("button", { name: "Прикрепить документы" }));
  await userEvent.type(intake.getByRole("textbox", { name: "Цель" }), "Publish the new API");
  await userEvent.type(intake.getByRole("textbox", { name: "Контекст (Markdown)" }), "Example context");
  await userEvent.type(intake.getByRole("textbox", { name: "Ограничения, по одному в строке" }), "Scope{enter}Compatibility");
  await userEvent.type(intake.getByRole("textbox", { name: "ID версий файлов RAG" }), versionId);
  await userEvent.click(intake.getByRole("button", { name: "Сохранить бриф" }));
  await userEvent.click(await intake.findByRole("button", { name: "Открыть черновик" }));
  await userEvent.click(await intake.findByRole("button", { name: "Связать бриф с черновиком" }));
  await screen.findByRole("heading", { name: "Редактор черновика" });
  expect(writes.map(({ path, body }) => ({ path, body }))).toEqual([
    { path: project + "/plans", body: { title: "Ship new API" } },
    { path: plan + "/design-briefs", body: {
      goal: "Publish the new API", context_md: "Example context", constraints: ["Scope", "Compatibility"],
      rag_file_version_ids: [versionId],
      research_references: [{ reference: `research-query:${queryId}/${documentId}`, content_digest: digest }],
    } },
    { path: plan + "/drafts", body: { base: "empty" } },
    { path: plan + "/drafts/draft", body: { design_brief_id: "brief" } },
  ]);
  expect(writes[1]?.headers.get("Idempotency-Key")).toMatch(/^web-/);
  expect(writes[3]?.headers.get("If-Match")).toBe('W/"v1"');
});
