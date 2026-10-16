import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FakeTransport, Wrapper } from "../test/fakes";
import { BootstrapGate } from "./BootstrapGate";
import { REQUIRED_CONTRACTS } from "./compat";

function bootstrap(min: string, max: string, contracts = REQUIRED_CONTRACTS) {
  return { $schema: "urn:swissknifeman:gui:bootstrap:v1", mode: "browser", epoch: "epoch-0001",
    backend: { version: "0.1.0", python: "3.12.3" }, gui_protocol: { min, max },
    contracts: contracts.map(([id, version]) => ({ id, version })), units: [], features: [],
    platform: { os: "linux", arch: "x86_64" } };
}

function renderGate(answer: unknown) {
  const transport = new FakeTransport({ "GET /v1/bootstrap": answer });
  render(
    <Wrapper transport={transport}>
      <BootstrapGate>{() => <div>main ui</div>}</BootstrapGate>
    </Wrapper>,
  );
  return transport;
}

describe("bootstrap gate", () => {
  it("opens the UI for a compatible backend and keeps its epoch", async () => {
    const transport = renderGate(bootstrap("1", "1"));
    expect(await screen.findByText("main ui")).toBeTruthy();
    expect(transport.epoch).toBe("epoch-0001");
  });

  it("shows PROTOCOL_INCOMPATIBLE for another protocol", async () => {
    renderGate(bootstrap("2", "3"));
    expect(await screen.findByText("PROTOCOL_INCOMPATIBLE")).toBeTruthy();
    expect(screen.queryByText("main ui")).toBeNull();
  });

  it("shows PROTOCOL_INCOMPATIBLE when a contract is missing", async () => {
    renderGate(bootstrap("1", "1", REQUIRED_CONTRACTS.slice(1)));
    expect(await screen.findByText("PROTOCOL_INCOMPATIBLE")).toBeTruthy();
  });
});
