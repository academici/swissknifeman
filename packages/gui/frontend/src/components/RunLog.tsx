import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Chunk, LogPage } from "../contracts";
import { useTransport } from "../transport/context";

type Stream = "stdout" | "stderr";

/** Merge chunks by number: a chunk seen once (from a page or a live frame) is never added twice. */
export function mergeChunks(known: Map<number, Chunk>, chunks: Iterable<Chunk>): Map<number, Chunk> {
  let next = known;
  for (const chunk of chunks) {
    if (next.has(chunk.chunk)) continue;
    if (next === known) next = new Map(known);
    next.set(chunk.chunk, chunk);
  }
  return next;
}

/** The log of a run: stored pages first, then live `log` frames of a subscription to the run; deduplicated. */
export function RunLog({ runId }: { runId: string }) {
  const transport = useTransport();
  const queryClient = useQueryClient();
  const [logs, setLogs] = useState<Record<Stream, Map<number, Chunk>>>({ stdout: new Map(), stderr: new Map() });
  const alive = useRef(true);

  const add = useCallback((stream: Stream, chunks: Chunk[]) => {
    if (!alive.current || chunks.length === 0) return;
    setLogs((current) => {
      const merged = mergeChunks(current[stream], chunks);
      return merged === current[stream] ? current : { ...current, [stream]: merged };
    });
  }, []);

  const load = useCallback(async () => {
    for (const stream of ["stdout", "stderr"] as const) {
      let cursor = 0;
      for (let page = 0; page < 100; page += 1) {
        const answer = await transport.request<LogPage>(
          "GET",
          `/v1/runs/${encodeURIComponent(runId)}/log?stream=${stream}&cursor=${cursor}&limit=500`,
        );
        add(stream, answer.chunks);
        if (answer.next_cursor === null || answer.chunks.length === 0) break;
        cursor = answer.next_cursor;
      }
    }
  }, [add, runId, transport]);

  useEffect(() => {
    alive.current = true;
    const subscription = transport.subscribe(
      { runs: [runId] },
      {
        onFrame: (frame) => {
          if (frame.kind === "log") {
            add(frame.stream, [{ chunk: frame.chunk, at: "", text: frame.text, truncated: frame.truncated }]);
          } else if (frame.kind === "run") {
            void queryClient.invalidateQueries({ queryKey: ["run", runId] });
          }
        },
        onSnapshotRequired: () => {
          void load();
          void queryClient.invalidateQueries({ queryKey: ["run", runId] });
        },
      },
    );
    void load().catch(() => undefined);
    return () => {
      alive.current = false;
      subscription.close();
    };
  }, [add, load, queryClient, runId, transport]);

  return (
    <div className="run-log">
      {(["stdout", "stderr"] as const).map((stream) => {
        const chunks = [...logs[stream].values()].sort((a, b) => a.chunk - b.chunk);
        const truncated = chunks.some((chunk) => chunk.truncated);
        return (
          <section key={stream}>
            <h3>{stream}</h3>
            <pre data-testid={`log-${stream}`}>{chunks.map((chunk) => chunk.text).join("")}</pre>
            {truncated && <div className="muted">The log was cut at its size limit.</div>}
          </section>
        );
      })}
    </div>
  );
}
