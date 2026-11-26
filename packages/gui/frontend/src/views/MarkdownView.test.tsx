import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarkdownView, safeUrl } from "./MarkdownView";

describe("markdown of contributions", () => {
  it("drops raw HTML and scripts", () => {
    const { container } = render(
      <MarkdownView data={{ text: "# Title\n\n<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>\n\n<b>bold</b> text" }} />,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelector("h1")?.textContent).toBe("Title");
  });

  it("keeps only relative and http(s) links", () => {
    const { container } = render(
      <MarkdownView data={{ text: "[a](javascript:alert(1)) [b](https://example.org/x) [c](plans/one) [d](data:text/html,x) [e](//evil.example)" }} />,
    );
    const hrefs = [...container.querySelectorAll("a")].map((a) => a.getAttribute("href") ?? "");
    expect(hrefs).toEqual(["", "https://example.org/x", "plans/one", "", ""]);
    expect(safeUrl("JAVASCRIPT:alert(1)")).toBe("");
  });
});
