import { randomUUID } from "node:crypto";
import { test as base, expect } from "@playwright/test";
import type { APIRequestContext, Page, Response } from "@playwright/test";

function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Missing ${name} from Playwright global setup`);
  return value;
}

export const ownerToken = () => requiredEnv("SKM_E2E_TOKEN");
export const workspaceId = () => requiredEnv("SKM_E2E_WORKSPACE");
export const projectId = () => requiredEnv("SKM_E2E_PROJECT");

export const test = base.extend<{ networkGuard: void }>({
  networkGuard: [async ({ context, baseURL, request }, use, testInfo) => {
    const origin = new URL(baseURL ?? "").origin;
    const denied: string[] = [];
    await context.route("**/*", async (route) => {
      const url = new URL(route.request().url());
      if (url.origin === origin) await route.continue();
      else {
        denied.push(url.origin);
        await route.abort("blockedbyclient");
      }
    });
    await context.routeWebSocket("**/*", (socket) => {
      denied.push(new URL(socket.url()).origin);
      void socket.close();
    });
    await use();
    if (testInfo.status !== testInfo.expectedStatus) {
      const logs = await request.get("/__skm_e2e/logs", {
        headers: { Authorization: `Bearer ${ownerToken()}` }, timeout: 2_000,
      }).catch(() => undefined);
      if (logs?.ok()) await testInfo.attach("SKM process logs", { body: await logs.body(), contentType: "text/plain" });
    }
    expect(denied, "unexpected network destinations").toEqual([]);
  }, { auto: true }],
});

export { expect };

export async function signIn(page: Page, token = ownerToken(), path = "/") {
  await page.goto(`${path}#token=${encodeURIComponent(token)}`);
  await expect(page).not.toHaveURL(/#token=/);
  await expect(page.getByRole("navigation").first()).toBeVisible();
}

export async function assertAccessible(page: Page, heading: string) {
  const main = page.getByRole("main");
  await expect(main).toHaveCount(1);
  await expect(main.getByRole("heading", { name: heading, exact: true })).toBeVisible();
  for (const role of ["button", "link", "textbox", "combobox", "spinbutton", "checkbox", "radio", "tab"] as const) {
    await expect(main.getByRole(role, { name: "", exact: true }), `unnamed ${role}`).toHaveCount(0);
  }
}

export function responseFor(page: Page, method: string, path: string | RegExp): Promise<Response> {
  return page.waitForResponse((response) => {
    const pathname = new URL(response.url()).pathname;
    return response.request().method() === method && (typeof path === "string" ? pathname === path : path.test(pathname));
  });
}

export async function api<T>(
  request: APIRequestContext,
  method: string,
  path: string,
  data?: unknown,
  options: { token?: string; idempotent?: boolean; headers?: Record<string, string> } = {},
): Promise<T> {
  const response = await request.fetch(`/api/v1${path}`, {
    method,
    ...(data === undefined ? {} : { data }),
    headers: {
      Authorization: `Bearer ${options.token ?? ownerToken()}`,
      "SKM-Client-Version": "2.0.0",
      ...(method === "POST" && data === undefined ? { "Content-Type": "application/json" } : {}),
      ...(options.idempotent === false || method === "GET" ? {} : { "Idempotency-Key": randomUUID() }),
      ...options.headers,
    },
    maxRedirects: 0,
  });
  expect(response.ok(), `${method} ${path}: ${response.ok() ? response.status() : await response.text()}`).toBeTruthy();
  return await response.json() as T;
}

export async function viewerToken(request: APIRequestContext): Promise<string> {
  const { principal_id } = await api<{ principal_id: string }>(request, "POST", "/principals", {
    kind: "human", display_name: "M5 viewer",
  });
  await api(request, "POST", "/memberships", { scope_id: workspaceId(), principal_id, role: "viewer" });
  const token = await api<{ secret: string }>(request, "POST", "/tokens", {
    principal_id, name: "M5 viewer session",
  }, { idempotent: false });
  return token.secret;
}
