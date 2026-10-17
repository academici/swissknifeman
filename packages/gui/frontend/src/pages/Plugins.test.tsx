import { render, screen, waitFor, within } from "@testing-library/react";
import { act } from "react";
import { describe, expect, it } from "vitest";
import type { Trust } from "../contracts/generated/plugin-api";
import { useCatalog } from "../app/catalog";
import { useGuiPluginEvents } from "../plugins/useGuiPluginEvents";
import { FakeTransport, Wrapper } from "../test/fakes";
import { trust } from "../test/plugins";
import { Plugins } from "./Plugins";

const catalog = (digest: string) => ({ $schema: "urn:swissknifeman:gui:catalog:v1", host: { gui_protocol: { min: "1", max: "1" } },
  contributions: [], rejected: [], digest });

function list(plugins: Trust[]) {
  return { $schema: "urn:swissknifeman:gui:plugin-api:v1", kind: "plugin_list", plugins };
}

describe("Plugins", () => {
  it("lists every plugin with state as text, flags, compatibility, failures and grants", async () => {
    const fake = new FakeTransport({
      "GET /v1/plugins": list([
        trust("hub-bridge", { source: "unit" }),
        trust("ext-demo", { state: "quarantined", runtime_enabled: false, ui_enabled: false,
          failures: { count: 3, window_s: 300, last_code: "PROCESS_TIMEOUT" },
          compatibility: { protocol_ok: false, missing_contracts: [{ id: "urn:swissknifeman:gui:view-data", version: "v9" }] },
          grants: [{ id: `grant-${"a".repeat(32)}`, plugin: "ext-demo", capability: "network", project_id: null, manifest_digest: `sha256:${"1".repeat(64)}`,
            granted_at: "2026-10-16T10:00:00Z", expires_at: null, granted_by: "cli" }] }),
      ]),
    });
    render(<Wrapper transport={fake}><Plugins /></Wrapper>);
    const row = (await screen.findByRole("link", { name: "ext-demo" })).closest("tr")!;
    const cells = within(row);
    expect(cells.getByText("quarantined")).toBeTruthy();
    expect(cells.getByText("runtime off")).toBeTruthy();
    expect(cells.getByText("ui off")).toBeTruthy();
    expect(cells.getByText(/protocol mismatch; missing view-data v9/)).toBeTruthy();
    expect(cells.getByText(/3 in 300 s, last PROCESS_TIMEOUT/)).toBeTruthy();
    expect(row.querySelectorAll("td")[6]?.textContent).toBe("1");
    expect(screen.getByRole("link", { name: "ext-demo" }).getAttribute("href")).toBe("/plugins/ext-demo");
    const hub = screen.getByRole("link", { name: "hub-bridge" }).closest("tr")!;
    expect(within(hub).getByText("healthy")).toBeTruthy();
    expect(within(hub).getByText("runtime on")).toBeTruthy();
  });

  it("refreshes the list and the catalog on a gui.plugin.state frame", async () => {
    let state: Trust["state"] = "compatible";
    let digest = "a";
    const fake = new FakeTransport({
      "GET /v1/plugins": () => list([trust("ext-demo", { state })]),
      "GET /v1/ui/contributions": () => catalog(`sha256:${digest.repeat(64)}`),
    });
    function Harness() {
      useGuiPluginEvents();
      const current = useCatalog();
      return (
        <>
          <Plugins />
          <span data-testid="digest">{current.data?.digest.slice(7, 8)}</span>
        </>
      );
    }
    render(<Wrapper transport={fake}><Harness /></Wrapper>);
    await screen.findByText("compatible");
    await waitFor(() => expect(screen.getByTestId("digest").textContent).toBe("a"));
    const subscription = fake.subscriptions.find((entry) => entry.filter.types?.includes("gui.plugin.*"));
    expect(subscription).toBeTruthy();
    state = "enabled";
    digest = "b";
    const before = fake.calls.filter((call) => call.path === "/v1/ui/contributions").length;
    act(() => subscription!.handlers.onFrame({ $schema: "urn:swissknifeman:gui:stream:v1", kind: "event", seq: 1, sub: "s",
      event: { type: "gui.plugin.state", data: { plugin: "ext-demo", from: "compatible", to: "enabled", reason: "enable" } } } as never));
    await screen.findByText("enabled");
    await waitFor(() => expect(screen.getByTestId("digest").textContent).toBe("b"));
    expect(fake.calls.filter((call) => call.path === "/v1/ui/contributions").length).toBeGreaterThan(before);
  });

  it("refreshes after a snapshot_required too and closes the subscription on unmount", async () => {
    let count = 1;
    const fake = new FakeTransport({ "GET /v1/plugins": () => list(Array.from({ length: count }, (_, i) => trust(`p${i}`))) });
    function Harness() {
      useGuiPluginEvents();
      return <Plugins />;
    }
    const view = render(<Wrapper transport={fake}><Harness /></Wrapper>);
    await screen.findByRole("link", { name: "p0" });
    count = 2;
    act(() => fake.subscriptions[0]!.handlers.onSnapshotRequired?.("overflow"));
    await screen.findByRole("link", { name: "p1" });
    view.unmount();
    expect(fake.subscriptions[0]!.closed).toBe(true);
  });
});
