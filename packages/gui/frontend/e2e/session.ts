import type { Page } from "@playwright/test";

export const origin = () => process.env.GUI_E2E_ORIGIN ?? "";

/** A fresh one-time browser URL from the backend (the session secret is a bearer; the browser never sees it). */
export async function newSessionUrl(): Promise<string> {
  const response = await fetch(`${origin()}/v1/session/tokens`, {
    method: "POST",
    headers: { Authorization: `Bearer ${process.env.GUI_E2E_SECRET}`, "Content-Type": "application/json" },
    body: "{}",
  });
  if (response.status !== 201) throw new Error(`session token: HTTP ${response.status}`);
  return ((await response.json()) as { url: string }).url;
}

export async function api<T>(path: string): Promise<T> {
  const response = await fetch(`${origin()}${path}`, { headers: { Authorization: `Bearer ${process.env.GUI_E2E_SECRET}` } });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return (await response.json()) as T;
}

export async function signIn(page: Page): Promise<void> {
  await page.goto(await newSessionUrl());
  await page.getByText("SKM GUI", { exact: true }).waitFor();
}

/** The `tick N` numbers of a log text, in order. */
export function ticks(text: string): number[] {
  return [...text.matchAll(/tick (\d+)/g)].map((match) => Number(match[1]));
}
