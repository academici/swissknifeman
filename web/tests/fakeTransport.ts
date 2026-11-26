import { vi } from "vitest";
import type { WhoAmIView } from "../src/api/generated/access";
import type { IsoDateTime, Uuid } from "../src/api/generated/kernel";

export const testIdentity: WhoAmIView = {
  principal: {
    principal_id: "56c44502-acd3-417d-8c7c-be9e61406c0f" as Uuid,
    display_name: "Тестовый пользователь",
    kind: "human",
    state: "active",
    created_at: "2026-01-01T00:00:00.000Z" as IsoDateTime,
    identities: [],
    row_version: 1,
  },
  token: null,
  memberships: [],
  effective_permissions: [],
  permissions_by_scope: {},
  modules: { knowledge: true, learning: true },
  events_cursor: null,
};

export function stubFetch(handler: typeof fetch = async () => Response.json(testIdentity)) {
  const fetch = vi.fn<typeof globalThis.fetch>(handler);
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
