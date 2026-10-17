import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TauriGlobal } from "../transport/TauriTransport";
import { Diagnostics, SidecarGate } from "./Diagnostics";

function fake(status: () => unknown, lines: string[] = []) {
  const invoke = vi.fn(async (command: string) => {
    if (command === "sidecar_status") return status();
    if (command === "sidecar_log") return lines;
    return null;
  });
  return { invoke, tauri: { core: { invoke, Channel: class {} } } as unknown as TauriGlobal };
}

const settle = async (ms = 0) => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
};

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("Diagnostics", () => {
  it.each(["starting", "restarting", "failed"])("shows the state %s as a word with restarts, error and log", async (state) => {
    const { tauri } = fake(() => ({ state, restarts: 3, last_error: "boom <b>x</b>" }), ["line one", "<script>no</script>"]);
    render(<Diagnostics tauri={tauri} />);
    await settle();
    expect(screen.getByTestId("sidecar-state").textContent).toBe(state);
    expect(screen.getByTestId("sidecar-restarts").textContent).toBe("3");
    expect(screen.getByTestId("sidecar-error").textContent).toBe("boom <b>x</b>");
    expect(screen.getByTestId("sidecar-log").textContent).toBe("line one\n<script>no</script>");
  });

  it("shows ready too and restarts on the button", async () => {
    const { tauri, invoke } = fake(() => ({ state: "ready", restarts: 0, port: 1234 }));
    render(<Diagnostics tauri={tauri} />);
    await settle();
    expect(screen.getByTestId("sidecar-state").textContent).toBe("ready");
    expect(screen.getByTestId("sidecar-error").textContent).toBe("none");
    fireEvent.click(screen.getByRole("button", { name: "Restart sidecar" }));
    await settle();
    expect(invoke).toHaveBeenCalledWith("sidecar_restart");
  });

  it("polls every 2 s and stops after unmount", async () => {
    const { tauri, invoke } = fake(() => ({ state: "starting", restarts: 0 }));
    const view = render(<Diagnostics tauri={tauri} />);
    await settle();
    const count = () => invoke.mock.calls.filter(([c]) => c === "sidecar_status").length;
    expect(count()).toBe(1);
    await settle(2000);
    expect(count()).toBe(2);
    view.unmount();
    await settle(10000);
    expect(count()).toBe(2);
  });

  it("says so when the state cannot be read", async () => {
    const { tauri } = fake(() => "garbage");
    render(<Diagnostics tauri={tauri} />);
    await settle();
    expect(screen.getByText("The sidecar state cannot be read")).toBeTruthy();
  });
});

describe("SidecarGate", () => {
  it("opens the app only while the sidecar is ready", async () => {
    let state = "starting";
    const { tauri } = fake(() => ({ state, restarts: 0 }));
    render(
      <SidecarGate tauri={tauri}>
        <div>the app</div>
      </SidecarGate>,
    );
    await settle();
    expect(screen.queryByText("the app")).toBeNull();
    expect(screen.getByTestId("sidecar-state").textContent).toBe("starting");
    state = "ready";
    await settle(2000);
    expect(screen.getByText("the app")).toBeTruthy();
    state = "failed";
    await settle(2000);
    expect(screen.queryByText("the app")).toBeNull();
    expect(screen.getByTestId("sidecar-state").textContent).toBe("failed");
  });
});
