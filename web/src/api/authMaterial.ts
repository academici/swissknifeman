export type AuthMode = "none" | "admin_login" | "token";

export interface AuthMaterial {
  readonly mode: AuthMode;
  readonly token: string | null;
  readonly csrfToken: string | null;
}

export interface AuthSessionView {
  readonly mode: "none" | "admin_login";
  readonly authMethod: "bearer" | "session" | "none";
}

const unsafeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export function readCsrfCookie(): string | null {
  if (typeof document === "undefined") return null;
  for (const part of document.cookie.split(";")) {
    const [name, ...rest] = part.trim().split("=");
    if (name === "skm_csrf") {
      const value = rest.join("=");
      return value ? decodeURIComponent(value) : null;
    }
  }
  return null;
}

export function parseAuthSession(value: unknown): AuthSessionView | null {
  if (typeof value !== "object" || value === null) return null;
  const record = value as Record<string, unknown>;
  if (record.authenticated !== true) return null;
  if (record.mode !== "none" && record.mode !== "admin_login") return null;
  if (record.auth_method !== "bearer" && record.auth_method !== "session" && record.auth_method !== "none") return null;
  if (typeof record.display_name !== "string") return null;
  return { mode: record.mode, authMethod: record.auth_method };
}

// Token mode omits cookies so a leftover session cannot combine with Bearer
// and raise AMBIGUOUS_CREDENTIALS. Cookie modes send the session and, on
// mutations, the CSRF header that must match the skm_csrf cookie.
export function applyAuthHeaders(headers: Headers, method: string, material: AuthMaterial): RequestCredentials {
  if (material.mode === "token") {
    if (material.token) headers.set("Authorization", `Bearer ${material.token}`);
    return "omit";
  }
  if (material.mode === "admin_login" && unsafeMethods.has(method)) {
    const csrf = material.csrfToken ?? readCsrfCookie();
    if (csrf) headers.set("X-SKM-CSRF", csrf);
  }
  return "include";
}
