import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { MemoryRouter } from "react-router";
import { expect, it } from "vitest";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import { useDiff, useEntity, useExport, useReadyPreview, useStats, useText } from "../../api/hooks/planning";
import { App } from "../../app/App";
import { AuthProvider } from "../../app/providers/AuthProvider";
import { ScopeProvider } from "../../app/providers/ScopeProvider";
import { StreamProvider } from "../../app/providers/StreamProvider";
import { ToastProvider } from "../../app/providers/ToastProvider";

it("shows the two pinned revisions and groups server changes without losing identity on move or rekey", async () => {
  const paths: string[] = [];
  stubFetch(async (input) => {
    const path = String(input);
    paths.push(path);
    if (path === "/api/v1/me") return Response.json(testIdentity);
    if (path === "/api/v1/plans/p") return Response.json({ plan_id: "p" });
    if (path !== "/api/v1/plans/p/revisions/new/diff?against=old") throw new Error(path);
    const entity = { entity_kind: "item", fields: [], rekeyed: false, moved: false };
    return Response.json({
      from: { revision_id: "old", revision_no: 1 }, to: { id: "new", revision_no: 2 }, from_digest: "old-digest", to_digest: "new-digest",
      summary: { added: 1, removed: 1, changed: 1, moved: 1, rekeyed: 1 },
      plan_fields: [{ op: "replace", pointer: "/title", before: "Old title", after: "New title" }],
      entities: [
        { ...entity, change: "changed", entity_id: "same-id", key_before: "P1.2", key_after: "P2.1", moved: true, rekeyed: true,
          fields: [{ op: "replace", pointer: "/summary", before: "before", after: "after" }] },
        { ...entity, change: "added", entity_id: "added-id", key_before: null, key_after: "P1.3" },
        { ...entity, change: "removed", entity_id: "removed-id", key_before: "P1.4", key_after: null },
      ],
    });
  });
  history.replaceState(null, "", "/plans/p/revisions/new/diff/old");
  render(<App initialToken="test" />);
  const entities = within((await screen.findByRole("heading", { name: "Сущности" }, { timeout: 5000 })).closest("section")!);
  for (const group of ["Добавлено", "Удалено", "Изменено", "Переименовано", "Перемещено"]) {
    const section = within(entities.getByRole("heading", { name: group }).closest("section")!);
    if (group === "Переименовано" || group === "Перемещено") {
      expect(section.getByRole("listitem").textContent).toContain("same-id");
      expect(section.getByText("P1.2", { selector: "del" })).toBeTruthy();
      expect(section.getByText("P2.1", { selector: "ins" })).toBeTruthy();
    }
  }
  expect(screen.getByRole("link", { name: "r1" }).getAttribute("href")).toBe("/plans/p/revisions/old");
  expect(screen.getByText("old-digest")).toBeTruthy();
  expect(screen.getByText("/title")).toBeTruthy();
  expect(paths).toContain("/api/v1/plans/p/revisions/new/diff?against=old");
});

it("isolates late diff responses by saved edit version and pins every derived read, including export provenance", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Wrapper({ children }: PropsWithChildren) {
    return <MemoryRouter><QueryClientProvider client={client}><AuthProvider initialToken={null}><ScopeProvider>
      <ToastProvider><StreamProvider>{children}</StreamProvider></ToastProvider>
    </ScopeProvider></AuthProvider></QueryClientProvider></MemoryRouter>;
  }
  let finishOld!: (response: Response) => void;
  const old = new Promise<Response>((resolve) => { finishOld = resolve; });
  const urls: URL[] = [];
  stubFetch(async (input) => {
    const url = new URL(String(input), location.origin);
    urls.push(url);
    const version = url.searchParams.get("expected_edit_version");
    if (url.pathname.endsWith("/diff") && version === "4") return old;
    return Response.json({
      to_digest: `digest-${version}`, export_meta: { source: { kind: "draft", draft_id: "d", edit_version: Number(version), base_revision_id: null } },
    });
  });
  const { result, rerender } = renderHook(({ version }) => {
    const source = { draftId: "d", expectedEditVersion: version };
    const diff = useDiff("p", source, "base");
    const preview = useReadyPreview("p", source, { assume_done: ["P1.1"], limit: 1 });
    const stats = useStats("p", source);
    const spec = useExport("p", source);
    const text = useText("p", source, { target: "P1.1/U1", pointer: "/summary" });
    const entity = useEntity("p", source, "P1.1/U1");
    return { diff, preview, stats, spec, text, entity };
  }, { wrapper: Wrapper, initialProps: { version: 4 } });
  await waitFor(() => expect(result.current.spec.isSuccess).toBe(true));
  rerender({ version: 5 });
  await waitFor(() => expect(Object.values(result.current).every((query) => query.isSuccess)).toBe(true));
  expect(result.current.spec.data?.export_meta.source).toEqual({ kind: "draft", draft_id: "d", edit_version: 5, base_revision_id: null });
  await act(async () => finishOld(Response.json({ to_digest: "old" })));
  expect(result.current.diff.data?.to_digest).toBe("digest-5");
  for (const version of [4, 5]) {
    const sent = urls.filter((url) => url.searchParams.get("expected_edit_version") === String(version));
    expect(sent.map((url) => url.pathname.split("/").at(-1)).sort()).toEqual(["P1.1%2FU1", "diff", "export", "ready-preview", "stats", "text"]);
    expect(sent.find((url) => url.pathname.endsWith("/text"))?.searchParams.get("draft_id")).toBe("d");
    const entries = client.getQueryCache().findAll().map((query) => JSON.stringify(query.queryKey));
    expect(entries.filter((key) => key.includes(`"p","draft","d",${version},`))).toHaveLength(6);
  }
});
