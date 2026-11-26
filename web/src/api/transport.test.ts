import { version as packageVersion } from "../../package.json";
import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement, type PropsWithChildren } from "react";
import { describe, expect, it } from "vitest";
import { stubFetch } from "../../tests/fakeTransport";
import { createQueryClient } from "../app/providers/QueryProvider";
import { tokenStore } from "../features/auth/tokenStore";
import { ApiError } from "./errors";
import { whoAmIOptions } from "./hooks/access";
import { useIdempotentMutation } from "./idempotency";
import { HttpTransport } from "./transport";

const requestIdPattern = /^web-[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/u;

describe("HttpTransport", () => {
  it("sends the bearer, version, correlation, concurrency and idempotency headers", async () => {
    tokenStore.set("session-token");
    const fetch = stubFetch(async () => Response.json({ state: "saved" }, {
      headers: { ETag: 'W/"v4"', "X-Request-Id": "server-correlation", "Idempotency-Replayed": "true" },
    }));
    const response = await new HttpTransport().request("PATCH", "/api/v1/draft", {
      body: { title: "Draft" },
      contentType: "application/merge-patch+json",
      ifMatch: 'W/"v3"',
      ifNoneMatch: "*",
      idempotencyKey: "web-mutation",
    });

    const [path, init] = fetch.mock.calls[0] ?? [];
    const headers = new Headers(init?.headers);
    expect(path).toBe("/api/v1/draft");
    expect(init).toMatchObject({ method: "PATCH", body: '{"title":"Draft"}', credentials: "omit", redirect: "error" });
    expect(headers.get("Authorization")).toBe("Bearer session-token");
    expect(headers.get("X-Request-Id")).toMatch(requestIdPattern);
    expect(headers.get("SKM-Client-Version")).toBe(packageVersion);
    expect(headers.get("If-Match")).toBe('W/"v3"');
    expect(headers.get("If-None-Match")).toBe("*");
    expect(headers.get("Idempotency-Key")).toBe("web-mutation");
    expect(headers.get("Content-Type")).toBe("application/merge-patch+json");
    expect(response).toEqual({
      data: { state: "saved" }, etag: 'W/"v4"', requestId: "server-correlation", replayed: true,
    });
  });

  it.each(["POST", "PUT", "PATCH", "DELETE"] as const)("sends a JSON content type on bodyless %s", async (method) => {
    const fetch = stubFetch(async () => new Response(null, { status: 204 }));
    await new HttpTransport().request(method, "/api/v1/resource");
    const init = fetch.mock.calls[0]?.[1];
    expect(init?.body).toBeUndefined();
    expect(new Headers(init?.headers).get("Content-Type")).toBe("application/json");
  });

  it.each([new FormData(), new Blob(["bytes"], { type: "application/octet-stream" })])(
    "passes native %j bodies through for fetch to set their content type",
    async (body) => {
      const fetch = stubFetch(async () => new Response(null, { status: 204 }));
      await new HttpTransport().request("POST", "/api/v1/resource", { body });
      const init = fetch.mock.calls[0]?.[1];
      expect(init?.body).toBe(body);
      expect(new Headers(init?.headers).has("Content-Type")).toBe(false);
    },
  );

  it("sends the session cookie and CSRF header for admin mutations and omits the bearer token", async () => {
    const fetch = stubFetch(async () => Response.json({ ok: true }));
    const transport = new HttpTransport({
      getAuth: () => ({ mode: "admin_login", token: "should-not-send", csrfToken: "skm_csrf_test" }),
    });
    await transport.request("POST", "/api/v1/memberships", { body: { role: "member" } });
    const init = fetch.mock.calls[0]?.[1];
    const headers = new Headers(init?.headers);
    expect(init?.credentials).toBe("include");
    expect(headers.get("X-SKM-CSRF")).toBe("skm_csrf_test");
    expect(headers.get("Authorization")).toBeNull();
  });

  it("passes raw streamed-upload bytes with the abort signal and accepts empty success", async () => {
    const fetch = stubFetch(async () => new Response(null, { status: 204 }));
    const raw = new Blob(["file bytes"]);
    const { signal } = new AbortController();
    const response = await new HttpTransport().request<void>("POST", "/api/v1/blobs", { raw, signal });
    const [, options] = fetch.mock.calls[0] ?? [];
    const headers = new Headers(options?.headers);

    expect(options?.body).toBe(raw);
    expect(options?.signal).toBe(signal);
    expect(headers.get("Content-Type")).toBe("application/octet-stream");
    expect(headers.has("Authorization")).toBe(false);
    expect(response).toEqual({ data: undefined, etag: null, requestId: headers.get("X-Request-Id"), replayed: false });
  });

  it.each([
    "api/v1/me",
    "https://other.invalid/api/v1/me",
    "//other.invalid/api/v1/me",
    " /api/v1/me",
    "/\\other.invalid",
    "/%2fother.invalid",
    "/api/../me",
    "/api/%2e./me",
    "/api/%252e%252e/me",
    "/api/\t/me",
    "/api/v1/me#fragment",
  ])("rejects %j before reaching fetch", async (path) => {
    const fetch = stubFetch();
    await expect(new HttpTransport().request("GET", path)).rejects.toThrow(TypeError);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("preserves valid query parameters including dots and escaped spaces", async () => {
    const fetch = stubFetch();
    const path = "/api/v1/me?name=two..dots%20and%20spaces";
    await new HttpTransport().request("GET", path);
    expect(fetch.mock.calls[0]?.[0]).toBe(path);
  });

  it("decodes problem+json using HTTP status and preserves the reported request ID", async () => {
    const problem = {
      code: "VERSION_CONFLICT", category: "conflict", status: 200, detail: "Draft changed",
      details: { expected: 3, actual: 4 }, retryable: false, request_id: "problem-request", instance: "/draft/1",
    };
    stubFetch(async () => Response.json(problem, {
      status: 409,
      headers: { "Content-Type": "application/problem+json; charset=utf-8", "X-Request-Id": "header-request" },
    }));
    const result = new HttpTransport().request("PATCH", "/api/v1/draft");
    await expect(result).rejects.toBeInstanceOf(ApiError);
    await expect(result).rejects.toMatchObject({
      status: 409, code: problem.code, category: "conflict", detail: problem.detail,
      details: problem.details, retryable: false, requestId: "problem-request", instance: "/draft/1",
    });
    await result.catch((error: ApiError) => {
      expect(error.isConflict()).toBe(true);
      expect(error.isWaiting()).toBe(false);
    });
    expect(ApiError.fromResponse(409, { code: "MANUAL_PENDING", category: "waiting" }, "id", "/").isWaiting()).toBe(true);
  });

  it.each([
    [null, "application/problem+json"],
    ["{", "application/problem+json"],
    ["<html>Bad Gateway</html>", "text/html"],
  ])("falls back safely for a response without a usable problem document", async (body, contentType) => {
    stubFetch(async () => new Response(body, {
      status: 502, headers: { "Content-Type": contentType, "X-Request-Id": "edge-request" },
    }));
    await expect(new HttpTransport().request("GET", "/api/v1/me")).rejects.toMatchObject({
      status: 502, code: "INTERNAL_ERROR", retryable: false, requestId: "edge-request",
    });
  });

  it("preserves a JSON parse error after a successful body read", async () => {
    stubFetch(async () => new Response("{", { headers: { "Content-Type": "application/json" } }));
    await expect(new HttpTransport().request("GET", "/api/v1/me")).rejects.toThrow(SyntaxError);
  });

  it.each([
    [200, "application/json", "response-request"],
    [502, "application/problem+json", null],
  ] as const)("reports an interrupted body read after HTTP %i as retryable", async (status, contentType, responseId) => {
    const body = new ReadableStream<Uint8Array>({
      start(controller) { controller.enqueue(new TextEncoder().encode('{"partial":')); },
      pull(controller) { controller.error(new TypeError("connection reset")); },
    });
    const headers = new Headers({ "Content-Type": contentType });
    if (responseId !== null) headers.set("X-Request-Id", responseId);
    const fetch = stubFetch(async () => new Response(body, { status, headers }));
    const path = "/api/v1/me";
    const result = new HttpTransport().request("GET", path);
    await expect(result).rejects.toBeInstanceOf(ApiError);
    const outgoingId = new Headers(fetch.mock.calls[0]?.[1]?.headers).get("X-Request-Id");
    expect(outgoingId).toMatch(requestIdPattern);
    await expect(result).rejects.toMatchObject({
      code: "BACKEND_UNAVAILABLE", category: "backend", retryable: true, requestId: responseId ?? outgoingId, instance: path,
    });
  });

  it("preserves AbortError during a problem response body read", async () => {
    const cancelled = new DOMException("Aborted", "AbortError");
    const body = new ReadableStream({ start(controller) { controller.error(cancelled); } });
    stubFetch(async () => new Response(body, { status: 503, headers: { "Content-Type": "application/problem+json" } }));
    await expect(new HttpTransport().request("GET", "/api/v1/me")).rejects.toBe(cancelled);
  });

  it("surfaces network errors as retryable and preserves cancellation", async () => {
    const fetch = stubFetch(async () => { throw new TypeError("network error"); });
    const transport = new HttpTransport();
    await expect(transport.request("GET", "/api/v1/me")).rejects.toMatchObject({
      code: "BACKEND_UNAVAILABLE", category: "backend", retryable: true,
    });

    const cancelled = new DOMException("Aborted", "AbortError");
    fetch.mockRejectedValueOnce(cancelled);
    await expect(transport.request("GET", "/api/v1/me")).rejects.toBe(cancelled);
  });
});

describe("Query retry policy", () => {
  it.each([[401, 1], [403, 1], [404, 1], [503, 4]])(
    "makes %i handling use %i GET attempt(s)",
    async (status, calls) => {
      const fetch = stubFetch(async () => new Response(null, { status }));
      const client = createQueryClient();
      try {
        await expect(client.fetchQuery({ ...whoAmIOptions(new HttpTransport()), retryDelay: 0 }))
          .rejects.toMatchObject({ status });
        expect(fetch).toHaveBeenCalledTimes(calls);
        const delay = client.getDefaultOptions().queries?.retryDelay;
        expect(typeof delay === "function" && delay(2, new Error())).toBe(4_000);
      } finally {
        client.clear();
      }
    },
  );

  it("only retries mutations on demand and keeps the same key for that operation", async () => {
    const fetch = stubFetch(async () => Response.json({ ok: true }, {
      headers: { "Idempotency-Replayed": "true" },
    }));
    fetch.mockRejectedValueOnce(new TypeError("connection lost"));
    const transport = new HttpTransport();
    const client = createQueryClient();
    const wrapper = ({ children }: PropsWithChildren) =>
      createElement(QueryClientProvider, { client }, children);
    const { result, unmount } = renderHook(() => useIdempotentMutation((title: string, key) =>
      transport.request("POST", "/api/v1/draft", { body: { title }, idempotencyKey: key })), { wrapper });

    try {
      act(() => result.current.submit("first"));
      await waitFor(() => expect(result.current.status).toBe("error"));
      expect(fetch).toHaveBeenCalledTimes(1);
      act(() => result.current.retry());
      await waitFor(() => expect(result.current.status).toBe("success"));
      expect(result.current.data?.replayed).toBe(true);

      act(() => result.current.submit("second"));
      await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
      const [first, replay, other] = fetch.mock.calls.map(([, init]) => new Headers(init?.headers));
      expect(first?.get("Idempotency-Key")).toMatch(requestIdPattern);
      expect(replay?.get("Idempotency-Key")).toBe(first?.get("Idempotency-Key"));
      expect(replay?.get("X-Request-Id")).not.toBe(first?.get("X-Request-Id"));
      expect(other?.get("Idempotency-Key")).not.toBe(first?.get("Idempotency-Key"));
      expect(fetch.mock.calls[0]?.[1]?.body).toBe(fetch.mock.calls[1]?.[1]?.body);
    } finally {
      unmount();
      client.clear();
    }
  });
});
