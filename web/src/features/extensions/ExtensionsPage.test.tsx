// @vitest-environment jsdom
import "../../../tests/setup";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import { App } from "../../app/App";

const pack = { pack_id: "p1", title: "Overlay", slug: "overlay", trust: "operator", priority: 23,
  versions: [{ version: "1.2", version_id: "pv2", state: "active", installed_at: "2026-01-01T00:00:00Z" }] };
const resource = { key: "design", kind: "skill", version: "2", digest: "sha256:test", pack_slug: "overlay",
  pack_version: "1.2", verdict: "clean", quarantined: true };
const detail = { ...resource, resource_version_id: "rv2", pack_version_id: "pv2",
  manifest: { provenance: { source: "upstream", upstream_sha: "abc123" } }, files: [],
  bodies: { "guide.md": "<img src=x onerror=alert(1)>\u202e" } };
const root = "/api/v1/extensions/";
function open(path: string, permissions = ["ext.read", "ext.install"], numberedPacks = false, role = "owner") {
  const reads: URL[] = [];
  const commands: { path: string; method: string; body: unknown; key: string | null }[] = [];
  const fetch = stubFetch(async (input, init) => {
    const url = new URL(String(input), location.origin);
    if (url.pathname === "/api/v1/me") return Response.json({ ...testIdentity, effective_permissions: permissions,
      memberships: [{ scope_kind: "instance", scope_id: "instance-id", role }], permissions_by_scope: { "instance-id": permissions } });
    if (url.pathname === "/api/v1/config/effective") return Response.json({ keys: [{ key: "ui.stale_after_seconds", value: 2 }] });
    if (init?.method !== "GET") {
      commands.push({ path: url.pathname, method: String(init?.method),
        body: init?.body ? JSON.parse(String(init.body)) : null, key: new Headers(init?.headers).get("Idempotency-Key") });
      return Response.json({});
    }
    reads.push(url);
    switch (url.pathname.slice(root.length)) {
      case "packs": return Response.json({ items: [numberedPacks
        ? { ...pack, title: "Poll " + reads.filter(r => r.pathname === url.pathname).length } : pack], next_cursor: null });
      case "packs/p1": return Response.json({ ...pack, manifest: { overrides: [] }, resources_by_kind: { skill: 1 } });
      case "resources": return Response.json({ items: [resource], next_cursor: null });
      case "resolve": return Response.json({ chosen: { ...detail, version: "1", resource_version_id: "rv1" }, candidates: [{ pack: "overlay", version: "1.2", verdict: "clean", reason: "override" }], diagnostics: [] });
      case "resource-versions/rv2": return Response.json(detail);
      default: throw new Error("Unexpected path " + url.pathname);
    }
  });
  history.replaceState(null, "", path);
  render(<App initialToken="extensions-test" />);
  return { reads, commands, fetch };
}

describe("Extensions", () => {
  it("lists quarantined rows and resolves the chosen version without guessing a version ID", async () => {
    const { reads } = open("/extensions", ["ext.read"]);
    expect((await screen.findByRole("link", { name: "Overlay" }, { timeout: 5000 })).getAttribute("href")).toBe("/extensions/packs/p1");
    expect(screen.getByRole("cell", { name: "В карантине" })).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "skill:design" }));
    expect((await screen.findByRole("link", { name: "design · 1" })).getAttribute("href")).toBe("/extensions/resources/rv1");
    expect(screen.getByRole("cell", { name: "override" })).toBeTruthy();
    expect(reads.find(u => u.pathname.endsWith("/resources"))?.searchParams.get("include_quarantined")).toBe("true");
    expect(Object.fromEntries(reads.find(u => u.pathname.endsWith("/resolve"))!.searchParams)).toEqual({ kind: "skill", key: "design", scope: "instance" });
    expect(screen.queryByRole("button", { name: "Установить пакет" })).toBeNull();
  });

  it("reads bodies as inert text, displays provenance and sends reasoned quarantine/release commands", async () => {
    const { reads, commands } = open("/extensions/resources/rv2");
    await screen.findByRole("heading", { name: "Происхождение" });
    expect(reads.find(u => u.pathname.endsWith("/rv2"))?.searchParams.get("include_bodies")).toBe("true");
    expect(screen.getAllByText(/abc123/u).length).toBeGreaterThan(0);
    expect(screen.getByText("<img src=x onerror=alert(1)>\\u202e")).toBeTruthy();
    expect(document.querySelector("img")).toBeNull();
    for (const [label, action] of [["Поместить в карантин", "quarantine"], ["Снять карантин", "release"]] as const) {
      await userEvent.click(screen.getByRole("button", { name: label }));
      const dialog = within(await screen.findByRole("alertdialog", { name: label }));
      await userEvent.type(dialog.getByRole("textbox", { name: "Причина" }), "reviewed");
      await userEvent.click(dialog.getByRole("button", { name: "Подтвердить" }));
      await waitFor(() => expect(commands.at(-1)).toEqual({ path: root + "resource-versions/rv2/" + action,
        method: "POST", body: { reason: "reviewed" }, key: expect.stringMatching(/^web-/u) }));
    }
  });

  it("lets an installer quarantine a version while reserving release for the instance owner", async () => {
    open("/extensions/resources/rv2", ["ext.read", "ext.install"], false, "maintainer");
    await screen.findByRole("button", { name: "Поместить в карантин" });
    expect(screen.queryByRole("button", { name: "Снять карантин" })).toBeNull();
  });

  it("confirms deleting the exact pack version", async () => {
    const { commands } = open("/extensions/packs/p1");
    await userEvent.click(await screen.findByRole("button", { name: "Удалить версию 1.2" }));
    await userEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Подтвердить" }));
    await waitFor(() => expect(commands).toEqual([{ path: root + "pack-versions/pv2", method: "DELETE", body: null, key: expect.any(String) }]));
  });

  it("installs the supplied pack payload and synchronizes builtin packs", async () => {
    const { commands } = open("/extensions");
    await userEvent.type(await screen.findByRole("textbox", { name: "Источник" }), "path:review");
    await userEvent.type(screen.getByRole("textbox", { name: "Манифест пакета" }), "slug = 'review'");
    fireEvent.change(screen.getByRole("textbox", { name: /Файлы пакета/u }), { target: { value: '[{"path":"guide","content_b64":"YQ=="}]' } });
    await userEvent.click(screen.getByRole("button", { name: "Установить пакет" }));
    await screen.findByText("Операция завершена");
    await userEvent.click(screen.getByRole("button", { name: "Синхронизировать встроенные пакеты" }));
    await waitFor(() => expect(commands).toEqual([
      { path: root + "packs", method: "POST", key: expect.any(String), body: { origin_label: "path:review",
        payload: { manifest_text: "slug = 'review'", files: [{ path: "guide", content_b64: "YQ==" }] },
        trust: "third_party", dry_run: false, allow_quarantine: true } },
      { path: root + "packs/sync-builtin", method: "POST", key: expect.any(String), body: null },
    ]));
  });

  it("does not read a resource on a forbidden deep link", async () => {
    const { reads } = open("/extensions/resources/rv2", []);
    await screen.findByRole("alert");
    expect(reads).toEqual([]);
  });

  it("refreshes instance data at the configured interval and on focus", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    try {
      const { reads } = open("/extensions", ["config.read", "ext.read"], true);
      await screen.findByRole("link", { name: "Poll 1" }, { timeout: 5000 });
      const count = () => reads.filter(u => u.pathname.endsWith("/packs")).length;
      expect(count()).toBe(1);
      await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
      await screen.findByRole("link", { name: "Poll 2" });
      act(() => { window.dispatchEvent(new Event("visibilitychange")); });
      await screen.findByRole("link", { name: "Poll 3" });
    } finally { vi.useRealTimers(); }
  });
});
