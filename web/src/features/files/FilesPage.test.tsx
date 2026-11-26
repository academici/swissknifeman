// @vitest-environment jsdom
import "../../../tests/setup";
import { createHash, webcrypto } from "node:crypto";
import { StrictMode } from "react";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import { App } from "../../app/App";
import { tokenStore } from "../auth/tokenStore";

const ws = "workspace-a";
const project = "project-a";
const version = { file_version_id: "v1", version_no: 1, original_filename: "notes.txt", size_bytes: 5,
  digest: "sha256:example", declared_media_type: "text/plain", detected_media_type: "text/plain", safety_verdict: "ok" };
const file = { file_id: "f1", workspace_id: ws, project_id: project, state: "active", row_version: 7,
  title: "Notes", origin: "upload", classification: "internal", current_version: version };
const scope = `?workspace_id=${ws}&project_id=${project}`;
const list = `/p/${project}/files${scope}`;
const detail = "/files/f1" + scope;
const blobPath = `/api/v1/workspaces/${ws}/blobs`;
const commitPath = `/api/v1/projects/${project}/files`;
const contentPath = "/api/v1/file-versions/v1/content";

function problem(status: number, code: string, details = {}) {
  return Response.json({ code, category: status === 403 ? "forbidden" : status === 409 ? "conflict" : "validation",
    detail: code, details, request_id: "req-files", retryable: false },
  { status, headers: { "Content-Type": "application/problem+json" } });
}

type Handler = (url: URL, init: RequestInit) => Response | undefined | Promise<Response | undefined>;
function open(path: string, override: Handler, write = true) {
  vi.stubGlobal("crypto", webcrypto);
  const fetch = stubFetch(async (input, init = {}) => {
    const url = new URL(String(input), location.origin);
    const response = await override(url, init);
    if (response) return response;
    switch (url.pathname) {
      case "/api/v1/me": return Response.json({ ...testIdentity, permissions_by_scope: {
        [ws]: ["workspace.read", "file.read", ...(write ? ["file.write"] : [])],
        [project]: ["project.read", "file.read", ...(write ? ["file.write"] : [])],
      } });
      case `/api/v1/projects/${project}`: return Response.json({ project_id: project, workspace_id: ws, state: "active" });
      case `/api/v1/workspaces/${ws}`: return Response.json({ workspace_id: ws, slug: "example", title: "Example", state: "active" });
      case "/api/v1/files": return Response.json({ items: [], next: null });
      case "/api/v1/files/f1": return Response.json(file);
      case "/api/v1/files/f1/versions": return Response.json({ items: [version], next: null });
      default: throw new Error("Unexpected request " + url.pathname);
    }
  });
  tokenStore.set("file-token");
  history.replaceState(null, "", path);
  render(<StrictMode><App initialToken="file-token" /></StrictMode>);
  return fetch;
}

async function selectFile(user: ReturnType<typeof userEvent.setup>, label = "Загрузить файл", filename = "ёж.txt") {
  await user.click(await screen.findByRole("button", { name: label }, { timeout: 5000 }));
  const dialog = within(await screen.findByRole("dialog", { name: label }));
  const input = dialog.getByLabelText("Файл");
  await user.upload(input, new File([new Uint8Array([0, 255, 31, 10, 150])], filename, { type: "text/plain" }));
  await user.click(dialog.getByRole("button", { name: label }));
  return dialog;
}

const staged = { staged_blob_id: "staged-a", workspace_id: ws, digest: "sha256:example", size: 5, media_type: "text/plain" };

function workspaceEvents() {
  let controller: ReadableStreamDefaultController<Uint8Array>;
  return {
    response: () => new Response(new ReadableStream<Uint8Array>({ start: value => { controller = value; } }),
      { headers: { "Content-Type": "text/event-stream" } }),
    emit(cursor: number, event: { stream_kind: string; stream_id: string; type: string; payload: Record<string, string> }) {
      const data = JSON.stringify({ ...event, workspace_id: ws });
      act(() => controller.enqueue(new TextEncoder().encode(`id: ${cursor}\nevent: event\ndata: ${data}\n\n`)));
    },
  };
}

describe("Files", () => {
  it("sends identical staged and downloaded bytes and the SHA-256 of those bytes", async () => {
    const user = userEvent.setup();
    let stored: ArrayBuffer | undefined;
    let added = false;
    let contentReads = 0;
    const digest = createHash("sha256").update(Buffer.from([0, 255, 31, 10, 150])).digest("hex");
    const receive = vi.fn<(blob: Blob) => string>(() => "blob:download");
    vi.stubGlobal("URL", class extends URL {
      static createObjectURL = receive;
      static revokeObjectURL = vi.fn();
    });
    const clicks: { href: string; name: string }[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clicks.push({ href: this.href, name: this.download });
    });
    const fetch = open(list, async (url, init) => {
      const headers = new Headers(init.headers);
      if (url.pathname === blobPath) {
        expect(headers.get("Authorization")).toBe("Bearer file-token");
        expect(headers.get("X-Request-Id")).toMatch(/^web-/);
        expect(headers.get("SKM-Expected-Digest")).toBe("sha256:" + digest);
        expect(headers.get("Content-Type")).toBe("application/octet-stream");
        expect(headers.get("Idempotency-Key")).toMatch(/^web-/);
        expect(url.searchParams.get("media_type")).toBe("text/plain");
        stored = await new Promise<ArrayBuffer>(resolve => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result as ArrayBuffer);
          reader.readAsArrayBuffer(init.body as Blob);
        });
        return Response.json({ ...staged, digest: "sha256:" + digest }, { status: 201 });
      }
      if (url.pathname === commitPath) {
        expect(JSON.parse(String(init.body))).toMatchObject({ workspace_id: ws, project_id: project, title: "ёж.txt",
          blob: { ...staged, digest: "sha256:" + digest }, original_filename: "ёж.txt", origin: "upload", source: { kind: "upload" } });
        added = true;
        return Response.json({ file_id: file.file_id }, { status: 201 });
      }
      if (url.pathname === "/api/v1/files") return Response.json({ items: added ? [file] : [], next: null });
      if (url.pathname === contentPath) {
        expect(headers.get("Authorization")).toBe("Bearer file-token");
        expect(headers.has("Range")).toBe(false);
        const etag = `"sha256:${digest}"`;
        contentReads++;
        if (contentReads === 2) {
          expect(headers.get("If-None-Match")).toBe(etag);
          return new Response(null, { status: 304, headers: { ETag: etag } });
        }
        expect(headers.has("If-None-Match")).toBe(false);
        return new Response(stored, { headers: { ETag: etag } });
      }
    });
    await selectFile(user);
    const link = await screen.findByRole("link", { name: "Notes" });
    // SafeLink is an ordinary same-origin link. Simulate its browser navigation in jsdom.
    history.pushState(null, "", link.getAttribute("href"));
    window.dispatchEvent(new PopStateEvent("popstate"));
    await user.click(await screen.findByRole("button", { name: "Скачать" }));
    await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:download"));
    expect(clicks).toEqual([{ href: "blob:download", name: "notes.txt" }]);
    const downloaded = Buffer.from(await receive.mock.calls[0]![0].arrayBuffer());
    expect(downloaded.equals(Buffer.from(stored!))).toBe(true);
    expect(createHash("sha256").update(downloaded).digest("hex")).toBe(digest);
    await user.click(screen.getByRole("button", { name: "Скачать" }));
    await waitFor(() => expect(receive).toHaveBeenCalledTimes(2));
    expect(receive.mock.calls[1]?.[0]).toBe(receive.mock.calls[0]?.[0]);
    expect(contentReads).toBe(2);
    expect(fetch.mock.calls.filter(([path]) => String(path).includes("/blobs?"))).toHaveLength(1);
    expect(document.querySelector('a[href*="/content"]')).toBeNull();
  });

  it.each([true, false])("submits version acknowledgement to the server (policy permits it: %s)", async permitted => {
    const user = userEvent.setup();
    const commits: { body: Record<string, unknown>; key: string | null; version: string | null }[] = [];
    const findings = [{ rule: "CS-SECRET-NAME", level: "block", detail: "Check filename" }];
    const fetch = open(detail, (url, init) => {
      if (url.pathname === blobPath) return Response.json(staged);
      if (url.pathname === "/api/v1/files/f1/versions" && init.method === "POST") {
        const headers = new Headers(init.headers);
        commits.push({ body: JSON.parse(String(init.body)), key: headers.get("Idempotency-Key"), version: headers.get("If-Match") });
        if (commits.length === 1) return problem(422, "CONTENT_UNSAFE", { reason: "not_acknowledged", findings });
        return permitted ? Response.json({ file_id: file.file_id }, { status: 201 })
          : problem(422, "CONTENT_UNSAFE", { reason: "classification_below_acknowledge_minimum", findings });
      }
    });
    const dialog = await selectFile(user, "Добавить версию");
    const submit = await dialog.findByRole<HTMLButtonElement>("button", { name: "Отправить с подтверждением" });
    expect(submit.disabled).toBe(true);
    await user.click(dialog.getByRole("checkbox", { name: "Подтверждаю указанные риски" }));
    await user.click(submit);
    if (permitted) {
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    } else {
      await dialog.findByText(/Классификация текущего файла ниже минимума/);
      expect(dialog.queryByRole("button", { name: "Отправить с подтверждением" })).toBeNull();
      expect(dialog.getByLabelText("Файл")).toBeTruthy();
    }
    expect(commits).toHaveLength(2);
    expect(commits[1]?.body).toEqual({ ...commits[0]?.body, blob: staged, acknowledge: ["CS-SECRET-NAME"] });
    expect(commits[1]?.body).not.toHaveProperty("classification");
    expect(commits.map(commit => commit.version)).toEqual(['W/"v7"', 'W/"v7"']);
    expect(commits[1]?.key).not.toBe(commits[0]?.key);
    expect(fetch.mock.calls.filter(([path]) => String(path).includes("/blobs?"))).toHaveLength(1);
  });

  it("requires explicit acknowledgement, submits confidential with a fresh key, and stages once", async () => {
    const user = userEvent.setup();
    const commits: { body: Record<string, unknown>; key: string | null }[] = [];
    const fetch = open(list, (url, init) => {
      if (url.pathname === blobPath) return Response.json(staged);
      if (url.pathname === commitPath) {
        commits.push({ body: JSON.parse(String(init.body)), key: new Headers(init.headers).get("Idempotency-Key") });
        return commits.length === 1 ? problem(422, "CONTENT_UNSAFE", {
          findings: [{ rule: "CS-SECRET-NAME", level: "block", detail: "Check filename" }],
        }) : Response.json({ file_id: "new" });
      }
    });
    const dialog = await selectFile(user);
    expect((await dialog.findByRole("alert")).textContent).toContain("CONTENT_UNSAFE");
    const confirm = dialog.getByRole<HTMLButtonElement>("button", { name: "Отправить с подтверждением" });
    expect(confirm.disabled).toBe(true);
    expect(dialog.getByRole<HTMLSelectElement>("combobox", { name: "Классификация" }).value).toBe("confidential");
    await user.click(dialog.getByRole("checkbox", { name: "Подтверждаю указанные риски" }));
    await user.click(confirm);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(commits[1]?.body).toMatchObject({ classification: "confidential", blob: staged, acknowledge: ["CS-SECRET-NAME"] });
    expect(commits[0]?.key).toBeTruthy();
    expect(commits[1]?.key).not.toBe(commits[0]?.key);
    expect(fetch.mock.calls.filter(([path]) => String(path).includes("/blobs?"))).toHaveLength(1);
  });

  it.each([
    ["PROJECT_ARCHIVED", 409, false], ["FILE_TRASHED", 409, false], ["STAGED_BLOB_EXPIRED", 409, false],
    ["STAGED_BLOB_CONSUMED", 409, false], ["BLOB_DIGEST_MISMATCH", 422, true], ["BLOB_TOO_LARGE", 413, true],
  ] as const)("displays %s at its failing upload phase", async (code, status, stageFails) => {
    let stages = 0;
    let commits = 0;
    open(code === "FILE_TRASHED" ? detail : list, (url, init) => {
      if (url.pathname === blobPath) { stages++; return stageFails ? problem(status, code) : Response.json(staged); }
      if (init.method === "POST") { commits++; return problem(status, code); }
    });
    const dialog = await selectFile(userEvent.setup(), code === "FILE_TRASHED" ? "Добавить версию" : "Загрузить файл");
    expect((await dialog.findByRole("alert")).textContent).toContain(code);
    expect(stages).toBe(1);
    expect(commits).toBe(stageFails ? 0 : 1);
  });

  it("uses If-Match for versions, trash, and restore; reads individual versions", async () => {
    const user = userEvent.setup();
    const commands: [string, string | null, unknown][] = [];
    let current = { ...file };
    open(detail, (url, init) => {
      if (url.pathname === blobPath) return Response.json(staged);
      if (init.method === "POST") {
        const action = url.pathname.split("/").at(-1)!;
        commands.push([action, new Headers(init.headers).get("If-Match"), JSON.parse(String(init.body))]);
        current = { ...current, row_version: current.row_version + 1, state: action === "trash" ? "trashed" : "active" };
        return Response.json({ file_id: file.file_id });
      }
      if (url.pathname === "/api/v1/files/f1") return Response.json(current);
      if (url.pathname === "/api/v1/file-versions/v1") return Response.json({ ...version, file_id: "f1" });
    });
    await selectFile(user, "Добавить версию");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await user.click(screen.getByRole("button", { name: "Версия 1" }));
    await screen.findByRole("heading", { name: "Версия 1" });
    await user.click(screen.getByRole("button", { name: "В корзину" }));
    const confirm = within(await screen.findByRole("alertdialog"));
    await user.type(confirm.getByRole("textbox", { name: "Причина" }), "Outdated");
    await user.click(confirm.getByRole("button", { name: "Подтвердить" }));
    await user.click(await screen.findByRole("button", { name: "Восстановить" }));
    await screen.findByRole("button", { name: "В корзину" });
    expect(commands).toEqual([
      ["versions", 'W/"v7"', { blob: staged, source: { kind: "upload" }, declared_media_type: "text/plain", original_filename: "ёж.txt" }],
      ["trash", 'W/"v8"', { reason: "Outdated" }], ["restore", 'W/"v9"', {}],
    ]);
  });

  it("hides upload on the dedicated Files route when another client archives the project", async () => {
    const stream = workspaceEvents();
    let archived = false;
    const fetch = open(list, url => {
      if (url.pathname === `/api/v1/projects/${project}`) {
        return Response.json({ project_id: project, workspace_id: ws, state: archived ? "archived" : "active" },
          { headers: { "SKM-Events-Cursor": archived ? "43" : "42" } });
      }
      if (url.pathname === "/api/v1/events") {
        expect(url.searchParams.get("after")).toBe("42");
        return stream.response();
      }
    });
    await screen.findByRole("button", { name: "Загрузить файл" });
    archived = true;
    stream.emit(43, { stream_kind: "project", stream_id: project, type: "urn:skm:workspace:event:project-archived:v1",
      payload: { project_id: project } });
    await waitFor(() => expect(screen.queryByRole("button", { name: "Загрузить файл" })).toBeNull());
    expect(fetch.mock.calls.filter(([path]) => String(path).startsWith("/api/v1/events?"))).toHaveLength(1);
  });

  it.each([list, detail])("refreshes %s when another client restores a file", async path => {
    const stream = workspaceEvents();
    let restored = false;
    open(path, url => {
      const snapshot = { headers: { "SKM-Events-Cursor": restored ? "51" : "50" } };
      if (url.pathname === "/api/v1/files") return Response.json({ items: restored ? [file] : [], next: null }, snapshot);
      if (url.pathname === "/api/v1/files/f1") return Response.json({ ...file, state: restored ? "active" : "trashed" }, snapshot);
      if (url.pathname === "/api/v1/events") return stream.response();
    });
    if (path === list) await screen.findByRole("heading", { name: "Нет файлов" });
    else await screen.findByRole("button", { name: "Восстановить" });
    restored = true;
    stream.emit(51, { stream_kind: "file", stream_id: "f1", type: "urn:skm:artifacts:event:file-restored:v1", payload: { file_id: "f1" } });
    if (path === list) await screen.findByRole("link", { name: "Notes" });
    else await screen.findByRole("button", { name: "В корзину" });
  });

  it("shows a foreign file's 403 without attempting version or content reads", async () => {
    const fetch = open("/files/foreign", url => url.pathname === "/api/v1/files/foreign" ? problem(403, "FORBIDDEN") : undefined);
    expect((await screen.findByRole("alert")).textContent).toContain("FORBIDDEN");
    expect(screen.queryByRole("button", { name: "Скачать" })).toBeNull();
    expect(fetch.mock.calls.some(([path]) => /versions|content/.test(String(path)))).toBe(false);
  });

  it.each(["text/html", "image/svg+xml", "application/xhtml+xml", "text/markdown"])("renders %s bytes as safe preview only", async mime => {
    const payload = '<svg onload="bad()"></svg><img src=x onerror=bad()><script>bad()</script>\n\n[link](javascript:bad) [data](data:text/html,bad) label\u202eend';
    open(detail, url => {
      if (url.pathname.endsWith("/versions")) return Response.json({ items: [{ ...version, declared_media_type: mime }], next: null });
      if (url.pathname === contentPath) return new Response(payload);
    }, false);
    await userEvent.click(await screen.findByRole("button", { name: "Предпросмотр" }));
    await waitFor(() => expect(screen.getByRole("main").textContent).toContain("label\\u202eend"), { timeout: 3000 });
    const main = screen.getByRole("main");
    expect(main.querySelector("svg, img, script, iframe, [onerror], [onload], a[href^='javascript:'], a[href^='data:']")).toBeNull();
    expect(main.textContent).not.toContain("\u202e");
    expect(screen.queryByRole("button", { name: "Добавить версию" })).toBeNull();
  });

  it("uploads workspace files without a project and reuses the shell feed", async () => {
    const user = userEvent.setup();
    const requests: URL[] = [];
    let committed = false;
    open(`/w/example?workspace_id=${ws}`, (url, init) => {
      if (url.pathname === `/api/v1/workspaces/${ws}`) {
        return Response.json({ workspace_id: ws, slug: "example", title: "Example", state: "active" },
          { headers: { "SKM-Events-Cursor": "36" } });
      }
      if (url.pathname === `/api/v1/workspaces/${ws}/projects`) return Response.json({ items: [], next: null });
      if (url.pathname === "/api/v1/files") {
        expect(url.searchParams.has("project_id")).toBe(false);
        return Response.json({ items: committed ? [{ ...file, project_id: null }] : [], next: null }, { headers: { "SKM-Events-Cursor": "37" } });
      }
      if (url.pathname === "/api/v1/events") {
        requests.push(url);
        return new Response(new ReadableStream(), { headers: { "Content-Type": "text/event-stream" } });
      }
      if (url.pathname === blobPath) return Response.json(staged);
      if (url.pathname === `/api/v1/workspaces/${ws}/files`) {
        expect(JSON.parse(String(init.body))).toMatchObject({ project_id: null, workspace_id: ws, blob: staged });
        committed = true;
        return Response.json({ file_id: "f1" });
      }
    });
    await user.click(await screen.findByRole("tab", { name: "Файлы" }));
    await screen.findByRole("heading", { name: "Нет файлов" });
    await selectFile(user);
    await screen.findByRole("link", { name: "Notes" });
    expect(requests.map(url => url.searchParams.toString())).toEqual([`workspace_id=${ws}&after=36`]);
  });

  it("uses opaque next cursors and resets pagination on filter changes", async () => {
    const user = userEvent.setup();
    const seen: URLSearchParams[] = [];
    open(list, url => {
      if (url.pathname !== "/api/v1/files") return;
      seen.push(url.searchParams);
      const second = url.searchParams.has("after");
      return Response.json({ items: [{ ...file, title: second ? "Page two" : "Page one" }], next: second ? null : "next/+==" });
    });
    await user.click(await screen.findByRole("button", { name: "Далее" }));
    await screen.findByRole("link", { name: "Page two" });
    expect(screen.queryByRole("link", { name: "Page one" })).toBeNull();
    expect(seen.at(-1)?.get("after")).toBe("next/+==");
    await user.selectOptions(screen.getByRole("combobox", { name: "Состояние файла" }), "trashed");
    await screen.findByRole("link", { name: "Page one" });
    expect(seen.at(-1)?.get("state")).toBe("trashed");
    expect(seen.at(-1)?.has("after")).toBe(false);
    expect(seen.every(params => params.get("limit") === "50" && params.get("workspace_id") === ws && params.get("project_id") === project)).toBe(true);
  });
});
