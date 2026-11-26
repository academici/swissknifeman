import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { readFile } from "node:fs/promises";
import { request } from "node:http";
import type { ServerResponse } from "node:http";
import { join } from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import { preview } from "vite";
import type { Plugin } from "vite";

interface ReadyInstance {
  backend: string;
  token: string;
  workspaceId: string;
  projectId: string;
  logsDirectory: string;
}

export interface EventConnection {
  lastEventId: string | null;
  events: { id: string; type: string; data: string }[];
}

const web = fileURLToPath(new URL("../../", import.meta.url));
const repo = fileURLToPath(new URL("../../../", import.meta.url));

function recordEvents(connection: EventConnection) {
  let buffer = "";
  return (chunk: string) => {
    buffer += chunk;
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const id = /^id: *(.+)$/m.exec(frame)?.[1];
      const type = /^event: *(.+)$/m.exec(frame)?.[1];
      const data = /^data: *(.*)$/m.exec(frame)?.[1];
      if (id && type && data !== undefined) connection.events.push({ id, type, data });
    }
  };
}

function backendProxy(instance: ReadyInstance): Plugin {
  const connections: EventConnection[] = [];
  const streams = new Set<ServerResponse>();
  let offline = false;
  return {
    name: "skm-e2e-proxy",
    configurePreviewServer(server) {
      server.middlewares.use((incoming, outgoing, next) => {
        const path = new URL(incoming.url ?? "/", "http://127.0.0.1").pathname;
        if (path.startsWith("/__skm_e2e/")) {
          if (incoming.headers.authorization !== `Bearer ${instance.token}`) {
            outgoing.writeHead(403).end();
            return;
          }
          if (path === "/__skm_e2e/logs") {
            void Promise.all(["serve", "worker"].map(async (process) => {
              const log = await readFile(join(instance.logsDirectory, process + ".stderr"), "utf8");
              return process + "\n" + log.slice(-24_000);
            })).then((logs) => outgoing.end(logs.join("\n\n")), () => outgoing.writeHead(500).end());
            return;
          }
          if (incoming.method === "POST" && path === "/__skm_e2e/events/disconnect") {
            offline = true;
            for (const stream of streams) stream.destroy();
          }
          if (incoming.method === "POST" && path === "/__skm_e2e/events/restore") offline = false;
          outgoing.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify(connections));
          return;
        }
        if (!path.startsWith("/api/") && !/^\/health\/(live|ready|details)$/.test(path)) {
          next();
          return;
        }

        const events = path === "/api/v1/events";
        if (events && offline) {
          outgoing.destroy();
          return;
        }
        // Stream the original HTTP response. In particular, never buffer SSE or downloads.
        const headers = { ...incoming.headers, host: new URL(instance.backend).host };
        if (incoming.headers.origin === `http://${incoming.headers.host}`) headers.origin = instance.backend;
        const upstream = request(instance.backend, {
          path: incoming.url,
          method: incoming.method,
          headers,
        }, (response) => {
          outgoing.writeHead(response.statusCode ?? 502, response.headers);
          if (events && response.statusCode === 200) {
            const connection: EventConnection = {
              lastEventId: incoming.headers["last-event-id"]?.toString() ?? null,
              events: [],
            };
            connections.push(connection);
            if (connections.length > 40) connections.shift();
            response.setEncoding("utf8");
            response.on("data", recordEvents(connection));
            streams.add(outgoing);
            outgoing.once("close", () => streams.delete(outgoing));
          }
          response.once("error", () => outgoing.destroy());
          response.pipe(outgoing);
        });
        outgoing.once("close", () => upstream.destroy());
        upstream.once("error", () => {
          if (outgoing.headersSent) outgoing.destroy();
          else outgoing.writeHead(502).end();
        });
        incoming.pipe(upstream);
      });
    },
  };
}


export default async function globalSetup() {
  assert(process.env.SKM_TEST_DATABASE_URL, "SKM_TEST_DATABASE_URL is required for the real PostgreSQL suite");
  const child = spawn("uv", ["run", "--frozen", "python", "-m", "support.processes"], {
    cwd: repo,
    env: { ...process.env, PYTHONPATH: join(repo, "tests"), UV_OFFLINE: "1" },
    stdio: ["pipe", "pipe", "inherit"],
  });
  const closed = once(child, "close");
  const lines = createInterface({ input: child.stdout });
  const cleanup = async () => {
    child.stdin.end();
    lines.close();
    const [status, signal] = await closed;
    assert.equal(status, 0, `SKM launcher exited with ${status ?? signal}`);
  };
  try {
    const [line] = await Promise.race([
      once(lines, "line"),
      closed.then(([status]) => { throw new Error(`SKM launcher exited during setup (${status})`); }),
    ]);
    const instance = JSON.parse(String(line)) as ReadyInstance;
    const frontend = await preview({
      configFile: false,
      root: web,
      plugins: [backendProxy(instance)],
      preview: { host: "127.0.0.1", port: 0, strictPort: true },
    });
    const address = frontend.httpServer.address();
    assert(address && typeof address !== "string");
    process.env.PLAYWRIGHT_TEST_BASE_URL = `http://127.0.0.1:${address.port}`;
    process.env.SKM_E2E_TOKEN = instance.token;
    process.env.SKM_E2E_WORKSPACE = instance.workspaceId;
    process.env.SKM_E2E_PROJECT = instance.projectId;

    return async () => {
      try {
        if ("closeAllConnections" in frontend.httpServer) frontend.httpServer.closeAllConnections();
        await frontend.close();
      } finally {
        await cleanup();
      }
    };
  } catch (error) {
    await cleanup().catch((failure: unknown) => { console.error(failure); });
    throw error;
  }
}
