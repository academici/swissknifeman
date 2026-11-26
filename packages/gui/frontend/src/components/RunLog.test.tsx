import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FakeTransport, Wrapper } from "../test/fakes";
import { RunLog, mergeChunks } from "./RunLog";

const RUN = `run-${"c".repeat(32)}`;
const chunk = (n: number, text: string) => ({ chunk: n, at: "2026-10-16T00:00:00Z", text, truncated: false });

describe("run log", () => {
  it("merges by chunk number", () => {
    const first = mergeChunks(new Map(), [chunk(0, "a"), chunk(1, "b")]);
    expect(mergeChunks(first, [chunk(1, "b")])).toBe(first);
    expect([...mergeChunks(first, [chunk(2, "c")]).keys()]).toEqual([0, 1, 2]);
  });

  it("loads the pages, adds live frames once and subscribes to the run", async () => {
    const transport = new FakeTransport({
      [`GET /v1/runs/${RUN}/log?stream=stdout&cursor=0&limit=500`]: { kind: "log_page", run_id: RUN, stream: "stdout",
        chunks: [chunk(0, "one\n"), chunk(1, "two\n")], next_cursor: 2 },
      [`GET /v1/runs/${RUN}/log?stream=stdout&cursor=2&limit=500`]: { kind: "log_page", run_id: RUN, stream: "stdout",
        chunks: [], next_cursor: 2 },
      [`GET /v1/runs/${RUN}/log?stream=stderr&cursor=0&limit=500`]: { kind: "log_page", run_id: RUN, stream: "stderr",
        chunks: [], next_cursor: null },
    });
    render(
      <Wrapper transport={transport}>
        <RunLog runId={RUN} />
      </Wrapper>,
    );
    await waitFor(() => expect(screen.getByTestId("log-stdout").textContent).toBe("one\ntwo\n"));
    const subscription = transport.subscriptions[0]!;
    expect(subscription.filter).toEqual({ runs: [RUN] });
    act(() => {
      for (const n of [1, 2, 2]) {
        subscription.handlers.onFrame({ $schema: "urn:swissknifeman:gui:stream:v1", kind: "log", seq: 10 + n, sub: "s1",
          run_id: RUN, stream: "stdout", chunk: n, text: n === 1 ? "two\n" : "three\n", truncated: false });
      }
    });
    expect(screen.getByTestId("log-stdout").textContent).toBe("one\ntwo\nthree\n");
  });
});
