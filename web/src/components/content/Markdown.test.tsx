import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { sanitizeLink } from "../../lib/safeLink";
import { escapeText } from "../../lib/safeText";
import { CodeBlock } from "./CodeBlock";
import { EmptyState } from "../data/EmptyState";
import { Markdown } from "./Markdown";
import { SafeLink } from "./SafeLink";
import { StatusBadge } from "../primitives/StatusBadge";

describe("SURFACE-04 Markdown", () => {
  it("renders Markdown but never creates raw script, event handlers, images, SVG or HTML", async () => {
    const text = [
      "# Rendered heading",
      "<script>throw new Error('unexpected script')</script>",
      '<img src="missing" onerror="unexpected()">',
      '<svg onload="unexpected()"><title>Injected</title></svg>',
      '<iframe srcdoc="<p>unexpected</p>"></iframe>',
      '<a href="/settings" onclick="unexpected()">Raw link</a>',
      "![remote image](https://elsewhere.invalid/pixel.png)",
    ].join("\n\n");
    const { container } = render(<Markdown text={text} />);
    await screen.findByRole("heading", { name: "Rendered heading" });
    expect(container.querySelector("script, img, svg, iframe, [onclick], [onerror], [onload]")).toBeNull();
    expect(screen.queryByRole("link", { name: "Raw link" })).toBeNull();
  });

  it("removes unsafe hrefs and displays the real origin for a disguised external link", async () => {
    const text = [
      "[Settings](/settings?scope=instance)",
      '[https://trusted.invalid](https://elsewhere.invalid:8443/path "ti&#x202e;tle")',
      "[bad JavaScript](JaVaScRiPt:example)",
      "[bad data](data:text/html,example)",
      "[bad scheme](java&#x09;script:example)",
      "[bad external](//elsewhere.invalid/path)",
      "[bad encoded scheme](java%0ascript:example)",
    ].join("\n\n");
    render(<Markdown text={text} />);
    const local = await screen.findByRole("link", { name: "Settings" });
    expect(local.getAttribute("href")).toBe("/settings?scope=instance");
    const external = screen.getByRole("link", { name: "https://trusted.invalid (https://elsewhere.invalid:8443)" });
    expect(external.getAttribute("href")).toBe("https://elsewhere.invalid:8443/path");
    expect(external.getAttribute("rel")).toBe("noopener noreferrer");
    expect(external.getAttribute("title")).toBe("ti\\u202etle");
    expect(screen.getAllByRole("link")).toHaveLength(2);
  });

  it("escapes controls and bidi markers in headings, text, link labels and inline code", async () => {
    render(<Markdown text={"# a\u202eb\n\np\u009fq **r&#x2066;s** [x\u200fy](/inbox) `c\u202ad`"} />);
    await screen.findByRole("heading", { name: "a\\u202eb" });
    expect(screen.getByText("r\\u2066s")).toBeTruthy();
    expect(screen.getByText("c\\u202ad")).toBeTruthy();
    expect(screen.getByRole("link", { name: "x\\u200fy" })).toBeTruthy();
    expect(screen.getByText(/p\\u009fq/u)).toBeTruthy();
  });

  it("renders fenced code as text and copies the same visible content", async () => {
    const user = userEvent.setup();
    const clipboard = vi.spyOn(navigator.clipboard, "writeText");
    const { container } = render(<Markdown text={"\x60\x60\x60html\n<svg onload='unexpected()'>\u202e\nnext line\n\x60\x60\x60"} />);
    await user.click(await screen.findByRole("button", { name: "Копировать код" }));
    const visible = container.querySelector("pre code")?.textContent;
    expect(visible).toBe("<svg onload='unexpected()'>\\u202e\\u000anext line");
    expect(container.querySelector("svg")).toBeNull();
    expect(clipboard).toHaveBeenCalledWith(visible);
  });
});

describe("safe link destinations", () => {
  it.each([
    "javascript:example",
    "JaVaScRiPt:example",
    "data:text/html,example",
    "file:///tmp/example",
    "vbscript:example",
    "mailto:example@example.org",
    "//elsewhere.invalid",
    "/\\elsewhere.invalid",
    "/%2felsewhere.invalid",
    "./settings",
    "\tjavascript:example",
    " javaScript:example",
    "ja\u000avascript:example",
    "ja\u0085vascript:example",
    "java script:example",
    "java%09script:example",
    "https:\\elsewhere.invalid",
    "https://trusted.invalid@elsewhere.invalid",
    "https://elsewhere.invalid/\u202e",
    "https://elsewhere.invalid/%E2%80%AE",
    "/safe%00tail",
  ])("rejects %j", (url) => {
    expect(sanitizeLink(url)).toBeNull();
    render(<SafeLink href={url}>Destination</SafeLink>);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("Destination")).toBeTruthy();
  });

  it("normalizes the actual origin and allows HTTP and in-app links", () => {
    expect(sanitizeLink("HTTP://EXAMPLE.ORG:80/path")).toEqual({
      href: "http://example.org/path", origin: "http://example.org",
    });
    expect(sanitizeLink("/settings?q=with%20spaces")).toEqual({ href: "/settings?q=with%20spaces", origin: null });
  });

  it.each(["/settings", "javascript:example"])("escapes composed labels for %s", (href) => {
    const { container } = render(
      <SafeLink href={href} title={"title\u202e\t"}>
        {"Open\t"}<><strong>{"settings\u061c\u202e"}</strong>{"\u009f"}</>
      </SafeLink>,
    );
    const label = container.firstElementChild;
    expect(label?.textContent).toBe("Open\\u0009settings\\u061c\\u202e\\u009f");
    expect(label?.querySelector("strong")?.textContent).toBe("settings\\u061c\\u202e");
    if (href === "/settings") expect(label?.getAttribute("title")).toBe("title\\u202e\\u0009");
  });
});

describe("plain text and code", () => {
  it("escapes an empty state's title", () => {
    render(<EmptyState title={"Empty\u061c\u202e\t\u009f"} />);
    expect(screen.getByRole("heading").textContent).toBe("Empty\\u061c\\u202e\\u0009\\u009f");
  });

  it("escapes all specified bidi markers and C0/C1 controls", () => {
    const codePoints = [
      ...Array.from({ length: 32 }, (_, i) => i),
      ...Array.from({ length: 33 }, (_, i) => i + 127),
      0x061c, 0x200e, 0x200f, 0x202a, 0x202b, 0x202c, 0x202d, 0x202e, 0x2066, 0x2067, 0x2068, 0x2069,
    ];
    expect(escapeText(String.fromCharCode(...codePoints))).toBe(
      codePoints.map((code) => "\\u" + code.toString(16).padStart(4, "0")).join(""),
    );
  });

  it("copies exactly the visibly escaped code without parsing markup", async () => {
    const user = userEvent.setup();
    const clipboard = vi.spyOn(navigator.clipboard, "writeText");
    const { container } = render(<CodeBlock text={"<script>unexpected()</script>\u0000\u009f\u2069"} />);
    const visible = container.querySelector("code")?.textContent;
    expect(visible).toBe("<script>unexpected()</script>\\u0000\\u009f\\u2069");
    expect(container.querySelector("script")).toBeNull();
    await user.click(within(container).getByRole("button", { name: "Копировать код" }));
    expect(clipboard).toHaveBeenCalledExactlyOnceWith(visible);
    expect((await screen.findByRole("status")).textContent).toBe("Скопировано");
  });

  it("uses a neutral text badge for unknown statuses, including inherited property names", () => {
    const { rerender } = render(<StatusBadge status="constructor" />);
    expect(screen.getByText("constructor").getAttribute("data-tone")).toBe("neutral");
    rerender(<StatusBadge status={"new<state>\u202e"} />);
    expect(screen.getByText("new<state>\\u202e").getAttribute("data-tone")).toBe("neutral");
  });
});
