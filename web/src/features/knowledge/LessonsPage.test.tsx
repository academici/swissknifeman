// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import "../../../tests/setup";
import { App } from "../../app/App";

it.each([["human", true], ["human", false], ["worker", true]])("gates curation for %s with grant %s", async (kind, grant) => {
  let header: string | null = null;
  stubFetch(async (input, init) => {
    const url = new URL(String(input), location.origin);
    if (url.pathname === "/api/v1/me") return Response.json({
      ...testIdentity, principal: { ...testIdentity.principal, kind },
      effective_permissions: grant && url.searchParams.get("scope_id") === "work" ? ["lesson.curate"] : [],
    });
    if (init?.method === "POST") {
      header = new Headers(init.headers).get("If-Match");
      return Response.json({ state: "deprecated" });
    }
    return Response.json({ items: [{
      id: "lesson", trigger: "Pool\u202e", action: "Wait", confidence: 0.5, confidence_tier: "moderate",
      review_flag: "none", applicability: {}, row_version: 3, state: "curated",
    }] });
  });
  history.replaceState(null, "", "/lessons?workspace_id=work");
  render(<App initialToken="test" />);
  await screen.findByRole("heading", { name: "Pool\\u202e" });
  expect(screen.getByText("Source association")).toBeTruthy();
  const action = screen.queryByRole("button", { name: "Пометить устаревшим" });
  if (kind !== "human" || !grant) {
    expect(action).toBeNull();
    return;
  }
  const user = userEvent.setup();
  await user.click(action!);
  await user.type(screen.getByRole("textbox", { name: /Причина/ }), "Replaced");
  await user.click(screen.getByRole("button", { name: "Подтвердить" }));
  expect(header).toBe('W/"v3"');
});
